"""A migration: source tables, conformed by their mappings, written to a target database.

Then reconciled, so the run that wrote the target also proves it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl

from relay_engine.io import TableSink, TableSource
from relay_engine.io.catalog import (
    DatabaseSource,
    SourceConfig,
    SourcesError,
    tunnels,
    without_credentials,
)
from relay_engine.io.readers import CatalogSource
from relay_engine.layers.silver import conform, spec_dtype
from relay_engine.mapping import MappingError, MappingSpec, validate_mapping
from relay_engine.matching import check_match_key
from relay_engine.pipeline import MigrationSummary, order_by_references, run_migration, unexpected
from relay_engine.sides import expected_missing
from relay_engine.subset import Subset, SubsetSource

if TYPE_CHECKING:
    from relay_engine.io.database import DatabaseTarget


@dataclass(frozen=True)
class TablePlan:
    """What a migration writes to one target table."""

    entity: str
    table: str
    rows: int
    existing_rows: int
    columns: list[str]
    create: str | None = None


@dataclass(frozen=True)
class MigrationPlan:
    """The dry run: every table written, in order, and what stands in the way."""

    database: str
    tables: list[TablePlan]
    replace: bool

    @property
    def blocked(self) -> list[TablePlan]:
        """Target tables that already hold rows, when the migration does not replace them."""
        if self.replace:
            return []
        return [t for t in self.tables if t.existing_rows]


def _target(specs: list[MappingSpec], catalog: dict[str, SourceConfig]) -> DatabaseTarget:
    from relay_engine.io.database import DatabaseTarget

    return DatabaseTarget(_target_url(specs, catalog))


def _target_url(specs: list[MappingSpec], catalog: dict[str, SourceConfig]) -> str:
    urls: set[str] = set()
    for spec in specs:
        config = catalog.get(spec.target.table)
        if not isinstance(config, DatabaseSource):
            raise SourcesError([f"{spec.target.table}: a migration target must be a database"])
        urls.add(config.database)
    if len(urls) != 1:
        raise SourcesError(["every target table of a migration must be in the same database"])
    return urls.pop()


def _primary_key(rows: pl.DataFrame, key: list[str]) -> list[str]:
    """The match key, when it identifies every row: otherwise no primary key at all."""
    keyed = rows.select(key)
    if keyed.null_count().sum_horizontal().item() or keyed.is_duplicated().any():
        return []
    return key


def _foreign_keys(
    spec: MappingSpec, target: DatabaseTarget, table_of: Callable[[str], str]
) -> list[tuple[str, str, str]]:
    """References to the primary key of a known target table become foreign keys."""
    return [
        (r.column, table_of(r.table), r.key)
        for r in spec.references
        if target.exists(table_of(r.table)) and target.key(table_of(r.table)) == [r.key]
    ]


def _source(catalog: dict[str, SourceConfig], subset: Subset | None) -> TableSource:
    source = CatalogSource(catalog)
    return SubsetSource(source, subset) if subset else source


class _Read:
    """A source that hands out the tables already read once, then forgets them."""

    def __init__(self, frames: dict[str, pl.DataFrame], source: TableSource) -> None:
        self._frames = frames
        self._source = source

    def read(self, table: str) -> pl.DataFrame:
        frame = self._frames.pop(table, None)
        return self._source.read(table) if frame is None else frame


def _prepare(
    specs: list[MappingSpec], catalog: dict[str, SourceConfig], replace: bool,
    source: TableSource,
) -> tuple[DatabaseTarget, MigrationPlan, list[tuple[str, pl.DataFrame]], dict[str, pl.DataFrame]]:
    target = _target(specs, catalog)

    def table_of(name: str) -> str:
        config = catalog[name]
        assert isinstance(config, DatabaseSource)
        return config.table

    plans: list[TablePlan] = []
    writes: list[tuple[str, pl.DataFrame]] = []
    read: dict[str, pl.DataFrame] = {}
    for spec in order_by_references(specs):
        table = table_of(spec.target.table)
        exists = target.exists(table)

        try:
            if spec.source.table not in read:
                read[spec.source.table] = source.read(spec.source.table)
            legacy = read[spec.source.table]
            columns = target.columns(table) if exists else list(spec.entries_by_target())
            referenced = {t: target.columns(table_of(t)) for t in spec.referenced_tables()}
            validate_mapping(spec, legacy.columns, columns, referenced)
            silver = conform(legacy, spec)
            check_match_key(silver, spec.match_key, spec.max_duplicate_share)
            rows = silver.join(
                expected_missing(legacy, spec), on=spec.match_key, how="anti", nulls_equal=True
            )
            create = None
            if not exists:
                rows = rows.with_columns(
                    pl.lit(None, spec_dtype(e.type) if e.type else pl.String()).alias(name)
                    for name, e in spec.entries_by_target().items()
                    if e.target_only
                )
                create = target.define(table, rows, _primary_key(rows, spec.match_key),
                                       _foreign_keys(spec, target, table_of))
        except MappingError as error:
            if len(specs) == 1:
                raise
            raise MappingError([f"{spec.entity}: {p}" for p in error.problems]) from error
        except pl.exceptions.PolarsError as error:
            raise unexpected(spec.entity) from error
        plans.append(TablePlan(spec.entity, table, rows.height,
                               0 if create else target.count(table), rows.columns, create))
        writes.append((table, rows))
    plan = MigrationPlan(without_credentials(target.url), plans, replace)
    return target, plan, writes, read


def plan_migration(
    specs: list[MappingSpec], catalog: dict[str, SourceConfig], *, replace: bool = False,
    subset: Subset | None = None,
) -> MigrationPlan:
    """The dry run: read, conform and check everything, write nothing."""
    with tunnels(catalog) as reached:
        plan = _prepare(specs, reached, replace, _source(reached, subset))[1]
    return dataclasses.replace(plan, database=without_credentials(_target_url(specs, catalog)))


def migrate(
    specs: list[MappingSpec],
    catalog: dict[str, SourceConfig],
    sink: TableSink,
    run_id: str,
    decisions: pl.DataFrame | None = None,
    *,
    replace: bool = False,
    subset: Subset | None = None,
) -> MigrationSummary:
    """Write every source table to the target in one transaction, then reconcile it.

    A target table that already holds rows stops the migration, unless `replace`
    empties it first, within the same transaction.
    """
    with tunnels(catalog) as reached:
        source = _source(reached, subset)
        target, plan, writes, read = _prepare(specs, reached, replace, source)
        if plan.blocked:
            raise SourcesError([
                f"{t.table}: already holds {t.existing_rows} row(s); "
                "replace them or empty the table"
                for t in plan.blocked
            ])
        target.write(writes, replace=replace)
        del writes
        return run_migration(specs, _Read(read, source), sink, run_id, decisions)
