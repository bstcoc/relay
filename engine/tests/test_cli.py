"""Walking-skeleton tests: the CLI is wired and responds."""

from __future__ import annotations

from typer.testing import CliRunner

from relay_engine import __version__
from relay_engine.cli import app

runner = CliRunner()


def test_version_command_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Relay" in result.stdout


def test_generate_command_exists() -> None:
    result = runner.invoke(app, ["generate"])
    assert result.exit_code == 0


def test_validate_accepts_reference_mapping(tmp_path) -> None:
    from pathlib import Path

    from relay_engine.generator.generate import generate

    generate(tmp_path, seed=42, rows=20)
    mapping = Path(__file__).parent.parent / "examples" / "mappings" / "chantiers.yaml"
    result = runner.invoke(app, ["validate", str(mapping), "--data", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert "valid" in result.stdout


def test_validate_rejects_broken_mapping_with_exit_1(tmp_path) -> None:
    from relay_engine.generator.generate import generate

    generate(tmp_path, seed=42, rows=20)
    broken = tmp_path / "broken.yaml"
    broken.write_text("""
version: 1
entity: chantiers
source: {table: chantiers_legacy}
target: {table: chantiers_target}
match_key: [chantier_id]
columns:
  - {source: chantier, target: chantier_id, type: string}
""")
    result = runner.invoke(app, ["validate", str(broken), "--data", str(tmp_path)])
    assert result.exit_code == 1
    assert "target column 'libelle' is not mapped" in result.stdout
