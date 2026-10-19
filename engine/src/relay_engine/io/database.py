"""Writing to a target database, in one transaction."""

from __future__ import annotations

import os
import ssl
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import polars as pl
import sqlalchemy as sa
from sqlalchemy import exc
from sqlalchemy.schema import CreateTable

from relay_engine.io.catalog import SourcesError, describe, sqlite_file

_DRIVERS = {
    "postgresql": "postgresql+psycopg",
    "postgres": "postgresql+psycopg",
    "mysql": "mysql+pymysql",
    "mssql": "mssql+pymssql",
}
_POSTGRES = ("postgresql", "postgres")
_VERIFY = ("verify-ca", "verify-full")
_BATCH = 10_000
CONNECT_TIMEOUT = 10


def _mysql_ssl(mode: str | None, ca: str) -> dict[str, object]:
    if mode is None:
        return {}
    if mode == "disable":
        return {"ssl_disabled": True}
    context = ssl.create_default_context(cafile=ca or None)
    context.check_hostname = mode == "verify-full"
    if mode == "require":
        context.verify_mode = ssl.CERT_NONE
    return {"ssl": context}


def driver_options(url: str) -> tuple[str, dict[str, object]]:
    """The URL its driver receives and the connect arguments, with the SSL mode mapped."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    mode = query.pop("sslmode", None)
    ca = os.path.expanduser(query.pop("sslrootcert", ""))
    if ca and not Path(ca).is_file():
        raise SourcesError([f"the CA certificate file {ca} does not exist"])
    args: dict[str, object] = {}
    if parts.scheme in _POSTGRES:
        if mode == "verify-ca" and not ca:
            raise SourcesError([
                "SSL mode verify-ca needs the server's CA certificate file; "
                "verify-full trusts the certificates of the system"
            ])
        query |= {"sslmode": mode} if mode else {}
        query |= {"sslrootcert": ca or "system"} if mode in _VERIFY else {}
        args["connect_timeout"] = CONNECT_TIMEOUT
    elif parts.scheme == "mysql":
        args["connect_timeout"] = CONNECT_TIMEOUT
        args |= _mysql_ssl(mode, ca)
    else:
        if mode in _VERIFY:
            raise SourcesError([
                "SQL Server: certificate verification is not available yet; "
                "choose the require SSL mode"
            ])
        args["login_timeout"] = CONNECT_TIMEOUT
        if mode:
            args["encryption"] = "off" if mode == "disable" else "require"
    return urlunsplit(parts._replace(query=urlencode(query))), args


def connectorx_url(url: str) -> str | None:
    """The URL ConnectorX reads, or None when only the SQLAlchemy driver honors its SSL mode."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    mode = query.get("sslmode")
    if parts.scheme in _POSTGRES:
        return None if mode in _VERIFY else url
    if mode not in (None, "disable"):
        return None
    query.pop("sslmode", None)
    return urlunsplit(parts._replace(query=urlencode(query)))


def _type_name(type_: object) -> str:
    try:
        return str(type_)
    except exc.CompileError:
        return type(type_).__name__


def sql_engine(url: str) -> sa.Engine:
    scheme = url.partition("://")[0]
    if scheme == "sqlite":
        path, _ = sqlite_file(url)
        return sa.create_engine(f"sqlite:///{path.resolve()}", poolclass=sa.NullPool)
    if scheme not in _DRIVERS:
        raise SourcesError([f"cannot write to a {scheme} database"])
    driven, args = driver_options(url)
    return sa.create_engine(
        f"{_DRIVERS[scheme]}://{driven.partition('://')[2]}",
        poolclass=sa.NullPool, connect_args=args,
    )


def _split(table: str) -> tuple[str | None, str]:
    schema, _, name = table.rpartition(".")
    return (schema or None), name


def column_type(values: pl.Series) -> sa.types.TypeEngine:
    """The portable SQL type of a column; each database's dialect renders its own."""
    dtype = values.dtype
    if isinstance(dtype, pl.Decimal):
        return sa.Numeric(dtype.precision or 38, dtype.scale)
    if dtype == pl.Boolean:
        return sa.Boolean()
    if dtype.is_integer():
        return sa.BigInteger()
    if dtype.is_float():
        return sa.Float()
    if dtype == pl.Date:
        return sa.Date()
    if isinstance(dtype, pl.Datetime):
        return sa.DateTime()
    lengths = pl.first().cast(pl.String).str.len_chars().max().fill_null(0)
    longest: int = values.to_frame().select(lengths).item()
    if longest > 4000:
        return sa.UnicodeText()
    return sa.Unicode(max(64, 1 << max(longest - 1, 0).bit_length()))


class DatabaseTarget:
    """One target database: what its tables hold, and a transactional write."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._engine = sql_engine(url)
        self._metadata = sa.MetaData()
        self._tables: dict[str, sa.Table] = {}
        self._created: list[sa.Table] = []

    def _table(self, connection: sa.Connection, table: str) -> sa.Table:
        if table not in self._tables:
            schema, name = _split(table)
            try:
                self._tables[table] = sa.Table(
                    name, self._metadata, schema=schema, autoload_with=connection
                )
            except exc.NoSuchTableError as error:
                raise SourcesError([f"{table}: no such table in the target database"]) from error
        return self._tables[table]

    def exists(self, table: str) -> bool:
        if table in self._tables:
            return True
        schema, name = _split(table)
        with self._connect() as connection:
            return sa.inspect(connection).has_table(name, schema=schema)

    def key(self, table: str) -> list[str]:
        """The primary key columns of a table, created here or found in the database."""
        with self._connect() as connection:
            return [c.name for c in self._table(connection, table).primary_key.columns]

    def define(
        self,
        table: str,
        frame: pl.DataFrame,
        key: list[str],
        references: list[tuple[str, str, str]],
    ) -> str:
        """Plan a table to create from `frame`; return its CREATE TABLE for this database.

        `key` becomes the primary key; each (column, table, key) reference a foreign key.
        """
        schema, name = _split(table)
        pointing = {column: f"{self._tables[t].fullname}.{k}" for column, t, k in references}
        columns = [
            sa.Column(
                column,
                column_type(frame.get_column(column)),
                *([sa.ForeignKey(pointing[column])] if column in pointing else []),
                primary_key=column in key,
                nullable=column not in key,
            )
            for column in frame.columns
        ]
        defined = sa.Table(name, self._metadata, *columns, schema=schema)
        self._tables[table] = defined
        self._created.append(defined)
        return str(CreateTable(defined).compile(self._engine)).strip()

    @contextmanager
    def _connect(self) -> Iterator[sa.Connection]:
        try:
            with self._engine.connect() as connection:
                yield connection
        except exc.SQLAlchemyError as error:
            raise SourcesError([f"database: {describe(error)}"]) from error

    def tables(self) -> list[str]:
        """Every table of the database's default schema, by name."""
        with self._connect() as connection:
            return sorted(sa.inspect(connection).get_table_names())

    def schema(self) -> list[dict]:
        """Every table with its columns, row count, primary key and foreign keys."""
        with self._connect() as connection:
            inspector = sa.inspect(connection)
            return [
                {
                    "name": name,
                    "rows": int(connection.execute(
                        sa.select(sa.func.count()).select_from(sa.table(name))
                    ).scalar_one()),
                    "key": inspector.get_pk_constraint(name).get("constrained_columns") or [],
                    "references": [
                        {"columns": fk["constrained_columns"], "table": fk["referred_table"],
                         "to": fk["referred_columns"]}
                        for fk in inspector.get_foreign_keys(name)
                    ],
                    "columns": [
                        {"name": c["name"], "type": _type_name(c["type"]),
                         "nullable": bool(c.get("nullable", True))}
                        for c in inspector.get_columns(name)
                    ],
                }
                for name in sorted(inspector.get_table_names())
            ]

    def columns(self, table: str) -> list[str]:
        with self._connect() as connection:
            return [c.name for c in self._table(connection, table).columns]

    def count(self, table: str) -> int:
        if any(t is self._tables.get(table) for t in self._created):
            return 0
        with self._connect() as connection:
            query = sa.select(sa.func.count()).select_from(self._table(connection, table))
            return int(connection.execute(query).scalar_one())

    def write(self, frames: Sequence[tuple[str, pl.DataFrame]], *, replace: bool) -> None:
        """Create the planned tables, then insert every frame, parents first.

        With `replace`, existing tables are emptied first. All or nothing: any
        failure rolls the whole write back, and drops the tables created here.
        """
        current = ""
        try:
            with self._engine.begin() as connection:
                tables = [(self._table(connection, t), frame) for t, frame in frames]
                for table in self._created:
                    current = table.fullname
                    table.create(connection)
                if replace:
                    for table, _ in reversed(tables):
                        current = table.fullname
                        connection.execute(table.delete())
                for table, frame in tables:
                    current = table.fullname
                    as_text = [
                        name for name, dtype in frame.schema.items()
                        if isinstance(dtype, pl.Decimal)
                        and not isinstance(table.columns[name].type, sa.Numeric)
                    ]
                    frame = frame.with_columns(pl.col(as_text).cast(pl.String))
                    for batch in frame.iter_slices(_BATCH):
                        connection.execute(table.insert(), batch.to_dicts())
        except exc.SQLAlchemyError as error:
            self._drop_created()
            where = f"writing {current}" if current else "target database"
            raise SourcesError([f"{where}: {describe(error)}; nothing was written"]) from error

    def _drop_created(self) -> None:
        """MySQL commits a CREATE TABLE at once: its tables outlive the rollback."""
        try:
            with self._engine.begin() as connection:
                for table in reversed(self._created):
                    table.drop(connection, checkfirst=True)
        except exc.SQLAlchemyError:
            return
