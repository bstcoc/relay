"""Seam 1: fidelity — value-level comparison of matched rows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl

from conftest import frame, prepared, records
from relay_engine.checks.fidelity import check_fidelity
from relay_engine.mapping import MappingSpec

SPEC = MappingSpec.model_validate({
    "version": 1,
    "entity": "items",
    "source": {"table": "items_legacy"},
    "target": {"table": "items_target"},
    "match_key": ["id"],
    "columns": [
        {"source": "code", "target": "id", "type": "string"},
        {"source": "lib", "target": "nom", "type": "string", "normalize": ["trim"]},
        {"source": "mnt", "target": "montant", "type": "decimal(12,2)", "tolerance": 0.01},
        {"source": "dt", "target": "jour", "type": "date"},
    ],
})
SCHEMA = "id string, nom string, montant decimal(12,2), jour date"
D = date(2024, 3, 1)


def _frame(rows: list[tuple]) -> pl.DataFrame:
    return frame(rows, SCHEMA)


def _findings(source: list[tuple], target: list[tuple]) -> set[tuple]:
    rows = records(check_fidelity(prepared(SPEC, _frame(source), _frame(target)), SPEC))
    return {(r.match_key_value, r.column, r.source_value, r.target_value, r.verdict) for r in rows}


def test_identical_rows_yield_nothing_and_a_changed_value_is_reviewed() -> None:
    source = [("k1", "Villa", Decimal("100.00"), D), ("k2", "Garage", Decimal("50.00"), D)]
    target = [("k1", "Villa", Decimal("100.00"), D), ("k2", "Garages", Decimal("50.00"), D)]
    assert _findings(source, target) == {
        ("id=k2", "nom", "Garage", "Garages", "REVIEW"),
    }


def test_tolerance_absorbs_small_gaps_and_reports_larger_ones() -> None:
    source = [("k1", "A", Decimal("100.00"), D), ("k2", "B", Decimal("100.00"), D)]
    target = [("k1", "A", Decimal("99.99"), D), ("k2", "B", Decimal("99.97"), D)]
    rows = records(check_fidelity(prepared(SPEC, _frame(source), _frame(target)), SPEC))
    assert [(r.match_key_value, r.column, r.verdict, r.rule) for r in rows] == [
        ("id=k2", "montant", "REVIEW", "tolerance 0.01 exceeded (diff 0.03)"),
    ]


def test_a_value_lost_in_the_target_fails() -> None:
    source = [("k1", "Villa", Decimal("100.00"), D)]
    target = [("k1", None, Decimal("100.00"), D)]
    rows = records(check_fidelity(prepared(SPEC, _frame(source), _frame(target)), SPEC))
    assert [(r.column, r.source_value, r.target_value, r.verdict, r.rule) for r in rows] == [
        ("nom", "Villa", None, "FAIL", "value lost in target"),
    ]


def test_a_key_duplicated_in_the_source_is_not_compared() -> None:
    lenient = SPEC.model_copy(update={"max_duplicate_share": Decimal(1)})
    source = [
        ("k1", "Villa", Decimal("100.00"), D), ("k1", "Garage", Decimal("50.00"), D),
        ("k2", "Cave", Decimal("10.00"), D),
    ]
    target = [("k1", "Villa", Decimal("100.00"), D), ("k2", "Caves", Decimal("10.00"), D)]
    rows = records(check_fidelity(prepared(lenient, _frame(source), _frame(target)), lenient))
    assert [(r.match_key_value, r.column, r.source_value, r.target_value) for r in rows] == [
        ("id=k2", "nom", "Cave", "Caves"),
    ]

def test_normalization_applies_to_both_sides() -> None:
    source = [("k1", "Villa", Decimal("100.00"), D)]
    target = [("k1", "  Villa  ", Decimal("100.00"), D)]
    assert _findings(source, target) == set()


def test_each_differing_column_is_its_own_finding() -> None:
    source = [("k1", "Villa", Decimal("100.00"), D), ("k2", "Garage", Decimal("50.00"), D)]
    target = [
        ("k1", "Villas", Decimal("100.00"), date(2024, 3, 2)),
        ("k2", "Garage", Decimal("50.00"), D),
    ]
    assert _findings(source, target) == {
        ("id=k1", "nom", "Villa", "Villas", "REVIEW"),
        ("id=k1", "jour", "2024-03-01", "2024-03-02", "REVIEW"),
    }


LEGACY_SCHEMA = "code string, lib string, mnt string, dt string"
TEXT_TARGET = "id string, nom string, montant string, jour string"


def _raw_findings(
    legacy: list[tuple], target: list[tuple]
) -> set[tuple]:
    from relay_engine.sides import prepare

    sides = prepare(SPEC, frame(legacy, LEGACY_SCHEMA), frame(target, TEXT_TARGET))
    rows = records(check_fidelity(sides, SPEC))
    return {
        (r.match_key_value, r.column, r.source_value, r.target_value, r.verdict, r.rule)
        for r in rows
    }


def test_an_unreadable_source_date_is_one_failed_cell() -> None:
    legacy = [("k1", "Villa", "100.00", "30/08/2023")]
    target = [("k1", "Villa", "100.00", "2023-08-30")]
    assert _raw_findings(legacy, target) == {
        ("id=k1", "jour", "30/08/2023", "2023-08-30", "FAIL",
         "source value is not a valid date"),
    }


def test_an_unreadable_target_value_is_one_failed_cell() -> None:
    legacy = [("k1", "Villa", "100.00", "2023-08-30")]
    target = [("k1", "Villa", "12x", "2023-08-30")]
    assert _raw_findings(legacy, target) == {
        ("id=k1", "montant", "100.00", "12x", "FAIL",
         "target value is not a valid decimal(12,2)"),
    }


def test_an_unreadable_value_is_reported_even_when_the_other_side_is_empty() -> None:
    legacy = [("k1", "Villa", "cent", "2023-08-30")]
    target = [("k1", "Villa", None, "2023-08-30")]
    assert _raw_findings(legacy, target) == {
        ("id=k1", "montant", "cent", None, "FAIL",
         "source value is not a valid decimal(12,2)"),
    }


def test_an_empty_value_is_not_unreadable() -> None:
    legacy = [("k1", "Villa", "100.00", "   ")]
    target = [("k1", "Villa", "100.00", None)]
    assert _raw_findings(legacy, target) == set()
