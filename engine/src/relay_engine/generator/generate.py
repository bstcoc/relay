"""Deterministic synthetic migration generator (increment 1).

Produces a legacy dataset, an ideal target derived from it, then injects a
fixed set of known anomalies into the target — each recorded in the manifest.
The manifest is the ground truth used to test later increments.
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

import polars as pl

from relay_engine.generator.model import (
    Anomaly,
    AnomalyType,
    ExpectedVerdict,
    Manifest,
)

_STREETS = ["rue Hugo", "avenue Zola", "rue Verne", "cours Mirabeau", "rue Carnot"]
_CITIES = [("Paris", "75001"), ("Lyon", "69002"), ("Nantes", "44000"),
           ("Lille", "59000"), ("Rennes", "35000")]
_LABELS = ["Rénovation", "Extension", "Gros œuvre", "Voirie", "Réfection toiture"]

_MONTANT = pl.Decimal(12, 2)


class ChantierLegacy(TypedDict):
    chantier: str
    lib: str
    mnt_marche: float
    dt_ouv: datetime
    adresse_complete: str


class ChantierTarget(TypedDict):
    chantier_id: str
    libelle: str
    montant_marche: Decimal
    date_ouverture: date
    rue: str
    code_postal: str
    ville: str


class FactureLegacy(TypedDict):
    facture: str
    chantier: str
    mnt_ht: float
    dt: datetime


class FactureTarget(TypedDict):
    facture_id: str
    chantier_id: str
    montant_hors_taxes: Decimal
    date_facture: date


def _money(x: float) -> Decimal:
    return Decimal(str(round(x, 2)))


def generate(out_dir: Path, seed: int = 42, rows: int = 100) -> Manifest:
    """Generate the datasets and manifest under ``out_dir``. Returns the manifest."""
    rng = random.Random(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chantiers_legacy: list[ChantierLegacy] = []
    chantiers_target: list[ChantierTarget] = []
    for i in range(rows):
        cid = f"C{i:05d}"
        num = rng.randint(1, 200)
        street = rng.choice(_STREETS)
        city, cp = rng.choice(_CITIES)
        montant = rng.uniform(10_000, 900_000)
        opened = datetime(2020, 1, 1) + timedelta(days=rng.randint(0, 1800),
                                                  hours=rng.randint(0, 23))
        label = rng.choice(_LABELS)
        chantiers_legacy.append(ChantierLegacy(
            chantier=cid, lib=f"  {label}  ", mnt_marche=round(montant, 2),
            dt_ouv=opened, adresse_complete=f"{num} {street}, {cp}, {city}",
        ))
        chantiers_target.append(ChantierTarget(
            chantier_id=cid, libelle=label, montant_marche=_money(montant),
            date_ouverture=opened.date(), rue=f"{num} {street}",
            code_postal=cp, ville=city,
        ))

    n_fact = rows * 2
    factures_legacy: list[FactureLegacy] = []
    factures_target: list[FactureTarget] = []
    for j in range(n_fact):
        fid = f"F{j:06d}"
        cid = f"C{rng.randint(0, rows - 1):05d}"
        ht = rng.uniform(500, 80_000)
        dt = datetime(2021, 1, 1) + timedelta(days=rng.randint(0, 1500),
                                              hours=rng.randint(0, 23))
        factures_legacy.append(FactureLegacy(facture=fid, chantier=cid,
                                             mnt_ht=round(ht, 2), dt=dt))
        factures_target.append(FactureTarget(facture_id=fid, chantier_id=cid,
                                             montant_hors_taxes=_money(ht),
                                             date_facture=dt.date()))

    anomalies: list[Anomaly] = []

    t1, t2, shifted, dropped, duplicated = rng.sample(range(rows), 5)
    orphaned, truncated_facture, negative = rng.sample(range(n_fact), 3)
    by_id = {r["chantier_id"]: r for r in chantiers_target}
    chantier = [f"C{i:05d}" for i in (t1, t2, shifted, dropped, duplicated)]

    for cid in chantier[:2]:
        ct = by_id[cid]
        ct["montant_marche"] = ct["montant_marche"] - Decimal("0.03")
        anomalies.append(Anomaly(
            "chantiers", cid, AnomalyType.VALUE_TRUNCATED,
            ExpectedVerdict.REVIEW, "montant_marche", "montant amputé de 0,03 €"))

    ct = by_id[chantier[2]]
    ct["date_ouverture"] = ct["date_ouverture"] + timedelta(days=1)
    anomalies.append(Anomaly(
        "chantiers", chantier[2], AnomalyType.DATE_SHIFTED,
        ExpectedVerdict.REVIEW, "date_ouverture", "date décalée d'un jour"))

    dropped_id = chantier[3]
    chantiers_target = [r for r in chantiers_target if r["chantier_id"] != dropped_id]
    anomalies.append(Anomaly(
        "chantiers", dropped_id, AnomalyType.ROW_DROPPED,
        ExpectedVerdict.FAIL, None, "ligne source absente de la cible"))

    dup = by_id[chantier[4]]
    chantiers_target.append(dup)
    anomalies.append(Anomaly(
        "chantiers", dup["chantier_id"], AnomalyType.NATURAL_KEY_DUPLICATED,
        ExpectedVerdict.FAIL, "chantier_id", "clé naturelle en double"))

    ft = factures_target[orphaned]
    ft["chantier_id"] = f"C{max(rows, 99_999):05d}"
    anomalies.append(Anomaly(
        "factures", ft["facture_id"], AnomalyType.FK_ORPHAN,
        ExpectedVerdict.FAIL, "chantier_id", "FK vers un chantier inexistant"))

    extra_id = f"F{n_fact:06d}"
    factures_target.append(FactureTarget(
        facture_id=extra_id, chantier_id=chantiers_target[0]["chantier_id"],
        montant_hors_taxes=_money(1234.56), date_facture=date(2022, 6, 1)))
    anomalies.append(Anomaly(
        "factures", extra_id, AnomalyType.ROW_EXTRA,
        ExpectedVerdict.FAIL, None, "ligne cible sans source"))

    ft = factures_target[truncated_facture]
    ft["montant_hors_taxes"] = ft["montant_hors_taxes"] - Decimal("0.02")
    anomalies.append(Anomaly(
        "factures", ft["facture_id"], AnomalyType.VALUE_TRUNCATED,
        ExpectedVerdict.REVIEW, "montant_hors_taxes", "montant amputé de 0,02 €"))

    ft = factures_target[negative]
    ft["montant_hors_taxes"] = -ft["montant_hors_taxes"]
    anomalies.append(Anomaly(
        "factures", ft["facture_id"], AnomalyType.BUSINESS_RULE_VIOLATED,
        ExpectedVerdict.FAIL, "montant_hors_taxes", "montant de facture négatif"))

    for ft in factures_target:
        if ft["chantier_id"] == dropped_id:
            anomalies.append(Anomaly(
                "factures", ft["facture_id"], AnomalyType.FK_ORPHAN,
                ExpectedVerdict.FAIL, "chantier_id",
                f"FK vers le chantier {dropped_id}, supprimé par la migration"))

    schemas = {
        "chantiers_target": {"montant_marche": _MONTANT},
        "factures_target": {"montant_hors_taxes": _MONTANT},
    }
    frames: dict[str, list[object]] = {
        "chantiers_legacy": list(chantiers_legacy),
        "chantiers_target": list(chantiers_target),
        "factures_legacy": list(factures_legacy),
        "factures_target": list(factures_target),
    }
    for name, data in frames.items():
        pl.DataFrame(data, schema_overrides=schemas.get(name)).write_parquet(
            out_dir / f"{name}.parquet"
        )

    manifest = Manifest(seed=seed, entities=["chantiers", "factures"], anomalies=anomalies)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False)
    )
    return manifest
