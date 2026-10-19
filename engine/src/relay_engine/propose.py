"""What the app proposes for a migration between two connections.

A source table that matches a table of the target gets the suggested mapping;
any other source table gets a copy of itself, which the migration creates in
the target. Nothing here is applied: a person reviews every proposal first.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field

import polars as pl

from relay_engine.mapping import MappingSpec
from relay_engine.mapping.model import MASKS_BY_TYPE
from relay_engine.mapping.scaffold import spec_type
from relay_engine.suggest import ColumnMatch, suggest_tables, to_mapping

SOURCE = "source."
TARGET = "target."
PERSONAL = tuple((kind, re.compile(rf"(^|_)({words})($|_)")) for kind, words in (
    ("email", r"e?mail|courriel"),
    ("phone", r"phone|tel|telephone|mobile|portable|fax|gsm"),
    ("first_name", r"first_?name|firstname|given_?name|prenom"),
    ("last_name", r"last_?name|lastname|surname|family_?name|nom_?(de_?)?famille"),
    ("birth_date", r"birth|birth_?date|dob|date_?(de_?)?naissance|naissance"),
    ("full_name", r"full_?name|nom_?complet|nom|name|contact"),
    ("address", r"address|adresse|street|rue"),
    ("postal_code", r"zip|zip_?code|postal_?code|code_?postal|cp"),
    ("city", r"city|ville|town|commune"),
    ("iban", r"iban"),
    ("ssn", r"ssn|nir|secu|num_?secu|social_?security"),
    ("pseudonym", r"bic|passport|passeport|ip|ip_?address"),
))


@dataclass(frozen=True)
class Proposal:
    source: str
    target: str
    create: bool
    score: float
    columns: list[ColumnMatch]
    unmatched_source: list[str] = field(default_factory=list)
    unmatched_target: list[str] = field(default_factory=list)
    mapping: dict = field(default_factory=dict)
    personal: dict[str, str] = field(default_factory=dict)
    target_columns: dict[str, str | None] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _types(frame: pl.DataFrame) -> dict[str, str | None]:
    """Each column of a target table and its mapping-spec type, unknown when it is empty."""
    known: dict[str, str | None] = {}
    for name, dtype in frame.schema.items():
        try:
            known[name] = spec_type(dtype)
        except ValueError:
            known[name] = None
    return known


def personal(spec: MappingSpec) -> dict[str, str]:
    """Source columns that look like personal data, and the mask that fits each."""
    found = {}
    for entry in spec.columns:
        if not isinstance(entry.source, str) or entry.exclude or entry.transform:
            continue
        words = re.sub(r"([a-z])([A-Z])", r"\1_\2", entry.source).lower()
        words = re.sub(r"[^a-z0-9]+", "_", words)
        kind = next((k for k, pattern in PERSONAL if pattern.search(words)), None)
        if kind is None:
            continue
        allowed = MASKS_BY_TYPE.get(entry.type or "string", ("blank",))
        found[entry.source] = kind if kind in allowed else allowed[0]
    return found


def declared_type(sql: str) -> str | None:
    """The mapping-spec type of a column as its database declares it, when that says more."""
    name = sql.lower().strip()
    exact = re.match(r"(numeric|decimal)\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", name)
    if exact:
        return f"decimal({exact[2]},{exact[3]})"
    for prefixes, kind in (
        (("timestamp", "datetime"), "datetime"),
        (("date",), "date"),
        (("bool",), "boolean"),
        (("int", "bigint", "smallint", "tinyint"), "integer"),
        (("real", "float", "double"), "float"),
        (("char", "varchar", "nvarchar", "nchar", "text", "character", "clob", "string"), "string"),
    ):
        if name.startswith(prefixes):
            return kind
    return None


def _identifies(frame: pl.DataFrame, column: str) -> bool:
    values = frame.get_column(column)
    return values.null_count() == 0 and values.n_unique() == frame.height


def copy_mapping(
    table: str, frame: pl.DataFrame, key: list[str],
    declared: dict[str, str] | None = None, links: list[dict] | None = None,
) -> MappingSpec:
    """The mapping that copies a source table as it is into a new target table.

    Declared types win over what the driver returns (SQLite gives dates as text
    and NUMERIC(12,2) as floats), and single-column foreign keys come along.
    """
    declared = declared or {}
    columns: list[dict[str, object]] = []
    for name, dtype in frame.schema.items():
        try:
            kind = declared_type(declared.get(name, "")) or spec_type(dtype)
            columns.append({"source": name, "target": name, "type": kind})
        except ValueError:
            columns.append({"source": name, "exclude": True,
                            "reason": f"type {dtype} cannot be copied yet"})
    copied = [c["target"] for c in columns if not c.get("exclude")]
    if not copied:
        raise ValueError(f"no column of {table} can be copied")
    match_key = [k for k in key if k in copied] or [
        next((c for c in copied if _identifies(frame, str(c))), copied[0])
    ]
    return MappingSpec.model_validate({
        "version": 1,
        "entity": table,
        "source": {"table": SOURCE + table},
        "target": {"table": TARGET + table},
        "match_key": match_key,
        "columns": columns,
        "references": [
            {"column": link["columns"][0], "table": TARGET + link["table"], "key": link["to"][0]}
            for link in links or []
            if len(link["columns"]) == 1 and link["columns"][0] in copied
        ],
    })


def propose(
    sources: dict[str, pl.DataFrame],
    targets: dict[str, pl.DataFrame],
    keys: dict[str, list[str]],
    declared: dict[str, dict[str, str]] | None = None,
    links: dict[str, list[dict]] | None = None,
) -> list[Proposal]:
    """One proposal per source table, by source table name."""
    matches = {m.source: m for m in suggest_tables(
        {SOURCE + name: frame for name, frame in sources.items()},
        {TARGET + name: frame for name, frame in targets.items()},
    )}
    proposals = []
    for name, frame in sources.items():
        match = matches.get(SOURCE + name)
        if match is not None and match.columns:
            target = match.target.removeprefix(TARGET)
            mapping = to_mapping(match, frame, targets[target], entity=name,
                                 target_key=keys.get(TARGET + target),
                                 source_key=keys.get(SOURCE + name))
            proposals.append(Proposal(
                name, target, False, match.score, match.columns,
                match.unmatched_source, match.unmatched_target,
                mapping.model_dump(mode="json", exclude_defaults=True), personal(mapping),
                _types(targets[target]),
            ))
            continue
        spec = copy_mapping(name, frame, keys.get(SOURCE + name, []),
                            (declared or {}).get(name), (links or {}).get(name))
        proposals.append(Proposal(
            name, name, True, 1.0,
            [ColumnMatch(c, c, 1.0, "copied as it is") for c in spec.target_columns()],
            mapping=spec.model_dump(mode="json", exclude_defaults=True), personal=personal(spec),
        ))
    return proposals
