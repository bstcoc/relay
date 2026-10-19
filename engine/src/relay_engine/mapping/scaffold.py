"""Scaffold a mapping skeleton from the real source and target schemas.

The skeleton lists every target column. A source column with exactly the same
name is pre-filled; anything else is left as TODO. It never pairs two different
names, however alike: naming the link is a human decision (AGENTS.md).
"""

from __future__ import annotations

import polars as pl

TODO = "TODO"


def spec_type(dtype: pl.DataType) -> str:
    """The mapping-spec type of a column, as Polars reads it (Parquet, CSV, database)."""
    if isinstance(dtype, pl.Decimal):
        return f"decimal({dtype.precision},{dtype.scale})"
    if dtype.is_integer():
        return "integer"
    if dtype.is_float():
        return "float"
    if dtype == pl.String:
        return "string"
    if dtype == pl.Date:
        return "date"
    if isinstance(dtype, pl.Datetime):
        return "datetime"
    if dtype == pl.Boolean:
        return "boolean"
    raise ValueError(f"unsupported column type {dtype}")


_HEADER = """\
# Squelette généré par `relay scaffold`. Compléter chaque TODO, puis lancer
# `relay validate` : il liste ce qui reste à faire. Voir docs/mapping-spec.md.
"""


def scaffold_mapping(
    entity: str,
    source_table: str,
    source_schema: dict[str, str],
    target_table: str,
    target_schema: dict[str, str],
) -> str:
    """Return the YAML skeleton. Schemas map column names to spec types."""
    lines = [
        _HEADER,
        "version: 1",
        f"entity: {entity}",
        "",
        "source:",
        f"  table: {source_table}",
        "target:",
        f"  table: {target_table}",
        "",
        "# TODO: the target column(s) that identify a row.",
        "match_key:",
        f"  - {TODO}",
        "",
        "columns:",
    ]
    used: set[str] = set()
    for column, declared_type in target_schema.items():
        if column in source_schema:
            used.add(column)
            lines.append(f"  - source: {column}")
        else:
            lines.append(
                f"  - source: {TODO}  # quelle colonne source alimente {column} ? "
                "(aucune : target_only: true, sans source ni type)"
            )
        lines += [f"    target: {column}", f"    type: {declared_type}", ""]

    unused = [c for c in source_schema if c not in used]
    if unused:
        lines += [
            "# Colonnes source sans usage : les mapper ci-dessus, ou les exclure avec",
            "#   - source: <colonne>",
            "#     exclude: true",
            "#     reason: <pourquoi elle n'est pas migrée>",
            "#",
            *[f"#   {c}" for c in unused],
        ]
    return "\n".join(lines) + "\n"
