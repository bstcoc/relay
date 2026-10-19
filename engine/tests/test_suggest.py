"""Relay suggests which table and which column goes where, with score and reason."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import polars as pl

from relay_engine.generator.generate import generate
from relay_engine.io import LocalParquetStore
from relay_engine.mapping import validate_mapping
from relay_engine.pipeline import run
from relay_engine.suggest import name_score, suggest_columns, suggest_tables, to_mapping


def _generated(tmp_path: Path) -> dict[str, pl.DataFrame]:
    generate(tmp_path, seed=42, rows=40)
    return {p.stem: pl.read_parquet(p) for p in tmp_path.glob("*.parquet")}


def test_the_generated_migration_is_matched_table_by_table_and_column_by_column(
    tmp_path: Path,
) -> None:
    tables = _generated(tmp_path)
    legacy = {n: f for n, f in tables.items() if n.endswith("_legacy")}
    target = {n: f for n, f in tables.items() if n.endswith("_target")}
    matches = {m.source: m for m in suggest_tables(legacy, target)}
    assert {s: m.target for s, m in matches.items()} == {
        "chantiers_legacy": "chantiers_target",
        "factures_legacy": "factures_target",
    }
    chantiers = matches["chantiers_legacy"]
    assert {(c.source, c.target) for c in chantiers.columns} == {
        ("chantier", "chantier_id"), ("lib", "libelle"),
        ("mnt_marche", "montant_marche"), ("dt_ouv", "date_ouverture"),
    }
    assert all(c.sure for c in chantiers.columns)
    assert chantiers.unmatched_source == ["adresse_complete"]
    assert chantiers.unmatched_target == ["rue", "code_postal", "ville"]
    assert {(c.source, c.target) for c in matches["factures_legacy"].columns} == {
        ("facture", "facture_id"), ("chantier", "chantier_id"),
        ("mnt_ht", "montant_hors_taxes"), ("dt", "date_facture"),
    }


def test_the_suggested_mapping_is_valid_and_reconciles(tmp_path: Path) -> None:
    tables = _generated(tmp_path / "data")
    source, target = tables["chantiers_legacy"], tables["chantiers_target"]
    match = suggest_columns(source, target)
    match = type(match)("chantiers_legacy", "chantiers_target", match.score, match.columns,
                        match.unmatched_source, match.unmatched_target)
    spec = to_mapping(match, source, target, entity="chantiers")
    validate_mapping(spec, source.columns, target.columns)
    assert spec.match_key == ["chantier_id"]
    entries = {e.target if isinstance(e.target, str) else e.source: e for e in spec.columns}
    assert entries["libelle"].normalize == ["trim"]
    assert entries["date_ouverture"].normalize == ["date_only"]
    assert entries["montant_marche"].type == "decimal(12,2)"
    assert entries["adresse_complete"].exclude
    assert entries["rue"].target_only
    summary = run(spec, LocalParquetStore(tmp_path / "data"), LocalParquetStore(tmp_path / "out"),
                  "r1")
    assert summary.entity == "chantiers"


def test_identical_schemas_match_entirely_and_surely() -> None:
    frame = pl.DataFrame({"id": ["a", "b"], "nom": ["Ana", "Bo"], "montant": [1.5, 2.0]})
    match = suggest_columns(frame, frame.clear())
    assert [(c.source, c.target, c.score, c.reason) for c in match.columns] == [
        ("id", "id", 1.0, "same name"),
        ("nom", "nom", 1.0, "same name"),
        ("montant", "montant", 1.0, "same name"),
    ]


def test_an_empty_target_is_matched_on_names_synonyms_and_initials() -> None:
    source = pl.DataFrame({"nom_client": ["Ana"], "mnt_ht": [1.0], "dt_cde": [date(2024, 1, 1)]})
    target = pl.DataFrame(schema={
        "customer_name": pl.String, "order_date": pl.Date,
        "montant_hors_taxes": pl.Decimal(12, 2),
    })
    match = suggest_columns(source, target)
    assert {(c.source, c.target) for c in match.columns} == {
        ("nom_client", "customer_name"), ("mnt_ht", "montant_hors_taxes"),
        ("dt_cde", "order_date"),
    }


def test_values_of_different_kinds_lower_the_score() -> None:
    match = suggest_columns(
        pl.DataFrame({"ref": [1, 2, 3]}),
        pl.DataFrame({"ref": [datetime(2024, 1, d) for d in (1, 2, 3)]}),
    )
    (column,) = match.columns
    assert "number vs date" in column.reason
    assert column.score < 1


def test_name_scores() -> None:
    assert name_score("mnt_ht", "montant_hors_taxes") >= 0.85
    assert name_score("CustomerName", "customer_name") == 1.0
    assert name_score("ville", "city") == 1.0
    assert name_score("ville", "montant") < 0.4


def test_french_contact_headers_find_their_english_columns() -> None:
    source = pl.DataFrame(schema={c: pl.String for c in [
        "Type", "Nom", "Prénom", "Fonction", "Fixe", "Portable", "N° poste", "Mail", "Enseigne(s)",
    ]})
    target = pl.DataFrame(schema={c: pl.String for c in [
        "contact_type", "last_name", "first_name", "job_title", "phone", "mobile", "extension",
        "email", "brand",
    ]})
    match = suggest_columns(source, target)
    assert [(c.source, c.target) for c in match.columns] == list(
        zip(source.columns, target.columns, strict=True)
    )


def test_many_distinct_values_all_shared_are_enough_to_be_sure() -> None:
    values = [f"agent{i}@example.org" for i in range(30)]
    (column,) = suggest_columns(
        pl.DataFrame({"x9": values}), pl.DataFrame({"y2": list(reversed(values))})
    ).columns
    assert column.sure
    few = ["a", "b", "c"]
    (column,) = suggest_columns(pl.DataFrame({"x9": few}), pl.DataFrame({"y2": few})).columns
    assert not column.sure
