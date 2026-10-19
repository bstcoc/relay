"""Migration on database servers. Each runs when its RELAY_TEST_<ENGINE> URL is set."""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl
import pytest
import sqlalchemy as sa

from relay_engine.generator.generate import generate
from relay_engine.io import LocalParquetStore
from relay_engine.io.catalog import load_sources
from relay_engine.io.database import sql_engine
from relay_engine.mapping import load_mappings
from relay_engine.migrate import migrate

EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"
SERVERS = ["POSTGRESQL", "MYSQL", "MSSQL"]
TABLES = [
    """CREATE TABLE chantiers (
        chantier_id VARCHAR(20) PRIMARY KEY, libelle VARCHAR(200),
        montant_marche NUMERIC(12,2), date_ouverture DATE,
        rue VARCHAR(200), code_postal VARCHAR(10), ville VARCHAR(100))""",
    """CREATE TABLE factures (
        facture_id VARCHAR(20) PRIMARY KEY,
        chantier_id VARCHAR(20) REFERENCES chantiers(chantier_id),
        montant_hors_taxes NUMERIC(12,2), date_facture DATE)""",
]


@pytest.mark.parametrize("server", SERVERS)
def test_a_migration_to_a_server_writes_and_proves(tmp_path: Path, server: str) -> None:
    variable = f"RELAY_TEST_{server}"
    if variable not in os.environ:
        pytest.skip(f"{variable} is not set")
    engine = sql_engine(os.environ[variable])
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE IF EXISTS factures"))
        connection.execute(sa.text("DROP TABLE IF EXISTS chantiers"))
        for table in TABLES:
            connection.execute(sa.text(table))
    data = tmp_path / "data"
    generate(data, seed=42, rows=30)
    (tmp_path / "sources.yaml").write_text(
        f"chantiers_legacy:\n  parquet: {data / 'chantiers_legacy.parquet'}\n"
        f"factures_legacy:\n  parquet: {data / 'factures_legacy.parquet'}\n"
        f"chantiers_target:\n  database: ${{{variable}}}\n  table: chantiers\n"
        f"factures_target:\n  database: ${{{variable}}}\n  table: factures\n"
    )
    catalog = load_sources(tmp_path / "sources.yaml")
    for run in ("first", "again"):
        migrate(load_mappings(EXAMPLES), catalog, LocalParquetStore(tmp_path / run), run,
                replace=run == "again")
        found = pl.read_parquet(tmp_path / run / "gold" / "recon_finding" / "*.parquet")
        lost = found.filter(pl.col("check_family").is_in(["completeness", "fidelity"]))
        assert lost.is_empty(), lost
    with engine.connect() as connection:
        rows = connection.execute(sa.text("SELECT count(*) FROM chantiers")).scalar_one()
    assert rows == pl.read_parquet(data / "chantiers_legacy.parquet").height


@pytest.mark.parametrize("server", SERVERS)
def test_a_migration_creates_the_tables_of_an_empty_server(tmp_path: Path, server: str) -> None:
    variable = f"RELAY_TEST_{server}"
    if variable not in os.environ:
        pytest.skip(f"{variable} is not set")
    engine = sql_engine(os.environ[variable])
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE IF EXISTS factures"))
        connection.execute(sa.text("DROP TABLE IF EXISTS chantiers"))
    data = tmp_path / "data"
    generate(data, seed=42, rows=30)
    (tmp_path / "sources.yaml").write_text(
        f"chantiers_legacy:\n  parquet: {data / 'chantiers_legacy.parquet'}\n"
        f"factures_legacy:\n  parquet: {data / 'factures_legacy.parquet'}\n"
        f"chantiers_target:\n  database: ${{{variable}}}\n  table: chantiers\n"
        f"factures_target:\n  database: ${{{variable}}}\n  table: factures\n"
    )
    migrate(load_mappings(EXAMPLES), load_sources(tmp_path / "sources.yaml"),
            LocalParquetStore(tmp_path / "run"), "run")
    found = pl.read_parquet(tmp_path / "run" / "gold" / "recon_finding" / "*.parquet")
    lost = found.filter(pl.col("check_family").is_in(["completeness", "fidelity"]))
    assert lost.is_empty(), lost
    inspector = sa.inspect(engine)
    amount = next(c for c in inspector.get_columns("chantiers") if c["name"] == "montant_marche")
    numeric = amount["type"]
    assert isinstance(numeric, sa.Numeric)
    assert (numeric.precision, numeric.scale) == (12, 2)
    assert inspector.get_pk_constraint("chantiers")["constrained_columns"] == ["chantier_id"]
    (foreign,) = inspector.get_foreign_keys("factures")
    assert foreign["referred_table"] == "chantiers"
