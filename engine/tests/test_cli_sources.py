"""Seam 4: run, validate and scaffold read their tables through a sources catalog."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import polars as pl
import pytest
import yaml
from typer.testing import CliRunner

from relay_engine.cli import app
from relay_engine.generator.generate import generate

runner = CliRunner()
EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"


def _erp(tmp_path: Path) -> Path:
    """Legacy side as a French CSV export, target side in a database, plus a catalog."""
    data = tmp_path / "data"
    generate(data, seed=42, rows=20)
    legacy = pl.read_parquet(data / "chantiers_legacy.parquet").with_columns(
        pl.col("mnt_marche").cast(pl.String).str.replace(".", ",", literal=True),
        pl.col("dt_ouv").dt.strftime("%Y-%m-%d %H:%M:%S"),
    )
    (tmp_path / "chantiers.csv").write_bytes(legacy.write_csv(separator=";").encode("cp1252"))
    target = pl.read_parquet(data / "chantiers_target.parquet")
    with sqlite3.connect(tmp_path / "erp.db") as conn:
        conn.execute(
            "CREATE TABLE chantier (chantier_id TEXT, libelle TEXT, montant_marche DECIMAL(12,2),"
            " date_ouverture DATE, rue TEXT, code_postal TEXT, ville TEXT)"
        )
        conn.executemany("INSERT INTO chantier VALUES (?, ?, ?, ?, ?, ?, ?)", [
            (r["chantier_id"], r["libelle"], str(r["montant_marche"]),
             r["date_ouverture"].isoformat(), r["rue"], r["code_postal"], r["ville"])
            for r in target.iter_rows(named=True)
        ])
    (tmp_path / "sources.yaml").write_text("""
chantiers_legacy:
  csv: chantiers.csv
  delimiter: ";"
  encoding: cp1252
chantiers_target:
  database: ${RELAY_TEST_DB_URL}
  table: chantier
""")
    raw = yaml.safe_load((EXAMPLES / "chantiers.yaml").read_text())
    next(c for c in raw["columns"] if c["source"] == "mnt_marche")["normalize"] = ["decimal_comma"]
    (tmp_path / "chantiers.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True))
    return tmp_path / "sources.yaml"


def test_validate_and_run_through_the_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = _erp(tmp_path)
    monkeypatch.setenv(
        "RELAY_TEST_DB_URL", f"sqlite:///{tmp_path / 'erp.db'}"
    )
    mapping = str(tmp_path / "chantiers.yaml")

    validated = runner.invoke(app, ["validate", mapping, "--sources", str(sources)])
    assert validated.exit_code == 0, validated.stdout

    ran = runner.invoke(app, [
        "run", mapping, "--sources", str(sources), "--out", str(tmp_path / "runs"),
        "--decisions", str(tmp_path / "decisions"),
    ])
    assert ran.exit_code == 0, ran.stdout
    assert "chantiers: FAIL" in ran.stdout


def test_scaffold_reads_the_target_schema_from_the_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = _erp(tmp_path)
    monkeypatch.setenv(
        "RELAY_TEST_DB_URL", f"sqlite:///{tmp_path / 'erp.db'}"
    )
    output = tmp_path / "skeleton.yaml"
    result = runner.invoke(app, [
        "scaffold", "chantiers", "--source", "chantiers_legacy", "--target", "chantiers_target",
        "--sources", str(sources), "--output", str(output),
    ])
    assert result.exit_code == 0, result.stdout
    targets = [c["target"] for c in yaml.safe_load(output.read_text())["columns"]]
    assert targets == [
        "chantier_id", "libelle", "montant_marche", "date_ouverture", "rue", "code_postal", "ville",
    ]


def test_a_missing_secret_is_reported_not_crashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = _erp(tmp_path)
    monkeypatch.delenv("RELAY_TEST_DB_URL", raising=False)
    result = runner.invoke(
        app, ["validate", str(tmp_path / "chantiers.yaml"), "--sources", str(sources)]
    )
    assert result.exit_code == 1
    assert "environment variable RELAY_TEST_DB_URL is not set" in result.stdout
