# Relay

**Move data between databases, then prove nothing was lost.**

Relay is a free, open-source desktop app for data migration. Connect your
databases, see your infrastructure, and migrate from one database to another,
same schema or not, same engine or not. Relay suggests which column goes
where, runs the migration, then checks it row by row and hands you a
signable report. No scripts, no YAML.

It is for anyone who has to move data: a solo developer copying production
to staging, a team switching ERPs, a company moving to a new database.

## What it does

1. **Connect** your databases (PostgreSQL, Supabase, SQL Server, MySQL,
   SQLite) and files (CSV, Parquet). Credentials go to the system keychain
   and never leave your machine.
2. **See** a map of your infrastructure: databases, tables, columns, volumes,
   links between tables.
3. **Pick a source and a target**, with the same schema (copy prod to
   staging) or a different one (a `client` table on PostgreSQL to a
   `customers` table on SQL Server, with renamed columns). Relay creates the
   tables of an empty target.
4. **Validate the mappings** Relay suggests. Nothing is applied until a
   human approves it.
5. **Migrate**: a dry run first, then a write in a single transaction.
6. **Prove it**: four families of checks (completeness, fidelity, business
   rules, referential integrity) give each row a verdict, `Pass`, `Review`
   or `Fail`. Decisions on gaps are remembered across runs.

Options for any migration: keep only a **consistent subset** of the data,
and **anonymize** personal data, on by default from production to a
non-production target.

## Download

Builds for macOS (Apple silicon), Windows and Linux are published on the
[Releases](https://github.com/bstcoc/relay/releases) page of this
repository. The app updates itself.

The macOS build is only ad hoc signed: on first launch, macOS blocks it.
Allow it in System Settings → Privacy & Security → "Open Anyway".

## Build from source

Requirements: [Bun](https://bun.sh) and [uv](https://docs.astral.sh/uv/)
(the engine runs on Python 3.14; uv installs it).

```sh
bun install                      # once, from the repository root
bun run desktop                  # run the desktop app

cd engine
uv sync --all-extras             # engine and database drivers
uv run pytest && uv run ruff check . && uv run ty check
```

The engine needs neither Java nor Spark. See [engine/README.md](engine/README.md)
for the engine and its developer CLI, and
[apps/desktop/README.md](apps/desktop/README.md) for the app and packaging.

## Repository layout

| Path | Content |
|---|---|
| `engine/` | The engine (Python, Polars): read, transform, write, verify; plus a developer CLI |
| `apps/desktop/` | The desktop app (Electron, Next.js), the main interface |
| `apps/landing/` | The landing page |
| `packages/ui/` | `@relay/ui`, the shared design system (shadcn/ui, Tailwind CSS) |
| `packages/contract/` | The results schema shared by the engine and the apps |
| `supabase/` | Database schema for optional team accounts |
| `relay-brand/` | Logos |
| `docs/` | Technical documentation |

## Documentation

- [Architecture](docs/architecture.md)
- [Mapping specification](docs/mapping-spec.md)
- [Results model](docs/results-model.md)
- [Source catalog](docs/sources.md), for the CLI
- [Performance at scale](docs/performance.md)
- [Roadmap](ROADMAP.md)

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE). Copyright 2026 Bastien Cochet.
