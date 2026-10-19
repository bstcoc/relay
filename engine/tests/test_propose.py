from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from relay_engine.service import Service, handle


def _call(service: Service, method: str, **params: object) -> dict:
    answer = handle(service, json.dumps({"id": method, "method": method, "params": params}))
    assert "error" not in answer, answer
    return answer["result"]


def _source(path: Path) -> dict:
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sites (code TEXT PRIMARY KEY, name TEXT NOT NULL)")
        db.executemany("INSERT INTO sites VALUES (?, ?)", [("00412", "Lyon"), ("00007", "Brest")])
        db.execute("CREATE TABLE workers (id INTEGER PRIMARY KEY, full_name TEXT, site TEXT)")
        db.executemany("INSERT INTO workers VALUES (?, ?, ?)",
                       [(1, "Ana Martin", "00412"), (2, "Bo Lee", "00007"),
                        (3, "Cy Durand", "00412")])
    return {"database": f"sqlite:///{path}"}


def test_an_empty_target_gets_a_copy_of_every_source_table(tmp_path: Path) -> None:
    service = Service(tmp_path / "data")
    source = _source(tmp_path / "erp.db")
    target = {"database": f"sqlite:///{tmp_path / 'new.db'}"}
    sqlite3.connect(tmp_path / "new.db").close()

    proposals = _call(service, "propose", source=source, target=target)["proposals"]

    assert {(p["source"], p["target"], p["create"]) for p in proposals} == {
        ("sites", "sites", True), ("workers", "workers", True),
    }
    mappings = [p["mapping"] for p in proposals]
    plan = _call(service, "plan", source=source, target=target, mappings=mappings)
    assert {t["table"]: t["rows"] for t in plan["tables"]} == {"sites": 2, "workers": 3}
    assert plan["blocked"] == []

    summary = _call(service, "migrate", source=source, target=target, mappings=mappings)

    assert summary["verdict"] == "PASS"
    with sqlite3.connect(tmp_path / "new.db") as db:
        codes = db.execute("SELECT code FROM sites ORDER BY name").fetchall()
    assert codes == [("00007",), ("00412",)]


def test_a_target_table_with_other_names_gets_a_suggested_mapping(tmp_path: Path) -> None:
    service = Service(tmp_path / "data")
    source = _source(tmp_path / "erp.db")
    with sqlite3.connect(tmp_path / "new.db") as db:
        db.execute("CREATE TABLE employees "
                   "(employee_id INTEGER PRIMARY KEY, name TEXT, site_code TEXT)")
    target = {"database": f"sqlite:///{tmp_path / 'new.db'}"}

    answer = _call(service, "propose", source=source, target=target, tables=["workers"])

    [workers] = answer["proposals"]
    assert (workers["target"], workers["create"]) == ("employees", False)
    assert {(c["source"], c["target"]) for c in workers["columns"]} >= {("full_name", "name")}
    assert workers["mapping"]["target"] == {"table": "target.employees"}


def test_personal_columns_are_pseudonymized_and_still_reconcile(tmp_path: Path) -> None:
    service = Service(tmp_path / "data")
    source = _source(tmp_path / "erp.db")
    target = {"database": f"sqlite:///{tmp_path / 'new.db'}"}
    sqlite3.connect(tmp_path / "new.db").close()
    [workers] = _call(service, "propose", source=source, target=target,
                      tables=["workers"])["proposals"]
    assert workers["personal"] == {"full_name": "full_name"}
    mapping = workers["mapping"]
    for column in mapping["columns"]:
        if column["source"] in workers["personal"]:
            column["anonymize"] = workers["personal"][column["source"]]

    summary = _call(service, "migrate", source=source, target=target, mappings=[mapping])

    assert summary["verdict"] == "PASS"
    with sqlite3.connect(tmp_path / "new.db") as db:
        names = [n for (n,) in db.execute("SELECT full_name FROM workers")]
    assert not {"Ana Martin", "Bo Lee", "Cy Durand"} & set(names)
    assert all(len(name.split()) == 2 for name in names)


def test_a_subset_keeps_the_rows_below_the_kept_rows(tmp_path: Path) -> None:
    service = Service(tmp_path / "data")
    with sqlite3.connect(tmp_path / "erp.db") as db:
        db.execute("CREATE TABLE sites (code TEXT PRIMARY KEY, name TEXT)")
        db.executemany("INSERT INTO sites VALUES (?, ?)", [("00412", "Lyon"), ("00007", "Brest")])
        db.execute("CREATE TABLE workers (id INTEGER PRIMARY KEY, "
                   "site TEXT REFERENCES sites(code))")
        db.executemany("INSERT INTO workers VALUES (?, ?)", [(1, "00412"), (2, "00007"),
                                                              (3, "00412")])
    source = {"database": f"sqlite:///{tmp_path / 'erp.db'}"}
    target = {"database": f"sqlite:///{tmp_path / 'new.db'}"}
    sqlite3.connect(tmp_path / "new.db").close()
    mappings = [p["mapping"] for p in _call(service, "propose", source=source,
                                            target=target)["proposals"]]
    subset = {"table": "sites", "where": "name = 'Lyon'"}

    plan = _call(service, "plan", source=source, target=target, mappings=mappings, subset=subset)
    summary = _call(service, "migrate", source=source, target=target, mappings=mappings,
                    subset=subset)

    assert {t["table"]: t["rows"] for t in plan["tables"]} == {"sites": 1, "workers": 2}
    assert summary["verdict"] == "PASS"


def test_a_copied_table_keeps_its_declared_types_and_its_links(tmp_path: Path) -> None:
    service = Service(tmp_path / "data")
    with sqlite3.connect(tmp_path / "erp.db") as db:
        db.execute("CREATE TABLE clients (code TEXT PRIMARY KEY)")
        db.execute("INSERT INTO clients VALUES ('00412')")
        db.execute("CREATE TABLE factures (numero TEXT PRIMARY KEY, "
                   "client TEXT REFERENCES clients(code), montant NUMERIC(12,2), jour DATE)")
        db.execute("INSERT INTO factures VALUES ('F1', '00412', 21740.23, '2021-12-21')")
    source = {"database": f"sqlite:///{tmp_path / 'erp.db'}"}
    target = {"database": f"sqlite:///{tmp_path / 'new.db'}"}
    sqlite3.connect(tmp_path / "new.db").close()

    proposals = _call(service, "propose", source=source, target=target)["proposals"]

    factures = next(p["mapping"] for p in proposals if p["source"] == "factures")
    types = {c["source"]: c["type"] for c in factures["columns"]}
    assert (types["montant"], types["jour"]) == ("decimal(12,2)", "date")
    assert factures["references"] == [
        {"column": "client", "table": "target.clients", "key": "code"},
    ]
    mappings = [p["mapping"] for p in proposals]
    assert _call(service, "migrate", source=source, target=target,
                 mappings=mappings)["verdict"] == "PASS"
    with sqlite3.connect(tmp_path / "new.db") as db:
        assert db.execute("PRAGMA foreign_key_list(factures)").fetchall()


def test_two_filters_keep_the_rows_that_pass_both_down_the_links(tmp_path: Path) -> None:
    service = Service(tmp_path / "data")
    with sqlite3.connect(tmp_path / "erp.db") as db:
        db.execute("CREATE TABLE sites (code TEXT PRIMARY KEY, name TEXT)")
        db.executemany("INSERT INTO sites VALUES (?, ?)", [("00412", "Lyon"), ("00007", "Brest")])
        db.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, "
                   "site TEXT REFERENCES sites(code), year INTEGER)")
        db.executemany("INSERT INTO invoices VALUES (?, ?, ?)",
                       [(1, "00412", 2025), (2, "00412", 2024), (3, "00007", 2025)])
        db.execute("CREATE TABLE lines (id INTEGER PRIMARY KEY, "
                   "invoice INTEGER REFERENCES invoices(id))")
        db.executemany("INSERT INTO lines VALUES (?, ?)", [(1, 1), (2, 2), (3, 3), (4, 1)])
    source = {"database": f"sqlite:///{tmp_path / 'erp.db'}"}
    target = {"database": f"sqlite:///{tmp_path / 'new.db'}"}
    sqlite3.connect(tmp_path / "new.db").close()
    mappings = [p["mapping"] for p in _call(service, "propose", source=source,
                                            target=target)["proposals"]]
    subset = [{"table": "sites", "where": "name = 'Lyon'"},
              {"table": "invoices", "where": "year = 2025"}]

    plan = _call(service, "plan", source=source, target=target, mappings=mappings, subset=subset)
    summary = _call(service, "migrate", source=source, target=target, mappings=mappings,
                    subset=subset)

    rows = {t["table"]: t["rows"] for t in plan["tables"]}
    assert rows == {"sites": 1, "invoices": 1, "lines": 2}
    assert summary["verdict"] == "PASS"
