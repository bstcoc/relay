"""The sources catalog (`sources.yaml`): where each table is read from.

Kept apart from the mapping: the mapping describes a correspondence,
the catalog describes storage. Secrets never appear in the file: `${VAR}` is
read from the environment. Paths are relative to the catalog file.
"""

from __future__ import annotations

import importlib.util
import os
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

DATABASE_SCHEMES = ("postgresql", "postgres", "mysql", "mssql", "sqlite")
SSL_MODES = ("disable", "require", "verify-ca", "verify-full")
_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_KINDS = ("parquet", "csv", "database")
_CREDENTIALS = re.compile(r"(\w[\w+.-]*://[^\s:/@]*:)[^\s@]+@")


def without_credentials(text: str) -> str:
    """`postgresql://user:secret@db` becomes `postgresql://user:***@db`."""
    return _CREDENTIALS.sub(r"\1***@", text)


_REASONS = [
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in [
        (r"could not translate host name|nodename nor servname|name or service not known"
         r"|getaddrinfo failed|unknown mysql server host|name resolution",
         "host not found: check the host name"),
        (r"connection refused|errno 61\b|errno 111\b",
         "connection refused: nothing listens on this host and port; "
         "check the port and that the server is running"),
        (r"no pg_hba\.conf entry|is not allowed to connect|allow_?list|network restriction",
         "this computer's IP address is not allowed by the server: "
         "add it to the database firewall or allow list"),
        (r"does not support (ssl|tls)|ssl is not enabled",
         "the server does not accept SSL: choose the disable SSL mode"),
        (r"password authentication failed|access denied for user|login failed"
         r"|authentication failed",
         "authentication failed: check the user and the password"),
        (r"certificate|\bssl|\btls",
         "SSL failed: check the SSL mode and the CA certificate file"),
        (r"timeout|timed out",
         "no answer in time: the host may be wrong, or a firewall drops the connection"),
    ]
]


def explained(message: str) -> str:
    """A driver's first line without credentials, after its likely cause when one is known."""
    lines = message.strip().splitlines()
    detail = without_credentials(lines[0]) if lines else ""
    for pattern, reason in _REASONS:
        if pattern.search(message):
            return f"{reason} ({detail})" if detail else reason
    return detail


def describe(error: BaseException) -> str:
    """The database's own first line, never the SQL parameters (row values) nor a password."""
    cause = getattr(error, "orig", None) or error
    return explained(str(cause)) or type(cause).__name__


class SourcesError(Exception):
    """The catalog is invalid. Carries every problem found."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("Invalid sources catalog:\n" + "\n".join(f"  - {p}" for p in problems))


@dataclass(frozen=True)
class ParquetSource:
    parquet: Path


@dataclass(frozen=True)
class CsvSource:
    csv: Path
    delimiter: str = ","
    encoding: str = "utf-8"
    header: bool = True


@dataclass(frozen=True)
class SshTunnel:
    """An SSH server that reaches the database; `secret` is its password or the key's passphrase."""

    host: str
    user: str
    port: int = 22
    key: str = ""
    secret: str = field(default="", repr=False)


@dataclass(frozen=True)
class DatabaseSource:
    database: str
    table: str
    ssh: SshTunnel | None = None


SourceConfig = ParquetSource | CsvSource | DatabaseSource


class _Problem(Exception):
    pass


def _resolve_env(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in os.environ:
            raise _Problem(f"environment variable {name} is not set")
        return os.environ[name]

    return _ENV.sub(replace, value)


def _existing(base: Path, raw: str) -> Path:
    path = (base / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
    if not path.exists():
        raise _Problem(f"file {raw} does not exist")
    if path.is_dir():
        raise _Problem(f"{raw} is a folder; give the path of the file itself")
    return path


def sqlite_file(url: str) -> tuple[Path, str]:
    """The file and query of `sqlite:///relative.db`, `sqlite:////abs.db` or `sqlite:///C:/x.db`."""
    parts = urlsplit(url)
    path = parts.path.removeprefix("/")
    return Path(path), parts.query


def _database(base: Path, url: str) -> str:
    scheme = urlsplit(url).scheme
    if scheme not in DATABASE_SCHEMES:
        raise _Problem(
            f"unsupported database URL '{scheme or url}' ({', '.join(DATABASE_SCHEMES)})"
        )
    if scheme == "sqlite":
        path, query = sqlite_file(url)
        resolved = _existing(base, str(path))
        return f"sqlite:///{resolved}" + (f"?{query}" if query else "")
    mode = dict(parse_qsl(urlsplit(url).query)).get("sslmode")
    if mode is not None and mode not in SSL_MODES:
        raise _Problem(f"unknown sslmode '{mode}' ({', '.join(SSL_MODES)})")
    return url


def _ssh(raw: object) -> SshTunnel | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _Problem("ssh needs a host, a user, and optionally a port, a key and a secret")
    text = {str(k): _resolve_env(str(v)) for k, v in raw.items()}
    missing = [k for k in ("host", "user") if not text.get(k)]
    if missing:
        raise _Problem(f"ssh needs a {' and a '.join(missing)}")
    port = text.get("port", "22")
    if not port.isdigit():
        raise _Problem(f"ssh port '{port}' is not a number")
    return SshTunnel(
        host=text["host"], user=text["user"], port=int(port),
        key=os.path.expanduser(text.get("key", "")), secret=text.get("secret", ""),
    )


def _parse(base: Path, entry: dict[str, object]) -> SourceConfig:
    kinds = [k for k in _KINDS if k in entry]
    if len(kinds) != 1:
        raise _Problem("declare exactly one of parquet, csv or database")
    text = {
        k: _resolve_env(str(v)) for k, v in entry.items() if not isinstance(v, bool | dict)
    }
    if kinds[0] == "parquet":
        return ParquetSource(parquet=_existing(base, text["parquet"]))
    if kinds[0] == "csv":
        return CsvSource(
            csv=_existing(base, text["csv"]),
            delimiter=text.get("delimiter", ","),
            encoding=text.get("encoding", "utf-8"),
            header=bool(entry.get("header", True)),
        )
    if "table" not in text:
        raise _Problem("database source needs a table")
    return DatabaseSource(
        database=_database(base, text["database"]), table=text["table"],
        ssh=_ssh(entry.get("ssh")),
    )


def parse_sources(raw: dict, base: Path) -> dict[str, SourceConfig]:
    """Parse catalog entries, paths relative to `base`; raise SourcesError with every problem."""
    sources: dict[str, SourceConfig] = {}
    problems: list[str] = []
    for name, entry in raw.items():
        try:
            sources[name] = _parse(base.resolve(), entry or {})
        except _Problem as problem:
            problems.append(f"{name}: {problem}")
    if problems:
        raise SourcesError(problems)
    return sources


def load_sources(path: Path) -> dict[str, SourceConfig]:
    """Parse a `sources.yaml` file."""
    path = Path(path)
    return parse_sources(yaml.safe_load(path.read_text()) or {}, path.parent)


_DEFAULT_PORTS = {"postgresql": 5432, "postgres": 5432, "mysql": 3306, "mssql": 1433}


def through_tunnel(url: str, local_port: int) -> str:
    """The URL reaching a tunnel's local end; PostgreSQL keeps the host its certificate names."""
    parts = urlsplit(url)
    credentials = parts.netloc.rpartition("@")[0]
    login = f"{credentials}@" if credentials else ""
    if parts.scheme not in ("postgresql", "postgres"):
        return urlunsplit(parts._replace(netloc=f"{login}127.0.0.1:{local_port}"))
    host = parts.hostname or ""
    named = f"[{host}]" if ":" in host else host
    query = urlencode(dict(parse_qsl(parts.query)) | {"hostaddr": "127.0.0.1"})
    return urlunsplit(parts._replace(netloc=f"{login}{named}:{local_port}", query=query))


@contextmanager
def tunnels(catalog: dict[str, SourceConfig]) -> Iterator[dict[str, SourceConfig]]:
    """The catalog with each database behind SSH reached through its tunnel, open in the block."""
    behind = {
        name: config for name, config in catalog.items()
        if isinstance(config, DatabaseSource) and config.ssh is not None
    }
    if not behind:
        yield catalog
        return
    if importlib.util.find_spec("paramiko") is None:
        raise SourcesError([
            "an SSH tunnel needs the databases extra: uv tool install 'relay-engine[databases]'"
        ])
    from relay_engine.io.tunnel import forwarded

    with ExitStack() as stack:
        ports: dict[tuple[SshTunnel, str, int], int] = {}
        reached: dict[str, SourceConfig] = {}
        for name, config in behind.items():
            parts = urlsplit(config.database)
            if parts.hostname is None or parts.scheme not in _DEFAULT_PORTS:
                raise SourcesError([f"{name}: an SSH tunnel leads to a database server"])
            assert config.ssh is not None
            target = (config.ssh, parts.hostname, parts.port or _DEFAULT_PORTS[parts.scheme])
            if target not in ports:
                ports[target] = stack.enter_context(forwarded(*target))
            reached[name] = replace(
                config, database=through_tunnel(config.database, ports[target]), ssh=None
            )
        yield catalog | reached
