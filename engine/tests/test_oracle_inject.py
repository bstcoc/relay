"""Defect injection into a migrated SQLite target, driven by the mapping only."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from relay_engine.generator.model import AnomalyType
from relay_engine.mapping import MappingSpec
from relay_engine.oracle.inject import inject

KEY = ["Enseigne", "N° magasin"]
SPEC = MappingSpec.model_validate({
    "version": 1,
    "entity": "sites",
    "source": {"table": "sites_legacy"},
    "target": {"table": "sites_target"},
    "match_key": KEY,
    "columns": [
        {"source": "Enseigne", "target": "Enseigne", "type": "string"},
        {"source": "N° mag", "target": "N° magasin", "type": "string"},
        {"source": "Ville", "target": "Ville", "type": "string", "normalize": ["trim"]},
        {"source": "Adresse", "target": "Adresse", "type": "string", "normalize": ["lower"]},
        {"source": "Créé le", "target": "Créé le", "type": "date", "normalize": "date_only"},
    ],
})
COLUMNS = ("Enseigne", "N° magasin", "Ville", "Adresse", "Créé le")


def _db(tmp_path: Path, name: str = "target.db") -> Path:
    """12 clean rows, one row with a NULL key part, one key already duplicated."""
    rows: list[tuple[str, str | None, str, str, str]] = [
        ("SHOP", f"{n:04}", f"City {n}", f"{n} Main Street", f"2024-01-{n:02}")
        for n in range(1, 13)
    ]
    rows += [
        ("SHOP", None, "Nowhere", "1 Void Lane", "2024-02-01"),
        ("DUP", "0001", "Twin", "2 Twin Road", "2024-02-02"),
        ("DUP", "0001", "Twin", "2 Twin Road", "2024-02-02"),
    ]
    db = tmp_path / name
    with sqlite3.connect(db) as conn:
        quoted = ", ".join(f'"{c}" TEXT' for c in COLUMNS)
        conn.execute(f'CREATE TABLE "site list" ({quoted})')
        conn.executemany('INSERT INTO "site list" VALUES (?, ?, ?, ?, ?)', rows)
    return db


def _rows(db: Path) -> list[dict[str, object]]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute('SELECT * FROM "site list"')]


def _key(row: dict[str, object]) -> str:
    return ", ".join(f"{k}={row[k]}" for k in KEY)


def test_each_type_is_injected_once_on_distinct_rows(tmp_path: Path) -> None:
    result = inject(_db(tmp_path), SPEC, "site list", seed=1, per_type=1, avoid=set())
    kinds = [a.anomaly_type for a in result.manifest.anomalies]
    assert kinds == [
        AnomalyType.VALUE_TRUNCATED, AnomalyType.VALUE_LOST, AnomalyType.DATE_SHIFTED,
        AnomalyType.ROW_DROPPED, AnomalyType.ROW_EXTRA, AnomalyType.NATURAL_KEY_DUPLICATED,
    ]
    assert result.skipped == []
    keys = [a.match_key for a in result.manifest.anomalies]
    assert len(set(keys)) == len(keys)


def test_same_seed_same_injection(tmp_path: Path) -> None:
    first = _db(tmp_path, "a.db")
    second = tmp_path / "b.db"
    shutil.copyfile(first, second)
    a = inject(first, SPEC, "site list", seed=7, per_type=2, avoid=set())
    b = inject(second, SPEC, "site list", seed=7, per_type=2, avoid=set())
    assert a.manifest.to_dict() == b.manifest.to_dict()
    assert _rows(first) == _rows(second)


def test_alterations_survive_normalization(tmp_path: Path) -> None:
    db = _db(tmp_path)
    before = {_key(r): r for r in _rows(db) if r["N° magasin"] is not None}
    result = inject(db, SPEC, "site list", seed=3, per_type=2, avoid=set())
    after: dict[str, list[dict[str, object]]] = {}
    for row in _rows(db):
        after.setdefault(_key(row), []).append(row)

    for anomaly in result.manifest.anomalies:
        assert anomaly.column not in KEY
        kind, key, column = anomaly.anomaly_type, anomaly.match_key, anomaly.column
        if kind is AnomalyType.VALUE_TRUNCATED:
            assert column is not None
            old, new = str(before[key][column]), str(after[key][0][column])
            assert new.strip().lower() != old.strip().lower()
            assert any(c.isalnum() for c in new)
        elif kind is AnomalyType.VALUE_LOST:
            assert column is not None
            assert str(before[key][column]).strip()
            assert after[key][0][column] is None
        elif kind is AnomalyType.DATE_SHIFTED:
            assert column == "Créé le"
            assert after[key][0][column] != before[key][column]
        elif kind is AnomalyType.ROW_DROPPED:
            assert key not in after
        elif kind is AnomalyType.ROW_EXTRA:
            assert key not in before and len(after[key]) == 1
        elif kind is AnomalyType.NATURAL_KEY_DUPLICATED:
            assert len(after[key]) == 2


def test_null_duplicated_and_avoided_keys_are_never_touched(tmp_path: Path) -> None:
    avoided = "Enseigne=SHOP, N° magasin=0005"
    result = inject(_db(tmp_path), SPEC, "site list", seed=11, per_type=2, avoid={avoided})
    touched = {a.match_key for a in result.manifest.anomalies}
    assert avoided not in touched
    assert "Enseigne=DUP, N° magasin=0001" not in touched
    assert not any(key.endswith("=None") for key in touched)


def test_a_short_pool_is_reported_not_raised(tmp_path: Path) -> None:
    result = inject(_db(tmp_path), SPEC, "site list", seed=1, per_type=5, avoid=set())
    assert len(result.manifest.anomalies) <= 12
    assert result.skipped
    assert all("injected, no eligible row or column left" in s for s in result.skipped)


def test_a_mapping_without_dates_skips_date_shifted(tmp_path: Path) -> None:
    no_date = SPEC.model_copy(
        update={"columns": [c for c in SPEC.columns if c.target != "Créé le"]}
    )
    result = inject(_db(tmp_path), no_date, "site list", seed=1, per_type=1, avoid=set())
    assert AnomalyType.DATE_SHIFTED not in [a.anomaly_type for a in result.manifest.anomalies]
    assert result.skipped == [
        "date_shifted: 0 of 1 injected, no eligible row or column left"
    ]


def _plain_db(tmp_path: Path, ddl: str, rows: list[tuple[object, ...]]) -> Path:
    db = tmp_path / "plain.db"
    with sqlite3.connect(db) as conn:
        conn.execute(ddl)
        marks = ", ".join("?" for _ in rows[0])
        conn.executemany(f"INSERT INTO shop VALUES ({marks})", rows)
    return db


def _shop_spec(key_type: str = "string", **city: object) -> MappingSpec:
    return MappingSpec.model_validate({
        "version": 1, "entity": "shops",
        "source": {"table": "shops_legacy"}, "target": {"table": "shops_target"},
        "match_key": ["id"],
        "columns": [
            {"source": "id", "target": "id", "type": key_type},
            {"source": "city", "target": "city", "type": "string", **city},
        ],
    })


def test_row_extra_on_an_integer_key_invents_an_integer(tmp_path: Path) -> None:
    db = _plain_db(
        tmp_path, "CREATE TABLE shop (id INTEGER, city TEXT)",
        [(n, f"City {n}") for n in range(1, 13)],
    )
    result = inject(db, _shop_spec(), "shop", seed=1, per_type=1, avoid=set())
    extra = [a for a in result.manifest.anomalies if a.anomaly_type is AnomalyType.ROW_EXTRA]
    assert [a.match_key for a in extra] == ["id=13"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT typeof(id) FROM shop WHERE id = 13").fetchone() == ("integer",)


def test_row_extra_is_skipped_when_the_key_cannot_take_a_suffix(tmp_path: Path) -> None:
    db = _plain_db(
        tmp_path, "CREATE TABLE shop (id TEXT, city TEXT)",
        [(f"{n:04}", f"City {n}") for n in range(1, 13)],
    )
    result = inject(db, _shop_spec("integer"), "shop", seed=1, per_type=1, avoid=set())
    assert AnomalyType.ROW_EXTRA not in [a.anomaly_type for a in result.manifest.anomalies]
    assert "row_extra: 0 of 1 injected, no eligible row or column left" in result.skipped


def test_schema_constraints_skip_what_the_database_forbids(tmp_path: Path) -> None:
    db = _plain_db(
        tmp_path, "CREATE TABLE shop (id TEXT PRIMARY KEY, city TEXT NOT NULL)",
        [(f"S{n:02}", f"City {n}") for n in range(1, 13)],
    )
    result = inject(db, _shop_spec(), "shop", seed=1, per_type=1, avoid=set())
    kinds = [a.anomaly_type for a in result.manifest.anomalies]
    assert AnomalyType.VALUE_LOST not in kinds
    assert AnomalyType.NATURAL_KEY_DUPLICATED not in kinds
    assert AnomalyType.VALUE_TRUNCATED in kinds
    assert (
        "natural_key_duplicated: 0 of 1 injected, blocked by a schema constraint"
        in result.skipped
    )


def test_the_last_representable_date_is_not_shifted(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("""UPDATE "site list" SET "Créé le" = '9999-12-31'""")
    result = inject(db, SPEC, "site list", seed=1, per_type=1, avoid=set())
    assert AnomalyType.DATE_SHIFTED not in [a.anomaly_type for a in result.manifest.anomalies]


def test_no_truncation_where_a_normalization_could_hide_it(tmp_path: Path) -> None:
    db = _plain_db(
        tmp_path, "CREATE TABLE shop (id TEXT, city TEXT)",
        [(f"S{n:02}", f"2024-01-{n:02} 10:30") for n in range(1, 13)],
    )
    spec = _shop_spec(normalize=["date_only"])
    result = inject(db, spec, "shop", seed=1, per_type=1, avoid=set())
    assert AnomalyType.VALUE_TRUNCATED not in [a.anomaly_type for a in result.manifest.anomalies]


def test_a_cell_flagged_by_the_baseline_is_avoided_but_its_row_is_not(tmp_path: Path) -> None:
    db = _plain_db(
        tmp_path, "CREATE TABLE shop (id TEXT, city TEXT, street TEXT)",
        [(f"S{n:02}", f"City {n}", f"{n} Main Street") for n in range(1, 13)],
    )
    spec = MappingSpec.model_validate({
        "version": 1, "entity": "shops",
        "source": {"table": "shops_legacy"}, "target": {"table": "shops_target"},
        "match_key": ["id"],
        "columns": [
            {"source": "id", "target": "id", "type": "string"},
            {"source": "city", "target": "city", "type": "string"},
            {"source": "street", "target": "street", "type": "string"},
        ],
    })
    every_city = {(f"id=S{n:02}", "city") for n in range(1, 13)}
    result = inject(
        db, spec, "shop", seed=1, per_type=2, avoid=set(), avoid_cells=every_city
    )
    values = [a for a in result.manifest.anomalies if a.column is not None]
    assert values
    assert all(a.column == "street" for a in values)
