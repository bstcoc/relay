from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import polars as pl

from relay_engine.io.catalog import parse_sources
from relay_engine.io.readers import CatalogSource
from relay_engine.layers.silver import try_cast


def test_a_year_or_a_month_reads_as_its_first_day() -> None:
    values = pl.DataFrame({"v": ["2024", "2024-03", "2024-03-12", "nope"]})

    read = values.select(try_cast(pl.col("v"), pl.String(), "date")).to_series().to_list()

    assert read == [date(2024, 1, 1), date(2024, 3, 1), date(2024, 3, 12), None]


def test_a_date_time_with_an_offset_reads_as_utc() -> None:
    values = pl.DataFrame({"v": ["2024-03-12T10:00:00Z", "2024-03-12 10:00:00+02:00",
                                 "2024-03-12T10:00:00.5+0200"]})

    read = values.select(try_cast(pl.col("v"), pl.String(), "datetime")).to_series().to_list()

    assert read == [datetime(2024, 3, 12, 10), datetime(2024, 3, 12, 8),
                    datetime(2024, 3, 12, 8, 0, 0, 500000)]


def test_a_schema_comes_without_reading_the_whole_table(tmp_path: Path) -> None:
    (tmp_path / "clients.csv").write_text("code;name\n00412;Lyon\n", encoding="cp1252")
    pl.DataFrame({"code": ["00412"], "amount": [1.5]}).write_parquet(tmp_path / "sites.parquet")
    with sqlite3.connect(tmp_path / "erp.db") as db:
        db.execute("CREATE TABLE workers (id INTEGER, name TEXT)")
        db.executemany("INSERT INTO workers VALUES (?, ?)", [(i, "x") for i in range(5000)])
    catalog = CatalogSource(parse_sources({
        "clients": {"csv": "clients.csv", "delimiter": ";", "encoding": "cp1252"},
        "sites": {"parquet": "sites.parquet"},
        "workers": {"database": f"sqlite:///{tmp_path / 'erp.db'}", "table": "workers"},
    }, tmp_path))

    assert dict(catalog.schema("clients")) == {"code": pl.String, "name": pl.String}
    assert list(catalog.schema("sites")) == ["code", "amount"]
    assert dict(catalog.schema("workers")) == {"id": pl.Int64, "name": pl.String}
    assert catalog.head("workers", 10).get_column("id").to_list() == list(range(10))
    assert catalog.head("sites", 0).columns == ["code", "amount"]
    assert catalog.head("clients", 5).rows() == [("00412", "Lyon")]
