"""Reading the tables of a sources catalog: Parquet and CSV files, and databases.

The catalog (relay_engine.io.catalog) says where each table lives; this module reads it.
"""

from __future__ import annotations

import codecs
import csv
import importlib.util
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import polars as pl

from relay_engine.io.catalog import (
    CsvSource,
    DatabaseSource,
    ParquetSource,
    SourceConfig,
    SourcesError,
    describe,
    sqlite_file,
)


class CsvShapeError(Exception):
    """A CSV whose records do not all have the header's fields: the data is at fault."""


_SHOWN_LINES = 5


def _blank_records(
    path: Path, source: CsvSource, limit: int | None = None, encoding: str = "utf-8-sig"
) -> tuple[list[int], int]:
    """Indexes of the blank records and the number of records, after checking every
    record has the header's fields.

    A line break inside an unquoted value splits a record into two half-empty
    rows, which would otherwise reconcile as data. Python's csv reader
    follows quotes like Polars does, so its records match Polars rows one to one.
    """
    expected: int | None = None
    blank: list[int] = []
    wrong: list[tuple[int, int]] = []
    with path.open(encoding=encoding, newline="") as lines:
        reader = csv.reader(lines, delimiter=source.delimiter)
        index = 0
        while True:
            start = reader.line_num + 1
            record = next(reader, None)
            if record is None or (limit is not None and index - len(blank) == limit):
                break
            if expected is None:
                expected = len(record)
                if source.header:
                    continue
            if not record:
                blank.append(index)
            elif len(record) != expected:
                wrong.append((start, len(record)))
            index += 1
    if wrong:
        shown = ", ".join(f"line {n} ({count} fields)" for n, count in wrong[:_SHOWN_LINES])
        hidden = len(wrong) - _SHOWN_LINES
        more = f" and {hidden} more" if hidden > 0 else ""
        raise CsvShapeError(
            f"{source.csv.name}: {len(wrong)} line(s) do not have the {expected} fields of "
            f"the header: {shown}{more}. A line break or a delimiter inside an unquoted "
            "value splits or widens a record: quote the value, or repair the export."
        )
    return blank, index


def _parse_csv(path: Path, source: CsvSource, limit: int | None = None) -> pl.DataFrame:
    blank, _ = _blank_records(path, source, limit)
    frame = pl.read_csv(
        path,
        separator=source.delimiter,
        has_header=source.header,
        infer_schema=False,
        n_rows=None if limit is None else limit + len(blank),
    )
    if not blank:
        return frame
    return frame.with_row_index("__row").filter(
        ~pl.col("__row").is_in(blank)
    ).drop("__row")


def _codec(source: CsvSource) -> str:
    try:
        return codecs.lookup(source.encoding).name
    except LookupError as error:
        raise SourcesError([f"{source.csv.name}: unknown encoding {source.encoding}"]) from error


def _undecodable(source: CsvSource, codec: str) -> SourcesError:
    if codec == "utf-8":
        return SourcesError([
            f"{source.csv.name} is not utf-8: declare its encoding, e.g. `encoding: cp1252`"
        ])
    return SourcesError([
        f"{source.csv.name} is not {source.encoding}: check the `encoding:` it declares"
    ])


def _csv_rows(source: CsvSource) -> int:
    """The records of a CSV file, counted without building a table."""
    codec = _codec(source)
    try:
        blank, records = _blank_records(
            source.csv, source, encoding="utf-8-sig" if codec == "utf-8" else codec
        )
    except UnicodeDecodeError as error:
        raise _undecodable(source, codec) from error
    return records - len(blank)


def _read_csv(source: CsvSource, limit: int | None = None) -> pl.DataFrame:
    codec = _codec(source)
    if codec == "utf-8":
        not_utf8 = _undecodable(source, codec)
        try:
            return _parse_csv(source.csv, source, limit)
        except UnicodeDecodeError as error:
            raise not_utf8 from error
        except pl.exceptions.ComputeError as error:
            if "utf-8" not in str(error).lower() and "utf8" not in str(error).lower():
                raise
            raise not_utf8 from error
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".csv") as utf8:
        try:
            with source.csv.open(encoding=codec, newline="") as original:
                while chunk := original.read(1 << 20):
                    utf8.write(chunk)
        except UnicodeDecodeError as error:
            raise _undecodable(source, codec) from error
        utf8.flush()
        return _parse_csv(Path(utf8.name), source, limit)


_PLAIN_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?")


def _quote(table: str, scheme: str) -> str:
    """A plain name is left as written, so the database folds its case as usual."""
    if _PLAIN_NAME.fullmatch(table):
        return table
    if scheme == "mysql":
        return ".".join("`" + part.replace("`", "``") + "`" for part in table.split("."))
    return ".".join('"' + part.replace('"', '""') + '"' for part in table.split("."))


def _header(source: CsvSource) -> pl.Schema:
    """The columns of a CSV file, from its first line only."""
    codec = _codec(source)
    try:
        with source.csv.open(encoding="utf-8-sig" if codec == "utf-8" else codec,
                             newline="") as text:
            first = text.readline()
    except UnicodeDecodeError as error:
        raise _undecodable(source, codec) from error
    frame = pl.read_csv(
        first.encode("utf-8"), separator=source.delimiter, has_header=source.header,
        infer_schema=False, n_rows=0,
    )
    return frame.schema


def _read_database(name: str, source: DatabaseSource, limit: int | None = None) -> pl.DataFrame:
    scheme = urlsplit(source.database).scheme
    table = _quote(source.table, scheme)
    if limit is None:
        query = f"SELECT * FROM {table}"
    elif scheme == "mssql":
        query = f"SELECT TOP {int(limit)} * FROM {table}"
    else:
        query = f"SELECT * FROM {table} LIMIT {int(limit)}"
    if scheme == "sqlite":
        path, options = sqlite_file(source.database)
        params = dict(parse_qsl(options))
        params.setdefault("mode", "ro")
        uri = f"{path.resolve().as_uri()}?{urlencode(params)}"
        try:
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                return pl.read_database(query, connection, infer_schema_length=None)
        except sqlite3.Error as error:
            raise SourcesError([f"{name}: cannot read table {source.table}: {error}"]) from error
    if importlib.util.find_spec("connectorx") is None:
        raise SourcesError([
            f"{name}: reading {scheme} needs the databases extra: "
            "uv tool install 'relay-engine[databases]'"
        ])
    from relay_engine.io.database import connectorx_url, sql_engine

    fast = connectorx_url(source.database)
    try:
        if fast is not None:
            return pl.read_database_uri(query, fast)
        with closing(sql_engine(source.database).raw_connection()) as connection:
            driver = connection.driver_connection
            assert driver is not None
            return pl.read_database(query, driver, infer_schema_length=None)
    except SourcesError:
        raise
    except Exception as error:
        raise SourcesError([
            f"{name}: cannot read table {source.table}: {describe(error)}"
        ]) from error


class CatalogSource:
    """A TableSource that reads each table from where the catalog says it lives."""

    def __init__(self, sources: dict[str, SourceConfig]) -> None:
        self._sources = sources

    def read(self, table: str) -> pl.DataFrame:
        return self.head(table, None)

    def head(self, table: str, rows: int | None) -> pl.DataFrame:
        """A table's first `rows` rows, or all of them."""
        if table not in self._sources:
            raise SourcesError([f"{table}: not declared in the sources catalog"])
        source = self._sources[table]
        if isinstance(source, ParquetSource):
            if rows is None:
                return pl.read_parquet(source.parquet)
            return pl.scan_parquet(source.parquet).head(rows).collect()
        if isinstance(source, CsvSource):
            return _read_csv(source, rows)
        return _read_database(table, source, rows)

    def rows(self, table: str) -> int:
        """A file's number of rows, counted without reading the file into a table."""
        source = self._sources[table]
        if isinstance(source, ParquetSource):
            return pl.scan_parquet(source.parquet).select(pl.len()).collect().item()
        if isinstance(source, CsvSource):
            return _csv_rows(source)
        return self.read(table).height

    def schema(self, table: str, sample: int = 1000) -> pl.Schema:
        """A table's columns and types without reading it whole.

        A Parquet file gives its schema, a CSV file its header line (every column is
        text), and a database the types of its first `sample` rows.
        """
        if table not in self._sources:
            raise SourcesError([f"{table}: not declared in the sources catalog"])
        source = self._sources[table]
        if isinstance(source, ParquetSource):
            return pl.Schema(pl.read_parquet_schema(source.parquet))
        if isinstance(source, CsvSource):
            return _header(source)
        return _read_database(table, source, sample).schema
