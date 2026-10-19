# Mapping specification

The mapping spec is the **contract** of a migration. The same declaration
drives the transformation (bronze → silver) and the fidelity checks. It is
written in YAML.

It is an **internal format**: in the app, the user validates column mappings
on screen and the app writes this spec for them. This document is for the
engine, the CLI, and the expert who wants to read or edit it.

**One entity per file.** A migration is a folder of mapping files, one
logical table per file.

## Structure

```yaml
version: 1
entity: sites                       # logical name of the reconciled entity

source:
  table: anc_sites
target:
  table: site

# match key between source and target; uniqueness checked by the engine
match_key:
  - magasin_id
# maximum share of source rows caught in a duplicated key (default 0.05)
max_duplicate_share: 0.05

# rows deliberately left out of the migration:
# their absence from the target is expected, not a completeness Fail
source_scope:
  expected_missing: "statut = 'archive'"

columns:
  # 1→1
  - source: nom_magasin
    target: nom
    type: string
    normalize: [trim, empty_as_null]

  # amount with a tolerance, applied to the column comparison
  - source: mnt_ht
    target: montant_hors_taxes
    type: decimal(12,2)
    tolerance: 0.01

  # date: time and time zone ignored
  - source: dt_ouverture
    target: date_ouverture
    type: date
    normalize: date_only

  # business identifier: stays a string, never a number
  - source: magasin
    target: magasin_id
    type: string

  # 1→N: one source split into several targets
  - source: adresse_complete
    target: [rue, code_postal, ville]
    transform: split
    separator: ", "

  # N→1: several sources merged into one target
  - source: [rue, code_postal, ville]
    target: adresse_complete
    transform: concat
    separator: ", "

  # excluded column: exists in the source, deliberately has no target
  - source: fichier_b64
    exclude: true
    reason: "base64 blob moved to a bucket, out of the database scope"

  # target column with no source: created by the new system
  - target: statut_workflow
    target_only: true
    reason: "field specific to the new ERP"
```

## Rules

### Exhaustive coverage
Any target column not covered by a `columns` entry is **reported when the
spec is validated**, never silently ignored. A column cannot be forgotten
without the tool saying so. A column only the new system has is declared
`target_only` (see below): it is covered, not forgotten.

### match_key
The key that pairs source and target rows, checked **on the source side**
before any comparison. Its columns get the same normalization and type on
both sides: a `trim` key pairs `"C001 "` in the target with `"C001"` in the
source, and a `string` key pairs an integer identifier from a target
database. What counts is the **share of source rows caught in a duplicate**
(three rows sharing a key count as three):

- above `max_duplicate_share` (**0.05** by default) → **stop**: the key does
  not tell rows apart; the diagnostic gives the share and examples;
- otherwise → the run goes on: each duplicated key becomes a Referential
  `REVIEW` finding (`match_key duplicated in source (×N)`) and leaves the
  fidelity comparison, which could not know which row to compare.

`max_duplicate_share` accepts a number in `[0, 1]`: `0` stops on the first
duplicate, `1` never stops. On the target side, a key is a `FAIL` when the
target has more copies of it than the source: the migration created a copy.

### tolerance and normalize
`normalize` brings values on both sides to a canonical form **before
comparison**. `tolerance` then applies, column by column, to the difference
between normalized values: a gap declared acceptable (e.g. `0.01`) passes;
beyond it, the verdict is `Review`, not `Fail`. Available normalizations:
`trim`, `empty_as_null`, `date_only`, `lower` and `decimal_comma` (decimal
comma of French exports, see [sources](sources.md)). An unknown rule is
rejected when the spec is loaded. `trim` removes whitespace from every
script, non-breaking space included, at both ends.

### source_format / target_format (dates)
The read format of a `date` or `datetime` column (or one normalized with
`date_only`), **declared separately for each side**, as `strftime`
directives:

```yaml
  - source: Créé le
    target: Créé le
    type: date
    normalize: [empty_as_null, date_only]
    source_format: "%d/%m/%Y"          # old ERP: 12/03/2024
    target_format: "%d/%m/%Y %H:%M"    # new ERP: 12/03/2024 10:30
```

Without a format, only ISO is read (`2024-03-12`, with or without a time). A
declared format is the **only** one read on that side, exactly: a value
written otherwise is unreadable and becomes a `FAIL` on its cell
([sources](sources.md#unreadable-values)). A `date` column read with a format
that carries a time keeps only the day. A format that cannot read back the
date it writes (`%Q`, `dd/mm/yyyy`) is rejected when the spec is loaded.

### transform: split / concat
1→N split or N→1 merge. `separator` is **required** both ways: without it,
the engine does not know where to cut or how to join. The fidelity check
works **by recomposition**: the engine re-joins the targets and compares them
with the normalized source. Equal → `Pass`; different → `Review`. The engine
does not have to "understand" the content (an address, say), only to check
that nothing is lost on the round trip.

### references (foreign keys)
Declares that a target column points to the key of another target table:

```yaml
references:
  - column: chantier_id        # target column of this entity
    table: chantiers_target    # referenced target table
    key: chantier_id           # its key
```

A value missing from `table.key` is an **orphan foreign key** (`Fail`,
Referential family). A `NULL` foreign key references nothing: it is not an
orphan. `relay validate` checks that the column, the table and the key exist.

The key of the referenced table is read with the normalization and type of
the column pointing to it: if `chantier_id` is trimmed, `"C1 "` on one side
matches `"C1"` on the other. The rules of the referenced table's own mapping
do not apply to this read.

**Inherited orphans.** A foreign key can already be an orphan in the old
system: the migration copied it faithfully and is not to blame. When the
referenced table's mapping is part of the run (`relay run mappings/`), the
engine also reads the parent table on the source side. A target orphan is
then **inherited** if the source row carried the same value, already missing
from the source parent: verdict `Review`, rule `… value not found in source
either (inherited)`. Any other orphan (parent lost on the way, value changed,
row without a source) stays a `Fail`. A run on a single entity does not see
the source parent: all its orphans stay `Fail`.

### business_rules
Invariants declared in SQL (Polars' SQL), in three forms:

```yaml
business_rules:
  - name: montant_positif              # must hold on every target row
    check: "montant_hors_taxes > 0"
    verdict: FAIL                      # FAIL (default) or REVIEW

  - name: totaux_mensuels              # same total on both sides, per group
    aggregate: "sum(montant_hors_taxes)"
    group_by: "strftime(date_facture, '%Y-%m')"
    tolerance: 0.01
    verdict: REVIEW

  - name: situations_dans_le_marche    # crosses another target table
    cross:
      table: contrats_target           # catalog name, as in references
      on: {contrat_id: contrat_id}     # column of this target: column of the other table
      totals: {total_situations: "sum(montant)"}
    check: "total_situations <= montant_marche"
```

`check` follows SQL semantics: a `NULL` result passes. `aggregate` compares
the total computed on the conformed source with the target's; without
`group_by`, a single global total. Both forms read the target **normalized
and typed by the mapping**, like every check: a column declared
`decimal(12,2)` compares with `0` without a `CAST`, even when read from a
CSV, and a value the mapping trims is trimmed before the rule. A rule
declares **exactly one** of `check` and `aggregate`.

`cross` turns a `check` into a **cross-entity** rule, evaluated on the
written target: the target is joined to another target table through `on`,
and the `check` must hold on every joined row. With `totals`, the target is
first aggregated by join key (`total_situations` per `contrat_id`) and each
group that breaks the rule yields a finding on that key (`contrat_id=c1`);
without `totals`, one finding per broken row, on the `match_key`. The other
table is read as written in the target (a column read from a CSV is text:
`CAST` if needed), join keys compare as text, and a column of the other table
named like a target column gets the `_right` suffix. An unknown table or join
column is rejected at validation.

### exclude, target_only and source_scope
They separate **intended** absence from **accidental** absence:
- `exclude: true` on a source column with no target;
- `target_only: true` on a target column with no source: a field the old
  system did not have. The entry only declares `target` and a `reason`; the
  column is neither compared nor written to silver, but `check` rules can
  read it as written. It cannot be a `match_key`: it has nothing to pair;
- `source_scope.expected_missing` for source rows that are not migrated: a
  **SQL predicate** on source columns, for example `statut = 'archive'` or
  `date_fin < '2015-01-01'`.

Without these declarations, such absences come up as `Fail`. With them, the
engine can tell "loss caused by a bug" from "migration choice".

### anonymize
`anonymize` masks a personal column on the source side, before writing,
keeping the shape of the value:

| Mask | Example | Types |
|---|---|---|
| `email` | `user-4146b15f@example.com` | text |
| `phone` | `06 48 21 93 07`: prefix and separators kept | text, integer |
| `first_name`, `last_name`, `full_name` | `Marc Imbert`, drawn from a fictional list | text |
| `address` | `42 rue des Lilas` | text |
| `city` | `Rennes`, drawn from a list | text |
| `postal_code` | `48217`: same number of digits | text, integer |
| `birth_date` | another date in the same year | text, date |
| `iban` | same country, valid check digits | text |
| `ssn` | same digits in number and position | text, integer |
| `pseudonym` | `AB-1234` becomes `QX-8812`: letters, digits and punctuation in place, an accented letter becomes a plain one | text, integer |
| `blank` | `NULL` | all |

A mask is stable: the same value gets the same mask throughout a running
engine, so a key or a link between tables stays consistent; the HMAC key
that derives it is created when the engine starts and is never written
anywhere. Reconciliation compares the target with the already-masked source:
an anonymized column stays proven, never reported as a gap. Relay recognizes
personal columns by their name and suggests the matching mask; the app
applies it by default from a production database to a non-production one.

### Subset
A migration can keep only part of its tables: on each, a SQL predicate
(`where`) and a row count (`limit`). Every table that references a filtered
table, directly or not, keeps only rows pointing to a kept row, and also
applies its own filter if it has one; tables above stay whole, so every
foreign key finds its parent. Reconciliation covers this subset.

## Suggested mappings

In the app, nobody writes this file: Relay suggests it
(`relay_engine.suggest`).

- **Tables** are paired by their names (ignoring `legacy`, `target`, `old`…)
  and above all by their columns.
- **Columns** are paired one by one, each at most once, with a score and its
  reason: names split into words, abbreviations and synonyms (`mnt` /
  `montant`, `nom` / `name`, `dt` / `date`), initials (`ht` / `hors_taxes`),
  then the share of shared values and the nature of the values (text,
  number, date). Two identical schemas match entirely.
- **The resulting mapping** declares the type of every target column, adds
  `trim` when the source has edge whitespace and `date_only` when a date
  becomes a day; unmatched columns are `exclude` or `target_only`, with their
  reason; the key is the target's primary key or, failing that, a column
  that identifies every row on both sides.

A score of 0.75 or more is a **confident** match; below that, it is
**uncertain** and the app flags it. A `split` or `concat` is never
suggested: the user declares it. Nothing is applied without human
validation.

## Starting a mapping from the command line

`relay scaffold <entity> --source <table> --target <table>` reads both real
schemas and writes a skeleton to `mappings/<entity>.yaml`:

- one entry per target column, with its type;
- the source column **pre-filled only when it has exactly the same name**;
  otherwise `source: TODO`;
- `match_key: [TODO]`: choosing the key is a business decision;
- unused source columns, listed as comments, to map or exclude.

Simpler than suggested mappings, the scaffold only pairs identical names. It
refuses to overwrite an existing mapping. The full path:

```
relay scaffold → fill in the TODOs → relay validate → relay run
```

## Validation

`relay validate <mapping.yaml> --data <folder>` checks the spec **before**
any run and lists **every** problem at once, in plain words: missing
required field, unknown type, `split`/`concat` without a separator, missing
source column, uncovered target column, target column declared but missing
from the data, `match_key` naming no produced column (or a `target_only`
column), and every `TODO` left in a skeleton. Exit code 1 if the spec is
invalid.

The reference mappings of the generated dataset, `engine/examples/mappings/`,
are complete templates.
