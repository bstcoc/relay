"""Human decisions on findings, persisted across runs (docs/results-model.md).

A decision is attached to a `finding_key`. Since the key hashes both values, a
changed value yields a new key: no decision matches and the finding is reviewed
again. When a finding was decided several times, the latest decision wins.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl


def latest_decisions(decisions: pl.DataFrame) -> pl.DataFrame:
    """One decision per finding_key: the most recent one."""
    return decisions.sort("decided_at", descending=True, nulls_last=True).unique(
        "finding_key", keep="first", maintain_order=True
    )


def apply_decisions(found: pl.DataFrame, decisions: pl.DataFrame | None) -> pl.DataFrame:
    """Add a `decision` column: accepted, rejected, or NULL when undecided."""
    if decisions is None:
        return found.with_columns(pl.lit(None, pl.String).alias("decision"))
    latest = latest_decisions(decisions).select("finding_key", "decision")
    return found.join(latest, on="finding_key", how="left")


def effective_counts(decided: pl.DataFrame) -> dict[str, int]:
    """Undecided REVIEW, failures (undecided FAIL or any rejected), and accepted findings."""
    decision, verdict = pl.col("decision"), pl.col("verdict")
    row = decided.select(
        (decision.is_null() & (verdict == "REVIEW")).sum().alias("review"),
        ((decision == "rejected").fill_null(False)
         | (decision.is_null() & (verdict == "FAIL"))).sum().alias("fail"),
        (decision == "accepted").fill_null(False).sum().alias("accepted"),
    ).row(0, named=True)
    return {k: int(row[k] or 0) for k in ("review", "fail", "accepted")}


def read_decisions(folder: Path) -> pl.DataFrame | None:
    """Every decision recorded under `folder`, or None when there is none."""
    recorded = sorted((folder / "recon_decision").glob("*.parquet"))
    return pl.read_parquet(recorded) if recorded else None


def record_decision(folder: Path, finding_key: str, decision: str, by: str, reason: str) -> None:
    """Append one decision; the latest one on a finding_key wins."""
    if len(finding_key) != 64 or any(c not in "0123456789abcdef" for c in finding_key):
        raise ValueError("A finding_key is 64 hexadecimal characters.")
    if decision not in ("accepted", "rejected"):
        raise ValueError("A decision is accepted or rejected.")
    if not reason.strip():
        raise ValueError("A reason is required: decisions form the audit trail.")
    target = folder / "recon_decision"
    target.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    pl.DataFrame({
        "finding_key": [finding_key],
        "decision": [decision],
        "decided_by": [by],
        "decided_at": [now.replace(tzinfo=None)],
        "reason": [reason],
    }).write_parquet(target / f"{now:%Y-%m-%dT%H%M%S%f}.parquet")
