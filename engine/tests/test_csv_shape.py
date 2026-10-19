"""Seam 1: a CSV whose records do not have the header's fields stops before the run.

A line break inside an unquoted value splits a record in two half-empty rows;
read as is, they would reconcile as data. Blank lines are not records.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from relay_engine.cli import app
from relay_engine.io.catalog import CsvSource
from relay_engine.io.readers import CatalogSource, CsvShapeError

HEADER = "id;name;city"


def _read(tmp_path: Path, *lines: str) -> list[tuple]:
    path = tmp_path / "shops.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return CatalogSource({"shops": CsvSource(path, delimiter=";")}).read("shops").rows()


def test_a_record_split_by_a_line_break_stops_with_its_lines(tmp_path: Path) -> None:
    with pytest.raises(CsvShapeError) as exc:
        _read(tmp_path, HEADER, "1;Alpha;Lyon", "2;12 rue", "des Lilas;Paris", "3;Charlie;Nantes")
    assert str(exc.value) == (
        "shops.csv: 2 line(s) do not have the 3 fields of the header: "
        "line 3 (2 fields), line 4 (2 fields). A line break or a delimiter inside an "
        "unquoted value splits or widens a record: quote the value, or repair the export."
    )


def test_an_extra_field_stops_too_and_long_lists_are_cut(tmp_path: Path) -> None:
    rows = [f"{i};n;c;extra" for i in range(8)]
    with pytest.raises(CsvShapeError) as exc:
        _read(tmp_path, HEADER, *rows)
    assert "8 line(s) do not have the 3 fields of the header: line 2 (4 fields), " in str(
        exc.value
    )
    assert "line 6 (4 fields) and 3 more. A line break" in str(exc.value)


def test_a_quoted_line_break_is_one_record(tmp_path: Path) -> None:
    assert _read(tmp_path, HEADER, '1;"12 rue\ndes Lilas";Lyon') == [
        ("1", "12 rue\ndes Lilas", "Lyon"),
    ]


def test_blank_lines_are_not_records(tmp_path: Path) -> None:
    assert _read(tmp_path, HEADER, "1;Alpha;Lyon", "", "2;Bravo;Paris", "", "") == [
        ("1", "Alpha", "Lyon"), ("2", "Bravo", "Paris"),
    ]


def test_the_first_rows_of_a_csv_match_a_whole_read(tmp_path: Path) -> None:
    path = tmp_path / "shops.csv"
    lines = [HEADER, "1;Alpha;Lyon", "", "2;Bravo;Paris", "", "3;Charlie;Nantes", "4;D;Brest"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    shops = CatalogSource({"shops": CsvSource(path, delimiter=";")})
    whole = shops.read("shops")
    for rows in range(7):
        assert shops.head("shops", rows).equals(whole.head(rows)), rows


def test_the_cli_reports_a_data_error_not_a_spec_error(tmp_path: Path) -> None:
    (tmp_path / "legacy.csv").write_text(f"{HEADER}\n1;Alpha;Lyon\n2;Bra\nvo;Paris\n")
    (tmp_path / "target.csv").write_text(f"{HEADER}\n1;Alpha;Lyon\n")
    (tmp_path / "sources.yaml").write_text(
        'shops_legacy:\n  csv: legacy.csv\n  delimiter: ";"\n'
        'shops_target:\n  csv: target.csv\n  delimiter: ";"\n'
    )
    (tmp_path / "mapping.yaml").write_text(
        "version: 1\nentity: shops\nsource: {table: shops_legacy}\n"
        "target: {table: shops_target}\nmatch_key: [id]\ncolumns:\n"
        + "".join(f"  - {{source: {c}, target: {c}}}\n" for c in ("id", "name", "city"))
    )
    result = CliRunner().invoke(app, [
        "run", str(tmp_path / "mapping.yaml"), "--sources", str(tmp_path / "sources.yaml"),
        "--out", str(tmp_path / "runs"),
    ])
    assert result.exit_code == 1
    assert result.stdout.startswith("legacy.csv: 2 line(s) do not have the 3 fields")
    assert "Invalid" not in result.stdout
    assert not (tmp_path / "runs").exists()
