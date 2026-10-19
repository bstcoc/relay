"""Suggested correspondences between two schemas: which table, which column goes where.

Rules only: names (tokens, abbreviations, synonyms, initials), compatible kinds of
values, and how many values the two columns share. Every suggestion carries its
score and its reason; nothing is applied until a person accepts it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import polars as pl

from relay_engine.mapping import MappingSpec
from relay_engine.mapping.scaffold import spec_type

SURE = 0.75
_ACCEPTED = 0.4
_SAMPLE = 2000
_DISTINCTIVE = 20
_DATE_PATTERNS = [None, "%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y"]
_SYNONYMS = [
    {"nom", "name", "lastname", "surname"},
    {"prenom", "firstname", "givenname"},
    {"mnt", "montant", "amount", "amt", "total"},
    {"dt", "dte", "date"},
    {"id", "identifiant", "identifier", "code", "num", "numero", "no", "nr", "ref", "reference"},
    {"lib", "libelle", "label", "designation", "description", "desc", "intitule"},
    {"adr", "adresse", "address", "addr"},
    {"ville", "city", "town", "commune"},
    {"cp", "zip", "zipcode", "postcode", "postal"},
    {"tel", "telephone", "phone", "fixe", "landline"},
    {"portable", "mobile", "cell", "cellular", "gsm"},
    {"poste", "extension", "ext"},
    {"enseigne", "brand", "banner", "marque"},
    {"fonction", "job", "jobtitle", "title", "role"},
    {"type", "kind", "category", "categorie"},
    {"mail", "email", "courriel", "e-mail"},
    {"qte", "quantite", "quantity", "qty"},
    {"prix", "price", "tarif"},
    {"client", "customer", "cust", "clt"},
    {"fournisseur", "supplier", "vendor", "frs"},
    {"cde", "commande", "order"},
    {"fact", "facture", "invoice", "inv"},
    {"art", "article", "item", "produit", "product"},
    {"soc", "societe", "company", "entreprise"},
    {"pays", "country"},
    {"statut", "status", "etat", "state"},
    {"cree", "creation", "created", "create"},
    {"maj", "modification", "updated", "update", "modified"},
]
_IGNORED_IN_TABLES = {"legacy", "target", "old", "new", "src", "source", "dst", "dest", "tbl",
                      "t", "tmp", "bak", "v1", "v2", "prod", "preprod", "staging", "dbo", "public"}


@dataclass(frozen=True)
class ColumnMatch:
    source: str
    target: str
    score: float
    reason: str

    @property
    def sure(self) -> bool:
        return self.score >= SURE


@dataclass(frozen=True)
class TableMatch:
    source: str
    target: str
    score: float
    columns: list[ColumnMatch]
    unmatched_source: list[str] = field(default_factory=list)
    unmatched_target: list[str] = field(default_factory=list)


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def tokens(name: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return [t for t in re.split(r"[^a-z0-9]+", _plain(spaced)) if t]


def _same_meaning(a: str, b: str) -> bool:
    return a == b or any(a in group and b in group for group in _SYNONYMS)


def _token_score(a: str, b: str) -> float:
    if _same_meaning(a, b):
        return 1.0
    if min(len(a), len(b)) >= 2 and (a.startswith(b) or b.startswith(a)):
        return 0.85
    return SequenceMatcher(None, a, b).ratio() * 0.7


def _initials(words: list[str]) -> dict[str, set[int]]:
    """Initials of every run of two or more words, with the positions they cover."""
    runs: dict[str, set[int]] = {}
    for i in range(len(words)):
        for j in range(i + 2, len(words) + 1):
            runs.setdefault("".join(w[0] for w in words[i:j]), set()).update(range(i, j))
    return runs


def _side(words: list[str], others: list[str]) -> list[float]:
    """Best score of each word: alike another word, initials of others, or spelled out by one."""
    mine, theirs = _initials(words), _initials(others)
    spelled = set().union(*(mine.get(o, set()) for o in others))
    return [
        max(
            max(_token_score(w, o) for o in others),
            0.9 if w in theirs or i in spelled else 0.0,
        )
        for i, w in enumerate(words)
    ]


def name_score(a: str, b: str) -> float:
    left, right = tokens(a), tokens(b)
    if not left or not right:
        return 0.0
    if left == right or _same_meaning("".join(left), "".join(right)):
        return 1.0
    scores = _side(left, right) + _side(right, left)
    return sum(scores) / len(scores)


def _distinct(values: pl.Series) -> pl.Series:
    """The first distinct values, in the order they appear, so a profile never varies."""
    return values.unique(maintain_order=True).head(_SAMPLE)


def _profile(values: pl.Series) -> tuple[str, set[str]]:
    """The kind of a column (text, number, date, boolean) and a sample of its values, canonical."""
    series = values.drop_nulls()
    dtype = series.dtype
    if dtype == pl.Boolean:
        return "boolean", set(_distinct(series.cast(pl.String)).to_list())
    if dtype.is_temporal():
        kind_values = series.cast(pl.Date)
        return "date", set(_distinct(kind_values.cast(pl.String)).to_list())
    if dtype.is_numeric():
        numbers = series.cast(pl.Float64).round(6)
        return "number", set(_distinct(numbers.cast(pl.String)).to_list())
    text = series.cast(pl.String).str.strip_chars()
    text = _distinct(text.filter(text != ""))
    if text.is_empty():
        return "text", set()
    numbers = text.str.replace_all(r"[\s ]", "").str.replace(",", ".").cast(
        pl.Float64, strict=False
    )
    if numbers.null_count() == 0 and not text.str.contains(r"^0\d").any():
        return "number", set(numbers.round(6).cast(pl.String).to_list())
    for pattern in _DATE_PATTERNS:
        try:
            dates = text.str.to_datetime(pattern, strict=False)
        except pl.exceptions.ComputeError:
            continue
        if dates.null_count() == 0:
            return "date", set(dates.cast(pl.Date).cast(pl.String).to_list())
    return "text", {_plain(v) for v in text.to_list()}


Profile = tuple[str, set[str]]


def profiles(frame: pl.DataFrame) -> dict[str, Profile]:
    """The profile of every column of a table, computed once for every pairing."""
    return {c: _profile(frame.get_column(c)) for c in frame.columns}


def _column_match(source: str, target: str, source_profile: Profile,
                  target_profile: Profile) -> ColumnMatch:
    by_name = name_score(source, target)
    (source_kind, source_values) = source_profile
    (target_kind, target_values) = target_profile
    reasons = []
    if tokens(source) == tokens(target):
        reasons.append("same name")
    elif by_name >= 0.5:
        reasons.append(f"similar name ({source} ~ {target})")
    score = by_name
    if source_values and target_values:
        shared = len(source_values & target_values) / min(len(source_values), len(target_values))
        score = 0.4 * by_name + 0.6 * shared
        if shared >= 0.9 and min(len(source_values), len(target_values)) >= _DISTINCTIVE:
            score = max(score, 0.8)
        if shared >= 0.05:
            reasons.append(f"{round(shared * 100)}% shared values")
    if source_kind != target_kind and "text" not in (source_kind, target_kind):
        score *= 0.6
        reasons.append(f"{source_kind} vs {target_kind}")
    if tokens(source) == tokens(target):
        score = max(score, _ACCEPTED + 0.1)
    return ColumnMatch(source, target, round(score, 3), ", ".join(reasons) or "weak")


def suggest_columns(
    source: pl.DataFrame, target: pl.DataFrame,
    source_profiles: dict[str, Profile] | None = None,
    target_profiles: dict[str, Profile] | None = None,
) -> TableMatch:
    """One-to-one correspondences between the columns of two tables, best first."""
    source_profiles = source_profiles or profiles(source)
    target_profiles = target_profiles or profiles(target)
    candidates = sorted(
        (
            _column_match(s, t, source_profiles[s], target_profiles[t])
            for s in source.columns for t in target.columns
        ),
        key=lambda m: m.score,
        reverse=True,
    )
    taken_source: set[str] = set()
    taken_target: set[str] = set()
    chosen: list[ColumnMatch] = []
    for match in candidates:
        if match.score < _ACCEPTED or match.source in taken_source or match.target in taken_target:
            continue
        chosen.append(match)
        taken_source.add(match.source)
        taken_target.add(match.target)
    chosen.sort(key=lambda m: target.columns.index(m.target))
    coverage = len(chosen) / max(len(target.columns), 1)
    score = sum(m.score for m in chosen) / max(len(chosen), 1) * coverage
    return TableMatch(
        "", "", round(score, 3), chosen,
        [c for c in source.columns if c not in taken_source],
        [c for c in target.columns if c not in taken_target],
    )


def _table_name_score(a: str, b: str) -> float:
    left = [t for t in tokens(a) if t not in _IGNORED_IN_TABLES]
    right = [t for t in tokens(b) if t not in _IGNORED_IN_TABLES]
    return name_score(" ".join(left), " ".join(right)) if left and right else 0.0


def suggest_tables(
    sources: dict[str, pl.DataFrame], targets: dict[str, pl.DataFrame]
) -> list[TableMatch]:
    """One-to-one correspondences between tables, each with its columns, best first."""
    source_profiles = {s: profiles(frame) for s, frame in sources.items()}
    target_profiles = {t: profiles(frame) for t, frame in targets.items()}
    candidates = []
    for s, source in sources.items():
        for t, target in targets.items():
            columns = suggest_columns(source, target, source_profiles[s], target_profiles[t])
            score = round(0.3 * _table_name_score(s, t) + 0.7 * columns.score, 3)
            candidates.append(TableMatch(s, t, score, columns.columns,
                                         columns.unmatched_source, columns.unmatched_target))
    candidates.sort(key=lambda m: m.score, reverse=True)
    chosen: list[TableMatch] = []
    for match in candidates:
        if match.score < _ACCEPTED * 0.5:
            continue
        if any(c.source == match.source or c.target == match.target for c in chosen):
            continue
        chosen.append(match)
    return chosen


def _entity(table: str) -> str:
    """`chantiers_target` is the entity `chantiers`."""
    kept = [t for t in tokens(table) if t not in _IGNORED_IN_TABLES]
    return "_".join(kept) or table


def _key(match: TableMatch, source: pl.DataFrame, target: pl.DataFrame,
         target_key: list[str] | None, source_key: list[str] | None) -> list[str]:
    matched = {m.target: m.source for m in match.columns}
    if target_key and all(k in matched for k in target_key):
        return target_key
    targets = {m.source: m.target for m in match.columns}
    if source_key and all(k in targets for k in source_key):
        return [targets[k] for k in source_key]

    def identifies(frame: pl.DataFrame, column: str) -> bool:
        values = frame.get_column(column)
        return values.null_count() == 0 and values.n_unique() == frame.height

    unique = [
        m.target for m in match.columns
        if identifies(source, m.source) and (target.is_empty() or identifies(target, m.target))
    ]
    named = [t for t in unique if any(_same_meaning(x, "id") for x in tokens(t))]
    return [(named or unique or [m.target for m in match.columns])[0]]


def to_mapping(
    match: TableMatch,
    source: pl.DataFrame,
    target: pl.DataFrame,
    *,
    entity: str | None = None,
    target_key: list[str] | None = None,
    source_key: list[str] | None = None,
) -> MappingSpec:
    """The mapping the suggestions amount to, ready for a person to review."""
    if not match.columns:
        raise ValueError(f"no column of {match.source} matches {match.target}")
    columns: list[dict[str, object]] = []
    for m in match.columns:
        known = target.schema[m.target]
        entry: dict[str, object] = {
            "source": m.source, "target": m.target,
            "type": spec_type(source.schema[m.source] if known == pl.Null else known),
        }
        source_dtype, target_dtype = source.schema[m.source], target.schema[m.target]
        normalize = []
        if source_dtype == pl.String:
            values = source.get_column(m.source).drop_nulls()
            if (values != values.str.strip_chars()).any():
                normalize.append("trim")
        if target_dtype == pl.Date and source_dtype != pl.Date:
            normalize.append("date_only")
        if normalize:
            entry["normalize"] = normalize
        columns.append(entry)
    columns += [{"source": c, "exclude": True, "reason": "no target column suggested"}
                for c in match.unmatched_source]
    columns += [{"target": c, "target_only": True, "reason": "no source column suggested"}
                for c in match.unmatched_target]
    return MappingSpec.model_validate({
        "version": 1,
        "entity": entity or _entity(match.target),
        "source": {"table": match.source},
        "target": {"table": match.target},
        "match_key": _key(match, source, target, target_key, source_key),
        "columns": columns,
    })
