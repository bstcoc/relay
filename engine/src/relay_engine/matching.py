"""Match-key guard: the key must identify a single source row.

The key is judged on the source side, by the share of rows caught in a
duplicate. Above `max_duplicate_share`, the key does not discriminate rows — a
spec defect, so the engine stops. Below it, the key is right and the source is
dirty: each duplicated value becomes a REVIEW finding and is left out of the
row-level comparison. A duplicate the migration added in the target is a FAIL.
"""

from __future__ import annotations

from decimal import Decimal

import polars as pl

from relay_engine.mapping.errors import MappingError

_SAMPLES = 3


class AmbiguousKeyError(MappingError):
    """The declared match_key designates several source rows too often to be right."""


def key_counts(frame: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    """Every key value of `frame` with its number of rows (`len`)."""
    return frame.group_by(keys).len()


def _shown(value: object) -> str:
    return "(empty)" if value is None else str(value)


def _percent(part: int, whole: int) -> int:
    """Whole percent, rounded up: a non-zero share never shows as 0%."""
    return -(-part * 100 // whole)


def check_match_key(
    source: pl.DataFrame, keys: list[str], max_share: Decimal = Decimal("0.05")
) -> pl.DataFrame:
    """Key values found more than once in the source, with their count (`len`).

    Raise AmbiguousKeyError when the rows sharing a key exceed `max_share` of the source.
    """
    duplicates = key_counts(source, keys).filter(pl.col("len") > 1)
    shared = int(duplicates.get_column("len").sum())
    if shared <= max_share * source.height:
        return duplicates
    top = duplicates.sort(["len", *keys], descending=[True] + [False] * len(keys))
    samples = ", ".join(
        f"'{'/'.join(_shown(row[k]) for k in keys)}' ×{row['len']}"
        for row in top.head(_SAMPLES).iter_rows(named=True)
    )
    limit = f"{(max_share * 100).normalize():f}%"
    raise AmbiguousKeyError([
        f"match_key ({', '.join(keys)}) is not unique in the source: "
        f"{_percent(shared, source.height)}% of rows ({shared} of {source.height}) share "
        f"their key with another row, above the {limit} limit (e.g. {samples}). "
        "Refine the key so it identifies a single row, or raise max_duplicate_share."
    ])
