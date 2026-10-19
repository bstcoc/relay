"""A real-data scenario.

A scenario is a folder kept outside the repository: the mapping (the intent),
the sources catalog, a migration written without Relay and, for tier 2, the
intents the mapping cannot express yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from relay_engine.mapping import MappingError, MappingSpec, load_mapping

TARGET_VARIABLE = "RELAY_ORACLE_TARGET"
_TARGET_REF = f"${{{TARGET_VARIABLE}}}"
_RELAY_IMPORT = re.compile(r"^\s*(import|from)\s+relay_engine\b", re.MULTILINE)
_REQUIRED = ("mapping.yaml", "sources.yaml", "migrate.py")


class ScenarioError(Exception):
    """The scenario is unusable. Carries every problem found."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("Invalid scenario:\n" + "\n".join(f"  - {p}" for p in problems))


class Expectation(BaseModel):
    """The findings an intent should produce: every declared field must match."""

    model_config = ConfigDict(extra="forbid")

    check: str | None = None
    column: str | None = None
    rule: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> Expectation:
        if self.check is None and self.column is None and self.rule is None:
            raise ValueError("expects declares at least one of check, column or rule")
        return self

    def matches(self, check_family: str, column: str | None, rule: str) -> bool:
        return (
            (self.check is None or self.check == check_family)
            and (self.column is None or self.column == column)
            and (self.rule is None or self.rule == rule)
        )


class Intent(BaseModel):
    """Something the migration does on purpose that the mapping cannot declare."""

    model_config = ConfigDict(extra="forbid")

    name: str
    why: str
    expects: Expectation


class _Intents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intents: list[Intent]


@dataclass(frozen=True)
class Scenario:
    root: Path
    mapping: MappingSpec
    sources: Path
    migrate: Path
    target_table: str
    intents: list[Intent]
    tier: int


def _target_table(sources: Path, table: str) -> tuple[str | None, str | None]:
    """The SQLite table behind the target, or the reason it cannot be used."""
    entry = (yaml.safe_load(sources.read_text()) or {}).get(table)
    if not isinstance(entry, dict):
        return None, f"sources.yaml: target table {table} is not declared"
    if str(entry.get("database", "")) != f"sqlite:///{_TARGET_REF}":
        return None, (
            f"sources.yaml: target table {table} must be read from "
            f"database: sqlite:///{_TARGET_REF}"
        )
    if "table" not in entry:
        return None, f"sources.yaml: target table {table} needs a table"
    return str(entry["table"]), None


def _intents(path: Path) -> tuple[list[Intent], list[str]]:
    try:
        raw = yaml.safe_load(path.read_text()) or {}
        return _Intents.model_validate(raw).intents, []
    except ValidationError as error:
        return [], [
            f"intents.yaml: {'.'.join(str(part) for part in e['loc'])}: {e['msg']}"
            for e in error.errors()
        ]


def load_scenario(root: Path) -> Scenario:
    """Load a scenario folder; raise ScenarioError listing every problem at once."""
    root = Path(root).resolve()
    missing = [f"{name} is missing" for name in _REQUIRED if not (root / name).is_file()]
    if missing:
        raise ScenarioError(missing)

    problems: list[str] = []
    mapping: MappingSpec | None = None
    try:
        mapping = load_mapping(root / "mapping.yaml")
    except MappingError as error:
        problems += [f"mapping.yaml: {p}" for p in error.problems]
    if mapping is not None and (mapping.business_rules or mapping.references):
        problems.append(
            "mapping.yaml: business_rules and references are not supported by the oracle yet"
        )

    if _RELAY_IMPORT.search((root / "migrate.py").read_text()):
        problems.append("migrate.py imports relay_engine: the migration must not know Relay")

    target_table: str | None = None
    if mapping is not None:
        target_table, problem = _target_table(root / "sources.yaml", mapping.target.table)
        if problem:
            problems.append(problem)

    intents_path = root / "intents.yaml"
    intents: list[Intent] = []
    if intents_path.is_file():
        intents, intent_problems = _intents(intents_path)
        problems += intent_problems

    if problems or mapping is None or target_table is None:
        raise ScenarioError(problems)
    return Scenario(
        root=root,
        mapping=mapping,
        sources=root / "sources.yaml",
        migrate=root / "migrate.py",
        target_table=target_table,
        intents=intents,
        tier=2 if intents_path.is_file() else 1,
    )
