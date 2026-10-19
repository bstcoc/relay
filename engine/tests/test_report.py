"""A reconciliation report a client can read and sign, built from the gold layer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from relay_engine import report
from relay_engine.checks.findings import FINDING_COLUMNS
from relay_engine.cli import app
from relay_engine.generator.generate import generate
from relay_engine.report import render_report

ROOT = Path(__file__).parent.parent.parent
EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"


def _runs(**overrides: object) -> pl.DataFrame:
    row = {
        "run_id": "2026-10-01T100000_ab12", "entity": "chantiers",
        "started_at": datetime(2026, 10, 1, 10), "finished_at": datetime(2026, 10, 1, 10, 1),
        "engine_version": "0.1.0", "mapping_version": "a1b2c3d4e5f6",
        "total_rows_source": 1234567, "total_rows_target": 1234566,
        "pass": 1234560, "review": 1, "fail": 1, "accepted": 1, "verdict": "FAIL",
    }
    return pl.DataFrame([row | overrides])


def _finding(verdict: str, key: str, decision: str | None = None, **values: str) -> dict:
    row = dict.fromkeys(FINDING_COLUMNS) | {
        "entity": "chantiers", "check_family": "fidelity", "match_key_value": key,
        "column": "montant", "verdict": verdict, "rule": "value differs",
        "finding_key": key * 8, "source_value": "10.00", "target_value": "9.99",
    }
    return row | values | {"decision": decision}


def _found(*rows: dict) -> pl.DataFrame:
    schema = dict.fromkeys([*FINDING_COLUMNS, "decision"], pl.String)
    return pl.DataFrame(list(rows), schema=schema)


def test_the_headline_states_the_migration_verdict() -> None:
    empty = _found()
    assert "The migration is verified" in render_report(_runs(verdict="PASS"), empty)
    assert "The migration needs a review" in render_report(_runs(verdict="REVIEW"), empty)
    assert "The migration has failures" in render_report(_runs(verdict="FAIL"), empty)


def test_counts_are_exact_with_thin_spaces() -> None:
    html = render_report(_runs(), _found())
    assert "1 234 567 source rows" in html


def test_decisions_apply_and_show_their_reason() -> None:
    found = _found(
        _finding("REVIEW", "id=1", "accepted"),
        _finding("REVIEW", "id=2", "rejected"),
        _finding("REVIEW", "id=3"),
    )
    decisions = pl.DataFrame({
        "finding_key": ["id=1" * 8, "id=1" * 8],
        "decision": ["rejected", "accepted"],
        "decided_by": ["bastien", "claire"],
        "decided_at": [datetime(2026, 9, 1), datetime(2026, 9, 2)],
        "reason": ["first look", "known rounding"],
    })
    html = render_report(_runs(), found, decisions)
    detail = html.split("Discrepancies in detail")[1]
    assert detail.index("id=2") < detail.index("id=3") < detail.index("id=1")
    decided = html.split(">Decisions<")[1]
    assert "known rounding" in decided and "claire" in decided
    assert "first look" not in decided


def test_values_are_escaped() -> None:
    found = _found(_finding("FAIL", "id=<b>", target_value="<script>alert(1)</script>"))
    html = render_report(_runs(), found)
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "id=&lt;b&gt;" in html


def test_a_long_detail_is_cut_and_says_so(monkeypatch) -> None:
    monkeypatch.setattr(report, "DETAIL_LIMIT", 2)
    found = _found(*(_finding("REVIEW", f"id={i}") for i in range(5)))
    html = render_report(_runs(), found)
    assert "First 2 of 5." in html
    assert "id=4" not in html.split("Discrepancies in detail")[1]


def test_a_run_writes_its_report(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "out"
    generate(data, seed=42, rows=30)
    result = CliRunner().invoke(
        app, ["run", str(EXAMPLES), "--data", str(data), "--out", str(out),
              "--decisions", str(tmp_path / "decisions")],
    )
    assert result.exit_code == 0, result.stdout
    (written,) = out.glob("*/report.html")
    assert result.stdout.rstrip().endswith(f"Report: {written}")
    html = written.read_text(encoding="utf-8")
    assert "The migration has failures" in html
    for entity in ("chantiers", "factures"):
        assert f"<td>{entity}</td>" in html
