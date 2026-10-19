"""The scenario oracle end to end, on a 10-row demo scenario built in tmp_path."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from relay_engine.oracle.harness import OracleError, migrate, run_oracle
from relay_engine.oracle.scenario import TARGET_VARIABLE, load_scenario

UPPER_MIGRATE = """\
import csv
import sqlite3
import sys

with open("legacy.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f, delimiter=";"))
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE shop (id TEXT, name TEXT, city TEXT, opened TEXT)")
conn.executemany(
    "INSERT INTO shop VALUES (?, ?, ?, ?)",
    [
        (r["id"], r["name"].strip(),
         r["city"].upper() if r["id"] in {"C001", "C002"} else r["city"], r["opened"])
        for r in rows
    ],
)
conn.commit()
conn.close()
"""

DEMO_MIGRATE_VIEW = """\
import csv
import sqlite3
import sys

with open("legacy.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f, delimiter=";"))
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE raw (id TEXT, name TEXT, city TEXT, opened TEXT)")
conn.executemany(
    "INSERT INTO raw VALUES (?, ?, ?, ?)",
    [(r["id"], r["name"].strip(), r["city"], r["opened"]) for r in rows],
)
conn.execute("CREATE VIEW shop AS SELECT id, name, city, opened FROM raw")
conn.commit()
conn.close()
"""

UPPER_INTENT = """\
intents:
  - name: upper_city
    why: "two cities rewritten in capitals"
    expects:
      column: city
      rule: value differs
"""


@pytest.fixture(autouse=True)
def _restore_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TARGET_VARIABLE, "")


def test_tier1_detects_every_injected_defect(
    demo_scenario: Callable[..., Path]
) -> None:
    lines: list[str] = []
    assert run_oracle(demo_scenario(), seeds=1, per_type=1, echo=lines.append), lines
    assert lines[0].startswith("baseline (tier 1): 0 findings")
    assert lines[0].endswith("ok")
    assert any(line.startswith("seed 1: 6/6 detected, 0 false positives") for line in lines)
    assert lines[-1] == "1/1 seeds clean."


def test_tier2_measures_each_intent(
    demo_scenario: Callable[..., Path]
) -> None:
    lines: list[str] = []
    root = demo_scenario(migrate=UPPER_MIGRATE, intents=UPPER_INTENT)
    assert run_oracle(root, seeds=1, per_type=1, echo=lines.append), lines
    assert lines[0].startswith("baseline (tier 2): 2 findings")
    assert "  intent upper_city: 2 findings" in lines
    assert lines[-1] == "1/1 seeds clean."


def test_an_unexplained_baseline_stops_before_injecting(
    demo_scenario: Callable[..., Path]
) -> None:
    lines: list[str] = []
    assert not run_oracle(
        demo_scenario(migrate=UPPER_MIGRATE), seeds=1, per_type=1, echo=lines.append
    )
    assert lines[0].endswith("FAIL")
    assert "  unexplained: fidelity · city · value differs ×2" in lines
    assert not any(line.startswith("seed") for line in lines)


def test_a_failing_run_is_one_sentence(
    demo_scenario: Callable[..., Path]
) -> None:
    from conftest import DEMO_MAPPING

    lines: list[str] = []
    root = demo_scenario(mapping=DEMO_MAPPING.replace("source: city", "source: town"))
    assert not run_oracle(root, seeds=1, per_type=1, echo=lines.append)
    assert len(lines) == 1
    assert lines[0].startswith("relay run failed on clean.db: ")
    assert "town" in lines[0]
    assert "Traceback" not in lines[0]


def test_a_failing_migration_shows_its_last_error_lines(
    demo_scenario: Callable[..., Path],
) -> None:
    lines: list[str] = []
    migrate_body = "import sys\nsys.stderr.write('boom: bad row 42\\n')\nsys.exit(3)\n"
    assert not run_oracle(
        demo_scenario(migrate=migrate_body), seeds=1, per_type=1, echo=lines.append
    )
    assert lines == ["migrate.py failed (exit 3):\nboom: bad row 42"]


def test_migrate_starts_from_a_fresh_database(
    demo_scenario: Callable[..., Path], tmp_path: Path
) -> None:
    scenario = load_scenario(demo_scenario())
    db = tmp_path / "keep" / "clean.db"
    db.parent.mkdir()
    migrate(scenario, db)
    migrate(scenario, db)
    assert db.is_file()


def test_a_migration_that_writes_nothing_is_reported(
    demo_scenario: Callable[..., Path], tmp_path: Path
) -> None:
    scenario = load_scenario(demo_scenario(migrate="print('nothing to do')\n"))
    with pytest.raises(OracleError, match="migrate.py exited without writing clean.db"):
        migrate(scenario, tmp_path / "clean.db")


ALL_UPPER_MIGRATE = UPPER_MIGRATE.replace(
    'r["city"].upper() if r["id"] in {"C001", "C002"} else r["city"]', 'r["city"].upper()'
)
ALL_UPPER_INTENT = UPPER_INTENT.replace("two cities", "every city")


def test_tier2_still_injects_when_every_row_carries_an_intent(
    demo_scenario: Callable[..., Path]
) -> None:
    lines: list[str] = []
    root = demo_scenario(migrate=ALL_UPPER_MIGRATE, intents=ALL_UPPER_INTENT)
    assert run_oracle(root, seeds=1, per_type=1, echo=lines.append), lines
    assert "  intent upper_city: 10 findings" in lines
    assert any(line.startswith("seed 1: 6/6 detected") for line in lines)


def test_a_relative_keep_folder_works(
    demo_scenario: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conftest import DEMO_MAPPING

    root = demo_scenario(mapping=DEMO_MAPPING.replace("source: city", "source: town"))
    monkeypatch.chdir(tmp_path)
    lines: list[str] = []
    assert not run_oracle(root, seeds=1, per_type=1, keep=Path("out"), echo=lines.append)
    assert lines[0].startswith("relay run failed on clean.db: ")
    assert (tmp_path / "out" / "clean.db").is_file()


def test_an_injection_error_is_one_sentence(
    demo_scenario: Callable[..., Path]
) -> None:
    view_migrate = DEMO_MIGRATE_VIEW
    lines: list[str] = []
    assert not run_oracle(
        demo_scenario(migrate=view_migrate), seeds=1, per_type=1, echo=lines.append
    )
    assert lines[-1].startswith("injection failed on seed-1.db: ")

