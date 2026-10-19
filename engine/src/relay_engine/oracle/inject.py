"""Inject known defects into a migrated SQLite target, driven by the mapping only.

The injector never uses Relay's code to decide an alteration: it reads the
declaration (key, columns, types, normalizations) and alters values in ways
the declared normalizations keep visible. One defect per row, never on a key
column, never on a row whose key is NULL or duplicated. The baseline run
decides what to avoid: whole rows with a row-level finding, single cells
with a value-level one. What the schema forbids (NOT NULL, UNIQUE) is skipped
and reported: a constrained database could not hold that defect.
"""

from __future__ import annotations

import random
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import count
from pathlib import Path

from relay_engine.generator.model import Anomaly, AnomalyType, ExpectedVerdict, Manifest
from relay_engine.mapping import MappingSpec
from relay_engine.mapping.model import ColumnMapping

_SKIP = object()
_STRING_TYPES: tuple[str | None, ...] = (None, "string")
_DATE_TYPES: tuple[str | None, ...] = ("date", "datetime")
_TRUNCATION_SAFE = {"trim", "lower", "empty_as_null"}


@dataclass
class Injection:
    manifest: Manifest
    skipped: list[str]


class _Blocked(Exception):
    """The database schema refuses the defect (NOT NULL, UNIQUE, PRIMARY KEY)."""


def _truncate(value: object) -> object:
    """Drop the last alphanumeric character, keeping at least one (survives trim, lower)."""
    if not isinstance(value, str) or sum(c.isalnum() for c in value) < 2:
        return _SKIP
    last = max(i for i, c in enumerate(value) if c.isalnum())
    return value[:last] + value[last + 1:]


def _lose(value: object) -> object:
    """NULL a non-empty value (an empty one would equal NULL under empty_as_null)."""
    return None if isinstance(value, str) and value.strip() else _SKIP


def _shift(value: object) -> object:
    """Move an ISO date one day later, keeping any time part."""
    if not isinstance(value, str):
        return _SKIP
    try:
        return (date.fromisoformat(value[:10]) + timedelta(days=1)).isoformat() + value[10:]
    except (ValueError, OverflowError):
        return _SKIP


def _truncatable(entry: ColumnMapping) -> bool:
    return entry.type in _STRING_TYPES and set(entry.normalize) <= _TRUNCATION_SAFE


def _string(entry: ColumnMapping) -> bool:
    return entry.type in _STRING_TYPES


def _dated(entry: ColumnMapping) -> bool:
    return entry.type in _DATE_TYPES


_VALUE_KINDS: dict[
    AnomalyType,
    tuple[Callable[[ColumnMapping], bool], Callable[[object], object], ExpectedVerdict],
] = {
    AnomalyType.VALUE_TRUNCATED: (_truncatable, _truncate, ExpectedVerdict.REVIEW),
    AnomalyType.VALUE_LOST: (_string, _lose, ExpectedVerdict.FAIL),
    AnomalyType.DATE_SHIFTED: (_dated, _shift, ExpectedVerdict.REVIEW),
}
_ROW_KINDS = (
    AnomalyType.ROW_DROPPED, AnomalyType.ROW_EXTRA, AnomalyType.NATURAL_KEY_DUPLICATED,
)


def _q(name: str) -> str:
    """Quote an SQL identifier: real ERP columns carry spaces and accents."""
    return '"' + name.replace('"', '""') + '"'


def _render(row: sqlite3.Row | dict[str, object], keys: list[str]) -> str:
    """The key as Relay writes match_key_value: `a=1, b=2`."""
    return ", ".join(f"{k}={row[k]}" for k in keys)


def _plain_entries(spec: MappingSpec) -> list[ColumnMapping]:
    """Plain 1→1 entries, key columns excluded."""
    return [
        entry for entry in spec.columns
        if isinstance(entry.target, str)
        and not (entry.exclude or entry.target_only)
        and entry.transform is None
        and entry.target not in spec.match_key
    ]


@dataclass
class _Target:
    """What every injection needs to know about the table being altered."""

    conn: sqlite3.Connection
    table: str
    spec: MappingSpec
    not_null: set[str]
    taken: set[str]

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        try:
            self.conn.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise _Blocked from error


def _inject_value(
    target: _Target, kind: AnomalyType, pool: list[sqlite3.Row],
    avoid_cells: set[tuple[str, str]], rng: random.Random,
) -> Anomaly | None:
    eligible, alter, verdict = _VALUE_KINDS[kind]
    keys = target.spec.match_key
    columns = [
        str(entry.target) for entry in _plain_entries(target.spec)
        if eligible(entry) and not (alter is _lose and entry.target in target.not_null)
    ]
    candidates = (
        (i, [
            (c, v) for c in columns
            if (_render(pool[i], keys), c) not in avoid_cells
            and (v := alter(pool[i][c])) is not _SKIP
        ])
        for i in range(len(pool))
    )
    found = next(((i, options) for i, options in candidates if options), None)
    if found is None:
        return None
    index, options = found
    row = pool.pop(index)
    column, value = rng.choice(options)
    target.execute(
        f"UPDATE {_q(target.table)} SET {_q(column)} = ? WHERE rowid = ?",
        (value, row["_rowid"]),
    )
    return Anomaly(
        target.spec.entity, _render(row, keys), kind, verdict, column,
        f"{row[column]!r} -> {value!r}",
    )


def _invented(target: _Target, values: dict[str, object]) -> object:
    """A value for the last key column that no row uses yet, of the column's own kind."""
    keys = target.spec.match_key
    last, current = keys[-1], values[keys[-1]]
    declared = next(
        (e.type for e in target.spec.columns if e.target == last and not e.exclude), None
    )
    candidates: Iterator[object]
    if isinstance(current, int) and not isinstance(current, bool):
        top = target.conn.execute(
            f"SELECT MAX({_q(last)}) FROM {_q(target.table)} "
            f"WHERE typeof({_q(last)}) = 'integer'"
        ).fetchone()[0]
        candidates = (top + n for n in count(1))
    elif isinstance(current, str) and declared in _STRING_TYPES:
        candidates = (f"{current}-ORACLE-{n}" for n in count(1))
    else:
        return _SKIP
    for candidate in candidates:
        rendered = _render({**values, last: candidate}, keys)
        if rendered not in target.taken:
            target.taken.add(rendered)
            return candidate
    return _SKIP


def _inject_row(target: _Target, kind: AnomalyType, pool: list[sqlite3.Row]) -> Anomaly | None:
    if not pool:
        return None
    row, keys, table = pool.pop(), target.spec.match_key, _q(target.table)
    if kind is AnomalyType.ROW_DROPPED:
        target.execute(f"DELETE FROM {table} WHERE rowid = ?", (row["_rowid"],))
        return Anomaly(
            target.spec.entity, _render(row, keys), kind, ExpectedVerdict.FAIL, None,
            "row deleted",
        )
    values: dict[str, object] = dict(row)
    del values["_rowid"]
    detail = "row duplicated"
    if kind is AnomalyType.ROW_EXTRA:
        invented = _invented(target, values)
        if invented is _SKIP:
            pool.append(row)
            return None
        values[keys[-1]] = invented
        detail = "copy under an invented key"
    columns = ", ".join(_q(c) for c in values)
    placeholders = ", ".join("?" for _ in values)
    target.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values())
    )
    return Anomaly(
        target.spec.entity, _render(values, keys), kind, ExpectedVerdict.FAIL, None, detail
    )


def inject(
    db: Path,
    spec: MappingSpec,
    table: str,
    *,
    seed: int,
    per_type: int,
    avoid: set[str],
    avoid_cells: set[tuple[str, str]] | None = None,
) -> Injection:
    """Alter `db` in place: `per_type` defects of each kind, recorded in the manifest.

    `avoid` holds keys never touched; `avoid_cells` holds (key, column) pairs
    whose value must not be altered, while the rest of the row stays eligible.
    """
    rng = random.Random(seed)
    keys = spec.match_key
    cells = avoid_cells or set()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"SELECT rowid AS _rowid, * FROM {_q(table)}").fetchall()
        rendered = {
            r["_rowid"]: _render(r, keys) for r in rows if all(r[k] is not None for k in keys)
        }
        counts = Counter(rendered.values())
        pool = [
            r for r in rows
            if r["_rowid"] in rendered
            and counts[rendered[r["_rowid"]]] == 1
            and rendered[r["_rowid"]] not in avoid
        ]
        rng.shuffle(pool)
        not_null = {
            info["name"] for info in conn.execute(f"PRAGMA table_info({_q(table)})")
            if info["notnull"]
        }
        target = _Target(conn, table, spec, not_null, set(rendered.values()))

        anomalies: list[Anomaly] = []
        skipped: list[str] = []
        for kind in (*_VALUE_KINDS, *_ROW_KINDS):
            for done in range(per_type):
                try:
                    if kind in _VALUE_KINDS:
                        anomaly = _inject_value(target, kind, pool, cells, rng)
                    else:
                        anomaly = _inject_row(target, kind, pool)
                except _Blocked:
                    skipped.append(
                        f"{kind.value}: {done} of {per_type} injected, "
                        "blocked by a schema constraint"
                    )
                    break
                if anomaly is None:
                    skipped.append(
                        f"{kind.value}: {done} of {per_type} injected, "
                        "no eligible row or column left"
                    )
                    break
                anomalies.append(anomaly)
        conn.commit()
    finally:
        conn.close()
    manifest = Manifest(seed=seed, entities=[spec.entity], anomalies=anomalies)
    return Injection(manifest, skipped)
