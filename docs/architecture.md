# Architecture

## Overview

```
┌─ App ─────────────────────────────────────┐   the product
│  infrastructure · schema map               │   desktop first (Electron),
│  mappings · migration · proof              │   web later
└────────────────────┬──────────────────────┘
                     │ stdin / stdout, JSON
┌────────────────────▼──────────────────────┐
│  Local service                             │   started with the desktop app;
│  exposes the engine, keeps credentials     │   system keychain
└────────────────────┬──────────────────────┘
                     │ library
┌────────────────────▼──────────────────────┐   CLI: another consumer,
│  Engine (Python / Polars)                  │   for developers
│  read · transform · write · verify         │
└──────┬─────────────────────────────┬──────┘
       │ adapters, one per database   │ writes
┌──────▼──────────────┐   ┌───────────▼───────────────┐
│ PostgreSQL/Supabase │   │ Results + decisions       │
│ SQL Server · MySQL  │   │ (gold layer, contract)    │
│ SQLite · files      │   └───────────────────────────┘
│ then Oracle, Mongo… │
└─────────────────────┘
```

The **app** is the product: the user connects their databases, sees their
schemas, validates the column mappings and runs migrations. It does no
processing itself: it goes through the **local service**, which exposes the
**engine**. The local service talks to the app over stdin and stdout, with no
network port. The engine is a library with a stable output contract; the CLI
is another consumer of it.

Each database is an **adapter** of the core: read its schema, read its data,
write to it. The core only knows Polars and abstract interfaces, so adding a
database does not touch the rest.

The web app will come after the desktop app, with an **agent** installed on
the user's side to reach private databases: a hosted app cannot reach them
directly.

## A migration inside the engine

```
   source (adapter)                       target (adapter)
          │                                      ▲   │
          ▼                                      │   │ read back
   BRONZE   raw data, immutable                  │   │
          │        ◄── mapping (written by app)  │   │
          ▼                                      │   │
   SILVER   source shaped to the target schema ──┘   │
            renames, conversions, normalization      │ write
                                                     ▼
   GOLD     source ↔ target checks: completeness / fidelity /
            business_rule / referential
            recon_run ← the verdict · recon_finding ← one gap per row
```

The **silver** layer is exactly what gets written to the target. The
**gold** layer holds the check results; human decisions live next to it, so
they survive later runs. This is the contract the app reads
([results model](results-model.md)).

## Layers

| Layer | Role | Content |
|---|---|---|
| **Bronze** | Raw, immutable landing of both sides | Source and target data as received, plus `run_id`, `source`, `ingested_at` |
| **Silver** | Source shaped to the target schema | The mapping applied: renames, conversions, normalization; this is what Relay writes to the target |
| **Gold** | Check results | `recon_run` (one row per entity) and `recon_finding` (one row per gap); `recon_decision` is written separately, by the app |

## The four check families

| Family | Question | Examples |
|---|---|---|
| **Completeness** | Does every source row land somewhere? | Cardinality reconciliation, lost rows, rows deliberately left out |
| **Fidelity** | Did values survive the transformation? | Truncation, encoding, money rounding, time zones and date formats, `NULL` vs `''`, type changes |
| **Business rules** | Do domain invariants still hold? | Sum of invoices ≤ contract amount, identical monthly totals before and after |
| **Referential** | Is relational integrity preserved? | Orphan foreign keys, duplicates created by a merge, natural key collisions |

## The three-state verdict

| Verdict | Meaning | Example |
|---|---|---|
| **Pass** | Compliant | identical values after normalization |
| **Review** | Gap found, **human decision required** | amount off by 0.01 beyond tolerance |
| **Fail** | Clear, blocking anomaly | lost row, orphan foreign key |

Relay does not claim to know whether a 0.01 gap matters: that is a business
call. It puts it on the table, waits for a decision in the app, and
**remembers** it so it is not asked again on the next run.

The engine compares matched rows column by column after a join on the
declared match key, whose uniqueness is checked first. It does not compute a
row fingerprint: measurements show the direct comparison holds at 10 million
rows ([performance](performance.md)).
