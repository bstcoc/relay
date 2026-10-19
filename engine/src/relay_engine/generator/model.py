"""Reference schema and anomaly model for the synthetic data generator.

The generator produces a legacy dataset, an ideal target derived from it,
then injects known anomalies into the target. Each injected anomaly is
recorded in the manifest — the ground truth against which later increments
are tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AnomalyType(StrEnum):
    """The kinds of migration defects the generator can inject."""

    VALUE_TRUNCATED = "value_truncated"
    VALUE_LOST = "value_lost"
    DATE_SHIFTED = "date_shifted"
    ROW_DROPPED = "row_dropped"
    ROW_EXTRA = "row_extra"
    FK_ORPHAN = "fk_orphan"
    NATURAL_KEY_DUPLICATED = "natural_key_duplicated"
    BUSINESS_RULE_VIOLATED = "business_rule_violated"


class ExpectedVerdict(StrEnum):
    """The verdict a correct engine should reach for an injected anomaly."""

    REVIEW = "REVIEW"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Anomaly:
    """One injected defect, recorded as ground truth in the manifest."""

    entity: str
    match_key: str
    anomaly_type: AnomalyType
    expected_verdict: ExpectedVerdict
    column: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, str | None]:
        return {
            "entity": self.entity,
            "match_key": self.match_key,
            "column": self.column,
            "anomaly_type": self.anomaly_type.value,
            "expected_verdict": self.expected_verdict.value,
            "detail": self.detail,
        }


@dataclass
class Manifest:
    """The full ground truth of a generation run."""

    seed: int
    entities: list[str]
    anomalies: list[Anomaly] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "entities": self.entities,
            "anomalies": [a.to_dict() for a in self.anomalies],
        }
