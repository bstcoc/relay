"""Seam 3: `relay decide`, then a new run inherits the decision."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from relay_engine.cli import app
from relay_engine.generator.generate import generate

runner = CliRunner()
MAPPING = str(Path(__file__).parent.parent / "examples" / "mappings" / "chantiers.yaml")


def _run(data: Path, out: Path, decisions: Path) -> Path:
    before = set(out.iterdir()) if out.exists() else set()
    result = runner.invoke(app, [
        "run", MAPPING, "--data", str(data), "--out", str(out), "--decisions", str(decisions),
    ])
    assert result.exit_code == 0, result.stdout
    (run_dir,) = set(out.iterdir()) - before
    return run_dir


def _gold(run_dir: Path, table: str) -> pl.DataFrame:
    return pl.read_parquet(run_dir / "gold" / table / "*.parquet")


def test_an_accepted_review_is_not_asked_again(tmp_path: Path) -> None:
    data, out, decisions = tmp_path / "data", tmp_path / "out", tmp_path / "decisions"
    generate(data, seed=42, rows=40)

    first = _run(data, out, decisions)
    listing = runner.invoke(app, ["findings", str(first)])
    assert listing.exit_code == 0
    review = _gold(first, "recon_finding").filter(pl.col("verdict") == "REVIEW").row(0, named=True)
    assert review["finding_key"] in listing.stdout

    decided = runner.invoke(app, [
        "decide", review["finding_key"], "--accept", "--reason", "arrondi connu",
        "--decisions", str(decisions),
    ])
    assert decided.exit_code == 0, decided.stdout

    second = _run(data, out, decisions)
    again = _gold(second, "recon_finding").filter(pl.col("finding_key") == review["finding_key"])
    assert again["decision"].to_list() == ["accepted"]

    before, after = _gold(first, "recon_run").row(0, named=True), _gold(second, "recon_run").row(
        0, named=True
    )
    assert after["review"] == before["review"] - 1
    assert after["accepted"] == 1
    assert not str(decisions).startswith(str(out))


def test_decide_rejects_a_malformed_finding_key(tmp_path: Path) -> None:
    for bad in ("", "abc123", "Z" * 64):
        result = runner.invoke(app, [
            "decide", bad, "--accept", "--reason", "x", "--decisions", str(tmp_path),
        ])
        assert result.exit_code == 1, bad
        assert "64 hexadecimal characters" in result.stdout
    assert not (tmp_path / "recon_decision").exists()
