"""Seam 1: business rules — row invariants and before/after aggregates."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from conftest import frame, prepared, records
from relay_engine.checks.business_rules import check_business_rules
from relay_engine.io import LocalParquetStore
from relay_engine.mapping import MappingError, MappingSpec, validate_mapping
from relay_engine.pipeline import run

SPEC = MappingSpec.model_validate({
    "version": 1,
    "entity": "items",
    "source": {"table": "items_legacy"},
    "target": {"table": "items_target"},
    "match_key": ["id"],
    "columns": [
        {"source": "code", "target": "id", "type": "string"},
        {"source": "mnt", "target": "montant", "type": "decimal(12,2)"},
        {"source": "dt", "target": "jour", "type": "date"},
    ],
    "business_rules": [
        {"name": "montant_positif", "check": "montant > 0"},
        {
            "name": "totaux_mensuels",
            "aggregate": "sum(montant)",
            "group_by": "strftime(jour, '%Y-%m')",
            "tolerance": 0.01,
            "verdict": "REVIEW",
        },
    ],
})
SCHEMA = "id string, montant decimal(12,2), jour date"


def test_violated_check_and_diverging_aggregate() -> None:
    silver = frame([
        ("k1", Decimal("100.00"), date(2024, 3, 1)),
        ("k2", Decimal("50.00"), date(2024, 3, 15)),
        ("k3", Decimal("30.00"), date(2024, 4, 2)),
    ], SCHEMA)
    target = frame([
        ("k1", Decimal("100.00"), date(2024, 3, 1)),
        ("k2", Decimal("-50.00"), date(2024, 3, 15)),
        ("k3", Decimal("30.01"), date(2024, 4, 2)),
    ], SCHEMA)

    rows = records(check_business_rules(prepared(SPEC, silver, target), SPEC))
    assert {
        (r.check_family, r.match_key_value, r.source_value, r.target_value, r.verdict, r.rule)
        for r in rows
    } == {
        ("business_rule", "id=k2", None, None, "FAIL", "montant_positif: montant > 0"),
        (
            "business_rule", "group=2024-03", "150.00", "50.00", "REVIEW",
            "totaux_mensuels: sum(montant) differs beyond tolerance 0.01",
        ),
    }


SITUATIONS = MappingSpec.model_validate({
    "version": 1,
    "entity": "situations",
    "source": {"table": "situations_legacy"},
    "target": {"table": "situations_target"},
    "match_key": ["situation_id"],
    "columns": [
        {"source": "situation_id", "target": "situation_id", "type": "string"},
        {"source": "contrat_id", "target": "contrat_id", "type": "string"},
        {"source": "montant", "target": "montant", "type": "decimal(12,2)"},
    ],
    "business_rules": [{
        "name": "situations_dans_le_marche",
        "cross": {
            "table": "contrats_target",
            "on": {"contrat_id": "contrat_id"},
            "totals": {"total_situations": "sum(montant)"},
        },
        "check": "total_situations <= montant_marche",
    }],
})
SITUATIONS_SCHEMA = "situation_id string, contrat_id string, montant decimal(12,2)"
CONTRATS = frame(
    [("c1", Decimal("100.00")), ("c2", Decimal("80.00"))],
    "contrat_id string, montant_marche decimal(12,2)",
)


def _situations(rows: list[tuple]) -> pl.DataFrame:
    return frame(rows, SITUATIONS_SCHEMA)


def test_a_cross_rule_that_holds_finds_nothing() -> None:
    rows = _situations([
        ("s1", "c1", Decimal("60.00")), ("s2", "c1", Decimal("40.00")),
        ("s3", "c2", Decimal("80.00")),
    ])
    sides = prepared(SITUATIONS, rows, rows)
    found = check_business_rules(sides, SITUATIONS, {"contrats_target": CONTRATS})
    assert found.is_empty()


def test_a_cross_rule_flags_each_contract_over_its_amount() -> None:
    rows = _situations([
        ("s1", "c1", Decimal("60.00")), ("s2", "c1", Decimal("40.01")),
        ("s3", "c2", Decimal("80.00")),
    ])
    sides = prepared(SITUATIONS, rows, rows)
    found = records(check_business_rules(sides, SITUATIONS, {"contrats_target": CONTRATS}))
    assert [(r.check_family, r.match_key_value, r.verdict, r.rule) for r in found] == [(
        "business_rule", "contrat_id=c1", "FAIL",
        "situations_dans_le_marche: total_situations <= montant_marche (across contrats_target)",
    )]


def test_a_cross_rule_violation_fails_the_run(tmp_path: Path) -> None:
    rows = _situations([("s1", "c1", Decimal("120.00")), ("s2", "c2", Decimal("10.00"))])
    for name, table in {
        "situations_legacy": rows, "situations_target": rows, "contrats_target": CONTRATS,
    }.items():
        table.write_parquet(tmp_path / f"{name}.parquet")
    summary = run(SITUATIONS, LocalParquetStore(tmp_path), LocalParquetStore(tmp_path), "r1")
    assert (summary.verdict, summary.fail, summary.passed) == ("FAIL", 1, 2)


def test_a_cross_rule_on_unknown_table_or_columns_is_refused() -> None:
    columns = ["situation_id", "contrat_id", "montant"]
    with pytest.raises(MappingError) as exc:
        validate_mapping(SITUATIONS, columns, columns, {})
    assert "business rule 'situations_dans_le_marche': table 'contrats_target' does not exist" in (
        str(exc.value)
    )
    with pytest.raises(MappingError) as exc:
        validate_mapping(SITUATIONS, columns, columns, {"contrats_target": ["id", "montant"]})
    assert (
        "business rule 'situations_dans_le_marche': column 'contrat_id' does not exist "
        "in 'contrats_target'"
    ) in str(exc.value)
