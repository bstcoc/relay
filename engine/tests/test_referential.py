"""Seam 2: referential integrity — key duplicates on each side, orphan foreign keys."""

from __future__ import annotations

from decimal import Decimal

from conftest import frame, prepared, records
from relay_engine.checks.referential import check_referential
from relay_engine.mapping import MappingSpec

SPEC = MappingSpec.model_validate({
    "version": 1,
    "entity": "factures",
    "source": {"table": "factures_legacy"},
    "target": {"table": "factures_target"},
    "match_key": ["facture_id"],
    "columns": [
        {"source": "facture", "target": "facture_id", "type": "string"},
        {"source": "chantier", "target": "chantier_id", "type": "string"},
    ],
    "references": [
        {"column": "chantier_id", "table": "chantiers_target", "key": "chantier_id"}
    ],
})
SCHEMA = "facture_id string, chantier_id string"
LENIENT = SPEC.model_copy(update={"max_duplicate_share": Decimal(1)})


def _duplicates(source_ids: list[str], target_ids: list[str]) -> set[tuple]:
    """(key, verdict, rule) of the key-duplicate findings, for bare lists of ids."""
    source = frame([(i, "c1") for i in source_ids], SCHEMA)
    target = frame([(i, "c1") for i in target_ids], SCHEMA)
    chantiers = frame([("c1",)], ["chantier_id"])
    sides = prepared(LENIENT, source, target)
    rows = records(check_referential(sides, LENIENT, {"chantiers_target": chantiers}))
    return {(r.match_key_value, r.verdict, r.rule) for r in rows}


def test_duplicates_and_orphans_fail() -> None:
    target = frame(
        [("f1", "c1"), ("f2", "c9"), ("f2", "c1"), ("f3", None)],
        SCHEMA,
    )
    source = frame([("f1", "c1"), ("f2", "c1"), ("f3", None)], SCHEMA)
    chantiers = frame([("c1",)], ["chantier_id"])

    sides = prepared(SPEC, source, target)
    rows = records(check_referential(sides, SPEC, {"chantiers_target": chantiers}))
    assert {(r.match_key_value, r.column, r.target_value, r.verdict, r.rule) for r in rows} == {
        ("facture_id=f2", "facture_id", None, "FAIL", "match_key duplicated in target (×2)"),
        (
            "facture_id=f2", "chantier_id", "c9", "FAIL",
            "references chantiers_target.chantier_id: value not found",
        ),
    }
    assert {r.check_family for r in rows} == {"referential"}


def test_orphans_keep_target_order_and_a_null_parent_key_matches_nothing() -> None:
    target = frame([("f3", "c7"), ("f1", "c1"), ("f2", "c9"), ("f4", None)], SCHEMA)
    chantiers = frame([("c1",), (None,)], ["chantier_id"])

    sides = prepared(SPEC, target, target)
    rows = records(check_referential(sides, SPEC, {"chantiers_target": chantiers}))
    assert [(r.match_key_value, r.target_value) for r in rows] == [
        ("facture_id=f3", "c7"), ("facture_id=f2", "c9"),
    ]


def test_a_source_duplicate_is_one_review_finding_per_key() -> None:
    rows = records(check_referential(
        prepared(
            LENIENT,
            frame([("f1", "c1"), ("f1", "c2"), ("f1", "c3"), ("f2", "c1")], SCHEMA),
            frame([("f1", "c1"), ("f2", "c1")], SCHEMA),
        ),
        LENIENT,
        {"chantiers_target": frame([("c1",)], ["chantier_id"])},
    ))
    assert [
        (r.check_family, r.match_key_value, r.column, r.source_value, r.target_value,
         r.verdict, r.rule)
        for r in rows
    ] == [(
        "referential", "facture_id=f1", "facture_id", None, None,
        "REVIEW", "match_key duplicated in source (×3)",
    )]


def test_an_accepted_source_duplicate_stays_accepted_when_it_grows() -> None:
    def finding_key(copies: int) -> str:
        source = frame([("f1", "c1")] * copies, SCHEMA)
        found = check_referential(
            prepared(LENIENT, source, source.head(1)), LENIENT, {"chantiers_target": source}
        )
        return found.get_column("finding_key").item()

    assert finding_key(2) == finding_key(3)


def test_a_target_duplicate_fails_only_when_the_migration_added_copies() -> None:
    assert _duplicates(["f1"], ["f1", "f1"]) == {
        ("facture_id=f1", "FAIL", "match_key duplicated in target (×2)"),
    }
    assert _duplicates([], ["f1", "f1"]) == {
        ("facture_id=f1", "FAIL", "match_key duplicated in target (×2)"),
    }
    source_only = {("facture_id=f1", "REVIEW", "match_key duplicated in source (×2)")}
    assert _duplicates(["f1", "f1"], ["f1", "f1"]) == source_only
    assert _duplicates(["f1", "f1"], ["f1"]) == source_only
    assert _duplicates(["f1", "f1"], ["f1", "f1", "f1"]) == source_only | {
        ("facture_id=f1", "FAIL", "match_key duplicated in target (×3, ×2 in source)"),
    }


def test_a_parent_key_is_read_with_the_rules_of_the_column_pointing_to_it() -> None:
    spec = SPEC.model_copy(update={"columns": [
        SPEC.columns[0], SPEC.columns[1].model_copy(update={"normalize": ["trim"]}),
    ]})
    for child, parent in (("c1 ", "c1"), ("c1 ", "c1 "), ("c1", "c1 ")):
        source = frame([("f1", child)], SCHEMA)
        sides = prepared(spec, source, source)
        chantiers = frame([(parent,)], ["chantier_id"])
        assert check_referential(sides, spec, {"chantiers_target": chantiers}).is_empty(), (
            child, parent,
        )


_RULE = "references chantiers_target.chantier_id: value not found"


def _orphans(source: list[tuple], target: list[tuple], source_parent: list[str] | None,
             target_parent: list[str]) -> set[tuple]:
    """(key, target value, verdict, rule) of the orphan findings."""
    sides = prepared(SPEC, frame(source, SCHEMA), frame(target, SCHEMA))
    parents = None if source_parent is None else {
        "chantiers_target": (frame([(c,) for c in source_parent], ["chantier"]), "chantier"),
    }
    rows = records(check_referential(
        sides, SPEC, {"chantiers_target": frame([(c,) for c in target_parent], ["chantier_id"])},
        parents,
    ))
    return {(r.match_key_value, r.target_value, r.verdict, r.rule) for r in rows}


def test_an_orphan_already_in_the_source_is_inherited() -> None:
    assert _orphans([("f1", "c9")], [("f1", "c9")], ["c1"], ["c1"]) == {
        ("facture_id=f1", "c9", "REVIEW", f"{_RULE} in source either (inherited)"),
    }


def test_an_orphan_the_migration_created_still_fails() -> None:
    assert _orphans([("f1", "c2")], [("f1", "c2")], ["c1", "c2"], ["c1"]) == {
        ("facture_id=f1", "c2", "FAIL", _RULE),
    }
    assert _orphans([("f1", "c1")], [("f1", "c9")], ["c1"], ["c1"]) == {
        ("facture_id=f1", "c9", "FAIL", _RULE),
    }
    assert _orphans([], [("f1", "c9")], ["c1"], ["c1"]) == {
        ("facture_id=f1", "c9", "FAIL", _RULE),
    }


def test_without_the_parent_mapping_an_orphan_fails() -> None:
    assert _orphans([("f1", "c9")], [("f1", "c9")], None, ["c1"]) == {
        ("facture_id=f1", "c9", "FAIL", _RULE),
    }


def test_the_source_parent_key_follows_the_rules_of_the_pointing_column() -> None:
    spec = SPEC.model_copy(deep=True)
    spec.columns[1].normalize = ["trim"]
    sides = prepared(spec, frame([("f1", "c1 ")], SCHEMA), frame([("f1", "c1")], SCHEMA))
    rows = records(check_referential(
        sides, spec, {"chantiers_target": frame([("c2",)], ["chantier_id"])},
        {"chantiers_target": (frame([(" c1",)], ["chantier"]), "chantier")},
    ))
    assert [(r.verdict, r.rule) for r in rows] == [("FAIL", _RULE)]
