"""Seam 3: the match_key must identify one source row."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from conftest import frame
from relay_engine.generator.generate import generate
from relay_engine.layers.silver import conform
from relay_engine.mapping import MappingError, load_mapping
from relay_engine.matching import AmbiguousKeyError, check_match_key

EXAMPLES = Path(__file__).parent.parent / "examples" / "mappings"


def _pupils(duplicated: dict[str, int], unique: int) -> pl.DataFrame:
    """`unique` pupils with distinct first names, plus each name of `duplicated` × count."""
    names = [f"p{i:03d}" for i in range(unique)]
    names += [name for name, count in duplicated.items() for _ in range(count)]
    return frame([(name, 10) for name in names], ["prenom", "moyenne"])


def test_a_key_shared_by_many_rows_stops_with_the_share() -> None:
    source = _pupils({"Léa": 3, "Tom": 3, "Zoé": 2}, unique=12)
    with pytest.raises(AmbiguousKeyError) as exc:
        check_match_key(source, ["prenom"])
    message = str(exc.value)
    assert (
        "match_key (prenom) is not unique in the source: 40% of rows (8 of 20) share their "
        "key with another row, above the 5% limit (e.g. 'Léa' ×3, 'Tom' ×3, 'Zoé' ×2)."
    ) in message
    assert "or raise max_duplicate_share" in message
    assert isinstance(exc.value, MappingError)


def test_a_few_duplicates_under_the_limit_are_returned_not_raised() -> None:
    duplicates = check_match_key(_pupils({"Léa": 2}, unique=48), ["prenom"])
    assert duplicates.rows() == [("Léa", 2)]


def test_a_share_equal_to_the_limit_does_not_stop() -> None:
    duplicates = check_match_key(_pupils({"Léa": 2}, unique=38), ["prenom"])
    assert duplicates.height == 1


def test_a_zero_limit_stops_on_the_first_duplicate() -> None:
    with pytest.raises(AmbiguousKeyError) as exc:
        check_match_key(_pupils({"Léa": 2}, unique=998), ["prenom"], max_share=Decimal(0))
    assert "1% of rows (2 of 1000)" in str(exc.value)
    assert "above the 0% limit" in str(exc.value)


def test_unique_source_key_passes(tmp_path: Path) -> None:
    generate(tmp_path, seed=42, rows=50)
    spec = load_mapping(EXAMPLES / "chantiers.yaml")
    legacy = pl.read_parquet(tmp_path / "chantiers_legacy.parquet")
    assert check_match_key(conform(legacy, spec), spec.match_key).is_empty()


def test_an_empty_key_part_reads_empty_not_none() -> None:
    source = frame([(None, 1), (None, 2), ("Tom", 3)], ["prenom", "moyenne"])
    with pytest.raises(AmbiguousKeyError) as exc:
        check_match_key(source, ["prenom"])
    assert "'(empty)' ×2" in str(exc.value)
    assert "None" not in str(exc.value)
