"""Silver layer: conform legacy data to the target schema through the mapping."""

from __future__ import annotations

import polars as pl

from relay_engine.checks.findings import datetime_text, text
from relay_engine.layers.masks import mask_date, mask_text
from relay_engine.mapping.model import ColumnMapping, MappingSpec

RAW = "__raw__"

_TRUE = ("true", "t", "yes", "y", "1")
_FALSE = ("false", "f", "no", "n", "0")
_DATE = r"^\d{4}-\d{1,2}-\d{1,2}"
_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S%.f", "%Y-%m-%dT%H:%M:%S%.f", "%Y-%m-%d %H:%M", "%Y-%m-%d")


def spec_dtype(declared: str) -> pl.DataType:
    """Translate a spec type (string, decimal(12,2), ...) into a Polars type."""
    if declared.startswith("decimal"):
        precision, scale = declared[len("decimal(") : -1].split(",")
        return pl.Decimal(int(precision), int(scale.strip()))
    return {
        "string": pl.String(),
        "integer": pl.Int64(),
        "float": pl.Float64(),
        "date": pl.Date(),
        "datetime": pl.Datetime("us"),
        "boolean": pl.Boolean(),
    }[declared]


def _as_string(column: pl.Expr, dtype: pl.DataType) -> pl.Expr:
    if isinstance(dtype, pl.Datetime):
        return datetime_text(column)
    return column.cast(pl.String)


def _to_decimal(column: pl.Expr, dtype: pl.DataType, target: pl.Decimal) -> pl.Expr:
    """Round half up to the declared scale, as Spark did: 12.345 → 12.35, never 12.34."""
    if dtype == pl.String:
        column = column.str.strip_chars()
    elif dtype.is_float():
        column = column.cast(pl.String)
    wide = column.cast(pl.Decimal(38, 10), strict=False)
    return wide.round(target.scale or 0, mode="half_away_from_zero").cast(target, strict=False)


def _whole(value: pl.Expr) -> pl.Expr:
    """A year alone is its first day, a year and month the first of that month."""
    return (
        pl.when(value.str.contains(r"^\d{4}$")).then(value + "-01-01")
        .when(value.str.contains(r"^\d{4}-\d{1,2}$")).then(value + "-01")
        .otherwise(value)
    )


def _to_utc(value: pl.Expr) -> pl.Expr:
    """A date-time with an offset (`Z`, `+02:00`, `+0200`), as UTC without a zone."""
    offset = value.str.replace(r"Z$", "+0000").str.replace(r"([+-]\d{2}):(\d{2})$", "$1$2")
    return pl.coalesce([
        offset.str.to_datetime(f, time_unit="us", time_zone="UTC", strict=False)
        for f in ("%Y-%m-%dT%H:%M:%S%.f%z", "%Y-%m-%d %H:%M:%S%.f%z")
    ]).dt.replace_time_zone(None)


def _to_date(column: pl.Expr, dtype: pl.DataType, pattern: str | None = None) -> pl.Expr:
    """ISO date (a time part is ignored), or exactly `pattern` when declared.

    A year alone (`2024`) or a year and month (`2024-03`) reads as their first day.

    Anything else is NULL, never an error.
    """
    if dtype == pl.Date:
        return column
    if isinstance(dtype, pl.Datetime):
        return column.dt.date()
    value = column.cast(pl.String).str.strip_chars()
    if pattern is not None:
        return value.str.to_datetime(pattern, time_unit="us", strict=False).dt.date()
    whole = _whole(value)
    return whole.str.extract(f"({_DATE})([ T].*)?$", 1).str.to_date("%Y-%m-%d", strict=False)


def _to_datetime(column: pl.Expr, dtype: pl.DataType, pattern: str | None = None) -> pl.Expr:
    if isinstance(dtype, pl.Datetime):
        return column.cast(pl.Datetime("us"))
    if dtype == pl.Date:
        return column.cast(pl.Datetime("us"))
    value = column.cast(pl.String).str.strip_chars()
    if pattern is not None:
        return value.str.to_datetime(pattern, time_unit="us", strict=False)
    whole = _whole(value)
    return pl.coalesce([
        *[whole.str.to_datetime(f, time_unit="us", strict=False) for f in _DATETIME_FORMATS],
        _to_utc(whole),
    ])


def _to_boolean(column: pl.Expr, dtype: pl.DataType) -> pl.Expr:
    if dtype == pl.Boolean:
        return column
    value = column.cast(pl.String).str.strip_chars().str.to_lowercase()
    return (
        pl.when(value.is_in(_TRUE)).then(pl.lit(True))
        .when(value.is_in(_FALSE)).then(pl.lit(False))
        .otherwise(pl.lit(None, pl.Boolean))
    )


def try_cast(
    column: pl.Expr, dtype: pl.DataType, declared: str, pattern: str | None = None
) -> pl.Expr:
    """Read a value as its declared type; a value that cannot be read becomes NULL.

    `pattern` is the declared date format of this side, if any.
    """
    if declared == "string":
        return _as_string(column, dtype)
    if declared == "date":
        return _to_date(column, dtype, pattern)
    if declared == "datetime":
        return _to_datetime(column, dtype, pattern)
    if declared == "boolean":
        return _to_boolean(column, dtype)
    target = spec_dtype(declared)
    if isinstance(target, pl.Decimal):
        return _to_decimal(column, dtype, target)
    if dtype == pl.String:
        column = column.str.strip_chars()
    return column.cast(target, strict=False)


def normalize(
    column: pl.Expr, rules: list[str], dtype: pl.DataType, pattern: str | None = None
) -> tuple[pl.Expr, pl.DataType]:
    """Apply normalization rules in order; returns the expression and its resulting type."""
    for rule in rules:
        if rule == "trim":
            column, dtype = _as_string(column, dtype).str.strip_chars(" "), pl.String()
        elif rule == "lower":
            column, dtype = _as_string(column, dtype).str.to_lowercase(), pl.String()
        elif rule == "empty_as_null":
            value = _as_string(column, dtype)
            column = pl.when(value.str.strip_chars(" ") == "").then(None).otherwise(value)
            dtype = pl.String()
        elif rule == "date_only":
            column, dtype = _to_date(column, dtype, pattern), pl.Date()
        elif rule == "decimal_comma":
            column = (
                _as_string(column, dtype)
                .str.replace_all(r"[\s  ]", "")
                .str.replace_all(",", ".", literal=True)
            )
            dtype = pl.String()
        else:
            raise ValueError(f"unknown normalize rule '{rule}'")
    return column, dtype


def typed(entry: ColumnMapping) -> bool:
    """Entries whose value is converted to a declared type (split parts stay text)."""
    return not entry.exclude and entry.type is not None and entry.transform != "split"


def conform_column(
    frame: pl.DataFrame, entry: ColumnMapping, name: str, pattern: str | None = None
) -> tuple[pl.Expr, pl.Expr]:
    """One plain column of `frame`, normalized and typed as `entry` declares; and as written.

    `pattern` is the date format of the side `frame` comes from.
    """
    dtype = frame.schema[name]
    column, dtype = normalize(pl.col(name), entry.normalize, dtype, pattern)
    if entry.type is not None:
        column = try_cast(column, dtype, entry.type, pattern)
    return column, text(frame, name)


def _anonymized(entry: ColumnMapping, column: pl.Expr, raw: pl.Expr) -> tuple[pl.Expr, pl.Expr]:
    """The column masked as `entry.anonymize` says, typed and as written."""
    kind = entry.anonymize or "blank"
    declared = entry.type or "string"
    if kind == "blank":
        return pl.lit(None, spec_dtype(declared)), pl.lit(None, pl.String)
    if declared in ("date", "datetime"):
        hidden = column.map_elements(mask_date, return_dtype=spec_dtype(declared))
        return hidden, _as_string(hidden, spec_dtype(declared))
    text = column.cast(pl.String).map_elements(lambda v: mask_text(v, kind), return_dtype=pl.String)
    if declared == "string":
        return text, text
    return text.cast(spec_dtype(declared), strict=False), text


def _entry_columns(
    frame: pl.DataFrame, entry: ColumnMapping, *, with_raw: bool = False
) -> list[pl.Expr]:
    targets = entry.target_list()
    sep = entry.separator or ""

    if entry.transform == "split":
        assert isinstance(entry.source, str)
        parts = pl.col(entry.source).cast(pl.String).str.split(sep, inclusive=False)
        return [parts.list.get(i, null_on_oob=True).alias(name) for i, name in enumerate(targets)]

    if entry.transform == "concat":
        assert isinstance(entry.source, list)
        joined = pl.concat_str(
            [_as_string(pl.col(s), frame.schema[s]) for s in entry.source],
            separator=sep, ignore_nulls=True,
        )
        column, dtype = normalize(joined, entry.normalize, pl.String(), entry.source_format)
        if entry.type is not None:
            column = try_cast(column, dtype, entry.type, entry.source_format)
        raw = joined
    else:
        assert isinstance(entry.source, str)
        column, raw = conform_column(frame, entry, entry.source, entry.source_format)

    if entry.anonymize is not None:
        column, raw = _anonymized(entry, column, raw)
    columns = [column.alias(targets[0])]
    if with_raw and typed(entry):
        columns.append(raw.alias(RAW + targets[0]))
    return columns


def conform(legacy: pl.DataFrame, spec: MappingSpec, *, with_raw: bool = False) -> pl.DataFrame:
    """Apply the mapping to legacy data. Returns the target columns, in declaration order.

    With `with_raw`, each typed column also comes as written, under RAW + its name.
    """
    columns = [
        c for entry in spec.columns if not (entry.exclude or entry.target_only)
        for c in _entry_columns(legacy, entry, with_raw=with_raw)
    ]
    return legacy.select(*columns)
