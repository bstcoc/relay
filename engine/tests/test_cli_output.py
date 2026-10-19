"""A clean command line — one sentence per error, findings grouped after a run."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from relay_engine.cli import app
from relay_engine.console import describe, summary_lines
from relay_engine.generator.generate import generate

runner = CliRunner()
EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"


def test_describe_joins_the_problems_of_a_spec_error() -> None:
    from relay_engine.mapping import MappingError

    assert describe(MappingError(["a is missing", "b is unknown"])) == "a is missing; b is unknown"


def test_describe_keeps_the_first_line_of_any_other_error() -> None:
    assert describe(RuntimeError("disk full\n  at somewhere deep")) == "disk full"
    assert describe(RuntimeError("")) == "RuntimeError"


def test_summary_groups_findings_most_frequent_first() -> None:
    found = pl.DataFrame({
        "verdict": ["REVIEW", "REVIEW", "FAIL"],
        "column": ["city", "city", None],
        "rule": ["value differs", "value differs", "target row has no source"],
    })
    assert summary_lines(found) == [
        "        2  REVIEW  city                  value differs",
        "        1  FAIL    (row)                 target row has no source",
    ]


def test_summary_folds_the_tail_beyond_the_limit() -> None:
    found = pl.DataFrame({
        "verdict": ["FAIL"] * 3, "column": ["a", "b", "c"], "rule": ["value differs"] * 3,
    })
    lines = summary_lines(found, limit=2)
    assert len(lines) == 3
    assert lines[-1] == "  … 1 more group(s)"


def test_a_run_ends_with_its_findings_grouped(tmp_path: Path) -> None:
    data = tmp_path / "data"
    generate(data, seed=42, rows=30)
    result = runner.invoke(
        app, ["run", str(EXAMPLES / "chantiers.yaml"), "--data", str(data),
              "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 0, result.stdout
    lines = result.stdout.splitlines()
    assert lines[0].startswith("Run ")
    assert any(line.lstrip()[:1].isdigit() and ("FAIL" in line or "REVIEW" in line)
               for line in lines[1:])
    assert lines[-2].startswith("Details: relay findings ")


def test_an_unexpected_error_is_one_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import relay_engine.pipeline

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("something broke deep inside\n  File x.py, line 3")

    monkeypatch.setattr(relay_engine.pipeline, "run_migration", explode)
    data = tmp_path / "data"
    generate(data, seed=42, rows=20)
    result = runner.invoke(
        app, ["run", str(EXAMPLES / "chantiers.yaml"), "--data", str(data),
              "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        "Run failed: something broke deep inside",
        "Details: rerun with relay --verbose.",
    ]


def test_verbose_shows_the_full_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import relay_engine.pipeline

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("something broke deep inside")

    monkeypatch.setattr(relay_engine.pipeline, "run_migration", explode)
    data = tmp_path / "data"
    generate(data, seed=42, rows=20)
    result = runner.invoke(
        app, ["--verbose", "run", str(EXAMPLES / "chantiers.yaml"), "--data", str(data),
              "--out", str(tmp_path / "out")],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)


def test_a_missing_file_is_a_plain_user_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1
    assert result.stdout.strip() == f"File not found: {tmp_path / 'nope.yaml'}"


def test_a_missing_run_folder_is_a_plain_user_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["findings", str(tmp_path / "no-run")])
    assert result.exit_code == 1
    assert result.stdout.strip() == f"No run found in {tmp_path / 'no-run'}."


def test_generate_speaks_english(tmp_path: Path) -> None:
    result = runner.invoke(app, ["generate", "--out", str(tmp_path / "g"), "--rows", "20"])
    assert result.exit_code == 0
    assert result.stdout.startswith(f"Generated in {tmp_path / 'g'}: 2 entities, ")


def test_a_migration_without_findings_prints_no_group() -> None:
    from relay_engine.checks.findings import empty_findings

    assert summary_lines(empty_findings(), by_entity=True) == []
