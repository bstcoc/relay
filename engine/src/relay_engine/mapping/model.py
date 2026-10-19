"""Mapping spec model — the declarative contract (docs/mapping-spec.md)."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TableRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str


class SourceScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_missing: str | None = None


NORMALIZE_RULES = ("trim", "lower", "empty_as_null", "date_only", "decimal_comma")
_SAMPLE = datetime(2024, 3, 12, 10, 30, 45)


def _reads_back(pattern: str) -> bool:
    """Whether a date written with `pattern` reads back as the same day.

    A typo (`%Q`) reads nothing; a pattern without directives (`jj/mm/aaaa`) reads
    its own text as year 1.
    """
    try:
        written = pl.Series([_SAMPLE]).dt.strftime(pattern)
        read = written.str.to_datetime(pattern, time_unit="us", strict=False)
    except (pl.exceptions.PolarsError, ValueError):
        return False
    return read.dt.date().to_list() == [_SAMPLE.date()]


MASKS_BY_TYPE = {
    "string": (
        "pseudonym", "email", "phone", "first_name", "last_name", "full_name", "address",
        "city", "postal_code", "birth_date", "iban", "ssn", "blank",
    ),
    "integer": ("pseudonym", "phone", "postal_code", "ssn", "blank"),
    "date": ("birth_date", "blank"),
    "datetime": ("birth_date", "blank"),
}

_TYPE = re.compile(r"^(string|integer|float|date|datetime|boolean|decimal\(\d+,\s*\d+\))$")


class ColumnMapping(BaseModel):
    """One entry of `columns`: 1→1, 1→N (split), N→1 (concat), an excluded source
    column, or a target column without source (`target_only`)."""

    model_config = ConfigDict(extra="forbid")

    source: str | list[str] | None = None
    target: str | list[str] | None = None
    type: str | None = None
    tolerance: Decimal | None = None
    normalize: list[str] = Field(default_factory=list)
    transform: Literal["split", "concat"] | None = None
    separator: str | None = None
    source_format: str | None = None
    target_format: str | None = None
    exclude: bool = False
    target_only: bool = False
    anonymize: Literal[
        "pseudonym", "email", "phone", "first_name", "last_name", "full_name", "address",
        "city", "postal_code", "birth_date", "iban", "ssn", "blank",
    ] | None = None
    reason: str | None = None

    @field_validator("normalize", mode="before")
    @classmethod
    def _scalar_to_list(cls, v: object) -> object:
        return [v] if isinstance(v, str) else v

    @field_validator("normalize")
    @classmethod
    def _known_rules(cls, rules: list[str]) -> list[str]:
        for rule in rules:
            if rule not in NORMALIZE_RULES:
                raise ValueError(
                    f"unknown normalize rule '{rule}' (known: {', '.join(NORMALIZE_RULES)})"
                )
        return rules

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str | None) -> str | None:
        if v is not None and not _TYPE.match(v):
            raise ValueError(f"unknown type '{v}'")
        return v

    @model_validator(mode="after")
    def _consistent_shape(self) -> ColumnMapping:
        if self.target_only:
            declared = self.model_fields_set - {"target", "target_only", "reason"}
            if declared or not isinstance(self.target, str):
                raise ValueError("a target-only column declares only its target and a reason")
            return self
        if self.source is None:
            raise ValueError(
                "source is required; a target column without source is declared "
                "with target_only: true"
            )
        dated = self.transform != "split" and (
            self.type in ("date", "datetime") or "date_only" in self.normalize
        )
        for side, pattern in (("source", self.source_format), ("target", self.target_format)):
            if pattern is None:
                continue
            if not dated:
                raise ValueError(f"{side}_format applies to a date or datetime column")
            if not _reads_back(pattern):
                raise ValueError(
                    f"{side}_format '{pattern}' cannot read back the dates it writes "
                    "(expected strftime directives, e.g. %d/%m/%Y)"
                )
        if self.anonymize and (self.exclude or self.transform == "split"):
            raise ValueError("anonymize applies to a column that is written whole")
        allowed = MASKS_BY_TYPE.get(self.type or "string", ("blank",))
        if self.anonymize and self.anonymize not in allowed:
            raise ValueError(
                f"a {self.type} column is anonymized with {' or '.join(allowed)}, "
                f"not {self.anonymize}"
            )
        if self.transform is not None and self.separator is None:
            raise ValueError(f"transform '{self.transform}' requires a separator")
        one_source = isinstance(self.source, str)
        one_target = isinstance(self.target, str)
        many_targets = isinstance(self.target, list) and len(self.target) >= 2
        many_sources = isinstance(self.source, list) and len(self.source) >= 2
        if self.exclude:
            if self.target is not None:
                raise ValueError("an excluded column must not declare a target")
        elif self.transform == "split":
            if not (one_source and many_targets):
                raise ValueError("split takes one source column and several targets")
        elif self.transform == "concat":
            if not (many_sources and one_target):
                raise ValueError("concat takes several source columns and one target")
        elif not (one_source and one_target):
            raise ValueError("a plain mapping takes one source column and one target")
        return self

    def target_list(self) -> list[str]:
        if self.target is None:
            return []
        return [self.target] if isinstance(self.target, str) else list(self.target)


class Reference(BaseModel):
    """A foreign key: `column` of this target must exist in `table.key`."""

    model_config = ConfigDict(extra="forbid")
    column: str
    table: str
    key: str


class CrossEntity(BaseModel):
    """Another target table joined to this one: `on` maps this target's columns to
    the other table's, `totals` names aggregates computed per joined key first."""

    model_config = ConfigDict(extra="forbid")
    table: str
    on: dict[str, str] = Field(min_length=1)
    totals: dict[str, str] = Field(default_factory=dict)


class BusinessRule(BaseModel):
    """A declared invariant: a row predicate (`check`), a before/after total
    (`aggregate`), or a predicate across another target table (`cross` + `check`)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    check: str | None = None
    aggregate: str | None = None
    group_by: str | None = None
    tolerance: Decimal | None = None
    cross: CrossEntity | None = None
    verdict: Literal["FAIL", "REVIEW"] = "FAIL"

    @model_validator(mode="after")
    def _one_form(self) -> BusinessRule:
        if (self.check is None) == (self.aggregate is None):
            raise ValueError("a business rule declares exactly one of check or aggregate")
        if self.check is not None and (self.group_by or self.tolerance is not None):
            raise ValueError("group_by and tolerance only apply to an aggregate rule")
        if self.cross is not None and self.check is None:
            raise ValueError("a cross rule declares its predicate with check")
        return self


class MappingSpec(BaseModel):
    """A full mapping spec for one entity."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    entity: str
    source: TableRef
    target: TableRef
    match_key: list[str]
    max_duplicate_share: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    source_scope: SourceScope | None = None
    columns: list[ColumnMapping]
    references: list[Reference] = Field(default_factory=list)
    business_rules: list[BusinessRule] = Field(default_factory=list)

    @field_validator("match_key")
    @classmethod
    def _distinct_keys(cls, keys: list[str]) -> list[str]:
        return list(dict.fromkeys(keys))

    def referenced_tables(self) -> list[str]:
        """Other target tables the spec reads: by `references` and `cross` rules."""
        tables = [r.table for r in self.references]
        tables += [r.cross.table for r in self.business_rules if r.cross is not None]
        return list(dict.fromkeys(tables))

    def target_columns(self) -> list[str]:
        """Target columns produced from the source, in declaration order."""
        return [
            t for c in self.columns if not (c.exclude or c.target_only) for t in c.target_list()
        ]

    def entries_by_target(self) -> dict[str, ColumnMapping]:
        """The entry declaring each target column, target-only ones included."""
        return {t: e for e in self.columns if not e.exclude for t in e.target_list()}
