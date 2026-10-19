"""Verdicts of the scenario oracle: pure functions, no run."""

from __future__ import annotations

from relay_engine.generator.model import Anomaly, AnomalyType, ExpectedVerdict, Manifest
from relay_engine.oracle.evaluate import (
    Found,
    evaluate_seed,
    explain_baseline,
    group,
)
from relay_engine.oracle.scenario import Expectation, Intent

TRUNCATED = Anomaly(
    "shops", "id=C001", AnomalyType.VALUE_TRUNCATED, ExpectedVerdict.REVIEW, "name"
)
DUPLICATED = Anomaly(
    "shops", "id=C002", AnomalyType.NATURAL_KEY_DUPLICATED, ExpectedVerdict.FAIL
)


def _manifest(*anomalies: Anomaly) -> Manifest:
    return Manifest(seed=1, entities=["shops"], anomalies=list(anomalies))


def _found(key: str, column: str | None, rule: str, verdict: str, family: str) -> Found:
    return Found(family, key, column, rule, verdict)


def test_an_anomaly_is_detected_on_its_key_verdict_and_column() -> None:
    found = [_found("id=C001", "name", "value differs", "REVIEW", "fidelity")]
    report = evaluate_seed(_manifest(TRUNCATED), found, baseline=[])
    assert report.ok
    assert (report.detected, report.total) == (1, 1)


def test_a_finding_on_the_wrong_column_misses_and_is_a_false_positive() -> None:
    found = [_found("id=C001", "city", "value differs", "REVIEW", "fidelity")]
    report = evaluate_seed(_manifest(TRUNCATED), found, baseline=[])
    assert report.missed == [TRUNCATED]
    assert report.false_positives == found
    assert not report.ok


def test_a_row_level_anomaly_matches_any_column() -> None:
    found = [_found("id=C002", "id", "match_key duplicated in target (×2)", "FAIL", "referential")]
    assert evaluate_seed(_manifest(DUPLICATED), found, baseline=[]).ok


def test_baseline_findings_do_not_count_as_false_positives() -> None:
    intended = _found("id=C009", "city", "value differs", "REVIEW", "fidelity")
    found = [intended, _found("id=C001", "name", "value differs", "REVIEW", "fidelity")]
    report = evaluate_seed(_manifest(TRUNCATED), found, baseline=[intended])
    assert report.ok


def test_a_new_unexplained_finding_is_a_false_positive() -> None:
    stray = _found("id=C007", None, "target row has no source", "FAIL", "completeness")
    found = [_found("id=C001", "name", "value differs", "REVIEW", "fidelity"), stray]
    report = evaluate_seed(_manifest(TRUNCATED), found, baseline=[])
    assert report.false_positives == [stray]
    assert not report.ok


def test_a_seed_with_nothing_injected_is_not_ok() -> None:
    report = evaluate_seed(_manifest(), [], baseline=[])
    assert report.total == 0
    assert not report.ok


def test_baseline_findings_are_explained_by_intents() -> None:
    upper = Intent(name="upper_city", why="capitals", expects=Expectation(column="city"))
    dedup = Intent(
        name="dedup", why="last kept", expects=Expectation(check="completeness")
    )
    found = [
        _found("id=C001", "city", "value differs", "REVIEW", "fidelity"),
        _found("id=C002", "city", "value differs", "REVIEW", "fidelity"),
        _found("id=C003", "name", "value differs", "REVIEW", "fidelity"),
    ]
    report = explain_baseline(found, [upper, dedup])
    assert report.per_intent == {"upper_city": 2, "dedup": 0}
    assert report.unexplained == [found[2]]
    assert report.silent == ["dedup"]
    assert not report.ok


def test_an_empty_baseline_is_ok_in_tier1() -> None:
    assert explain_baseline([], []).ok


def test_group_counts_by_family_column_and_rule() -> None:
    found = [
        _found("id=C001", "city", "value differs", "REVIEW", "fidelity"),
        _found("id=C002", "city", "value differs", "REVIEW", "fidelity"),
        _found("id=C003", None, "target row has no source", "FAIL", "completeness"),
    ]
    assert group(found) == [
        ("fidelity", "city", "value differs", 2),
        ("completeness", None, "target row has no source", 1),
    ]
