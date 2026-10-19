"""Command-line entry point for relay-engine."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import polars as pl
import typer

from relay_engine import __version__
from relay_engine.console import describe, summary_lines
from relay_engine.env import load_env_file
from relay_engine.generator.generate import generate as run_generate
from relay_engine.io.catalog import SourcesError
from relay_engine.io.readers import CatalogSource, CsvShapeError
from relay_engine.mapping import MappingError, load_mapping, validate_mapping

DataOption = Annotated[
    Path, typer.Option(help="Directory holding <table>.parquet files (when no --sources).")
]
SourcesOption = Annotated[
    Path | None,
    typer.Option(help="Sources catalog (sources.yaml): CSV, databases or Parquet per table."),
]
_USER_ERRORS = (MappingError, SourcesError, CsvShapeError, ValueError)
_verbose = False


@contextmanager
def _reported(action: str) -> Iterator[None]:
    """Any failure ends the command with one sentence, never a stack trace."""
    try:
        yield
    except typer.Exit:
        raise
    except FileNotFoundError as error:
        typer.echo(f"File not found: {error.filename or describe(error)}")
        raise typer.Exit(code=1) from error
    except _USER_ERRORS as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    except Exception as error:
        if _verbose:
            raise
        typer.echo(f"{action} failed: {describe(error)}")
        typer.echo("Details: rerun with relay --verbose.")
        raise typer.Exit(code=1) from error


class _Tables:
    """Where a command reads its tables: a Parquet directory, or a sources catalog."""

    def __init__(self, data: Path, sources: Path | None) -> None:
        self._data = data
        self._catalog: CatalogSource | None = None
        if sources is not None:
            from relay_engine.io.catalog import load_sources

            declared = load_sources(sources)
            self._declared = set(declared)
            self._catalog = CatalogSource(declared)

    def exists(self, table: str) -> bool:
        if self._catalog is None:
            return (self._data / f"{table}.parquet").exists()
        return table in self._declared

    def columns(self, table: str) -> list[str]:
        if self._catalog is None:
            return list(pl.read_parquet_schema(self._data / f"{table}.parquet"))
        return list(self._catalog.schema(table))

    def spec_types(self, table: str) -> dict[str, str]:
        from relay_engine.mapping.scaffold import spec_type

        if self._catalog is None:
            schema = pl.read_parquet_schema(self._data / f"{table}.parquet")
        else:
            schema = self._catalog.schema(table)
        return {c: spec_type(t) for c, t in schema.items()}

    def source(self):
        from relay_engine.io import LocalParquetStore

        return self._catalog or LocalParquetStore(self._data)


app = typer.Typer(
    name="relay",
    help="Relay — prove a data migration is correct.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


@app.callback()
def _options(
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Show the full error when something fails.")
    ] = False,
) -> None:
    global _verbose
    _verbose = verbose


@app.command()
def version() -> None:
    """Print the engine version."""
    typer.echo(__version__)


@app.command()
def generate(
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("data/generated"),
    seed: Annotated[int, typer.Option(help="Random seed (reproducible).")] = 42,
    rows: Annotated[int, typer.Option(help="Number of chantiers to generate.")] = 100,
) -> None:
    """Generate a synthetic legacy/target dataset with an anomaly manifest."""
    with _reported("Generate"):
        manifest = run_generate(out, seed=seed, rows=rows)
    typer.echo(
        f"Generated in {out}: {len(manifest.entities)} entities, "
        f"{len(manifest.anomalies)} injected anomalies (seed={seed})."
    )


@app.command()
def validate(
    mapping: Annotated[Path, typer.Argument(help="Mapping spec (YAML).")],
    data: DataOption = Path("data/generated"),
    sources: SourcesOption = None,
) -> None:
    """Check a mapping spec against the real source and target schemas."""
    with _reported("Validate"):
        spec = load_mapping(mapping)
        tables = _Tables(data, sources)
        referenced = {
            table: tables.columns(table)
            for table in spec.referenced_tables()
            if tables.exists(table)
        }
        validate_mapping(
            spec, tables.columns(spec.source.table), tables.columns(spec.target.table), referenced
        )
    typer.echo(f"Mapping '{spec.entity}' is valid.")


@app.command()
def run(
    mapping: Annotated[
        Path, typer.Argument(help="Mapping spec (YAML), or a folder of them for a whole migration.")
    ],
    data: DataOption = Path("data/generated"),
    sources: SourcesOption = None,
    out: Annotated[Path, typer.Option(help="Directory where runs are written.")] = Path(
        "data/runs"
    ),
    decisions: Annotated[
        Path, typer.Option(help="Directory of human decisions, shared by every run.")
    ] = Path("data/decisions"),
) -> None:
    """Run the pipeline: bronze, silver, checks and gold (checks run before any write)."""
    from relay_engine.decisions import read_decisions
    from relay_engine.io import LocalParquetStore
    from relay_engine.mapping import load_mappings
    from relay_engine.pipeline import new_run_id, run_migration
    from relay_engine.report import write_report

    run_id = new_run_id()
    with _reported("Run"):
        specs = load_mappings(mapping)
        source = _Tables(data, sources).source()
        decided = read_decisions(decisions)
        sink = LocalParquetStore(out / run_id)
        migration = run_migration(specs, source, sink, run_id, decided)
        found = pl.read_parquet(out / run_id / "gold" / "recon_finding" / "*.parquet")
        report = write_report(out / run_id, decided)

    def counts(e) -> str:
        return f"({e.fail} fail, {e.review} review, {e.accepted} accepted, {e.passed} pass)"

    if mapping.is_dir():
        typer.echo(
            f"Run {run_id} — migration ({len(migration.entities)} entities): {migration.verdict}"
        )
        width = max(len(e.entity) for e in migration.entities)
        for e in migration.entities:
            typer.echo(f"  {e.entity:<{width}}  {e.verdict:<6}  {counts(e)}")
    else:
        (e,) = migration.entities
        typer.echo(f"Run {run_id} — {e.entity}: {e.verdict} {counts(e)}.")
    for line in summary_lines(found, by_entity=mapping.is_dir()):
        typer.echo(line)
    typer.echo(f"Details: relay findings {out / run_id}")
    typer.echo(f"Report: {report}")


@app.command()
def findings(
    run_dir: Annotated[Path, typer.Argument(help="A run directory, e.g. data/runs/<run_id>.")],
) -> None:
    """List the findings of a run, with the finding_key needed to decide on them."""
    files = sorted((run_dir / "gold" / "recon_finding").glob("*.parquet"))
    if not files:
        typer.echo(f"No run found in {run_dir}.")
        raise typer.Exit(code=1)
    with _reported("Findings"):
        rows = pl.read_parquet(files).sort("verdict", "entity", "match_key_value")
    for r in rows.iter_rows(named=True):
        decision = f" [{r['decision']}]" if r["decision"] else ""
        values = (
            f"  {r['source_value']} → {r['target_value']}"
            if r["source_value"] is not None or r["target_value"] is not None
            else ""
        )
        column = f"  {r['column']}" if r["column"] else ""
        typer.echo(
            f"{r['verdict']}{decision}  {r['entity']}  {r['match_key_value']}{column}{values}\n"
            f"    {r['rule']}\n    key: {r['finding_key']}"
        )
    typer.echo(f"{rows.height} finding(s).")


@app.command()
def decide(
    finding_key: Annotated[str, typer.Argument(help="The finding_key to decide on.")],
    accept: Annotated[bool, typer.Option("--accept", help="Accept the discrepancy.")] = False,
    reject: Annotated[bool, typer.Option("--reject", help="Confirm it as a defect.")] = False,
    reason: Annotated[str, typer.Option(help="Why. Kept for the audit trail.")] = "",
    by: Annotated[str | None, typer.Option(help="Who decides (default: current user).")] = None,
    decisions: Annotated[
        Path, typer.Option(help="Directory of human decisions, shared by every run.")
    ] = Path("data/decisions"),
) -> None:
    """Record a decision on a finding. Later runs inherit it while the values are unchanged."""
    import getpass

    from relay_engine.decisions import record_decision

    if len(finding_key) != 64 or any(c not in "0123456789abcdef" for c in finding_key):
        typer.echo("A finding_key is 64 hexadecimal characters; copy it from `relay findings`.")
        raise typer.Exit(code=1)
    if accept == reject:
        typer.echo("Choose exactly one of --accept or --reject.")
        raise typer.Exit(code=1)
    if not reason.strip():
        typer.echo("A --reason is required: decisions form the audit trail.")
        raise typer.Exit(code=1)
    with _reported("Decide"):
        record_decision(decisions, finding_key, "accepted" if accept else "rejected",
                        by or getpass.getuser(), reason)
    typer.echo(f"Decision recorded: {'accepted' if accept else 'rejected'} {finding_key[:12]}…")


@app.command()
def scaffold(
    entity: Annotated[str, typer.Argument(help="Entity name, e.g. chantiers.")],
    source: Annotated[str, typer.Option(help="Source table name.")],
    target: Annotated[str, typer.Option(help="Target table name.")],
    data: DataOption = Path("data/generated"),
    sources: SourcesOption = None,
    output: Annotated[
        Path | None,
        typer.Option(help="Where to write the skeleton (default mappings/<entity>.yaml)."),
    ] = None,
) -> None:
    """Write a mapping skeleton from the real schemas: same names pre-filled, the rest TODO."""
    from relay_engine.mapping.scaffold import scaffold_mapping

    path = output or Path("mappings") / f"{entity}.yaml"
    if path.exists():
        typer.echo(f"{path} already exists; refusing to overwrite a mapping in progress.")
        raise typer.Exit(code=1)
    with _reported("Scaffold"):
        tables = _Tables(data, sources)
        schemas = [tables.spec_types(table) for table in (source, target)]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scaffold_mapping(entity, source, schemas[0], target, schemas[1]))
    todo = sum(line.lstrip().startswith(("- source: TODO", "- TODO")) for line in
               path.read_text().splitlines())
    typer.echo(
        f"Skeleton written to {path}: {todo} TODO(s) to complete, then run `relay validate`."
    )


def main() -> None:
    load_env_file(Path.cwd() / ".env")
    app()
