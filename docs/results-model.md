# Results model

This is the engine's **stable contract**: what the app and exports read. It
lives in the gold layer.

It answers three questions, at three zoom levels:

1. **Is this migration good?** → `recon_run`
2. **Where are the problems?** → `recon_finding`
3. **What was decided about them?** → `recon_decision`

The reconciliation report (`report.html`, written on every run) only reads
these three tables: it adds no fact, it lays them out for a client who signs
off.

## Why three tables, not one

A flat table would force the human decision to be written **on the same
row** as a fact produced by the engine. On the next run, the engine
regenerates its facts and overwrites the decision, or has to work around it.

With three tables, **the engine writes on one side, the human on the
other**: the engine alone owns `recon_run` and `recon_finding`, which it can
regenerate freely; it only **reads** `recon_decision` and never touches it.
They meet through the `finding_key`. That is what makes the audit reliable.

## `recon_run`: one row per entity and per run

The summary to sign off, shown first. A run covers a migration: every entity
reconciled together shares the same `run_id`. The **migration verdict** is
the worst verdict among the rows of a `run_id`; it is derived, not stored.

| Column | Example |
|---|---|
| `run_id` | `2026-09-23T084706_74cc` |
| `entity` | `chantiers`, one row per entity in the run |
| `started_at` / `finished_at` | UTC timestamp |
| `engine_version` | `0.4.1` |
| `mapping_version` | fingerprint of the spec used |
| `total_rows_source` / `total_rows_target` | `2847132` |
| `pass` / `review` / `fail` | `2840001` / `7100` / `31` |
| `accepted` | `12`, findings accepted by a human decision |
| `verdict` | `REVIEW`, the worst verdict found, decisions included |

`review` counts **undecided** `REVIEW` findings; `fail` counts undecided
`FAIL` findings **and** every rejected finding; `accepted` counts accepted
findings, which no longer weigh on the verdict. `pass` counts the **rows**
present on both sides that no check flagged.

## `recon_finding`: one row per gap

The core. Every gap, with what it takes to locate and decide it. Fully
regenerated on every run.

| Column | Example |
|---|---|
| `run_id` | → `recon_run` |
| `entity` | `sites` |
| `check_family` | `fidelity` / `completeness` / `business_rule` / `referential` |
| `match_key_value` | `magasin_id=00412`, `a=1, b=2` for a composite key |
| `column` | `montant_hors_taxes`, `null` for a row-level gap |
| `source_value` / `target_value` | `15000.00` / `14999.99`, as text |
| `verdict` | `REVIEW` |
| `rule` | `tolerance 0.01 exceeded (diff 0.03)` |
| `finding_key` | stable fingerprint, see below |
| `decision` | `accepted` / `rejected` / `null`, the inherited decision if any |

For an `aggregate` rule, `match_key_value` names the group
(`group=2024-03`), not a row. A value unreadable in its declared type is a
`fidelity` / `FAIL` gap, with rule `source value is not a valid <type>` or
`target value is not a valid <type>`, and the value as written.

## `recon_decision`: one row per human decision

Written by the consumer, never by the engine: the `relay decide` command or
the app. It lives **outside the runs** (`data/decisions/recon_decision/` by
default), since it must outlive them. When the same finding was decided
several times, **the most recent decision wins**.

| Column | Example |
|---|---|
| `finding_key` | → link to `recon_finding` |
| `decision` | `accepted` / `rejected` |
| `decided_by` | `alice` |
| `decided_at` | timestamp |
| `reason` | "known rounding, accepted" |

## The `finding_key` and carry-over

```
finding_key = hash(entity + match_key_value + column + source_value + target_value)
```

The key must be **stable** across runs, otherwise carry-over does not work,
and **value-sensitive**, otherwise a value that changed would stay approved
forever. Including the values in the hash gives both properties at once.

**Carry-over**, which solves "I re-approve 400 gaps on every run": on the
next run, the engine computes the `finding_key` of each gap and looks for an
existing decision.

- Decision found and values unchanged → the finding **inherits** the
  decision and does not go back to `Review`.
- Value changed → the key changes, so no decision matches: the finding goes
  **back** to `Review`. The previous decision was about another value; it no
  longer applies.

Hashing runs in Python over the list of strings of every gap in a run: it
handles a few million gaps easily, and needs watching beyond 20 million,
where that list weighs several gigabytes.

## Still to settle

- The hash function and its width (collision risk).
- Partitioning tables by `run_id` and retention of old runs.
