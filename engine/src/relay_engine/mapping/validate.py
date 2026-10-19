"""Semantic validation of a mapping spec against the real source/target schemas."""

from __future__ import annotations

from relay_engine.mapping.errors import MappingError
from relay_engine.mapping.model import MappingSpec
from relay_engine.mapping.scaffold import TODO


def validate_mapping(
    spec: MappingSpec,
    source_columns: list[str],
    target_columns: list[str],
    referenced_columns: dict[str, list[str]] | None = None,
) -> None:
    """Raise MappingError listing every mismatch between the spec and the schemas."""
    problems: list[str] = []

    existing = set(source_columns)
    for i, entry in enumerate(spec.columns):
        if entry.source is None:
            continue
        sources = [entry.source] if isinstance(entry.source, str) else entry.source
        for column in sources:
            if column == TODO:
                problems.append(
                    f"columns.{i} ({', '.join(entry.target_list())}): source column still TODO"
                )
            elif column not in existing:
                problems.append(f"source column '{column}' does not exist in the source data")

    declared = spec.entries_by_target()
    for column in target_columns:
        if column not in declared:
            problems.append(f"target column '{column}' is not mapped by any entry")
    for column in declared:
        if column not in target_columns:
            problems.append(f"target column '{column}' does not exist in the target data")

    mapped = set(spec.target_columns())

    for key in spec.match_key:
        if key == TODO:
            problems.append("match_key: still TODO, name the target column(s) that identify a row")
        elif key in declared and declared[key].target_only:
            problems.append(
                f"match_key '{key}' is a target-only column: it has no source to match"
            )
        elif key not in mapped:
            problems.append(
                f"match_key '{key}' is not a target column produced by the mapping"
            )

    known_tables = referenced_columns or {}
    for i, ref in enumerate(spec.references):
        where = f"references.{i}"
        if ref.column not in mapped:
            problems.append(f"{where}: column '{ref.column}' is not a target column")
        if ref.table not in known_tables:
            problems.append(f"{where}: table '{ref.table}' does not exist")
        elif ref.key not in known_tables[ref.table]:
            problems.append(f"{where}: key '{ref.key}' does not exist in '{ref.table}'")

    for rule in spec.business_rules:
        if rule.cross is None:
            continue
        where = f"business rule '{rule.name}'"
        table = rule.cross.table
        for column, other in rule.cross.on.items():
            if column not in declared:
                problems.append(f"{where}: column '{column}' is not a target column")
            if table in known_tables and other not in known_tables[table]:
                problems.append(f"{where}: column '{other}' does not exist in '{table}'")
        if table not in known_tables:
            problems.append(f"{where}: table '{table}' does not exist")

    if problems:
        raise MappingError(problems)
