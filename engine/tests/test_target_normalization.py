"""The target goes through the same normalization and typing as the source.

Every check reads the prepared sides: a key normalized on one side only reads
as a lost row and an extra row at once, and a key typed differently cannot join.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from relay_engine.io import LocalParquetStore
from relay_engine.mapping import MappingSpec
from relay_engine.pipeline import RunSummary, run


def _spec(key_rules: list[str], rules: list[dict] | None = None) -> MappingSpec:
    return MappingSpec.model_validate({
        "version": 1, "entity": "shops",
        "source": {"table": "shops_legacy"}, "target": {"table": "shops_target"},
        "match_key": ["id"],
        "columns": [
            {"source": "id", "target": "id", "type": "string", "normalize": key_rules},
            {"source": "name", "target": "name", "type": "string", "normalize": ["trim"]},
        ],
        "business_rules": rules or [],
    })


def _run(
    tmp_path: Path, spec: MappingSpec, legacy: pl.DataFrame, target: pl.DataFrame
) -> tuple[RunSummary, list[tuple[str, str]]]:
    data = tmp_path / "data"
    data.mkdir()
    legacy.write_parquet(data / "shops_legacy.parquet")
    target.write_parquet(data / "shops_target.parquet")
    summary = run(spec, LocalParquetStore(data), LocalParquetStore(tmp_path / "out"), "r1")
    found = pl.read_parquet(tmp_path / "out" / "gold" / "recon_finding" / "*.parquet")
    return summary, sorted(found.select("match_key_value", "rule").rows())


def _shops(ids: list[str], names: list[str] | None = None) -> pl.DataFrame:
    return pl.DataFrame({"id": ids, "name": names or ["x"] * len(ids)})


def test_a_padded_target_key_matches_its_source_row(tmp_path: Path) -> None:
    summary, found = _run(tmp_path, _spec(["trim"]), _shops(["C001", "C002"]),
                          _shops(["C001 ", "C002"]))
    assert found == []
    assert summary.passed == 2


def test_a_key_normalized_to_lower_case_matches_on_both_sides(tmp_path: Path) -> None:
    summary, found = _run(tmp_path, _spec(["lower"]), _shops(["c001"]), _shops(["C001"]))
    assert (found, summary.passed) == ([], 1)


def test_a_target_duplicate_hidden_by_padding_is_reported(tmp_path: Path) -> None:
    _, found = _run(tmp_path, _spec(["trim"]), _shops(["C001"]), _shops(["C001", "C001 "]))
    assert found == [("id=C001", "match_key duplicated in target (×2)")]


def test_an_integer_target_key_is_read_as_the_declared_string(tmp_path: Path) -> None:
    target = _shops(["412", "7"]).with_columns(pl.col("id").cast(pl.Int64))
    summary, found = _run(tmp_path, _spec([]), _shops(["412", "7"]), target)
    assert (found, summary.passed) == ([], 2)


def test_a_check_rule_reads_the_normalized_target(tmp_path: Path) -> None:
    spec = _spec(["trim"], [{"name": "named", "check": "name = 'x'"}])
    summary, found = _run(tmp_path, spec, _shops(["C001"]), _shops(["C001"], ["x "]))
    assert (found, summary.passed) == ([], 1)


def test_a_target_only_column_is_neither_compared_nor_in_silver(tmp_path: Path) -> None:
    spec = MappingSpec.model_validate({
        **_spec([]).model_dump(exclude_none=True),
        "columns": [
            {"source": "id", "target": "id", "type": "string"},
            {"source": "name", "target": "name", "type": "string"},
            {"target": "status", "target_only": True, "reason": "new ERP field"},
        ],
        "business_rules": [{"name": "known", "check": "status IN ('open', 'closed')"}],
    })
    target = _shops(["C001", "C002"]).with_columns(pl.Series("status", ["open", "gone"]))
    summary, found = _run(tmp_path, spec, _shops(["C001", "C002"]), target)
    assert found == [("id=C002", "known: status IN ('open', 'closed')")]
    assert summary.passed == 1
    silver = pl.read_parquet(tmp_path / "out" / "silver" / "shops" / "*.parquet")
    assert silver.columns == ["id", "name"]


def test_each_side_reads_its_dates_with_its_own_format(tmp_path: Path) -> None:
    spec = MappingSpec.model_validate({
        **_spec([]).model_dump(exclude_none=True),
        "columns": [
            {"source": "id", "target": "id", "type": "string"},
            {"source": "name", "target": "name", "type": "date",
             "source_format": "%d/%m/%Y", "target_format": "%d/%m/%Y %H:%M"},
        ],
    })
    source = _shops(["C001", "C002"], ["12/03/2024", "01/02/2023"])
    target = _shops(["C001", "C002"], ["12/03/2024 10:30", "02/02/2023 09:00"])
    summary, found = _run(tmp_path, spec, source, target)
    assert found == [("id=C002", "value differs")]
    assert summary.passed == 1
