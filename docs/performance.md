# Performance at scale

Does reconciliation hold on millions of rows?

## How to measure

```sh
cd engine
uv run python scripts/benchmark.py                      # 100,000, 1,000,000 and 10,000,000 rows
uv run python scripts/benchmark.py --rows 100000 1000000
```

The script generates the datasets with the synthetic generator
(`relay_engine.generator`, seed 42) in a temporary folder deleted at the end,
then replays the reconciliation of the two example entities (`chantiers`,
`factures`) step by step, in the same order as `pipeline.run_migration`. A
third process runs `run_migration` itself, in one go: its duration and peak
are the `run_migration` column.

- **"N rows"**: N `chantiers` and 2 × N `factures`, i.e. 6 × N rows read in
  total (source and target of both entities).
- **Time**: wall clock (`time.perf_counter`), in seconds, summed over both
  entities.
- **Memory**: peak resident memory of the process
  (`resource.getrusage(...).ru_maxrss`), not `tracemalloc`, which does not
  see Polars' native allocations. Generation, reconciliation and
  `run_migration` each run in a fresh process, so each peak belongs to one
  phase only.

## Machine

| | |
|---|---|
| CPU | Apple M5, 10 cores (`sysctl machdep.cpu.brand_string hw.ncpu`) |
| Memory | 16 GiB (`hw.memsize` = 17,179,869,184) |
| OS | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 |
| Python | 3.14.4 |
| Polars | 1.44.2 |

## Results

Times in seconds. Columns `completeness` to `business_rules` are the four
check families; `verdict` groups decisions, counting and passing rows;
`pipeline` is the sum of the steps, generation excluded.

### Before fixes (first measurement, the only one at 10 M)

| Rows | generation | read | silver | completeness | referential | fidelity | business_rules | verdict | write bronze | write silver | write gold | **pipeline** | generation peak | reconciliation peak |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100,000 | 0.96 | 0.01 | 0.09 | 0.01 | 0.02 | 0.05 | 0.00 | 0.01 | 0.03 | 0.01 | 0.00 | **0.23** | 456 MiB | 403 MiB |
| 1,000,000 | 10.78 | 0.04 | 0.38 | 0.16 | 0.52 | 0.84 | 0.00 | 0.15 | 0.15 | 0.06 | 0.00 | **2.31** | 2,548 MiB | 1,889 MiB |
| 10,000,000 | 508.26 | 0.34 | 6.69 | 3.93 | **98.80** | 19.82 | 0.02 | 2.15 | 1.94 | 0.59 | 0.01 | **134.28** | 6,491 MiB | 7,167 MiB |

At 10 M, the full run took 643.5 s (10 min 43 s), 508 s of which was
generation. Nothing broke: no error, no out-of-memory.

### After the referential check fix

| Rows | generation | read | silver | completeness | referential | fidelity | business_rules | verdict | write bronze | write silver | write gold | **pipeline** | generation peak | reconciliation peak |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100,000 | 0.92 | 0.01 | 0.08 | 0.01 | 0.02 | 0.05 | 0.00 | 0.01 | 0.02 | 0.01 | 0.00 | **0.22** | 448 MiB | 393 MiB |
| 1,000,000 | 9.22 | 0.04 | 0.36 | 0.15 | 0.36 | 0.73 | 0.00 | 0.13 | 0.14 | 0.06 | 0.00 | **1.98** | 3,279 MiB | 1,847 MiB |
| 3,000,000 | 36.46 | 0.11 | 1.19 | 0.63 | 1.38 | 2.96 | 0.00 | 0.57 | 0.47 | 0.17 | 0.00 | **7.48** | 5,645 MiB | 4,865 MiB |

10 M was not rerun after the fix. The generation peak varies between runs:
under memory pressure, macOS compresses and swaps, and resident memory then
underestimates the real need (7 GiB of swap used while generating 10 M).

### After the performance and memory pass

| Rows | generation | read | silver | completeness | referential | fidelity | business_rules | verdict | write bronze | write silver | write gold | **pipeline** | generation peak | reconciliation peak | `run_migration` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000,000, before | 12.12 | 0.04 | 0.38 | 0.15 | 0.38 | 0.78 | 0.00 | 0.14 | 0.15 | 0.05 | 0.00 | **2.09** | 3,238 MiB | 1,851 MiB | 2.08 s, 1,841 MiB |
| 1,000,000, after | 9.10 | 0.04 | 0.35 | 0.14 | 0.34 | 0.39 | 0.00 | 0.13 | 0.14 | 0.05 | 0.00 | **1.58** | 3,193 MiB | 1,803 MiB | 1.63 s, 1,685 MiB |

The `run_migration` column is the one that matters: the step-by-step replay
still keeps every table until the end. The peak varies by about 50 MiB
between runs.

Other measurements, outside `benchmark.py`, on the same 1 M dataset:

| Measurement | Before | After |
|---|---:|---:|
| `run_migration`, four independent entities of 1 M `chantiers` | 2.53 s, 2,237 MiB | 2.61 s, 1,452 MiB |
| `propose` then `suggest`, SQLite sources and targets (1 M `chantiers`, 2 M `factures`) | 8.1 s, 1,611 MiB | 0.4 s, 197 MiB |
| `connect` on a 2 M-row CSV | 0.62 s, 358 MiB | 0.59 s, 64 MiB |
| `connect` on a 2 M-row Parquet file | 210 MiB | 77 MiB |
| Idle service (`/usr/bin/time -l uv run python -c "import relay_engine.service"`) | 84.8 MB | 66.8 MB |

## Bottlenecks

1. **Referential check, `is_in` on a chunked target: fixed.**
   `checks/referential.py` looked for orphan foreign keys with
   `~value.is_in(parent.implode())`, twice per reference (target, then source
   for inheritance). On a table read from Parquet (49 chunks at 3 M), this
   test cost 0.84 s and 0.89 s at 3 M, against 0.06 s for an equivalent
   anti-join; at 10 M, it took most of the check's 98.8 s (190 times the 1 M
   time for 10 times the rows). It is replaced by an anti-join (`_not_in`),
   which keeps the target's order and matches no NULL key.
2. **The generator, not the engine, is the first wall.**
   `generator/generate.py` builds each row in Python (dicts, `Decimal`,
   `datetime`): 508 s and over 6 GiB at 10 M, four times the pipeline. It is
   enough to measure, but 30 M rows or more would not fit in 16 GiB.
3. **Fidelity grows faster than rows.** `checks/fidelity.py`
   (`check_fidelity`): 0.73 s at 1 M, 2.96 s at 3 M, 19.8 s at 10 M before
   the fix. Three joins on the key (uniqueness on each side, then pairing)
   copied each whole side. **Partly fixed**: each side only keeps the
   compared columns, after a semi-join on its unique keys, and both sides
   join in a single lazy query; 0.78 s → 0.39 s at 1 M. Not remeasured at
   10 M.
4. **Everything is loaded in memory: partly fixed.** `LocalParquetStore.read`
   still reads eagerly, but `run_migration` frees each table as soon as no
   later entity reads it; the bronze and silver of a freed table wait in a
   temporary folder (Arrow IPC) until every check has passed, so a stopped
   run still writes nothing. The peak no longer grows with the number of
   independent entities (four entities: 2,237 → 1,452 MiB), but stays that of
   the heaviest entity and the tables it references. `migrate` no longer
   rereads sources after writing them. Before the fix: 7.2 GiB peak at 10 M,
   about 0.7 GiB per million rows.
5. **No row fingerprint.** The engine compares columns directly after the
   join, and the measurement shows it holds at 10 M.
6. **`finding_key` is computed in Python.** `checks/findings.py` (`_sha256`)
   hashes each finding in a Python loop. Negligible here (a dozen findings),
   but a migration where a column differs everywhere would produce one
   finding per row: about a second per million. Polars has no stable native
   SHA-256, and the key must stay identical across runs to find decisions.

## Defect found along the way

The generator injected the orphan foreign key under the fixed value
`C99999`, which becomes a real `chantier` from 100,000 rows: the anomaly
disappeared and the oracle scan failed at that size (`missed=[('factures',
…, 'FAIL')]`). The orphan now points to `C{max(rows, 99999)}`, which never
exists; datasets under 100,000 rows are unchanged.

## Next steps

- Rerun `benchmark.py` at 10 M to measure the referential and fidelity
  fixes.
- An entity's peak comes mostly from the checks themselves (1.3 GiB for 1 M
  `chantiers` alone, for 0.2 GiB of data read): moving side preparation and
  checks to lazy (`scan_parquet`, streaming) is the next lead.
- Vectorize the generator in Polars to measure beyond 10 M.
- Bring back a row fingerprint only if a measurement shows it pays off.
