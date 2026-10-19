"""Seam 1: the sources catalog — where each table is read from."""

from __future__ import annotations

from pathlib import Path

import pytest

from relay_engine.io.catalog import (
    CsvSource,
    DatabaseSource,
    ParquetSource,
    SourcesError,
    load_sources,
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(body)
    return path


def test_each_kind_loads_with_paths_relative_to_the_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "chantiers.csv").write_text("a;b\n")
    (tmp_path / "factures.parquet").write_text("")
    (tmp_path / "erp.db").write_bytes(b"")
    monkeypatch.setenv("RELAY_TARGET_PASSWORD", "s3cret")

    sources = load_sources(_write(tmp_path, """
chantiers_legacy:
  csv: exports/chantiers.csv
  delimiter: ";"
  encoding: cp1252
factures_legacy:
  parquet: factures.parquet
chantiers_target:
  database: postgresql://relay:${RELAY_TARGET_PASSWORD}@db:5432/erp
  table: public.chantier
local_target:
  database: sqlite:///erp.db
  table: chantier
"""))

    assert sources["chantiers_legacy"] == CsvSource(
        csv=tmp_path / "exports" / "chantiers.csv", delimiter=";", encoding="cp1252"
    )
    assert sources["factures_legacy"] == ParquetSource(parquet=tmp_path / "factures.parquet")
    target = sources["chantiers_target"]
    assert target == DatabaseSource(
        database="postgresql://relay:s3cret@db:5432/erp", table="public.chantier"
    )
    assert sources["local_target"] == DatabaseSource(
        database=f"sqlite:///{tmp_path.resolve() / 'erp.db'}", table="chantier"
    )


def test_problems_are_all_reported_readably(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RELAY_MISSING", raising=False)
    with pytest.raises(SourcesError) as exc:
        load_sources(_write(tmp_path, """
a:
  csv: nowhere.csv
b:
  database: ${RELAY_MISSING}
  table: t
c:
  excel: x.xlsx
d:
  database: oracle://db/erp
  table: t
"""))
    assert exc.value.problems == [
        "a: file nowhere.csv does not exist",
        "b: environment variable RELAY_MISSING is not set",
        "c: declare exactly one of parquet, csv or database",
        "d: unsupported database URL 'oracle' (postgresql, postgres, mysql, mssql, sqlite)",
    ]
