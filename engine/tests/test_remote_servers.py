"""Remote databases on servers: an SSH tunnel and a PostgreSQL with SSL, in local containers.

RELAY_TEST_SSH is the SSH server (ssh://user:password@host:port), RELAY_TEST_SSH_POSTGRESQL
the database as the SSH server sees it, RELAY_TEST_SSL_POSTGRESQL the same database reached
directly, with SSL on, and RELAY_TEST_SSL_CA the certificate it presents (issued to localhost).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import polars as pl
import pytest
import sqlalchemy as sa

from relay_engine.generator.generate import generate
from relay_engine.io import LocalParquetStore
from relay_engine.io.catalog import parse_sources, tunnels
from relay_engine.io.database import sql_engine
from relay_engine.io.readers import CatalogSource
from relay_engine.mapping import load_mappings
from relay_engine.migrate import migrate, plan_migration
from relay_engine.service import Service, handle

EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"


def _env(name: str) -> str:
    if name not in os.environ:
        pytest.skip(f"{name} is not set")
    return os.environ[name]


def _ssh(**changes: object) -> dict:
    server = urlsplit(_env("RELAY_TEST_SSH"))
    return {"host": server.hostname, "port": server.port or 22, "user": server.username,
            "secret": server.password} | changes


def _call(method: str, **params: object) -> dict:
    request = json.dumps({"id": method, "method": method, "params": params})
    return handle(Service(Path("unused")), request)


def test_the_app_reaches_a_database_through_an_ssh_tunnel() -> None:
    database = _env("RELAY_TEST_SSH_POSTGRESQL")
    with sql_engine(_env("RELAY_TEST_SSL_POSTGRESQL")).begin() as connection:
        connection.execute(sa.text("CREATE TABLE IF NOT EXISTS behind_ssh (id VARCHAR(5))"))
    connection_entry = {"database": database, "ssh": _ssh()}
    assert "behind_ssh" in _call("connect", connection=connection_entry)["result"]["tables"]
    tables = _call("schema", connection=connection_entry)["result"]["tables"]
    assert "behind_ssh" in {t["name"] for t in tables}


def test_a_migration_writes_and_proves_through_an_ssh_tunnel(tmp_path: Path) -> None:
    database = _env("RELAY_TEST_SSH_POSTGRESQL")
    ssh = _ssh()
    with sql_engine(_env("RELAY_TEST_SSL_POSTGRESQL")).begin() as connection:
        connection.execute(sa.text("DROP TABLE IF EXISTS factures"))
        connection.execute(sa.text("DROP TABLE IF EXISTS chantiers"))
    data = tmp_path / "data"
    generate(data, seed=42, rows=30)
    catalog = parse_sources(
        {f"{e}_legacy": {"parquet": str(data / f"{e}_legacy.parquet")}
         for e in ("chantiers", "factures")}
        | {f"{e}_target": {"database": database, "table": e, "ssh": ssh}
           for e in ("chantiers", "factures")},
        tmp_path,
    )
    plan = plan_migration(load_mappings(EXAMPLES), catalog)
    assert urlsplit(plan.database).hostname == urlsplit(database).hostname
    migrate(load_mappings(EXAMPLES), catalog, LocalParquetStore(tmp_path / "run"), "run")
    found = pl.read_parquet(tmp_path / "run" / "gold" / "recon_finding" / "*.parquet")
    lost = found.filter(pl.col("check_family").is_in(["completeness", "fidelity"]))
    assert lost.is_empty(), lost
    with tunnels(catalog) as reached:
        written = CatalogSource(reached).read("chantiers_target")
    assert written.height == pl.read_parquet(data / "chantiers_legacy.parquet").height


def test_a_wrong_ssh_password_is_named_without_being_shown() -> None:
    entry = {"database": _env("RELAY_TEST_SSH_POSTGRESQL"), "ssh": _ssh(secret="n0t-th1s")}
    message = _call("connect", connection=entry)["error"]["message"]
    assert "authentication failed" in message
    assert "n0t-th1s" not in message


def test_an_unknown_ssh_server_is_refused_with_its_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = {"database": _env("RELAY_TEST_SSH_POSTGRESQL"), "ssh": _ssh()}
    monkeypatch.setenv("HOME", str(tmp_path))
    message = _call("connect", connection=entry)["error"]["message"]
    assert "does not know its host key" in message
    assert "SHA256:" in message


def test_a_database_the_ssh_server_cannot_reach_is_named() -> None:
    entry = {"database": "postgresql://postgres:relay@127.0.0.1:1/postgres", "ssh": _ssh()}
    message = _call("connect", connection=entry)["error"]["message"]
    assert "cannot reach 127.0.0.1:1" in message


def test_ssl_require_and_verify_ca_reach_the_server() -> None:
    url = _env("RELAY_TEST_SSL_POSTGRESQL")
    ca = _env("RELAY_TEST_SSL_CA")
    with sql_engine(url).begin() as connection:
        connection.execute(sa.text("CREATE TABLE IF NOT EXISTS over_ssl (id VARCHAR(5))"))
        connection.execute(sa.text("DELETE FROM over_ssl"))
        connection.execute(sa.text("INSERT INTO over_ssl VALUES ('00412')"))
    for query in ("sslmode=require", f"sslmode=verify-ca&sslrootcert={ca}"):
        entry = {"database": f"{url}?{query}", "table": "over_ssl"}
        frame = CatalogSource(parse_sources({"t": entry}, Path("."))).read("t")
        assert frame.get_column("id").to_list() == ["00412"]


def test_a_certificate_for_another_host_fails_verify_full_clearly() -> None:
    url = urlsplit(_env("RELAY_TEST_SSL_POSTGRESQL"))
    ip = url._replace(netloc=url.netloc.replace("localhost", "127.0.0.1")).geturl()
    entry = {"database": f"{ip}?sslmode=verify-full&sslrootcert={_env('RELAY_TEST_SSL_CA')}"}
    message = _call("connect", connection=entry)["error"]["message"]
    assert "SSL failed" in message
    assert ":relay@" not in message


def test_a_server_without_ssl_is_said_to_refuse_it() -> None:
    plain = os.environ.get("RELAY_TEST_POSTGRESQL")
    if plain is None:
        pytest.skip("RELAY_TEST_POSTGRESQL is not set")
    message = _call("connect", connection={"database": f"{plain}?sslmode=require"})
    assert "does not accept SSL" in message["error"]["message"]
