"""Seam 1: scaffolding a mapping skeleton from the two real schemas."""

from __future__ import annotations

import yaml

from relay_engine.mapping.scaffold import scaffold_mapping

SOURCE = {"id": "string", "nom": "string", "mnt_ht": "float", "ancien_code": "string"}
TARGET = {"id": "string", "nom": "string", "montant_hors_taxes": "decimal(12,2)"}


def _skeleton() -> str:
    return scaffold_mapping("factures", "factures_legacy", SOURCE, "factures_target", TARGET)


def test_same_name_columns_are_prefilled_others_left_todo() -> None:
    spec = yaml.safe_load(_skeleton())
    assert spec["entity"] == "factures"
    assert spec["source"] == {"table": "factures_legacy"}
    assert spec["target"] == {"table": "factures_target"}
    assert spec["match_key"] == ["TODO"]
    assert spec["columns"] == [
        {"source": "id", "target": "id", "type": "string"},
        {"source": "nom", "target": "nom", "type": "string"},
        {"source": "TODO", "target": "montant_hors_taxes", "type": "decimal(12,2)"},
    ]


def test_never_guesses_between_different_names() -> None:
    assert "mnt_ht" not in [c["source"] for c in yaml.safe_load(_skeleton())["columns"]]


def test_unused_source_columns_are_listed() -> None:
    text = _skeleton()
    unused = text[text.index("Colonnes source sans usage"):]
    assert "mnt_ht" in unused
    assert "ancien_code" in unused
    assert "nom" not in unused.split("\n", 1)[1]


def test_validate_reports_each_todo_plainly(tmp_path) -> None:
    import pytest

    from relay_engine.mapping import MappingError, load_mapping, validate_mapping

    path = tmp_path / "factures.yaml"
    path.write_text(_skeleton())
    with pytest.raises(MappingError) as exc:
        validate_mapping(load_mapping(path), list(SOURCE), list(TARGET))
    assert exc.value.problems == [
        "columns.2 (montant_hors_taxes): source column still TODO",
        "match_key: still TODO, name the target column(s) that identify a row",
    ]


def test_scaffold_command_writes_a_skeleton_and_never_overwrites(tmp_path) -> None:
    from typer.testing import CliRunner

    from relay_engine.cli import app
    from relay_engine.generator.generate import generate

    runner = CliRunner()
    data, output = tmp_path / "data", tmp_path / "mappings" / "chantiers.yaml"
    generate(data, seed=42, rows=10)
    args = [
        "scaffold", "chantiers", "--source", "chantiers_legacy", "--target", "chantiers_target",
        "--data", str(data), "--output", str(output),
    ]

    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.stdout
    spec = yaml.safe_load(output.read_text())
    types = {c["target"]: c["type"] for c in spec["columns"]}
    assert types["chantier_id"] == "string"
    assert types["montant_marche"] == "decimal(12,2)"
    assert types["date_ouverture"] == "date"
    assert {c["source"] for c in spec["columns"]} == {"TODO"}

    output.write_text(output.read_text() + "# work in progress\n")
    again = runner.invoke(app, args)
    assert again.exit_code == 1
    assert "already exists" in again.stdout
    assert output.read_text().endswith("# work in progress\n")
