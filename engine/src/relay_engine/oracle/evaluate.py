"""Verdicts of the scenario oracle: pure functions over findings, manifest and baseline.

Detection: each injected anomaly surfaces on its key with the expected verdict
and, when it targets a column, on that column. Precision: every finding absent
from the baseline run is explained by an injected anomaly.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from relay_engine.generator.model import Anomaly, Manifest
from relay_engine.oracle.scenario import Intent


@dataclass(frozen=True)
class Found:
    """The part of a recon_finding row the oracle judges."""

    check_family: str
    match_key_value: str
    column: str | None
    rule: str
    verdict: str

    @property
    def identity(self) -> tuple[str, str | None, str]:
        return (self.match_key_value, self.column, self.rule)


@dataclass
class BaselineReport:
    unexplained: list[Found]
    per_intent: dict[str, int]

    @property
    def silent(self) -> list[str]:
        """Intents that produced no finding: not applied, or already declarable."""
        return [name for name, count in self.per_intent.items() if count == 0]

    @property
    def ok(self) -> bool:
        return not self.unexplained and not self.silent


def explain_baseline(found: list[Found], intents: list[Intent]) -> BaselineReport:
    """Match every baseline finding to the intents that announce it."""
    per_intent = {intent.name: 0 for intent in intents}
    unexplained: list[Found] = []
    for finding in found:
        matched = [
            intent for intent in intents
            if intent.expects.matches(finding.check_family, finding.column, finding.rule)
        ]
        for intent in matched:
            per_intent[intent.name] += 1
        if not matched:
            unexplained.append(finding)
    return BaselineReport(unexplained, per_intent)


def _explains(anomaly: Anomaly, finding: Found) -> bool:
    return (
        finding.match_key_value == anomaly.match_key
        and finding.verdict == anomaly.expected_verdict.value
        and (anomaly.column is None or finding.column == anomaly.column)
    )


@dataclass
class SeedReport:
    seed: int
    total: int
    missed: list[Anomaly]
    false_positives: list[Found]

    @property
    def detected(self) -> int:
        return self.total - len(self.missed)

    @property
    def ok(self) -> bool:
        return self.total > 0 and not self.missed and not self.false_positives


def evaluate_seed(manifest: Manifest, found: list[Found], baseline: list[Found]) -> SeedReport:
    """Judge one injected run against its manifest, ignoring what the baseline already had."""
    known = {finding.identity for finding in baseline}
    new = [finding for finding in found if finding.identity not in known]
    missed = [a for a in manifest.anomalies if not any(_explains(a, f) for f in new)]
    false_positives = [f for f in new if not any(_explains(a, f) for a in manifest.anomalies)]
    return SeedReport(manifest.seed, len(manifest.anomalies), missed, false_positives)


def group(found: list[Found]) -> list[tuple[str, str | None, str, int]]:
    """(family, column, rule, count), most frequent first: readable at any volume."""
    counts = Counter((f.check_family, f.column, f.rule) for f in found)
    return [(family, column, rule, n) for (family, column, rule), n in counts.most_common()]
