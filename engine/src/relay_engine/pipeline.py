"""One reconciliation run: validate, land bronze, conform silver, check, write gold.

A run covers a migration: one or several entities under one run_id.
"""

from __future__ import annotations

import hashlib
import secrets
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from relay_engine import __version__
from relay_engine.checks.business_rules import check_business_rules
from relay_engine.checks.completeness import check_completeness
from relay_engine.checks.fidelity import check_fidelity
from relay_engine.checks.findings import key_value
from relay_engine.checks.referential import check_referential
from relay_engine.decisions import apply_decisions, effective_counts
from relay_engine.io import TableSink, TableSource
from relay_engine.layers.bronze import land
from relay_engine.mapping import MappingError, MappingSpec, validate_mapping
from relay_engine.sides import Sides, prepare

_RUN_SCHEMA = {
    "run_id": pl.String,
    "entity": pl.String,
    "started_at": pl.Datetime("us"),
    "finished_at": pl.Datetime("us"),
    "engine_version": pl.String,
    "mapping_version": pl.String,
    "total_rows_source": pl.Int64,
    "total_rows_target": pl.Int64,
    "pass": pl.Int64,
    "review": pl.Int64,
    "fail": pl.Int64,
    "accepted": pl.Int64,
    "verdict": pl.String,
}


_VERDICTS = ("PASS", "REVIEW", "FAIL")


@dataclass(frozen=True)
class RunSummary:
    """One entity of a run: its line of recon_run."""

    run_id: str
    entity: str
    verdict: str
    passed: int
    review: int
    fail: int
    accepted: int


@dataclass(frozen=True)
class MigrationSummary:
    """A run over one or several entities; its verdict is the worst of theirs."""

    run_id: str
    entities: list[RunSummary]

    @property
    def verdict(self) -> str:
        return max((e.verdict for e in self.entities), key=_VERDICTS.index)


@dataclass(frozen=True)
class _Reconciled:
    """What an entity writes besides its bronze tables."""

    silver: pl.DataFrame
    found: pl.DataFrame
    summary: pl.DataFrame
    result: RunSummary


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S") + "_" + secrets.token_hex(2)


def unexpected(entity: str) -> MappingError:
    """A Polars failure in plain words: the table it stopped on, never its values."""
    return MappingError([
        f"{entity}: an unexpected error stopped the processing of this table; "
        "the details are in the engine log"
    ])


def _passing_rows(sides: Sides, keys: list[str], found: pl.DataFrame) -> int:
    """Rows present on both sides that no check flagged."""
    matched = sides.source.select(keys).unique().join(sides.target.select(keys).unique(), on=keys)
    flagged = found.get_column("match_key_value").unique()
    return matched.filter(~key_value(matched, keys).is_in(flagged.implode())).height


def order_by_references(specs: list[MappingSpec]) -> list[MappingSpec]:
    """Parents before children along `references`, ties by entity name.

    A self-reference or a cycle does not block: what is left is taken by name.
    """
    by_target = {s.target.table: s.entity for s in specs}
    parents = {
        s.entity: {by_target[r.table] for r in s.references if r.table in by_target} - {s.entity}
        for s in specs
    }
    ordered: list[str] = []
    while len(ordered) < len(specs):
        left = sorted(e for e in parents if e not in ordered)
        ready = [e for e in left if parents[e] <= set(ordered)]
        ordered.append((ready or left)[0])
    position = {e: i for i, e in enumerate(ordered)}
    return sorted(specs, key=lambda s: position[s.entity])


def _parent_sources(
    spec: MappingSpec, by_target: dict[str, MappingSpec]
) -> dict[str, tuple[str, str]]:
    """Per referenced target table whose mapping is in the run: its source table, and
    the source column its key comes from (a plain 1→1 column only)."""
    parents: dict[str, tuple[str, str]] = {}
    for ref in spec.references:
        parent = by_target.get(ref.table)
        entry = parent.entries_by_target().get(ref.key) if parent else None
        if parent and entry and entry.transform is None and isinstance(entry.source, str):
            parents[ref.table] = (parent.source.table, entry.source)
    return parents


def _source_parents(
    spec: MappingSpec, by_target: dict[str, MappingSpec], read: Callable[[str], pl.DataFrame]
) -> dict[str, tuple[pl.DataFrame, str]]:
    return {
        table: (read(source), column)
        for table, (source, column) in _parent_sources(spec, by_target).items()
    }


def _tables(spec: MappingSpec, by_target: dict[str, MappingSpec]) -> set[str]:
    """Every table that reconciling an entity reads."""
    parents = {source for source, _ in _parent_sources(spec, by_target).values()}
    return {spec.source.table, spec.target.table, *spec.referenced_tables(), *parents}


def _reconcile(
    spec: MappingSpec,
    read: Callable[[str], pl.DataFrame],
    run_id: str,
    decisions: pl.DataFrame | None,
    by_target: dict[str, MappingSpec],
) -> _Reconciled:
    started_at = datetime.now(UTC)
    legacy = read(spec.source.table)
    target = read(spec.target.table)
    referenced = {table: read(table) for table in spec.referenced_tables()}
    validate_mapping(
        spec, legacy.columns, target.columns, {t: df.columns for t, df in referenced.items()}
    )

    sides = prepare(spec, legacy, target)
    found = pl.concat([
        check_completeness(sides, spec),
        check_referential(sides, spec, referenced, _source_parents(spec, by_target, read)),
        check_fidelity(sides, spec),
        check_business_rules(sides, spec, referenced),
    ])
    found = apply_decisions(found, decisions).with_columns(pl.lit(run_id).alias("run_id"))
    counts = effective_counts(found)
    fail, review, accepted = counts["fail"], counts["review"], counts["accepted"]
    verdict = "FAIL" if fail else "REVIEW" if review else "PASS"
    passed = _passing_rows(sides, spec.match_key, found)

    summary = pl.DataFrame(
        [(
            run_id, spec.entity, started_at.replace(tzinfo=None),
            datetime.now(UTC).replace(tzinfo=None), __version__,
            hashlib.sha256(spec.model_dump_json().encode()).hexdigest()[:12],
            legacy.height, target.height, passed, review, fail, accepted, verdict,
        )],
        schema=_RUN_SCHEMA,
        orient="row",
    )
    result = RunSummary(run_id, spec.entity, verdict, passed, review, fail, accepted)
    return _Reconciled(sides.silver, found, summary, result)


def run_migration(
    specs: list[MappingSpec],
    source: TableSource,
    sink: TableSink,
    run_id: str,
    decisions: pl.DataFrame | None = None,
) -> MigrationSummary:
    """Reconcile every entity, parents first, then write them all.

    Every check of every entity runs before the sink receives anything, so a
    stopped run leaves nothing behind. Meanwhile a table is released once no
    later entity reads it, its layers waiting in a staging folder. A problem on
    one entity stops the run and names it.
    """
    entities = [s.entity for s in specs]
    repeated = sorted({e for e in entities if entities.count(e) > 1})
    if repeated:
        raise MappingError([f"entity '{e}' is declared by more than one mapping" for e in repeated])

    by_target = {s.target.table: s for s in specs}
    ordered = order_by_references(specs)
    frames: dict[str, pl.DataFrame] = {}

    def read(table: str) -> pl.DataFrame:
        if table not in frames:
            frames[table] = source.read(table)
        return frames[table]

    found: list[pl.DataFrame] = []
    summaries: list[pl.DataFrame] = []
    results: list[RunSummary] = []
    pending: dict[str, pl.DataFrame | Path] = {}

    def layer(path: str, frame: pl.DataFrame | Path) -> pl.DataFrame:
        if isinstance(frame, Path):
            return pl.read_ipc(frame)
        bronze = path.removeprefix("bronze/")
        return land(frame, run_id, bronze) if bronze != path else frame

    with tempfile.TemporaryDirectory(prefix="relay-run-") as staging:
        for position, spec in enumerate(ordered):
            try:
                reconciled = _reconcile(spec, read, run_id, decisions, by_target)
            except MappingError as error:
                if len(specs) == 1:
                    raise
                raise MappingError([f"{spec.entity}: {p}" for p in error.problems]) from error
            except pl.exceptions.PolarsError as error:
                raise unexpected(spec.entity) from error
            for table in (spec.source.table, spec.target.table):
                pending.setdefault(f"bronze/{table}", frames[table])
            pending[f"silver/{spec.entity}"] = reconciled.silver
            found.append(reconciled.found)
            summaries.append(reconciled.summary)
            results.append(reconciled.result)
            del reconciled
            later = set().union(*(_tables(s, by_target) for s in ordered[position + 1:]))
            for table in frames.keys() - later:
                del frames[table]
            if position == len(ordered) - 1:
                break
            for path in pending:
                held = pending[path]
                if isinstance(held, pl.DataFrame) and path.removeprefix("bronze/") not in frames:
                    spilled = Path(staging) / f"{path.replace('/', '-')}.arrow"
                    layer(path, held).write_ipc(spilled)
                    pending[path] = spilled
            del held
        for path in list(pending):
            sink.write(layer(path, pending.pop(path)), path)
    sink.write(pl.concat(found), "gold/recon_finding")
    sink.write(pl.concat(summaries), "gold/recon_run")
    return MigrationSummary(run_id, results)


def run(
    spec: MappingSpec,
    source: TableSource,
    sink: TableSink,
    run_id: str,
    decisions: pl.DataFrame | None = None,
) -> RunSummary:
    """A run over a single entity."""
    return run_migration([spec], source, sink, run_id, decisions).entities[0]
