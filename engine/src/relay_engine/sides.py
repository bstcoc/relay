"""Both sides of a reconciliation, prepared once for every check.

The source is conformed through the mapping; the target receives the same
normalization and typing. Checks never see a raw frame: a key normalized on one
side only would read as a lost row and an extra row at once.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from relay_engine.checks.business_rules import sql_problem
from relay_engine.layers.silver import RAW, conform, conform_column, typed
from relay_engine.mapping import MappingError, MappingSpec
from relay_engine.matching import check_match_key


@dataclass(frozen=True)
class Sides:
    """Source and target in the target schema; typed columns also as written, under RAW + name."""

    source: pl.DataFrame
    target: pl.DataFrame
    expected_missing: pl.DataFrame

    @property
    def silver(self) -> pl.DataFrame:
        """The conformed source, without the values as written."""
        return self.source.select(pl.exclude(f"^{RAW}.*$"))


def _conformed_target(target: pl.DataFrame, spec: MappingSpec) -> pl.DataFrame:
    columns: list[pl.Expr] = []
    for name, entry in spec.entries_by_target().items():
        if entry.transform == "split" or entry.target_only:
            columns.append(pl.col(name))
            continue
        column, raw = conform_column(target, entry, name, entry.target_format)
        columns.append(column.alias(name))
        if typed(entry):
            columns.append(raw.alias(RAW + name))
    return target.select(*columns)


def expected_missing(legacy: pl.DataFrame, spec: MappingSpec) -> pl.DataFrame:
    keys = spec.match_key
    scope = spec.source_scope
    if scope is None or not scope.expected_missing:
        return conform(legacy.clear(), spec).select(keys)
    try:
        deliberate = legacy.filter(pl.sql_expr(scope.expected_missing))
    except pl.exceptions.PolarsError as error:
        raise MappingError([f"source_scope.expected_missing: {sql_problem(error)}"]) from error
    return conform(deliberate, spec).select(keys).unique()


def prepare(spec: MappingSpec, legacy: pl.DataFrame, target: pl.DataFrame) -> Sides:
    """Conform both sides through the mapping.

    Raise AmbiguousKeyError when the match_key is too often duplicated in the source
    to be the right key, and MappingError when source_scope cannot be evaluated.
    """
    source = conform(legacy, spec, with_raw=True)
    check_match_key(source, spec.match_key, spec.max_duplicate_share)
    return Sides(source, _conformed_target(target, spec), expected_missing(legacy, spec))
