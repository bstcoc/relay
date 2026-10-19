"""TDD for the synthetic data generator (increment 1)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from relay_engine.generator.generate import generate
from relay_engine.generator.model import AnomalyType, ExpectedVerdict

ENTITIES = ("chantiers", "factures")


def _read(out: Path, name: str) -> pl.DataFrame:
    return pl.read_parquet(out / f"{name}.parquet")


def test_generate_creates_all_files(tmp_path: Path) -> None:
    generate(tmp_path, seed=42, rows=50)
    for entity in ENTITIES:
        assert (tmp_path / f"{entity}_legacy.parquet").exists()
        assert (tmp_path / f"{entity}_target.parquet").exists()
    assert (tmp_path / "manifest.json").exists()


def test_generate_is_deterministic(tmp_path: Path) -> None:
    a = generate(tmp_path / "a", seed=7, rows=40)
    b = generate(tmp_path / "b", seed=7, rows=40)
    assert a.to_dict() == b.to_dict()
    for entity in ENTITIES:
        assert _read(tmp_path / "a", f"{entity}_target").equals(
            _read(tmp_path / "b", f"{entity}_target")
        )


def test_different_seed_differs(tmp_path: Path) -> None:
    a = generate(tmp_path / "a", seed=1, rows=40)
    b = generate(tmp_path / "b", seed=2, rows=40)
    assert a.to_dict() != b.to_dict()


def test_manifest_is_well_formed(tmp_path: Path) -> None:
    manifest = generate(tmp_path, seed=42, rows=80)
    assert manifest.anomalies, "the generator must inject at least one anomaly"
    valid_types = {t.value for t in AnomalyType}
    valid_verdicts = {v.value for v in ExpectedVerdict}
    on_disk = json.loads((tmp_path / "manifest.json").read_text())
    assert on_disk == manifest.to_dict()
    for a in on_disk["anomalies"]:
        assert a["anomaly_type"] in valid_types
        assert a["expected_verdict"] in valid_verdicts
        assert a["entity"] in ENTITIES
        assert a["match_key"]


def test_dropped_rows_absent_from_target(tmp_path: Path) -> None:
    manifest = generate(tmp_path, seed=42, rows=80)
    dropped = [
        a for a in manifest.anomalies if a.anomaly_type is AnomalyType.ROW_DROPPED
    ]
    assert dropped, "expected at least one dropped-row anomaly"
    for a in dropped:
        target = _read(tmp_path, f"{a.entity}_target")
        key_col = "chantier_id" if a.entity == "chantiers" else "facture_id"
        assert a.match_key not in target[key_col].to_list()


@pytest.mark.parametrize("rows", [80, 100_000])
def test_fk_orphans_point_nowhere(tmp_path: Path, rows: int) -> None:
    manifest = generate(tmp_path, seed=42, rows=rows)
    orphans = [
        a for a in manifest.anomalies if a.anomaly_type is AnomalyType.FK_ORPHAN
    ]
    assert orphans, "expected at least one FK-orphan anomaly"
    chantier_ids = set(_read(tmp_path, "chantiers_target")["chantier_id"].to_list())
    factures = _read(tmp_path, "factures_target")
    for a in orphans:
        row = factures.filter(pl.col("facture_id") == a.match_key)
        assert row.height == 1
        assert row["chantier_id"].item() not in chantier_ids


def test_every_orphan_in_the_data_is_in_the_manifest(tmp_path: Path) -> None:
    manifest = generate(tmp_path, seed=42, rows=60)
    chantier_ids = set(_read(tmp_path, "chantiers_target")["chantier_id"].to_list())
    factures = _read(tmp_path, "factures_target")
    orphans_in_data = set(
        factures.filter(~pl.col("chantier_id").is_in(list(chantier_ids)))["facture_id"].to_list()
    )
    recorded = {a.match_key for a in manifest.anomalies if a.anomaly_type is AnomalyType.FK_ORPHAN}
    assert len(orphans_in_data) > 1, "seed must produce a cascade, or this test proves nothing"
    assert orphans_in_data == recorded


def test_injected_anomalies_never_share_a_row(tmp_path: Path) -> None:
    cascade = "supprimé par la migration"
    for seed in range(1, 31):
        manifest = generate(tmp_path / str(seed), seed=seed, rows=60)
        for entity in ENTITIES:
            keys = [
                a.match_key for a in manifest.anomalies
                if a.entity == entity and cascade not in a.detail
            ]
            assert len(keys) == len(set(keys)), (seed, entity, keys)


def test_business_rule_violation_is_injected(tmp_path: Path) -> None:
    manifest = generate(tmp_path, seed=42, rows=60)
    violations = [
        a for a in manifest.anomalies if a.anomaly_type is AnomalyType.BUSINESS_RULE_VIOLATED
    ]
    assert [(a.entity, a.expected_verdict) for a in violations] == [
        ("factures", ExpectedVerdict.FAIL)
    ]
    factures = _read(tmp_path, "factures_target")
    row = factures.filter(pl.col("facture_id") == violations[0].match_key)
    assert row["montant_hors_taxes"].item() < 0
