"""Seam 1: completeness — lost rows, extra rows, and deliberate absences."""

from __future__ import annotations

from conftest import frame, records
from relay_engine.checks.completeness import check_completeness
from relay_engine.mapping import MappingSpec
from relay_engine.sides import prepare


def _spec(expected_missing: str | None = None) -> MappingSpec:
    return MappingSpec.model_validate({
        "version": 1,
        "entity": "items",
        "source": {"table": "items_legacy"},
        "target": {"table": "items_target"},
        "match_key": ["id"],
        "source_scope": {"expected_missing": expected_missing} if expected_missing else None,
        "columns": [
            {"source": "code", "target": "id", "type": "string"},
            {"source": "statut", "exclude": True, "reason": "not migrated"},
        ],
    })


def _findings(spec: MappingSpec) -> set[tuple[str, str, str, str]]:
    legacy = frame(
        [("k1", "actif"), ("k2", "archive"), ("k3", "actif")], ["code", "statut"]
    )
    target = frame([("k1",), ("k3",), ("k4",)], ["id"])
    rows = records(check_completeness(prepare(spec, legacy, target), spec))
    return {(r.check_family, r.match_key_value, r.verdict, r.rule) for r in rows}


def test_lost_and_extra_rows_fail() -> None:
    assert _findings(_spec()) == {
        ("completeness", "id=k2", "FAIL", "source row missing from target"),
        ("completeness", "id=k4", "FAIL", "target row has no source"),
    }


def test_expected_missing_rows_are_not_reported() -> None:
    assert _findings(_spec("statut = 'archive'")) == {
        ("completeness", "id=k4", "FAIL", "target row has no source"),
    }
