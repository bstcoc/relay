"""Scenario oracle: a real export, a known migration, injected defects — does Relay find them?

Detection: each injected defect surfaces on its key, with its verdict and column.
Precision: no other finding beyond the baseline run on the clean migration.
Exits 1 on any miss, false positive or unexpected baseline.

    uv run python scripts/scenario_oracle.py <scenario> --seeds 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from relay_engine.env import load_env_file
from relay_engine.oracle.harness import run_oracle

ENGINE = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", type=Path, help="scenario folder, outside the repository")
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--per-type", type=int, default=2)
    parser.add_argument(
        "--keep", type=Path, default=None, help="keep databases, manifests and runs here"
    )
    args = parser.parse_args()
    load_env_file(ENGINE / ".env")
    ok = run_oracle(args.scenario, seeds=args.seeds, per_type=args.per_type, keep=args.keep)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
