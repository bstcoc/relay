# Roadmap

Each step is a vertical slice that can be shown on its own. Every feature is
born in the engine and designed for the app.

## The engine migrates and proves

Reading files and databases (PostgreSQL, MySQL, SQL Server, SQLite),
declarative mapping, four check families, three-state verdict, carried-over
decisions, signable report. Writing to the target in dependency order with a
dry run first and a transaction, creating the tables of an empty target, and
suggested column mappings.

## The desktop app

Local service over stdin/stdout, connections with credentials in the system
keychain, infrastructure map, guided migration: pick a source and a target,
validate mappings visually, dry run, migrate, review the report and decide
on gaps, all without a terminal or YAML.

## Migration options

- **Consistent subset**: migrate only part of the data (one customer, one
  period); related rows follow and no foreign key breaks.
- **Anonymization**: personal data detected and masked on the way, stably;
  on by default from production to non-production.

## Teams

Solo use stays local, with no account. A team that wants accounts and shared
connections plugs in its own Supabase project (cloud free tier or
self-hosted).

## More databases

One adapter per database, in order of demand: Oracle, MongoDB, Firebase
(Firestore), then the next ones.

## Later

Mappings suggested by a language model, Power BI export, business rules
across several tables.
