"""Completeness: does every source row land in the target, and nothing else?"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from relay_engine.checks.findings import findings
from relay_engine.mapping import MappingSpec

if TYPE_CHECKING:
    from relay_engine.sides import Sides


def _keys(frame: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    return frame.select(keys).unique()


def check_completeness(sides: Sides, spec: MappingSpec) -> pl.DataFrame:
    """Lost source rows and extra target rows, both FAIL.

    Source rows matching `source_scope.expected_missing` (an SQL predicate on
    source columns) are deliberately not migrated: their absence is not a loss.
    """
    keys = spec.match_key
    source_keys = _keys(sides.source, keys)
    target_keys = _keys(sides.target, keys)

    lost = source_keys.join(target_keys, on=keys, how="anti").join(
        sides.expected_missing, on=keys, how="anti"
    )
    extra = target_keys.join(source_keys, on=keys, how="anti")

    lost_rows = findings(
        lost, entity=spec.entity, family="completeness", keys=keys, verdict="FAIL",
        rule="source row missing from target",
    )
    extra_rows = findings(
        extra, entity=spec.entity, family="completeness", keys=keys, verdict="FAIL",
        rule="target row has no source",
    )
    return pl.concat([lost_rows, extra_rows])
