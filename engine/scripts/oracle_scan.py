"""Oracle scan: generate datasets over several seeds and check every run against its manifest.

Detection: each injected anomaly surfaces on its key with the expected verdict.
Precision: no finding on a key the generator left untouched.
Exits 1 on the first seed with a miss or a false positive. Run it before changing
the generator or a check (AGENTS.md).

    uv run python scripts/oracle_scan.py --seeds 12
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import polars as pl

from relay_engine.generator.generate import generate
from relay_engine.io import LocalParquetStore
from relay_engine.mapping import load_mapping
from relay_engine.pipeline import new_run_id, run

ENGINE = Path(__file__).resolve().parent.parent
MAPPINGS = ENGINE / "examples" / "mappings"
KEY = {"chantiers": "chantier_id", "factures": "facture_id"}


def scan(seeds: int, rows: int) -> int:
    failures = 0
    for seed in range(1, seeds + 1):
        with tempfile.TemporaryDirectory() as tmp:
            data, out = Path(tmp) / "data", Path(tmp) / "out"
            manifest = generate(data, seed=seed, rows=rows)
            triples: set[tuple[str, str, str]] = set()
            for entity in KEY:
                run_id = new_run_id()
                run(
                    load_mapping(MAPPINGS / f"{entity}.yaml"),
                    LocalParquetStore(data),
                    LocalParquetStore(out / run_id),
                    run_id,
                )
                found = pl.read_parquet(out / run_id / "gold" / "recon_finding" / "*.parquet")
                triples |= set(found.select("entity", "match_key_value", "verdict").iter_rows())

        expected = {
            (a.entity, f"{KEY[a.entity]}={a.match_key}", a.expected_verdict.value)
            for a in manifest.anomalies
        }
        missed = sorted(expected - triples)
        touched = {(entity, key) for entity, key, _ in expected}
        false_positives = sorted({(e, k) for e, k, _ in triples} - touched)
        status = "ok" if not missed and not false_positives else "FAIL"
        print(
            f"seed {seed:3}: {len(manifest.anomalies):3} anomalies, "
            f"missed={missed} false_positives={false_positives} {status}",
            flush=True,
        )
        failures += status == "FAIL"
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--rows", type=int, default=60)
    args = parser.parse_args()
    failures = scan(args.seeds, args.rows)
    print(f"{args.seeds - failures}/{args.seeds} seeds clean.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
