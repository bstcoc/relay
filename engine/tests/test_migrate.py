"""Relay writes the source to the target database, then proves it."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import polars as pl
import pytest

from relay_engine.generator.generate import generate
from relay_engine.io import LocalParquetStore
from relay_engine.io.catalog import SourcesError, load_sources, without_credentials
from relay_engine.io.database import describe
from relay_engine.mapping import load_mappings
from relay_engine.migrate import migrate, plan_migration

EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"
TARGET_TABLES = """
CREATE TABLE chantiers (
    chantier_id TEXT PRIMARY KEY, libelle TEXT, montant_marche NUMERIC(12,2),
    date_ouverture DATE, rue TEXT, code_postal TEXT, ville TEXT
);
CREATE TABLE factures (
    facture_id TEXT PRIMARY KEY, chantier_id TEXT REFERENCES chantiers(chantier_id),
    montant_hors_taxes NUMERIC(12,2) {check}, date_facture DATE
);
"""


def _catalog(tmp_path: Path, check: str = "") -> tuple[dict, Path]:
    data = tmp_path / "data"
    generate(data, seed=42, rows=30)
    database = tmp_path / "target.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(TARGET_TABLES.format(check=check))
    (tmp_path / "sources.yaml").write_text(
        f"chantiers_legacy:\n  parquet: {data / 'chantiers_legacy.parquet'}\n"
        f"factures_legacy:\n  parquet: {data / 'factures_legacy.parquet'}\n"
        "chantiers_target:\n  database: sqlite:///target.db\n  table: chantiers\n"
        "factures_target:\n  database: sqlite:///target.db\n  table: factures\n"
    )
    return load_sources(tmp_path / "sources.yaml"), database


def _count(database: Path, table: str) -> int:
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def _run(tmp_path: Path, catalog: dict, name: str, *, replace: bool = False):
    sink = LocalParquetStore(tmp_path / "runs" / name)
    return migrate(load_mappings(EXAMPLES), catalog, sink, name, replace=replace)


def test_the_dry_run_plans_every_table_parents_first_and_writes_nothing(
    tmp_path: Path,
) -> None:
    catalog, database = _catalog(tmp_path)
    plan = plan_migration(load_mappings(EXAMPLES), catalog)
    assert [(t.entity, t.table, t.existing_rows) for t in plan.tables] == [
        ("chantiers", "chantiers", 0),
        ("factures", "factures", 0),
    ]
    legacy = pl.read_parquet(tmp_path / "data" / "chantiers_legacy.parquet")
    assert plan.tables[0].rows == legacy.height
    assert plan.tables[0].columns[:2] == ["chantier_id", "libelle"]
    assert not plan.blocked
    assert _count(database, "chantiers") == _count(database, "factures") == 0


def test_a_migration_writes_the_target_and_proves_it(tmp_path: Path) -> None:
    catalog, database = _catalog(tmp_path)
    summary = _run(tmp_path, catalog, "first")
    plan = plan_migration(load_mappings(EXAMPLES), catalog, replace=True)
    assert _count(database, "chantiers") == plan.tables[0].rows
    assert _count(database, "factures") == plan.tables[1].rows
    found = pl.read_parquet(tmp_path / "runs" / "first" / "gold" / "recon_finding" / "*.parquet")
    lost = found.filter(pl.col("check_family").is_in(["completeness", "fidelity"]))
    assert lost.is_empty(), lost
    assert {e.entity for e in summary.entities} == {"chantiers", "factures"}


def test_a_filled_target_stops_the_migration_unless_replaced(tmp_path: Path) -> None:
    catalog, database = _catalog(tmp_path)
    _run(tmp_path, catalog, "first")
    written = _count(database, "factures")
    with pytest.raises(SourcesError) as stopped:
        _run(tmp_path, catalog, "second")
    assert stopped.value.problems[0].startswith("chantiers: already holds ")
    _run(tmp_path, catalog, "third", replace=True)
    assert _count(database, "factures") == written


def test_a_failed_write_leaves_the_target_untouched(tmp_path: Path) -> None:
    catalog, database = _catalog(tmp_path, check="CHECK (montant_hors_taxes < 0)")
    with pytest.raises(SourcesError) as failed:
        _run(tmp_path, catalog, "first")
    (problem,) = failed.value.problems
    assert problem.startswith("writing factures: ")
    assert problem.endswith("; nothing was written")
    assert "parameters" not in problem
    assert _count(database, "chantiers") == 0


def test_a_target_must_be_one_database(tmp_path: Path) -> None:
    catalog, _ = _catalog(tmp_path)
    catalog["factures_target"] = catalog["chantiers_legacy"]
    with pytest.raises(SourcesError, match="must be a database"):
        plan_migration(load_mappings(EXAMPLES), catalog)


def test_credentials_never_reach_a_message() -> None:
    assert (
        without_credentials("cannot reach postgresql://relay:s3cr%3Et@db:5432/erp")
        == "cannot reach postgresql://relay:***@db:5432/erp"
    )
    assert describe(RuntimeError("mssql://sa:Pa55@host failed\n  at deep")) == (
        "mssql://sa:***@host failed"
    )


def _empty_target(tmp_path: Path, tables: str = "") -> tuple[dict, Path]:
    catalog, database = _catalog(tmp_path)
    database.unlink()
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(tables)
    return load_sources(tmp_path / "sources.yaml"), database


def _tables(database: Path) -> set[str]:
    with closing(sqlite3.connect(database)) as connection:
        return {r[0] for r in connection.execute("SELECT name FROM sqlite_master")
                if not r[0].startswith("sqlite_")}


def test_the_dry_run_shows_the_tables_an_empty_target_will_get(tmp_path: Path) -> None:
    catalog, database = _empty_target(tmp_path)
    plan = plan_migration(load_mappings(EXAMPLES), catalog)
    chantiers, factures = plan.tables
    assert chantiers.create is not None and factures.create is not None
    assert "chantier_id VARCHAR(64) NOT NULL" in chantiers.create
    assert "montant_marche NUMERIC(12, 2)" in chantiers.create
    assert "PRIMARY KEY (chantier_id)" in chantiers.create
    assert "FOREIGN KEY(chantier_id) REFERENCES chantiers (chantier_id)" in factures.create
    assert _tables(database) == set()


def test_a_migration_creates_the_tables_of_an_empty_target(tmp_path: Path) -> None:
    catalog, database = _empty_target(tmp_path)
    _run(tmp_path, catalog, "first")
    assert _tables(database) == {"chantiers", "factures"}
    found = pl.read_parquet(tmp_path / "runs" / "first" / "gold" / "recon_finding" / "*.parquet")
    lost = found.filter(pl.col("check_family").is_in(["completeness", "fidelity"]))
    assert lost.is_empty(), lost


def test_a_failed_write_drops_the_tables_it_created(tmp_path: Path) -> None:
    factures = TARGET_TABLES.split(";")[1].format(check="CHECK (montant_hors_taxes < 0)")
    catalog, database = _empty_target(tmp_path, factures)
    with pytest.raises(SourcesError, match="nothing was written"):
        _run(tmp_path, catalog, "first")
    assert _tables(database) == {"factures"}


def test_a_key_that_does_not_identify_every_row_is_no_primary_key() -> None:
    from relay_engine.migrate import _primary_key

    assert _primary_key(pl.DataFrame({"id": ["a", "b"]}), ["id"]) == ["id"]
    assert _primary_key(pl.DataFrame({"id": ["a", "a"]}), ["id"]) == []
    assert _primary_key(pl.DataFrame({"id": ["a", None]}), ["id"]) == []
