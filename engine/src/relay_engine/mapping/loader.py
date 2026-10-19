"""Load a mapping spec from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from relay_engine.mapping.errors import MappingError
from relay_engine.mapping.model import MappingSpec


def _describe(error: ValidationError) -> list[str]:
    problems = []
    for e in error.errors():
        where = ".".join(str(p) for p in e["loc"]) or "<root>"
        if e["type"] == "missing":
            problems.append(f"{where}: field is required")
        elif e["type"] == "value_error":
            problems.append(f"{where}: {e['ctx']['error']}")
        else:
            problems.append(f"{where}: {e['msg']}")
    return problems


def load_mapping(path: Path) -> MappingSpec:
    """Parse and structurally validate a mapping spec file."""
    raw = yaml.safe_load(Path(path).read_text())
    try:
        return MappingSpec.model_validate(raw)
    except ValidationError as error:
        raise MappingError(_describe(error)) from error


def load_mappings(path: Path) -> list[MappingSpec]:
    """Every mapping of a folder (`*.yaml`, `*.yml`), by file name; or a single file.

    Every broken file is reported at once, each problem prefixed with its file name.
    """
    path = Path(path)
    if not path.is_dir():
        return [load_mapping(path)]
    files = sorted(p for p in path.iterdir() if p.suffix in (".yaml", ".yml"))
    if not files:
        raise MappingError([f"no mapping (*.yaml) in {path}"])
    specs: list[MappingSpec] = []
    problems: list[str] = []
    for file in files:
        try:
            specs.append(load_mapping(file))
        except MappingError as error:
            problems += [f"{file.name}: {p}" for p in error.problems]
    if problems:
        raise MappingError(problems)
    return specs
