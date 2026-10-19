# Relay

This file holds **only what an agent cannot discover** by reading the
repository: intentions, prohibitions, and irreversible consequences.
Everything else (what the project does, how it is structured) is in
[README.md](README.md) and `docs/`. Add nothing here that can be deduced
from the code or the documentation.

## The product

Relay is a **migration assistant app**, desktop first, web later. The user
connects their databases, sees their infrastructure, and runs a migration
between two databases, same schema or not, same engine or not. Relay does
it, then proves it.

Relay is open source and free, for everyone, from the solo developer on a
cloud database to a large company's teams. The test for every choice: you
migrate without writing a script or YAML, and without spending a week on
it. A feature is born in the engine and designed for the app.

**The CLI is secondary.** It stays, for developers who want it, but it is
not the heart of the product: no feature is designed, planned or shipped for
the CLI alone. A ticket or plan that leads to a new command before the
matching screen is going the wrong way.

Solo use is local, with no account. A team that wants accounts and sharing
connects its own Supabase project (cloud free tier or self-hosted).

## Scope

Connectors are built **one database at a time**, each in its own adapter.
Out of scope unless explicitly asked:

- connectors to software APIs (CRM, SaaS): Airbyte does that;
- translating SQL code (queries, views, stored procedures): SQLGlot does
  that. Relay migrates data, and creates the tables of an empty target.

Relay **suggests** column mappings; it never applies a mapping a human has
not validated.

## User data and credentials

- **A connection credential never leaves a machine in clear text**: stored
  in the system keychain, encrypted for the team, or read from the company
  vault; never written in clear, not in a file, a log, or an error message.
- **No row or value from a user's database is ever stored by a shared
  service**: shared services keep metadata only; data stays on the user's
  machine or network.
- **A migration from production to a non-production target anonymizes
  personal data by default.** The user can turn it off, never forget it.
- **Nothing is written to a target database without a dry run offered
  first**, and the write happens in a transaction when the database allows
  it.

## Budget: 0 €, no exceptions

The project must cost its author nothing. Everything runs locally, with free
and open-source tools; cloud databases are tested locally (emulators,
containers). Do not provision billed capacity, create cloud resources,
subscribe to a paid service, or propose a solution whose free tier expires.

When a dependency or an API has a cost, say so before introducing it.

## Code rules you cannot deduce

- **The core only knows Polars and abstract interfaces.** A database's
  driver or SDK is imported in its adapter, never in the core.
- **Amounts are decimals, never floats.** A rounding introduced by Relay is
  indistinguishable from a real anomaly.
- **Business identifiers are strings**, never numbers. A site code
  `"00412"` must not lose its leading zero.
- **No comments in code.** The name of a function, variable or test says
  what it does; a decision is explained in a commit message or PR
  description, never in a comment.
- **Datasets are never committed.** `data/` is ignored. The generator and
  its anomaly manifest are committed: they are the source of truth, not
  their output.

## Language

Everything is in **English**: code, identifiers, documentation, error and
log messages, test names, CI steps, commit messages and PRs. Only the app's
localized UI strings are translated.

## Git workflow

**Never push or force-push to `main`.** Everything goes through a PR, and
Bastien merges after review.

- One branch per ticket of the Linear project **Relay**, named as Linear
  suggests (`bastiencochet/rel-23-…`). No ticket: create one first.
- Commits follow Conventional Commits, with `refs REL-23` in the body;
  `closes REL-23` on the commit that finishes the ticket.
- The command under `Commands` passes before opening the PR.
- One PR to `main` per ticket. The ticket then moves to `In Review`, and to
  `Done` on merge. Several related tickets may share a PR only when Bastien
  explicitly asks; it then closes each of them.
- Merge a PR only on Bastien's explicit instruction, PR by PR.
- Rewriting history (amend, rebase) is allowed only on your own branch,
  before the merge.
- A decision that goes beyond one commit is explained in the PR
  description.

## Limits of authority

Without explicit human instruction, do not: change the repository's
visibility, create or rotate secrets, merge a PR. Remote reads are allowed.

Every access to an outside service (Linear, Supabase, GitHub…) goes through
Composio, never through another connector plugged into the session.

## Commands

From `engine/`, the command that validates a change, to run before saying
any work is done:

```sh
uv run pytest && uv run ruff check . && uv run ty check
```

CI (`.github/workflows/engine.yml`) runs the same command on every PR that
touches `engine/`.

Before changing the generator or a check, also run the multi-seed oracle
scan (`uv run python scripts/oracle_scan.py`, one second): the test suite
uses a single seed, and the scan has already found two defects it missed.

The engine installs without Java or Spark, and must stay that way.

A Ruff or ty rule that blocks a change is solved by fixing the code, never
by disabling the rule.

## Visual identity

The design system is `@relay/ui`: the shadcn components in
`packages/ui/src/components` and the theme in
`packages/ui/src/styles/globals.css`. Use these components and variables,
never hard-coded values. For visual detail and motion, Emil Kowalski's
skills are the reference. `relay-brand` only keeps the logos.
