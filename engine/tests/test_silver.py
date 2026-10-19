"""Seam 2: conforming legacy data to the target schema through the mapping."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from polars.testing import assert_frame_equal

from conftest import frame, records
from relay_engine.generator.generate import generate
from relay_engine.layers.silver import conform
from relay_engine.mapping import load_mapping

EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"


def _check_entity(tmp_path: Path, entity: str, key: str) -> None:
    manifest = generate(tmp_path, seed=42, rows=50)
    spec = load_mapping(EXAMPLES / f"{entity}.yaml")
    corrupted = {a.match_key for a in manifest.anomalies if a.entity == entity}

    legacy = pl.read_parquet(tmp_path / f"{entity}_legacy.parquet")
    target = pl.read_parquet(tmp_path / f"{entity}_target.parquet")

    silver = conform(legacy, spec).filter(~pl.col(key).is_in(list(corrupted)))
    expected = target.filter(~pl.col(key).is_in(list(corrupted)))

    assert silver.columns == spec.target_columns()
    assert silver.height == expected.height > 0
    assert_frame_equal(silver, expected, check_row_order=False, check_dtypes=False)


def test_conform_chantiers_matches_ideal_target(tmp_path: Path) -> None:
    _check_entity(tmp_path, "chantiers", "chantier_id")


def test_conform_factures_matches_ideal_target(tmp_path: Path) -> None:
    _check_entity(tmp_path, "factures", "facture_id")


def test_an_unreadable_value_conforms_to_null_instead_of_failing() -> None:
    from relay_engine.layers.silver import conform
    from relay_engine.mapping import MappingSpec

    spec = MappingSpec.model_validate({
        "version": 1, "entity": "e",
        "source": {"table": "s"}, "target": {"table": "t"}, "match_key": ["id"],
        "columns": [
            {"source": "id", "target": "id", "type": "string"},
            {"source": "d", "target": "d", "type": "date", "normalize": "date_only"},
            {"source": "n", "target": "n", "type": "integer"},
        ],
    })
    legacy = frame([("k1", "30/08/2023", "abc")], "id string, d string, n string")
    row = records(conform(legacy, spec))[0]
    assert (row.d, row.n) == (None, None)


def _read(value: str, entry: dict) -> object:
    from relay_engine.layers.silver import conform
    from relay_engine.mapping import MappingSpec

    spec = MappingSpec.model_validate({
        "version": 1, "entity": "e", "source": {"table": "s"}, "target": {"table": "t"},
        "match_key": ["d"], "columns": [{"source": "d", "target": "d", **entry}],
    })
    return conform(pl.DataFrame({"d": [value]}), spec).item()


def test_a_declared_source_format_reads_french_dates() -> None:
    from datetime import date, datetime

    assert _read("12/03/2024", {"type": "date", "source_format": "%d/%m/%Y"}) == date(2024, 3, 12)
    assert _read(" 12/03/2024 10:30 ", {
        "type": "datetime", "source_format": "%d/%m/%Y %H:%M",
    }) == datetime(2024, 3, 12, 10, 30)
    assert _read("12/03/2024 10:30", {
        "type": "date", "source_format": "%d/%m/%Y %H:%M",
    }) == date(2024, 3, 12)
    assert _read("12/03/2024", {
        "type": "date", "normalize": ["empty_as_null", "date_only"], "source_format": "%d/%m/%Y",
    }) == date(2024, 3, 12)


def test_a_declared_format_is_the_only_one_read() -> None:
    assert _read("2024-03-12", {"type": "date", "source_format": "%d/%m/%Y"}) is None
    assert _read("12/03/2024 10:30", {"type": "date", "source_format": "%d/%m/%Y"}) is None
