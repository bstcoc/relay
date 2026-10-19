"""Run a scenario end to end: migrate, baseline, then inject and judge one seed at a time.

Every failure is one readable sentence, never a stack trace.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import polars as pl

from relay_engine.console import describe
from relay_engine.io import LocalParquetStore
from relay_engine.io.catalog import load_sources
from relay_engine.io.readers import CatalogSource
from relay_engine.oracle.evaluate import Found, evaluate_seed, explain_baseline, group
from relay_engine.oracle.inject import inject
from relay_engine.oracle.scenario import TARGET_VARIABLE, Scenario, ScenarioError, load_scenario
from relay_engine.pipeline import new_run_id, run

_TAIL = 5
_WIDTH = 52


class OracleError(Exception):
    """A step failed; the message is meant to be printed as is."""


def migrate(scenario: Scenario, db: Path) -> None:
    """Run migrate.py into a fresh database."""
    db.unlink(missing_ok=True)
    result = subprocess.run(
        [sys.executable, str(scenario.migrate), str(db)],
        cwd=scenario.root, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-_TAIL:])
        raise OracleError(f"migrate.py failed (exit {result.returncode}):\n{tail}")
    if not db.is_file():
        raise OracleError(f"migrate.py exited without writing {db.name}")


def _findings(scenario: Scenario, db: Path, runs: Path) -> list[Found]:
    """Run Relay on (raw source, db) and return its findings."""
    os.environ[TARGET_VARIABLE] = str(db)
    run_id = new_run_id()
    try:
        source = CatalogSource(load_sources(scenario.sources))
        run(scenario.mapping, source, LocalParquetStore(runs / run_id), run_id)
    except Exception as error:
        raise OracleError(f"relay run failed on {db.name}: {describe(error)}") from error
    files = sorted((runs / run_id / "gold" / "recon_finding").glob("*.parquet"))
    if not files:
        return []
    frame = pl.read_parquet(files)
    return [
        Found(r["check_family"], r["match_key_value"], r["column"], r["rule"], r["verdict"])
        for r in frame.iter_rows(named=True)
    ]


def _status(text: str, ok: bool) -> str:
    return f"{text:<{_WIDTH}} {'ok' if ok else 'FAIL'}"


def _run(
    scenario: Scenario, work: Path, seeds: int, per_type: int, echo: Callable[[str], None]
) -> bool:
    clean = work / "clean.db"
    migrate(scenario, clean)
    baseline = _findings(scenario, clean, work / "runs")
    report = explain_baseline(baseline, scenario.intents)
    echo(_status(f"baseline (tier {scenario.tier}): {len(baseline)} findings", report.ok))
    for name, count in report.per_intent.items():
        echo(f"  intent {name}: {count} findings")
    for family, column, rule, count in group(report.unexplained):
        echo(f"  unexplained: {family} · {column or '-'} · {rule} ×{count}")
    for name in report.silent:
        echo(f"  silent intent: {name} produced no finding")
    if not report.ok:
        return False

    avoid = {
        f.match_key_value for f in baseline if f.column is None or f.check_family != "fidelity"
    }
    avoid_cells = {(f.match_key_value, f.column) for f in baseline if f.column is not None}
    clean_seeds = 0
    for seed in range(1, seeds + 1):
        db = work / f"seed-{seed}.db"
        shutil.copyfile(clean, db)
        try:
            injection = inject(
                db, scenario.mapping, scenario.target_table,
                seed=seed, per_type=per_type, avoid=avoid, avoid_cells=avoid_cells,
            )
        except sqlite3.Error as error:
            raise OracleError(f"injection failed on {db.name}: {error}") from error
        (work / f"seed-{seed}.manifest.json").write_text(
            json.dumps(injection.manifest.to_dict(), indent=2, ensure_ascii=False)
        )
        for note in injection.skipped:
            echo(f"  skipped: {note}")
        result = evaluate_seed(injection.manifest, _findings(scenario, db, work / "runs"), baseline)
        echo(_status(
            f"seed {seed}: {result.detected}/{result.total} detected, "
            f"{len(result.false_positives)} false positives",
            result.ok,
        ))
        for anomaly in result.missed:
            echo(
                f"  missed: {anomaly.match_key} · {anomaly.anomaly_type.value} · "
                f"{anomaly.column or '-'}"
            )
        for finding in result.false_positives:
            echo(
                f"  false positive: {finding.match_key_value} · {finding.check_family} · "
                f"{finding.column or '-'} · {finding.rule}"
            )
        clean_seeds += result.ok
    echo(f"{clean_seeds}/{seeds} seeds clean.")
    return clean_seeds == seeds


def run_oracle(
    root: Path,
    *,
    seeds: int,
    per_type: int,
    keep: Path | None = None,
    echo: Callable[[str], None] = print,
) -> bool:
    """Run the whole oracle on a scenario folder. True when every step is clean."""
    try:
        scenario = load_scenario(root)
    except ScenarioError as error:
        echo(str(error))
        return False
    with tempfile.TemporaryDirectory() as tmp:
        work = (keep or Path(tmp)).resolve()
        work.mkdir(parents=True, exist_ok=True)
        try:
            return _run(scenario, work, seeds, per_type, echo)
        except OracleError as error:
            echo(str(error))
            return False
