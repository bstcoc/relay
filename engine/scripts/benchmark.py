"""Benchmark: time each stage of a reconciliation over synthetic datasets of growing size.

Each size runs in three fresh processes: one generates the data, one reconciles it stage
by stage, one runs `run_migration` whole; so each peak memory figure belongs to one phase.
Peak memory is the process high-water resident set size (resource.getrusage ru_maxrss),
which counts Polars' native allocations; tracemalloc would only see Python objects.

    uv run python scripts/benchmark.py --rows 100000 1000000
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
from pathlib import Path

import polars as pl

from relay_engine.checks.business_rules import check_business_rules
from relay_engine.checks.completeness import check_completeness
from relay_engine.checks.fidelity import check_fidelity
from relay_engine.checks.referential import check_referential
from relay_engine.decisions import apply_decisions, effective_counts
from relay_engine.generator.generate import generate
from relay_engine.io import LocalParquetStore
from relay_engine.layers.bronze import land
from relay_engine.mapping import MappingSpec, load_mapping
from relay_engine.pipeline import _passing_rows, _source_parents, new_run_id, run_migration
from relay_engine.sides import Sides, prepare

ENGINE = Path(__file__).resolve().parent.parent
MAPPINGS = ENGINE / "examples" / "mappings"
ENTITIES = ("chantiers", "factures")
STAGES = (
    "read", "silver", "completeness", "referential", "fidelity", "business_rules",
    "verdict", "bronze_write", "silver_write", "gold_write",
)


def peak_mib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 2**20 if sys.platform == "darwin" else peak / 2**10


class Clock:
    def __init__(self) -> None:
        self.seconds: dict[str, float] = dict.fromkeys(STAGES, 0.0)
        self.peak_after: dict[str, float] = {}

    @contextmanager
    def __call__(self, stage: str) -> Iterator[None]:
        start = time.perf_counter()
        yield
        self.seconds[stage] += time.perf_counter() - start
        self.peak_after[stage] = peak_mib()


def generate_worker(data: Path, rows: int) -> dict[str, object]:
    start = time.perf_counter()
    generate(data, seed=42, rows=rows)
    return {"seconds": time.perf_counter() - start, "peak_mib": peak_mib()}


def reconcile_worker(data: Path) -> dict[str, object]:
    specs = [load_mapping(MAPPINGS / f"{entity}.yaml") for entity in ENTITIES]
    by_target = {s.target.table: s for s in specs}
    source, run_id = LocalParquetStore(data), new_run_id()
    sink = LocalParquetStore(data / "out" / run_id)
    read = cache(source.read)
    clock = Clock()
    landed: set[str] = set()
    found_all: list[pl.DataFrame] = []
    for spec in specs:
        with clock("read"):
            legacy, target = read(spec.source.table), read(spec.target.table)
            referenced = {ref.table: read(ref.table) for ref in spec.references}
            parents = _source_parents(spec, by_target, read)
        with clock("silver"):
            sides = prepare(spec, legacy, target)
        with clock("completeness"):
            found = [check_completeness(sides, spec)]
        with clock("referential"):
            found.append(check_referential(sides, spec, referenced, parents))
        with clock("fidelity"):
            found.append(check_fidelity(sides, spec))
        with clock("business_rules"):
            found.append(check_business_rules(sides, spec))
        with clock("verdict"):
            found_all.append(_verdict(sides, spec, pl.concat(found), run_id))
        for table, frame in ((spec.source.table, legacy), (spec.target.table, target)):
            if table not in landed:
                landed.add(table)
                with clock("bronze_write"):
                    sink.write(land(frame, run_id, table), f"bronze/{table}")
        with clock("silver_write"):
            sink.write(sides.silver, f"silver/{spec.entity}")
    with clock("gold_write"):
        sink.write(pl.concat(found_all), "gold/recon_finding")
    findings = pl.concat(found_all).group_by("verdict").len().sort("verdict").rows()
    return {
        "seconds": clock.seconds, "peak_after": clock.peak_after, "peak_mib": peak_mib(),
        "findings": dict(findings),
    }


def migration_worker(data: Path) -> dict[str, object]:
    specs = [load_mapping(MAPPINGS / f"{entity}.yaml") for entity in ENTITIES]
    run_id = new_run_id()
    start = time.perf_counter()
    run_migration(specs, LocalParquetStore(data), LocalParquetStore(data / "out" / run_id), run_id)
    return {"seconds": time.perf_counter() - start, "peak_mib": peak_mib()}


def _verdict(sides: Sides, spec: MappingSpec, found: pl.DataFrame, run_id: str) -> pl.DataFrame:
    found = apply_decisions(found, None).with_columns(pl.lit(run_id).alias("run_id"))
    effective_counts(found)
    _passing_rows(sides, spec.match_key, found)
    return found


def child(worker: str, data: Path, rows: int, timeout: float) -> dict[str, object]:
    command = [sys.executable, __file__, "--worker", worker, "--data", str(data),
               "--rows", str(rows)]
    start = time.perf_counter()
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout:.0f} s"}
    if done.returncode != 0:
        tail = done.stderr.strip().splitlines()[-1:] or [f"exit code {done.returncode}"]
        return {"error": f"{tail[0]} (after {time.perf_counter() - start:.0f} s)"}
    return json.loads(done.stdout.strip().splitlines()[-1])


def print_table(results: dict[int, dict[str, dict[str, object]]]) -> None:
    columns = ["rows", "generate", *STAGES, "pipeline", "peak gen", "peak run", "run_migration"]
    print(" | ".join(columns))
    for rows, phases in results.items():
        gen, rec = phases["generate"], phases.get("reconcile", {"error": "skipped"})
        whole = phases.get("migration", {"error": "skipped"})
        cells = [f"{rows:,}", _seconds(gen)]
        if "error" in rec:
            cells += ["-"] * (len(STAGES) + 1) + [_mib(gen), str(rec["error"])]
        else:
            stages = rec["seconds"]
            assert isinstance(stages, dict)
            cells += [f"{stages[s]:.2f}" for s in STAGES]
            cells += [f"{sum(stages.values()):.2f}", _mib(gen), _mib(rec)]
        cells.append(f"{_seconds(whole)} s, {_mib(whole)}")
        print(" | ".join(cells))


def _seconds(phase: dict[str, object]) -> str:
    return str(phase["error"]) if "error" in phase else f"{phase['seconds']:.2f}"


def _mib(phase: dict[str, object]) -> str:
    return "-" if "error" in phase else f"{phase['peak_mib']:.0f} MiB"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, nargs="+", default=[100_000, 1_000_000, 10_000_000])
    parser.add_argument("--dir", type=Path, help="parent of the temp dir")
    parser.add_argument("--timeout", type=float, default=900, help="seconds per phase")
    parser.add_argument(
        "--worker", choices=["generate", "reconcile", "migration"], help=argparse.SUPPRESS
    )
    parser.add_argument("--data", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker == "generate":
        print(json.dumps(generate_worker(args.data, args.rows[0])))
        return
    if args.worker == "reconcile":
        print(json.dumps(reconcile_worker(args.data)))
        return
    if args.worker == "migration":
        print(json.dumps(migration_worker(args.data)))
        return

    with tempfile.TemporaryDirectory(dir=args.dir) as tmp:
        results: dict[int, dict[str, dict[str, object]]] = {}
        for rows in args.rows:
            data = Path(tmp) / str(rows)
            results[rows] = {"generate": child("generate", data, rows, args.timeout)}
            if "error" not in results[rows]["generate"]:
                results[rows]["reconcile"] = child("reconcile", data, rows, args.timeout)
                results[rows]["migration"] = child("migration", data, rows, args.timeout)
            print(json.dumps({"rows": rows, **results[rows]}), file=sys.stderr, flush=True)
        print_table(results)


if __name__ == "__main__":
    main()
