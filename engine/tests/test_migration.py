"""Seam 4: one run reconciles a whole migration."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from relay_engine.cli import app
from relay_engine.generator.generate import generate
from relay_engine.io import LocalParquetStore
from relay_engine.mapping import MappingError, MappingSpec, load_mapping, load_mappings
from relay_engine.pipeline import order_by_references, run_migration

EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"
runner = CliRunner()


def _spec(entity: str, *parents: str) -> MappingSpec:
    return MappingSpec.model_validate({
        "version": 1, "entity": entity,
        "source": {"table": f"{entity}_legacy"}, "target": {"table": f"{entity}_target"},
        "match_key": ["id"],
        "columns": [{"source": "id", "target": "id"}, {"source": "p", "target": "p"}],
        "references": [{"column": "p", "table": f"{p}_target", "key": "id"} for p in parents],
    })


def _order(*specs: MappingSpec) -> list[str]:
    return [s.entity for s in order_by_references(list(specs))]


def test_parents_come_before_their_children() -> None:
    assert _order(_spec("lignes", "factures"), _spec("factures", "chantiers"),
                  _spec("chantiers")) == ["chantiers", "factures", "lignes"]


def test_unrelated_entities_are_ordered_by_name() -> None:
    assert _order(_spec("b"), _spec("c", "a"), _spec("a")) == ["a", "b", "c"]


def test_a_self_reference_or_a_cycle_does_not_block() -> None:
    assert _order(_spec("chantiers", "chantiers")) == ["chantiers"]
    assert _order(_spec("b", "a"), _spec("a", "b"), _spec("c")) == ["c", "a", "b"]


def _migration(tmp_path: Path) -> tuple[Path, list[MappingSpec]]:
    data = tmp_path / "data"
    generate(data, seed=42, rows=40)
    specs = [load_mapping(EXAMPLES / name) for name in ("factures.yaml", "chantiers.yaml")]
    return data, specs


def test_one_run_id_one_recon_run_row_per_entity(tmp_path: Path) -> None:
    data, specs = _migration(tmp_path)
    out = tmp_path / "out"
    summary = run_migration(specs, LocalParquetStore(data), LocalParquetStore(out), "r1")

    assert [e.entity for e in summary.entities] == ["chantiers", "factures"]
    assert summary.verdict == "FAIL"
    runs = pl.read_parquet(out / "gold" / "recon_run" / "*.parquet")
    assert runs.select("run_id", "entity").rows() == [("r1", "chantiers"), ("r1", "factures")]
    assert runs.get_column("verdict").to_list() == [e.verdict for e in summary.entities]
    found = pl.read_parquet(out / "gold" / "recon_finding" / "*.parquet")
    assert set(found.get_column("entity")) == {"chantiers", "factures"}
    assert sorted(p.name for p in (out / "bronze").iterdir()) == [
        "chantiers_legacy", "chantiers_target", "factures_legacy", "factures_target",
    ]
    assert sorted(p.name for p in (out / "silver").iterdir()) == ["chantiers", "factures"]


def test_the_migration_verdict_is_the_worst_entity_verdict(tmp_path: Path) -> None:
    data, specs = _migration(tmp_path)
    store = LocalParquetStore(data)
    chantiers, factures = (
        run_migration([s], store, LocalParquetStore(tmp_path / s.entity), s.entity)
        for s in reversed(specs)
    )
    both = run_migration(specs, store, LocalParquetStore(tmp_path / "both"), "both")
    rank = ["PASS", "REVIEW", "FAIL"]
    assert both.verdict == max(chantiers.verdict, factures.verdict, key=rank.index)


def test_a_stop_on_one_entity_writes_nothing_and_names_it(tmp_path: Path) -> None:
    data, specs = _migration(tmp_path)
    legacy = pl.read_parquet(data / "factures_legacy.parquet")
    pl.concat([legacy, legacy]).write_parquet(data / "factures_legacy.parquet")
    out = tmp_path / "out"

    with pytest.raises(MappingError) as exc:
        run_migration(specs, LocalParquetStore(data), LocalParquetStore(out), "r1")
    assert exc.value.problems[0].startswith("factures: match_key (facture_id) is not unique")
    assert not out.exists()


def test_two_mappings_of_one_entity_are_refused(tmp_path: Path) -> None:
    data, specs = _migration(tmp_path)
    with pytest.raises(MappingError) as exc:
        run_migration([specs[1], specs[1]], LocalParquetStore(data),
                      LocalParquetStore(tmp_path / "out"), "r1")
    assert exc.value.problems == ["entity 'chantiers' is declared by more than one mapping"]


def test_a_folder_loads_every_mapping_and_reports_every_broken_one(tmp_path: Path) -> None:
    assert [s.entity for s in load_mappings(EXAMPLES)] == ["chantiers", "factures"]
    (tmp_path / "a.yaml").write_text("version: 1\nentity: a\n")
    (tmp_path / "b.yml").write_text("version: 2\n")
    with pytest.raises(MappingError) as exc:
        load_mappings(tmp_path)
    assert {p.split(":")[0] for p in exc.value.problems} == {"a.yaml", "b.yml"}
    (tmp_path / "empty").mkdir()
    with pytest.raises(MappingError) as exc:
        load_mappings(tmp_path / "empty")
    assert "no mapping" in str(exc.value)


def test_relay_run_on_a_folder_prints_each_entity_and_one_verdict(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "runs"
    generate(data, seed=42, rows=40)
    result = runner.invoke(app, ["run", str(EXAMPLES), "--data", str(data), "--out", str(out),
                                 "--decisions", str(tmp_path / "decisions")])
    assert result.exit_code == 0, result.stdout
    (run_dir,) = out.iterdir()
    lines = result.stdout.splitlines()
    assert lines[0] == f"Run {run_dir.name} — migration (2 entities): FAIL"
    assert lines[1].startswith("  chantiers  FAIL ")
    assert lines[2].startswith("  factures   ")
    assert lines[-2] == f"Details: relay findings {run_dir}"
    assert lines[-1] == f"Report: {run_dir / 'report.html'}"
    listing = runner.invoke(app, ["findings", str(run_dir)])
    assert "chantiers" in listing.stdout and "factures" in listing.stdout


def test_an_orphan_inherited_from_the_source_is_told_apart_in_a_migration(
    tmp_path: Path,
) -> None:
    """f1 pointed nowhere already in the source; f2 lost its parent on the way."""
    data = tmp_path / "data"
    data.mkdir()
    tables = {
        "chantiers_legacy": [("c1", None), ("c2", None)],
        "chantiers_target": [("c1", None)],
        "factures_legacy": [("f1", "c9"), ("f2", "c2")],
        "factures_target": [("f1", "c9"), ("f2", "c2")],
    }
    for name, rows in tables.items():
        pl.DataFrame(rows, schema=["id", "p"], orient="row").write_parquet(data / f"{name}.parquet")
    specs = [_spec("chantiers"), _spec("factures", "chantiers")]

    def orphans(chosen: list[MappingSpec], run: str) -> set[tuple[str, str]]:
        run_migration(chosen, LocalParquetStore(data), LocalParquetStore(tmp_path / run), run)
        found = pl.read_parquet(tmp_path / run / "gold" / "recon_finding" / "*.parquet")
        return {
            (r["match_key_value"], r["verdict"])
            for r in found.filter(pl.col("column") == "p").iter_rows(named=True)
        }

    assert orphans(specs, "whole") == {("id=f1", "REVIEW"), ("id=f2", "FAIL")}
    assert orphans(specs[1:], "alone") == {("id=f1", "FAIL"), ("id=f2", "FAIL")}
