"""Remote databases, without a server: SSL mapping, tunnel URLs and clear errors."""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest

from relay_engine.io.catalog import (
    DatabaseSource,
    SourcesError,
    SshTunnel,
    explained,
    parse_sources,
    through_tunnel,
    tunnels,
)
from relay_engine.io.database import DatabaseTarget, connectorx_url, describe, driver_options

pytest.importorskip("psycopg")

PG = "postgresql://relay:s3cret@db.example.org:5432/erp"


def test_postgresql_keeps_its_ssl_mode_and_trusts_the_system_for_verify_full() -> None:
    url, args = driver_options(PG + "?sslmode=verify-full")
    assert url.endswith("?sslmode=verify-full&sslrootcert=system")
    assert args == {"connect_timeout": 10}
    assert driver_options(PG + "?sslmode=require")[0].endswith("?sslmode=require")
    with pytest.raises(SourcesError, match="verify-ca needs the server's CA certificate"):
        driver_options(PG + "?sslmode=verify-ca")


def test_a_ca_certificate_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(SourcesError, match="does not exist"):
        driver_options(PG + f"?sslmode=verify-ca&sslrootcert={tmp_path / 'ca.pem'}")


def test_mysql_receives_an_ssl_context_per_mode() -> None:
    mysql = "mysql://relay:s3cret@db:3306/erp"
    url, args = driver_options(mysql + "?sslmode=require")
    assert url == mysql
    context = args["ssl"]
    assert isinstance(context, ssl.SSLContext)
    assert (context.verify_mode, context.check_hostname) == (ssl.CERT_NONE, False)
    full = driver_options(mysql + "?sslmode=verify-full")[1]["ssl"]
    assert isinstance(full, ssl.SSLContext)
    assert (full.verify_mode, full.check_hostname) == (ssl.CERT_REQUIRED, True)
    assert driver_options(mysql + "?sslmode=disable")[1]["ssl_disabled"] is True
    assert "ssl" not in driver_options(mysql)[1]


def test_sql_server_encrypts_but_cannot_verify_yet() -> None:
    mssql = "mssql://sa:s3cret@db:1433/erp"
    assert driver_options(mssql + "?sslmode=require")[1]["encryption"] == "require"
    assert driver_options(mssql + "?sslmode=disable")[1]["encryption"] == "off"
    with pytest.raises(SourcesError, match="choose the require SSL mode"):
        driver_options(mssql + "?sslmode=verify-full")


def test_connectorx_reads_unless_a_certificate_must_be_verified() -> None:
    assert connectorx_url(PG + "?sslmode=require") == PG + "?sslmode=require"
    assert connectorx_url(PG + "?sslmode=verify-full") is None
    assert connectorx_url("mysql://u@db/erp?sslmode=disable") == "mysql://u@db/erp"
    assert connectorx_url("mysql://u@db/erp?sslmode=require") is None


def test_an_unknown_ssl_mode_is_a_catalog_problem() -> None:
    with pytest.raises(SourcesError, match="unknown sslmode 'always'"):
        parse_sources({"erp": {"database": PG + "?sslmode=always", "table": "t"}}, Path("."))


def test_an_ssh_tunnel_is_declared_with_the_database_and_never_shows_its_secret() -> None:
    entry = {"database": PG, "table": "t",
             "ssh": {"host": "bastion", "port": 2222, "user": "ops", "secret": "hunter2"}}
    config = parse_sources({"erp": entry}, Path("."))["erp"]
    assert isinstance(config, DatabaseSource)
    assert config.ssh == SshTunnel("bastion", "ops", 2222, "", "hunter2")
    assert "hunter2" not in repr(config)
    with pytest.raises(SourcesError, match="ssh needs a host"):
        parse_sources({"erp": entry | {"ssh": {"user": "ops"}}}, Path("."))


def test_a_tunnel_url_reaches_the_local_end() -> None:
    assert through_tunnel(PG + "?sslmode=verify-full", 40001) == (
        "postgresql://relay:s3cret@db.example.org:40001/erp?sslmode=verify-full&hostaddr=127.0.0.1"
    )
    assert through_tunnel("mysql://relay:s3cret@db:3306/erp", 40001) == (
        "mysql://relay:s3cret@127.0.0.1:40001/erp"
    )


def test_a_catalog_without_ssh_opens_no_tunnel() -> None:
    catalog = parse_sources({"erp": {"database": PG, "table": "t"}}, Path("."))
    with tunnels(catalog) as reached:
        assert reached is catalog


@pytest.mark.parametrize(("message", "reason"), [
    ('could not translate host name "db.example" to address', "host not found"),
    ("connection to server failed: Connection refused", "connection refused"),
    ("connection to server failed: timeout expired", "no answer in time"),
    ('no pg_hba.conf entry for host "1.2.3.4", user "relay"', "IP address is not allowed"),
    ("Host '1.2.3.4' is not allowed to connect to this MySQL server", "IP address is not allowed"),
    ("server does not support SSL, but SSL was required", "does not accept SSL"),
    ("SSL error: certificate verify failed", "SSL failed"),
    ('password authentication failed for user "relay"', "authentication failed"),
])
def test_a_driver_message_comes_with_its_likely_cause(message: str, reason: str) -> None:
    assert explained(message).split(" (")[0].count(reason) == 1
    assert explained("postgresql://relay:s3cret@db " + message).count("s3cret") == 0


def test_a_refused_connection_says_so_without_the_password() -> None:
    with pytest.raises(SourcesError) as failed:
        DatabaseTarget("postgresql://relay:s3cret@127.0.0.1:1/erp").tables()
    (problem,) = failed.value.problems
    assert "connection refused" in problem
    assert "s3cret" not in problem


def test_an_unknown_host_says_so() -> None:
    with pytest.raises(SourcesError, match="host not found"):
        DatabaseTarget("postgresql://relay:s3cret@relay-no-such-host.invalid:5432/erp").tables()


def test_describe_explains_a_wrapped_driver_error() -> None:
    assert describe(RuntimeError("Connection refused\n  at deep")).startswith(
        "connection refused: nothing listens"
    )
