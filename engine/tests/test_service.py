"""The app drives a whole migration through the local service, over stdin/stdout."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from relay_engine.generator.generate import generate
from relay_engine.service import Service, _json, handle


def _call(service: Service, method: str, **params: object) -> dict:
    return handle(service, json.dumps({"id": method, "method": method, "params": params}))


def _catalogs(tmp_path: Path) -> tuple[dict, dict]:
    data = tmp_path / "data"
    generate(data, seed=42, rows=30)
    legacy = {f"{e}_legacy": {"parquet": str(data / f"{e}_legacy.parquet")}
              for e in ("chantiers", "factures")}
    existing = legacy | {f"{e}_target": {"parquet": str(data / f"{e}_target.parquet")}
                         for e in ("chantiers", "factures")}
    (tmp_path / "new.db").touch()
    empty = legacy | {f"{e}_target": {"database": f"sqlite:///{tmp_path / 'new.db'}", "table": e}
                      for e in ("chantiers", "factures")}
    return existing, empty


def test_a_whole_migration_goes_through_the_service(tmp_path: Path) -> None:
    service = Service(tmp_path / "app")
    existing, empty = _catalogs(tmp_path)

    suggested = _call(service, "suggest", catalog=existing,
                      sources=["chantiers_legacy", "factures_legacy"],
                      targets=["chantiers_target", "factures_target"])["result"]
    assert {(m["source"], m["target"]) for m in suggested} == {
        ("chantiers_legacy", "chantiers_target"), ("factures_legacy", "factures_target"),
    }
    mappings = [m["mapping"] for m in suggested]

    plan = _call(service, "plan", catalog=empty, mappings=mappings)["result"]
    assert [t["table"] for t in plan["tables"]] == ["chantiers", "factures"]
    assert all(t["create"].startswith("CREATE TABLE") for t in plan["tables"])

    done = _call(service, "migrate", catalog=empty, mappings=mappings)["result"]
    assert Path(done["report"]).exists()
    results = _call(service, "results", run_id=done["run_id"])["result"]
    assert {r["entity"] for r in results["runs"]} == {"chantiers", "factures"}

    assert (results["findings"], results["total"]) == ([], 0)
    json.dumps([suggested, plan, done, results], default=_json)
    recorded = _call(service, "decide", finding_key="a" * 64,
                     decision="accepted", by="bastien", reason="known")
    assert recorded == {"id": "decide", "result": {"recorded": True}}


def test_errors_are_answers_and_never_carry_a_password(tmp_path: Path) -> None:
    service = Service(tmp_path)
    assert _call(service, "drop_everything")["error"]["message"] == (
        "unknown method drop_everything"
    )
    assert _call(service, "__init__")["error"]["message"] == "unknown method __init__"
    assert "error" in handle(service, "not json")
    failed = _call(service, "plan", mappings=[], catalog={
        "t": {"database": "oracle://relay:S3cret@db/erp", "table": "x"},
    })["error"]
    assert "S3cret" not in json.dumps(failed)
    assert failed["problems"] == ["t: unsupported database URL 'oracle' "
                                  "(postgresql, postgres, mysql, mssql, sqlite)"]


def test_the_service_speaks_json_lines_and_nothing_else(tmp_path: Path) -> None:
    lines = "\n".join([
        json.dumps({"id": 1, "method": "ping"}),
        "",
        json.dumps({"id": 2, "method": "nope"}),
    ]) + "\n"
    done = subprocess.run(
        [sys.executable, "-m", "relay_engine.service", "--data", str(tmp_path)],
        input=lines, capture_output=True, text=True, check=True, timeout=60,
    )
    answers = [json.loads(line) for line in done.stdout.splitlines()]
    assert [a["id"] for a in answers] == [1, 2]
    assert "version" in answers[0]["result"]
    assert "error" in answers[1]


def test_a_connection_is_reached_and_described(tmp_path: Path) -> None:
    import sqlite3
    from contextlib import closing

    database = tmp_path / "erp.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript("CREATE TABLE clients (id TEXT); CREATE TABLE orders (id TEXT);")
    (tmp_path / "clients.csv").write_text("id;nom\nC1;Ana\n")
    service = Service(tmp_path)
    reached = _call(service, "connect", connection={"database": f"sqlite:///{database}"})
    assert reached["result"] == {"tables": ["clients", "orders"]}
    read = _call(service, "connect", connection={"csv": str(tmp_path / "clients.csv"),
                                                 "delimiter": ";"})
    assert read["result"] == {"columns": ["id", "nom"], "rows": 1}
    missing = _call(service, "connect", connection={"database": "sqlite:///nowhere.db"})
    assert missing["error"]["problems"] == ["connection: file nowhere.db does not exist"]
    folder = _call(service, "connect", connection={"database": f"sqlite:///{tmp_path}"})
    assert folder["error"]["problems"] == [
        f"connection: {tmp_path} is a folder; give the path of the file itself",
    ]
    refused = _call(service, "connect", connection={
        "database": "postgresql://relay:S3cret@127.0.0.1:1/erp",
    })
    assert "S3cret" not in json.dumps(refused)
    assert refused["error"]["message"].startswith("database: ")


def test_a_connection_shows_its_tables_keys_and_links(tmp_path: Path) -> None:
    import sqlite3
    from contextlib import closing

    database = tmp_path / "erp.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(
            "CREATE TABLE clients (code TEXT PRIMARY KEY, nom TEXT NOT NULL);"
            "CREATE TABLE chantiers (id TEXT PRIMARY KEY, client TEXT REFERENCES clients(code),"
            " montant NUMERIC(12, 2));"
            "INSERT INTO clients VALUES ('00412', 'Ana'), ('00413', 'Bo');"
            "INSERT INTO chantiers VALUES ('C1', '00412', 10.50);"
        )
        connection.commit()
    (tmp_path / "devis.csv").write_text("id;montant\nD1;3.20\nD2;4.10\n")
    service = Service(tmp_path)

    tables = _call(service, "schema", connection={"database": f"sqlite:///{database}"})["result"]
    assert tables == {"tables": [
        {"name": "chantiers", "rows": 1, "key": ["id"],
         "references": [{"columns": ["client"], "table": "clients", "to": ["code"]}],
         "columns": [{"name": "id", "type": "TEXT", "nullable": True},
                     {"name": "client", "type": "TEXT", "nullable": True},
                     {"name": "montant", "type": "NUMERIC(12, 2)", "nullable": True}]},
        {"name": "clients", "rows": 2, "key": ["code"], "references": [],
         "columns": [{"name": "code", "type": "TEXT", "nullable": True},
                     {"name": "nom", "type": "TEXT", "nullable": False}]},
    ]}
    file = _call(service, "schema", connection={"csv": str(tmp_path / "devis.csv"),
                                                "delimiter": ";"})["result"]
    assert file == {"tables": [
        {"name": "devis", "rows": 2, "key": [], "references": [],
         "columns": [{"name": "id", "type": "String", "nullable": True},
                     {"name": "montant", "type": "String", "nullable": True}]},
    ]}


def test_a_file_is_described_without_being_read_whole(tmp_path: Path) -> None:
    import polars as pl

    (tmp_path / "bom.csv").write_text("﻿code;ville\n00412;Lyon\n\n00007;Brest\n\n")
    (tmp_path / "ansi.csv").write_bytes("code;désignation\n1;Bâtiment\n".encode("cp1252"))
    pl.DataFrame({"code": ["00412"], "amount": [1.5]}).write_parquet(tmp_path / "sites.parquet")
    service = Service(tmp_path)
    for connection, columns, rows in [
        ({"csv": str(tmp_path / "bom.csv"), "delimiter": ";"}, ["code", "ville"], 2),
        ({"csv": str(tmp_path / "ansi.csv"), "delimiter": ";", "encoding": "cp1252"},
         ["code", "désignation"], 1),
        ({"parquet": str(tmp_path / "sites.parquet")}, ["code", "amount"], 1),
    ]:
        assert _call(service, "connect", connection=connection)["result"] == {
            "columns": columns, "rows": rows,
        }
        [table] = _call(service, "schema", connection=connection)["result"]["tables"]
        assert ([c["name"] for c in table["columns"]], table["rows"]) == (columns, rows)
    bad = _call(service, "connect", connection={"csv": str(tmp_path / "ansi.csv")})
    assert bad["error"]["problems"] == [
        "ansi.csv is not utf-8: declare its encoding, e.g. `encoding: cp1252`",
    ]


def test_results_page_the_findings_that_are_not_pass(tmp_path: Path) -> None:
    import polars as pl

    from relay_engine.io import LocalParquetStore
    from relay_engine.mapping import load_mapping
    from relay_engine.pipeline import run_migration

    data = tmp_path / "data"
    generate(data, seed=42, rows=30)
    mappings = Path(__file__).parent.parent / "examples" / "mappings"
    specs = [load_mapping(mappings / f"{e}.yaml") for e in ("chantiers", "factures")]
    service = Service(tmp_path / "app")
    run_migration(specs, LocalParquetStore(data), LocalParquetStore(service.runs / "r1"), "r1")
    stored = pl.read_parquet(service.runs / "r1" / "gold" / "recon_finding" / "*.parquet")
    flagged = stored.filter(pl.col("verdict") != "PASS").get_column("finding_key").to_list()
    assert len(flagged) > 3

    first = _call(service, "results", run_id="r1")["result"]
    pages = [_call(service, "results", run_id="r1", offset=offset, limit=2)["result"]
             for offset in range(0, len(flagged), 2)]

    assert {r["entity"] for r in first["runs"]} == {"chantiers", "factures"}
    assert first["total"] == len(flagged) and all(p["total"] == len(flagged) for p in pages)
    assert [f["finding_key"] for p in pages for f in p["findings"]] == [
        f["finding_key"] for f in first["findings"]
    ]
    assert sorted(f["finding_key"] for f in first["findings"]) == sorted(flagged)
    assert all(f["verdict"] != "PASS" for f in first["findings"])


def test_a_key_column_that_is_also_a_foreign_key_migrates_after_its_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import sqlite3
    from contextlib import closing

    source = tmp_path / "relay.db"
    with closing(sqlite3.connect(source)) as connection:
        connection.executescript(
            "CREATE TABLE teams (id TEXT PRIMARY KEY, name TEXT NOT NULL);"
            "CREATE TABLE members (team_id TEXT NOT NULL REFERENCES teams(id),"
            " user_id TEXT NOT NULL, email TEXT, full_name TEXT,"
            " PRIMARY KEY (team_id, user_id));"
            "CREATE TABLE invitations (id TEXT PRIMARY KEY,"
            " team_id TEXT NOT NULL REFERENCES teams(id), email TEXT NOT NULL,"
            " UNIQUE (team_id, email));"
            "INSERT INTO teams VALUES ('t1', 'Core'), ('t2', 'Ops');"
            "INSERT INTO members VALUES ('t1', 'u1', 'ana@relay.dev', 'Ana Lima'),"
            " ('t1', 'u2', 'bo@relay.dev', 'Bo Chen'), ('t2', 'u1', 'ana@relay.dev', 'Ana Lima');"
            "INSERT INTO invitations VALUES ('i1', 't1', 'cy@relay.dev');"
        )
        connection.commit()
    (tmp_path / "empty.db").touch()
    service = Service(tmp_path / "app")
    pair = {"source": {"database": f"sqlite:///{source}"},
            "target": {"database": f"sqlite:///{tmp_path / 'empty.db'}"}}

    proposals = _call(service, "propose", **pair)["result"]["proposals"]
    mappings = []
    for proposal in proposals:
        mapping = proposal["mapping"]
        for column in mapping["columns"]:
            if column.get("source") in proposal["personal"]:
                column["anonymize"] = proposal["personal"][column["source"]]
        mappings.append(mapping)
    assert any(c.get("anonymize") for m in mappings for c in m["columns"])

    plan = _call(service, "plan", mappings=mappings, **pair)["result"]
    assert sum(t["rows"] for t in plan["tables"]) == 6
    done = _call(service, "migrate", mappings=mappings, **pair)
    assert "error" not in done, done
    assert done["result"]["verdict"] == "PASS"

    import polars as pl

    def broken(*_: object) -> None:
        raise pl.exceptions.DuplicateError("duplicate output name 'team_id'")

    monkeypatch.setattr("relay_engine.pipeline.check_referential", broken)
    failed = _call(service, "migrate", mappings=mappings, replace=True, **pair)["error"]
    assert failed["problems"] == [
        "teams: an unexpected error stopped the processing of this table; "
        "the details are in the engine log"
    ]
    assert "duplicate output name 'team_id'" in capsys.readouterr().err
