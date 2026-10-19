"""Shared test helpers: small Polars frames and the demo scenario of the oracle."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from relay_engine.layers.silver import spec_dtype
from relay_engine.mapping import MappingSpec
from relay_engine.sides import Sides, prepare


def frame(rows: list[tuple], schema: str | list[str]) -> pl.DataFrame:
    """A frame from rows; `schema` is `"id string, montant decimal(12,2)"` or column names."""
    if isinstance(schema, list):
        return pl.DataFrame(rows, schema=schema, orient="row")
    columns: dict[str, pl.DataType] = {}
    for part in _split(schema):
        name, declared = part.split(None, 1)
        declared = declared.strip()
        columns[name] = pl.Datetime("us") if declared == "timestamp" else spec_dtype(declared)
    return pl.DataFrame(rows, schema=columns, orient="row")


def _split(schema: str) -> list[str]:
    """Split on commas outside parentheses: `decimal(12,2)` stays whole."""
    parts, depth, current = [], 0, ""
    for char in schema:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    return [*parts, current.strip()]


def prepared(spec: MappingSpec, source: pl.DataFrame, target: pl.DataFrame) -> Sides:
    """Sides for a source written with its target column names (plain 1→1 entries)."""
    names = {
        e.target: e.source for e in spec.columns
        if isinstance(e.target, str) and isinstance(e.source, str) and e.target in source.columns
    }
    return prepare(spec, source.rename(names), target)


def records(result: pl.DataFrame) -> list[SimpleNamespace]:
    """Rows with attribute access (`r.column`), for readable assertions."""
    return [SimpleNamespace(**row) for row in result.iter_rows(named=True)]


DEMO_ROWS = [
    ("C001", "  Alpha ", "Lyon", "2024-03-12"),
    ("C002", "Bravo", "Paris", "2023-11-02"),
    ("C003", "Charlie  ", "Nantes", "2022-06-30"),
    ("C004", "Delta", "Lille", "2024-01-15"),
    ("C005", "Echo", "Rennes", "2021-09-09"),
    ("C006", " Foxtrot", "Brest", "2020-02-29"),
    ("C007", "Golf", "Dijon", "2024-07-01"),
    ("C008", "Hotel", "Metz", "2019-12-31"),
    ("C009", "India", "Nice", "2023-05-20"),
    ("C010", "Juliett", "Caen", "2022-10-10"),
]

DEMO_MAPPING = """\
version: 1
entity: shops
source:
  table: shops_legacy
target:
  table: shops_target
match_key: [id]
columns:
  - source: id
    target: id
    type: string
  - source: name
    target: name
    type: string
    normalize: [trim]
  - source: city
    target: city
    type: string
  - source: opened
    target: opened
    type: date
    normalize: date_only
"""

DEMO_SOURCES = """\
shops_legacy:
  csv: legacy.csv
  delimiter: ";"
shops_target:
  database: sqlite:///${RELAY_ORACLE_TARGET}
  table: shop
"""

DEMO_MIGRATE = """\
import csv
import sqlite3
import sys

with open("legacy.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f, delimiter=";"))
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE shop (id TEXT, name TEXT, city TEXT, opened TEXT)")
conn.executemany(
    "INSERT INTO shop VALUES (?, ?, ?, ?)",
    [(r["id"], r["name"].strip(), r["city"], r["opened"]) for r in rows],
)
conn.commit()
conn.close()
"""


@pytest.fixture
def demo_scenario(tmp_path: Path) -> Callable[..., Path]:
    """Build a small scenario folder (10 shops) in tmp_path; no dataset is committed."""

    def build(
        *, migrate: str = DEMO_MIGRATE, mapping: str = DEMO_MAPPING, intents: str | None = None
    ) -> Path:
        root = tmp_path / "scenario"
        root.mkdir()
        lines = ["id;name;city;opened", *(";".join(row) for row in DEMO_ROWS)]
        (root / "legacy.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (root / "mapping.yaml").write_text(mapping)
        (root / "sources.yaml").write_text(DEMO_SOURCES)
        (root / "migrate.py").write_text(migrate)
        if intents is not None:
            (root / "intents.yaml").write_text(intents)
        return root

    return build
