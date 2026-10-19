"""Bronze layer: raw, immutable landing of both sides, plus ingestion metadata."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl


def land(frame: pl.DataFrame, run_id: str, source: str) -> pl.DataFrame:
    """Return the frame untouched, with `_run_id`, `_source` and `_ingested_at` appended."""
    return frame.with_columns(
        pl.lit(run_id).alias("_run_id"),
        pl.lit(source).alias("_source"),
        pl.lit(datetime.now(UTC).replace(tzinfo=None)).alias("_ingested_at"),
    )
