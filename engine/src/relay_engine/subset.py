"""A subset of the source: the rows of some tables, and the rows of every table below them.

Each filtered table keeps the rows that pass its own filter. A table that
references a kept table keeps only the rows pointing to kept rows, down every
foreign key, and still passes its own filter if it has one. Tables above stay
whole, so every foreign key of a kept row still finds its parent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from relay_engine.checks.business_rules import sql_problem
from relay_engine.io import TableSource
from relay_engine.mapping import MappingError


@dataclass(frozen=True)
class Reference:
    columns: list[str]
    table: str
    to: list[str]


@dataclass(frozen=True)
class Filter:
    table: str
    where: str | None = None
    limit: int | None = None


@dataclass(frozen=True)
class Subset:
    filters: list[Filter]
    references: dict[str, list[Reference]] = field(default_factory=dict)


class SubsetSource:
    """A TableSource that reads only the rows of the subset."""

    def __init__(self, source: TableSource, subset: Subset) -> None:
        self._source = source
        self._filters = {f.table: f for f in subset.filters}
        self._references = subset.references
        self._kept: dict[str, pl.DataFrame] = {}
        self._reading: set[str] = set()

    def _below(self, table: str, seen: frozenset[str] = frozenset()) -> bool:
        if table in self._filters:
            return True
        return any(
            self._below(ref.table, seen | {table})
            for ref in self._references.get(table, [])
            if ref.table not in seen and ref.table != table
        )

    def _own(self, frame: pl.DataFrame, rule: Filter) -> pl.DataFrame:
        if rule.where:
            try:
                frame = frame.filter(pl.sql_expr(rule.where))
            except pl.exceptions.PolarsError as error:
                raise MappingError([f"subset of {rule.table}: {sql_problem(error)}"]) from error
        return frame.head(rule.limit) if rule.limit is not None else frame

    def read(self, table: str) -> pl.DataFrame:
        if table in self._kept:
            return self._kept[table]
        if not self._below(table):
            return self._source.read(table)
        self._reading.add(table)
        frame = self._source.read(table)
        for ref in self._references.get(table, []):
            if ref.table == table or ref.table in self._reading or not self._below(ref.table):
                continue
            names = dict(zip(ref.to, ref.columns, strict=True))
            parents = self.read(ref.table).select(ref.to).rename(names)
            frame = frame.join(parents, on=ref.columns, how="semi", nulls_equal=False)
        self._reading.discard(table)
        if table in self._filters:
            frame = self._own(frame, self._filters[table])
        self._kept[table] = frame
        return frame
