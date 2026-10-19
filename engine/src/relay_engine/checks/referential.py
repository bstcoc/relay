"""Referential integrity: key duplicates on each side, orphan foreign keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from relay_engine.checks.findings import findings, text
from relay_engine.layers.silver import conform_column
from relay_engine.mapping import MappingSpec
from relay_engine.mapping.model import ColumnMapping
from relay_engine.matching import key_counts

_PARENT_KEY = "__parent_key__"

if TYPE_CHECKING:
    from relay_engine.sides import Sides


def _parent_keys(table: pl.DataFrame, entry: ColumnMapping, column: str,
                 pattern: str | None) -> pl.Series:
    """The keys of a parent table, read with the rules of the column pointing to it.

    The parent table belongs to another mapping: its own rules are not applied.
    Compared as text, since two tables may type the same key differently.
    """
    key = pl.col(column)
    if entry.transform != "split":
        key, _ = conform_column(table, entry, column, pattern)
    return table.select(key.cast(pl.String)).to_series().unique()


def _not_in(frame: pl.DataFrame, value: pl.Expr, parent: pl.Series) -> pl.DataFrame:
    """Rows of `frame` whose non-NULL `value`, as text, is not among `parent`."""
    return frame.filter(value.is_not_null()).join(
        parent.alias(_PARENT_KEY).to_frame(), left_on=value.cast(pl.String),
        right_on=_PARENT_KEY, how="anti", maintain_order="left",
    )


def check_referential(
    sides: Sides,
    spec: MappingSpec,
    referenced: dict[str, pl.DataFrame],
    source_referenced: dict[str, tuple[pl.DataFrame, str]] | None = None,
) -> pl.DataFrame:
    """Key duplicates on each side and orphan references.

    A key duplicated in the source is REVIEW: the migration is not at fault, but
    someone must decide which row holds (beyond `max_duplicate_share`
    the run stopped earlier). A key the target holds more often than the source
    is FAIL: the migration added copies. A NULL foreign key references nothing,
    so it is not an orphan.

    An orphan is FAIL, unless it was inherited: the source row held the
    same value, and that value was missing from the source parent too. Telling
    them apart takes the source parent: `source_referenced` gives, per referenced
    target table, its source table and the source column of its key, when the
    parent's mapping is part of the run.
    """
    keys = spec.match_key
    target = sides.target

    in_source = key_counts(sides.source, keys)
    in_target = key_counts(target, keys).join(
        in_source.rename({"len": "source_len"}), on=keys, how="left", nulls_equal=True
    ).with_columns(pl.col("source_len").fill_null(0))
    added = in_target.filter(pl.col("len") > pl.max_horizontal(pl.col("source_len"), 1))
    source_copies = pl.when(pl.col("source_len") > 1).then(
        pl.concat_str([pl.lit(", ×"), pl.col("source_len").cast(pl.String), pl.lit(" in source")])
    ).otherwise(pl.lit(""))
    results = [
        findings(
            in_source.filter(pl.col("len") > 1), entity=spec.entity, family="referential",
            keys=keys, verdict="REVIEW", column=", ".join(keys),
            rule=pl.concat_str([
                pl.lit("match_key duplicated in source (×"), pl.col("len").cast(pl.String),
                pl.lit(")"),
            ]),
        ),
        findings(
            added, entity=spec.entity, family="referential", keys=keys, verdict="FAIL",
            column=", ".join(keys),
            rule=pl.concat_str([
                pl.lit("match_key duplicated in target (×"), pl.col("len").cast(pl.String),
                source_copies, pl.lit(")"),
            ]),
        ),
    ]

    entries = spec.entries_by_target()
    for ref in spec.references:
        entry = entries[ref.column]
        parent = _parent_keys(referenced[ref.table], entry, ref.key, entry.target_format)
        value = pl.col(ref.column)
        orphans = _not_in(target, value, parent)
        rule = f"references {ref.table}.{ref.key}: value not found"
        inherited = orphans.clear()
        if source_referenced and ref.table in source_referenced and ref.column in sides.source:
            parent_source, parent_column = source_referenced[ref.table]
            source_parent = _parent_keys(parent_source, entry, parent_column, entry.source_format)
            already = _not_in(sides.source, value, source_parent).select(
                *keys, value.cast(pl.String).alias(_PARENT_KEY)
            )
            inherited, orphans = (
                orphans.join(
                    already.unique(), left_on=[*keys, value.cast(pl.String)],
                    right_on=[*keys, _PARENT_KEY], how=how, nulls_equal=True,
                )
                for how in ("semi", "anti")
            )
        for rows, verdict, why in (
            (orphans, "FAIL", rule),
            (inherited, "REVIEW", f"{rule} in source either (inherited)"),
        ):
            results.append(
                findings(
                    rows, entity=spec.entity, family="referential", keys=keys,
                    verdict=verdict, column=ref.column,
                    target_value=text(rows, ref.column), rule=why,
                )
            )

    return pl.concat(results)
