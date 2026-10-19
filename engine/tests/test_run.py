"""Seam 4: `relay run` end to end (bronze + silver)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from conftest import DEMO_MAPPING
from relay_engine.cli import app
from relay_engine.generator.generate import generate
from relay_engine.io import LocalParquetStore
from relay_engine.mapping import load_mapping
from relay_engine.pipeline import run

runner = CliRunner()
EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"
META = {"_run_id", "_source", "_ingested_at"}


def _single_run(out: Path) -> Path:
    runs = [p for p in out.iterdir() if p.is_dir()]
    assert len(runs) == 1
    return runs[0]


def test_run_writes_bronze_and_silver(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "out"
    generate(data, seed=42, rows=30)
    result = runner.invoke(
        app, ["run", str(EXAMPLES / "chantiers.yaml"), "--data", str(data), "--out", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    run_dir = _single_run(out)
    assert run_dir.name in result.stdout

    for table in ("chantiers_legacy", "chantiers_target"):
        bronze = pl.read_parquet(run_dir / "bronze" / table / "*.parquet")
        assert set(bronze.columns) >= META
        assert bronze["_run_id"].unique().to_list() == [run_dir.name]

    silver = pl.read_parquet(run_dir / "silver" / "chantiers" / "*.parquet")
    assert silver.columns == [
        "chantier_id", "libelle", "montant_marche", "date_ouverture",
        "rue", "code_postal", "ville",
    ]
    assert silver.height == 30


def test_run_stops_on_ambiguous_source_key(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "out"
    generate(data, seed=42, rows=30)
    legacy = pl.read_parquet(data / "chantiers_legacy.parquet")
    pl.concat([legacy, legacy.head(2)]).write_parquet(data / "chantiers_legacy.parquet")

    result = runner.invoke(
        app, ["run", str(EXAMPLES / "chantiers.yaml"), "--data", str(data), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "not unique in the source: 13% of rows (4 of 32)" in result.stdout


def test_a_few_source_duplicates_are_reviewed_and_the_run_completes(tmp_path: Path) -> None:
    shops = [(f"S{i:03d}", f"Shop {i}", "Lyon", "2024-01-01") for i in range(20)]
    columns = ["id", "name", "city", "opened"]
    data = tmp_path / "data"
    data.mkdir()
    legacy = [*shops, ("S000", "Shop zero", "Lyon", "2024-01-01"), shops[1]]
    pl.DataFrame(legacy, schema=columns, orient="row").write_parquet(
        data / "shops_legacy.parquet"
    )
    pl.DataFrame(shops, schema=columns, orient="row").write_parquet(data / "shops_target.parquet")
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text(DEMO_MAPPING + "max_duplicate_share: 0.2\n")

    store = LocalParquetStore(data)
    summary = run(load_mapping(mapping), store, LocalParquetStore(tmp_path / "out"), "r1")

    assert (summary.verdict, summary.review, summary.fail, summary.passed) == ("REVIEW", 2, 0, 18)
    found = pl.read_parquet(tmp_path / "out" / "gold" / "recon_finding" / "*.parquet")
    assert sorted(found.select("match_key_value", "rule").rows()) == [
        ("id=S000", "match_key duplicated in source (×2)"),
        ("id=S001", "match_key duplicated in source (×2)"),
    ]
