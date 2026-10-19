"""Seam 4: `relay run` writes the gold layer, checked against the generator's manifest."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from relay_engine.cli import app
from relay_engine.generator.generate import generate
from relay_engine.generator.model import AnomalyType

runner = CliRunner()
EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"
KEY = {"chantiers": "chantier_id", "factures": "facture_id"}
STRUCTURAL = {
    AnomalyType.ROW_DROPPED, AnomalyType.ROW_EXTRA,
    AnomalyType.FK_ORPHAN, AnomalyType.NATURAL_KEY_DUPLICATED,
}


def _run(entity: str, data: Path, out: Path) -> Path:
    before = set(out.iterdir()) if out.exists() else set()
    result = runner.invoke(
        app, ["run", str(EXAMPLES / f"{entity}.yaml"), "--data", str(data), "--out", str(out)]
    )
    assert result.exit_code == 0, result.stdout
    (run_dir,) = set(out.iterdir()) - before
    return run_dir


def test_structural_findings_match_the_manifest_exactly(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "out"
    manifest = generate(data, seed=42, rows=60)

    found: set[tuple[str, str]] = set()
    for entity in ("chantiers", "factures"):
        run_dir = _run(entity, data, out)
        rows = pl.read_parquet(run_dir / "gold" / "recon_finding" / "*.parquet")
        structural = rows.filter(pl.col("check_family").is_in(["completeness", "referential"]))
        assert structural["verdict"].unique().to_list() == ["FAIL"]
        found |= set(zip(structural["entity"], structural["match_key_value"], strict=True))

    expected = {
        (a.entity, f"{KEY[a.entity]}={a.match_key}")
        for a in manifest.anomalies
        if a.anomaly_type in STRUCTURAL
    }
    assert found == expected


def test_recon_run_summarises_the_verdict(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "out"
    generate(data, seed=42, rows=60)
    run_dir = _run("chantiers", data, out)

    runs = pl.read_parquet(run_dir / "gold" / "recon_run" / "*.parquet")
    findings = pl.read_parquet(run_dir / "gold" / "recon_finding" / "*.parquet")
    assert runs.height == 1
    run = runs.row(0, named=True)
    assert run["run_id"] == run_dir.name
    assert run["entity"] == "chantiers"
    assert run["verdict"] == "FAIL"
    assert run["fail"] == findings.filter(pl.col("verdict") == "FAIL").height
    assert run["total_rows_source"] == 60
    assert findings["run_id"].unique().to_list() == [run_dir.name]


def test_every_injected_anomaly_is_found_with_its_expected_verdict(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "out"
    manifest = generate(data, seed=42, rows=60)

    frames = [
        pl.read_parquet(_run(entity, data, out) / "gold" / "recon_finding" / "*.parquet")
        for entity in ("chantiers", "factures")
    ]
    found = pl.concat(frames)
    triples = set(zip(found["entity"], found["match_key_value"], found["verdict"], strict=True))

    for a in manifest.anomalies:
        key = f"{KEY[a.entity]}={a.match_key}"
        assert (a.entity, key, a.expected_verdict.value) in triples, a

    touched = {(a.entity, f"{KEY[a.entity]}={a.match_key}") for a in manifest.anomalies}
    assert {(e, k) for e, k, _ in triples} <= touched
