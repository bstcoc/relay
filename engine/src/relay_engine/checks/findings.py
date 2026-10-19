"""The recon_finding shape shared by every check (docs/results-model.md)."""

from __future__ import annotations

import hashlib

import polars as pl

FINDING_COLUMNS = [
    "entity", "check_family", "match_key_value", "column",
    "source_value", "target_value", "verdict", "rule", "finding_key",
]
FINDING_SCHEMA = pl.Schema({name: pl.String() for name in FINDING_COLUMNS})

_NULL = "\u0000"


def datetime_text(column: pl.Expr) -> pl.Expr:
    """`2024-01-01 10:00:00`, or `…10:00:00.5`: the fraction only when there is one."""
    return (
        column.dt.strftime("%Y-%m-%d %H:%M:%S%.6f")
        .str.replace(r"(\.\d*?)0+$", "$1")
        .str.replace(r"\.$", "")
    )


def text(frame: pl.DataFrame, name: str) -> pl.Expr:
    """A column of `frame` as text, the way the results contract has always shown it.

    Dates stay ISO, decimals keep their scale, datetimes print a fraction only when
    they have one. `finding_key` hashes this text, so it must not drift.
    """
    if isinstance(frame.schema[name], pl.Datetime):
        return datetime_text(pl.col(name))
    return pl.col(name).cast(pl.String)


def key_value(frame: pl.DataFrame, keys: list[str]) -> pl.Expr:
    """`id=k1` or `a=1, b=2` for composite keys; a NULL part is left out."""
    parts = [pl.concat_str([pl.lit(f"{k}="), text(frame, k)]) for k in keys]
    return pl.concat_str(parts, separator=", ", ignore_nulls=True)


def _sha256(values: pl.Series) -> pl.Series:
    return pl.Series(
        [hashlib.sha256(v.encode("utf-8")).hexdigest() for v in values.to_list()],
        dtype=pl.String,
    )


def findings(
    frame: pl.DataFrame,
    *,
    entity: str,
    family: str,
    keys: list[str],
    verdict: str | pl.Expr,
    rule: str | pl.Expr,
    column: str | None = None,
    source_value: pl.Expr | None = None,
    target_value: pl.Expr | None = None,
) -> pl.DataFrame:
    """Turn every row of `frame` into one finding.

    finding_key hashes the entity, key, column and both values: stable across
    runs, but a changed value yields a new key and so a fresh review.
    """
    none = pl.lit(None, pl.String)
    shaped = frame.select(
        pl.lit(entity).alias("entity"),
        pl.lit(family).alias("check_family"),
        key_value(frame, keys).alias("match_key_value"),
        (pl.lit(column) if column else none).alias("column"),
        (source_value if source_value is not None else none).cast(pl.String).alias("source_value"),
        (target_value if target_value is not None else none).cast(pl.String).alias("target_value"),
        (pl.lit(verdict) if isinstance(verdict, str) else verdict).alias("verdict"),
        (pl.lit(rule) if isinstance(rule, str) else rule).cast(pl.String).alias("rule"),
    )
    parts = [
        pl.col(c).fill_null(_NULL)
        for c in ("entity", "match_key_value", "column", "source_value", "target_value")
    ]
    return shaped.with_columns(
        pl.concat_str(parts, separator="|").map_batches(_sha256, return_dtype=pl.String)
        .alias("finding_key")
    ).select(FINDING_COLUMNS).cast(FINDING_SCHEMA)


def empty_findings() -> pl.DataFrame:
    return pl.DataFrame(schema=FINDING_SCHEMA)
