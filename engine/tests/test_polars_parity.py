"""Parity with the Spark engine and robustness on real sources."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from conftest import frame, prepared
from relay_engine.checks.business_rules import check_business_rules
from relay_engine.checks.findings import text
from relay_engine.io.catalog import CsvSource, SourcesError, load_sources
from relay_engine.io.readers import CatalogSource
from relay_engine.layers.silver import try_cast
from relay_engine.mapping import MappingError, MappingSpec


def _cast(values: list[object], declared: str, dtype: pl.DataType) -> list[object]:
    series = pl.Series("v", values, dtype=dtype)
    return series.to_frame().select(try_cast(pl.col("v"), dtype, declared)).to_series().to_list()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("12.345", "12.35"), ("-12.345", "-12.35"), ("0.125", "0.13"), ("1 234", None)],
)
def test_decimal_casts_round_half_up_like_spark(value: str, expected: str | None) -> None:
    [got] = _cast([value], "decimal(12,2)", pl.String())
    assert got == (Decimal(expected) if expected is not None else None)


def test_a_wider_decimal_rounds_half_up_too() -> None:
    [got] = _cast([Decimal("12.345")], "decimal(12,2)", pl.Decimal(12, 3))
    assert got == Decimal("12.35")


def test_datetime_text_keeps_its_fraction_like_spark() -> None:
    df = frame([(datetime(2024, 1, 1, 10, 0, 0, 500000),), (datetime(2024, 1, 1, 10, 0),)],
               "t timestamp")
    assert df.select(text(df, "t")).to_series().to_list() == [
        "2024-01-01 10:00:00.5", "2024-01-01 10:00:00",
    ]


RULE_SPEC = {
    "version": 1, "entity": "e", "source": {"table": "s"}, "target": {"table": "t"},
    "match_key": ["id"],
    "columns": [{"source": "id", "target": "id", "type": "string"},
                {"source": "m", "target": "m", "type": "string"}],
}


def test_a_rule_that_cannot_run_is_a_mapping_error_not_a_crash() -> None:
    spec = MappingSpec.model_validate(
        {**RULE_SPEC, "business_rules": [{"name": "positive", "check": "m > 0"}]}
    )
    target = frame([("k1", "12")], "id string, m string")
    with pytest.raises(MappingError) as error:
        check_business_rules(prepared(spec, target, target), spec)
    assert error.value.problems[0].startswith("business rule 'positive': ")


def test_a_missing_sqlite_file_is_reported_and_not_created(tmp_path: Path) -> None:
    (tmp_path / "sources.yaml").write_text("t:\n  database: sqlite:///nope.db\n  table: x\n")
    with pytest.raises(SourcesError) as error:
        load_sources(tmp_path / "sources.yaml")
    assert error.value.problems == ["t: file nope.db does not exist"]
    assert not (tmp_path / "nope.db").exists()


def test_a_missing_sqlite_table_is_a_sources_error(tmp_path: Path) -> None:
    sqlite3.connect(tmp_path / "erp.db").close()
    (tmp_path / "sources.yaml").write_text("t:\n  database: sqlite:///erp.db\n  table: x\n")
    with pytest.raises(SourcesError) as error:
        CatalogSource(load_sources(tmp_path / "sources.yaml")).read("t")
    assert error.value.problems[0].startswith("t: cannot read table x: ")


def test_a_sqlite_url_may_carry_options(tmp_path: Path) -> None:
    with sqlite3.connect(tmp_path / "erp.db") as conn:
        conn.execute("CREATE TABLE shop (id TEXT)")
        conn.execute("INSERT INTO shop VALUES ('k1')")
    (tmp_path / "sources.yaml").write_text(
        "t:\n  database: sqlite:///erp.db?mode=ro\n  table: shop\n"
    )
    assert CatalogSource(load_sources(tmp_path / "sources.yaml")).read("t").height == 1


def test_a_wrongly_encoded_csv_names_the_file_and_the_fix(tmp_path: Path) -> None:
    csv = tmp_path / "export.csv"
    csv.write_bytes("id;ville\nk1;Orléans\n".encode("cp1252"))
    with pytest.raises(SourcesError) as error:
        CatalogSource({"t": CsvSource(csv=csv, delimiter=";")}).read("t")
    assert error.value.problems == [
        "export.csv is not utf-8: declare its encoding, e.g. `encoding: cp1252`"
    ]


def test_a_cp1252_csv_is_read(tmp_path: Path) -> None:
    csv = tmp_path / "export.csv"
    csv.write_bytes("id;ville\nk1;Orléans\n".encode("cp1252"))
    read = CatalogSource({"t": CsvSource(csv=csv, delimiter=";", encoding="cp1252")}).read("t")
    assert read.row(0) == ("k1", "Orléans")


def test_a_database_connection_failure_is_a_sources_error() -> None:
    pytest.importorskip("connectorx")
    from relay_engine.io.catalog import DatabaseSource

    catalog = CatalogSource({
        "t": DatabaseSource(
            database="postgresql://relay:x@127.0.0.1:notaport/erp", table="chantier"
        )
    })
    with pytest.raises(SourcesError) as error:
        catalog.read("t")
    assert error.value.problems[0].startswith("t: cannot read table chantier: ")
