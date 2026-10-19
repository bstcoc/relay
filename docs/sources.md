# Source catalog

This catalog is for the **CLI**. In the app, the user adds connections on
screen and credentials stay in the system keychain.

`sources.yaml` says **where to read each table**: a Parquet file, a CSV
export or a database. It is kept apart from the mapping, which describes a
correspondence, not a storage.

```sh
relay validate mappings/chantiers.yaml --sources sources.yaml
relay run      mappings/chantiers.yaml --sources sources.yaml
relay run      mappings/ --sources sources.yaml        # every entity, one verdict
relay scaffold chantiers --source chantiers_legacy --target chantiers_target \
               --sources sources.yaml
```

Without `--sources`, commands read `<table>.parquet` in `--data`.

## Format

```yaml
chantiers_legacy:              # the table name used in the mapping
  csv: exports/chantiers.csv   # path relative to sources.yaml
  delimiter: ";"               # "," by default
  encoding: cp1252             # utf-8 by default
  header: true                 # default

factures_legacy:
  parquet: exports/factures.parquet

chantiers_target:
  database: postgresql://relay:${RELAY_TARGET_PASSWORD}@db:5432/erp
  table: public.chantier

erp_local:
  database: sqlite:///exports/erp.db   # path relative to sources.yaml
  table: chantier
```

Each table declares **exactly one** form: `parquet`, `csv` or `database`.
`relay validate` reports every catalog problem at once: missing file, missing
environment variable, unsupported dialect.

## Secrets

**No secret is ever written in `sources.yaml`.** Any `${VAR}` value is read
from the environment; a missing variable stops the command with a clear
message. The file can therefore be versioned with the mapping.

## CSV

Every column is read **as text**: the mapping's `type:` entries type them.
Settings specific to ERP exports:

- **Windows-1252 encoding** (`cp1252`): declare `encoding: cp1252`. Any
  encoding Python knows is accepted; a UTF-8 BOM is ignored.
- **Multi-line fields**: a quoted field may contain line breaks and is read
  as one value. A line break **outside quotes** splits the record into two
  half-empty lines: the engine does not guess how to glue them back. Before
  the run, it checks that every line has as many fields as the header, and
  stops otherwise, saying how many lines and which:
  `old.csv: 20 line(s) do not have the 12 fields of the header: line 1791 (5 fields), …`.
  Quote the value or repair the export. An empty line is not a record: it is
  ignored.
- **Decimal comma**: declare `normalize: [decimal_comma]` on numeric
  columns. `1 234,56` becomes `1234.56` (thousands spaces removed). Without
  this rule, the amount does not read as a number and comes up as a "value
  is not a valid decimal" gap (see below).
- **No header** (`header: false`): columns are named `column_1`,
  `column_2`… Two header columns with the same name keep the first; the
  next ones become `name_duplicated_0`, `name_duplicated_1`…
- **Schema**: `relay validate` and `relay scaffold` only read the first line
  of a CSV, the schema of a Parquet file and the first 1,000 rows of a
  database table to learn columns and types, never the whole table.

## Databases

Declared with a standard URL: `postgresql://…`, `mysql://…`, `mssql://…` or
`sqlite:///path/to/erp.db`. The table may carry its schema
(`public.chantier`).

**SQLite** reads and writes with nothing to install. Other databases need
the `databases` extra, which adds their read and write drivers.

## Migration target

The target tables of a migration are declared like the others, as
`database`, all in **the same database**: Relay writes them in a single
transaction, parents first. A target table that already holds rows stops the
migration, unless the user chooses to replace them; replacement happens in
the same transaction. A failure rolls everything back: the target stays as
it was.

A target table **missing** from the database is created by Relay from the
columns the mapping produces: types translated for each database (a
`decimal(12,2)` becomes `NUMERIC(12, 2)`, a string becomes `NVARCHAR` on SQL
Server), the match key as primary key when it identifies every row, and a
foreign key for each `references` to another target table's primary key.
The dry run shows each table's `CREATE TABLE` before it exists; a failure
drops the created tables.

## Dates

Without a declaration, only ISO (`2024-03-12`, with or without a time) is
read. A year alone (`2024`) reads as its January 1st, a year and month
(`2024-03`) as the 1st of the month. A datetime with an offset
(`2024-03-12T10:00:00Z`, `+02:00` or `+0200`) is read in UTC, without a time
zone: `2024-03-12 10:00:00+02:00` becomes `2024-03-12 08:00:00`; read as a
date, it keeps the written day. Other formats (`12/03/2024`) are declared in
the mapping, column by column and per side: `source_format` and
`target_format` ([mapping spec](mapping-spec.md#source_format--target_format-dates)).

## Unreadable values

A value that does not read in the type declared by the mapping (a date
`30/08/2023` without a declared format, `abc` for an `integer`) **does not
stop the run**. It becomes a `FAIL` gap on its cell, `fidelity` family, with
the value as written: `source value is not a valid date` or `target value is
not a valid date`. That cell is not compared a second time. An empty value is
never unreadable.
