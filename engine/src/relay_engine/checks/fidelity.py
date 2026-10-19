"""Fidelity: did values survive the migration?

Both sides come prepared the same way (relay_engine.sides), then are compared
column by column on the rows matched by the match_key. Tolerances apply at that level. A key
duplicated on either side matches no single row, so it is not compared: the
referential check reports it.

A value that cannot be read as its declared type is one FAIL finding
on its cell, with the value as written; that cell is not compared again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from relay_engine.checks.findings import empty_findings, findings, text
from relay_engine.layers.silver import RAW, typed
from relay_engine.mapping import MappingSpec

if TYPE_CHECKING:
    from relay_engine.sides import Sides


def _side(
    frame: pl.DataFrame, keys: list[str], compared: list[str], typed_columns: list[str],
    prefix: str,
) -> pl.LazyFrame:
    """Values to compare on the rows whose key is unique; for typed columns only, the value
    as written and whether it read."""

    def written(c: str) -> pl.Expr:
        return pl.col(RAW + c) if RAW + c in frame.columns else text(frame, c)

    def unreadable(c: str) -> pl.Expr:
        if RAW + c not in frame.columns:
            return pl.lit(False)
        raw = pl.col(RAW + c)
        return raw.is_not_null() & (raw.str.strip_chars(" ") != "") & pl.col(c).is_null()

    unique = frame.lazy().group_by(keys).len().filter(pl.col("len") == 1)
    return frame.lazy().join(unique, on=keys, how="semi").select(
        *keys,
        *[pl.col(c).alias(f"{prefix}{c}") for c in compared],
        *[written(c).alias(f"{prefix}raw_{c}") for c in typed_columns],
        *[unreadable(c).alias(f"{prefix}bad_{c}") for c in typed_columns],
    )


def check_fidelity(sides: Sides, spec: MappingSpec) -> pl.DataFrame:
    """One finding per differing column of every row matched on the match_key."""
    keys = spec.match_key
    compared = [c for c in spec.target_columns() if c not in keys]
    entries = spec.entries_by_target()
    typed_columns = [c for c in compared if typed(entries[c])]
    matched = _side(sides.source, keys, compared, typed_columns, "s_").join(
        _side(sides.target, keys, compared, typed_columns, "t_"), on=keys
    ).collect()

    results = [empty_findings()]
    for name in compared:
        s, t = pl.col(f"s_{name}"), pl.col(f"t_{name}")
        readable = (
            ~pl.col(f"s_bad_{name}") & ~pl.col(f"t_bad_{name}")
            if name in typed_columns else pl.lit(True)
        )
        tolerance = entries[name].tolerance
        if tolerance is None:
            differs = ~s.eq_missing(t)
            rule: pl.Expr = pl.lit("value differs")
        else:
            gap = (s - t).abs()
            within = (s.is_null() & t.is_null()) | (gap <= pl.lit(tolerance))
            differs = ~within.fill_null(False)
            rule = pl.concat_str([
                pl.lit(f"tolerance {tolerance} exceeded (diff "), gap.cast(pl.String), pl.lit(")")
            ])
        lost = s.is_not_null() & t.is_null()
        results.append(
            findings(
                matched.filter(differs & readable), entity=spec.entity, family="fidelity",
                keys=keys, column=name,
                verdict=pl.when(lost).then(pl.lit("FAIL")).otherwise(pl.lit("REVIEW")),
                source_value=text(matched, f"s_{name}"),
                target_value=text(matched, f"t_{name}"),
                rule=pl.when(lost).then(pl.lit("value lost in target")).otherwise(rule),
            )
        )
        if typed(entries[name]):
            for prefix, side_name in (("s_", "source"), ("t_", "target")):
                results.append(
                    findings(
                        matched.filter(pl.col(f"{prefix}bad_{name}")),
                        entity=spec.entity, family="fidelity", keys=keys, verdict="FAIL",
                        column=name,
                        source_value=pl.col(f"s_raw_{name}"),
                        target_value=pl.col(f"t_raw_{name}"),
                        rule=f"{side_name} value is not a valid {entries[name].type}",
                    )
                )
    return pl.concat(results)

