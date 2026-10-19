"""Seam 2: applying human decisions to findings (docs/results-model.md)."""

from __future__ import annotations

from datetime import datetime

from conftest import frame, records
from relay_engine.decisions import apply_decisions, effective_counts


def test_decisions_are_inherited_by_finding_key() -> None:
    found = frame(
        [("f1", "REVIEW"), ("f2", "REVIEW"), ("f3", "FAIL"), ("f4", "REVIEW")],
        "finding_key string, verdict string",
    )
    decisions = frame(
        [
            ("f1", "rejected", "bastien", datetime(2026, 9, 1), "first look"),
            ("f1", "accepted", "bastien", datetime(2026, 9, 2), "known rounding"),
            ("f2", "rejected", "bastien", datetime(2026, 9, 2), "real bug"),
            ("f3", "accepted", "bastien", datetime(2026, 9, 2), "row archived on purpose"),
            ("stale", "accepted", "bastien", datetime(2026, 9, 2), "value has since changed"),
        ],
        "finding_key string, decision string, decided_by string, decided_at timestamp, "
        "reason string",
    )

    decided = apply_decisions(found, decisions)
    assert {(r.finding_key, r.decision) for r in records(decided)} == {
        ("f1", "accepted"),
        ("f2", "rejected"),
        ("f3", "accepted"),
        ("f4", None),
    }
    assert effective_counts(decided) == {"review": 1, "fail": 1, "accepted": 2}


def test_no_decisions_leaves_findings_undecided() -> None:
    found = frame(
        [("f1", "REVIEW"), ("f2", "FAIL")], "finding_key string, verdict string"
    )
    decided = apply_decisions(found, None)
    assert effective_counts(decided) == {"review": 1, "fail": 1, "accepted": 0}
