"""Seams 2 and 3: a table read from CSV or a database must reconcile exactly like Parquet."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import yaml

from conftest import records
from relay_engine.generator.generate import generate
from relay_engine.io import LocalParquetStore, TableSource
from relay_engine.io.catalog import CsvSource, DatabaseSource, ParquetSource
from relay_engine.io.readers import CatalogSource
from relay_engine.mapping import MappingSpec, load_mapping
from relay_engine.pipeline import run

EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"


def _findings(
    spec: MappingSpec, source: TableSource, out: Path, run_id: str
) -> set[tuple]:
    run(spec, source, LocalParquetStore(out / run_id), run_id)
    rows = records(pl.read_parquet(out / run_id / "gold" / "recon_finding" / "*.parquet"))
    return {(r.finding_key, r.verdict, r.check_family, r.column) for r in rows}


def test_a_french_erp_csv_export_reconciles_like_parquet(
    tmp_path: Path
) -> None:
    data = tmp_path / "data"
    generate(data, seed=42, rows=40)

    legacy = pl.read_parquet(data / "chantiers_legacy.parquet").with_columns(
        pl.col("mnt_marche").cast(pl.String).str.replace(".", ",", literal=True),
        pl.col("dt_ouv").dt.strftime("%Y-%m-%d %H:%M:%S"),
    )
    csv = tmp_path / "chantiers.csv"
    csv.write_bytes(legacy.write_csv(separator=";").encode("cp1252"))

    raw = yaml.safe_load((EXAMPLES / "chantiers.yaml").read_text())
    next(c for c in raw["columns"] if c["source"] == "mnt_marche")["normalize"] = ["decimal_comma"]
    csv_spec = MappingSpec.model_validate(raw)

    catalog = CatalogSource({
        "chantiers_legacy": CsvSource(csv=csv, delimiter=";", encoding="cp1252"),
        "chantiers_target": ParquetSource(parquet=data / "chantiers_target.parquet"),
    })
    baseline = _findings(
        load_mapping(EXAMPLES / "chantiers.yaml"), LocalParquetStore(data),
        tmp_path / "out", "parquet",
    )
    from_csv = _findings(csv_spec, catalog, tmp_path / "out", "csv")

    assert baseline, "the generated data must produce findings to compare"
    assert from_csv == baseline


def test_a_target_read_from_a_database_reconciles_like_parquet(
    tmp_path: Path
) -> None:
    import sqlite3

    data = tmp_path / "data"
    generate(data, seed=42, rows=40)

    target = pl.read_parquet(data / "chantiers_target.parquet")
    db = tmp_path / "erp.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE chantier (chantier_id TEXT, libelle TEXT, montant_marche DECIMAL(12,2),"
            " date_ouverture DATE, rue TEXT, code_postal TEXT, ville TEXT)"
        )
        conn.executemany(
            "INSERT INTO chantier VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (r["chantier_id"], r["libelle"], str(r["montant_marche"]),
                 r["date_ouverture"].isoformat(), r["rue"], r["code_postal"], r["ville"])
                for r in target.iter_rows(named=True)
            ],
        )

    catalog = CatalogSource({
        "chantiers_legacy": ParquetSource(parquet=data / "chantiers_legacy.parquet"),
        "chantiers_target": DatabaseSource(database=f"sqlite:///{db}", table="chantier"),
    })
    spec = load_mapping(EXAMPLES / "chantiers.yaml")
    baseline = _findings(spec, LocalParquetStore(data), tmp_path / "out", "parquet")
    from_db = _findings(spec, catalog, tmp_path / "out", "database")

    assert baseline
    assert from_db == baseline
