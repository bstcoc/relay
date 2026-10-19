"""Business rules: declared invariants, in SQL.

`check` must hold on every target row; SQL semantics apply, so a NULL result
passes. `aggregate` must give the same total on both sides, per `group_by`
group, within `tolerance`. A `cross` rule joins the target to another target
table and holds `check` on every joined row; with `totals`, the target is first
aggregated per join key. The verdict is declared by the rule.

Expressions are read by Polars' SQL: simple predicates and
aggregates (`montant > 0`, `sum(montant)`) are written as in any SQL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from relay_engine.checks.findings import empty_findings, findings, text
from relay_engine.mapping import MappingError, MappingSpec
from relay_engine.mapping.model import BusinessRule

if TYPE_CHECKING:
    from relay_engine.sides import Sides


def _check(target: pl.DataFrame, spec: MappingSpec, rule: BusinessRule) -> pl.DataFrame:
    assert rule.check is not None
    violating = target.filter(~pl.sql_expr(rule.check).fill_null(True))
    return findings(
        violating, entity=spec.entity, family="business_rule", keys=spec.match_key,
        verdict=rule.verdict, rule=f"{rule.name}: {rule.check}",
    )


def _aggregate(
    silver: pl.DataFrame, target: pl.DataFrame, spec: MappingSpec, rule: BusinessRule
) -> pl.DataFrame:
    assert rule.aggregate is not None
    group = pl.sql_expr(rule.group_by) if rule.group_by else pl.lit("all")

    def totals(frame: pl.DataFrame, alias: str) -> pl.DataFrame:
        assert rule.aggregate is not None
        grouped = frame.with_columns(group.alias("group"))
        return grouped.group_by(text(grouped, "group").alias("group")).agg(
            pl.sql_expr(rule.aggregate).alias(alias)
        )

    both = totals(silver, "s").join(totals(target, "t"), on="group", how="full", coalesce=True)
    s, t = pl.col("s"), pl.col("t")
    if rule.tolerance is None:
        same = s.eq_missing(t)
        rule_text = f"{rule.name}: {rule.aggregate} differs"
    else:
        same = ((s - t).abs() <= pl.lit(rule.tolerance)).fill_null(False)
        rule_text = f"{rule.name}: {rule.aggregate} differs beyond tolerance {rule.tolerance}"
    return findings(
        both.filter(~same), entity=spec.entity, family="business_rule", keys=["group"],
        verdict=rule.verdict, source_value=s.cast(pl.String), target_value=t.cast(pl.String),
        rule=rule_text,
    )


def _cross(
    target: pl.DataFrame, spec: MappingSpec, rule: BusinessRule, other: pl.DataFrame
) -> pl.DataFrame:
    assert rule.cross is not None and rule.check is not None
    local, remote = list(rule.cross.on), list(rule.cross.on.values())
    mine = target.with_columns(pl.col(local).cast(pl.String))
    keys = spec.match_key
    if rule.cross.totals:
        mine = mine.group_by(local).agg(
            pl.sql_expr(expr).alias(name) for name, expr in rule.cross.totals.items()
        )
        keys = local
    theirs = other.with_columns(pl.col(remote).cast(pl.String))
    joined = mine.join(theirs, left_on=local, right_on=remote, suffix="_right")
    violating = joined.filter(~pl.sql_expr(rule.check).fill_null(True))
    return findings(
        violating, entity=spec.entity, family="business_rule", keys=keys,
        verdict=rule.verdict, rule=f"{rule.name}: {rule.check} (across {rule.cross.table})",
    )


def check_business_rules(
    sides: Sides, spec: MappingSpec, referenced: dict[str, pl.DataFrame] | None = None
) -> pl.DataFrame:
    """One finding per violating row (check) or diverging group (aggregate).

    Both forms read the prepared sides: the target as normalized and typed by the
    mapping, the source conformed with its duplicates (a store keyed in twice
    counts twice in a source total: a true finding on the source). A cross rule
    reads the other table from `referenced`, as written in the target.
    """
    results = [empty_findings()]
    for rule in spec.business_rules:
        try:
            if rule.cross is not None:
                other = (referenced or {})[rule.cross.table]
                results.append(_cross(sides.target, spec, rule, other))
            elif rule.check is not None:
                results.append(_check(sides.target, spec, rule))
            else:
                results.append(_aggregate(sides.source, sides.target, spec, rule))
        except pl.exceptions.PolarsError as error:
            raise MappingError([f"business rule '{rule.name}': {sql_problem(error)}"]) from error
    return pl.concat(results)


def sql_problem(error: Exception) -> str:
    """The first line of a Polars error, with a hint: CSV columns are read as text."""
    first = str(error).strip().splitlines()[0]
    return f"{first} (columns read from CSV are text: cast them, e.g. CAST(m AS DECIMAL(12,2)))"
