"""The local service: the engine, driven by the app over stdin and stdout.

One JSON request per line in, one JSON response per line out, nothing else on
stdout. Connections and their credentials come with each request and are
never written anywhere by the service.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from relay_engine import __version__
from relay_engine.decisions import read_decisions, record_decision
from relay_engine.io import LocalParquetStore
from relay_engine.io.catalog import (
    DatabaseSource,
    SourcesError,
    describe,
    parse_sources,
    tunnels,
    without_credentials,
)
from relay_engine.io.readers import CatalogSource
from relay_engine.mapping import MappingError, MappingSpec
from relay_engine.migrate import migrate, plan_migration
from relay_engine.pipeline import new_run_id
from relay_engine.propose import SOURCE, TARGET, propose
from relay_engine.report import write_report
from relay_engine.subset import Filter, Reference, Subset
from relay_engine.suggest import suggest_tables, to_mapping

if TYPE_CHECKING:
    from relay_engine.io.database import DatabaseTarget

Params = dict[str, Any]
SAMPLE_ROWS = 50_000
FINDING_ORDER = ["entity", "check_family", "match_key_value", "column", "finding_key"]
METHODS = (
    "ping", "connect", "schema", "suggest", "propose", "plan", "migrate", "results", "decide",
)


class Service:
    """Every method the app may call, against one data directory for runs and decisions."""

    def __init__(self, data: Path) -> None:
        self.runs = data / "runs"
        self.decisions = data / "decisions"

    def _catalog(self, params: Params) -> dict:
        if "catalog" in params:
            return parse_sources(params["catalog"], Path(params.get("base", ".")))
        tables = {
            name
            for m in params["mappings"]
            for name in (m["source"]["table"], m["target"]["table"])
        }
        return self._pair(params, tables)

    def _pair(self, params: Params, tables: set[str]) -> dict:
        """The catalog of a migration between the `source` and `target` connections."""
        sides = {SOURCE: params["source"], TARGET: params["target"]}
        raw = {}
        for name in tables:
            prefix = SOURCE if name.startswith(SOURCE) else TARGET
            entry = sides[prefix]
            table = name.removeprefix(prefix)
            raw[name] = entry | {"table": table} if "database" in entry else entry
        return parse_sources(raw, Path(params.get("base", ".")))

    def _schema(self, entry: dict, base: Path) -> list[dict]:
        """A connection's tables with their keys, links and declared types; a file is one table."""
        if "database" not in entry:
            name = Path(next(v for k, v in entry.items() if k in ("csv", "parquet"))).stem
            return [{"name": name, "key": [], "references": [], "columns": []}]
        with self._database({"connection": entry, "base": str(base)}) as database:
            return database.schema()

    def _subset(self, params: Params) -> Subset | None:
        """The rows to migrate, when `subset` keeps only part of some source tables."""
        wanted = params.get("subset") or []
        wanted = [wanted] if isinstance(wanted, dict) else wanted
        if not wanted:
            return None
        references: dict[str, list[Reference]] = {}
        if "database" in params["source"]:
            base = {"connection": params["source"], "base": params.get("base", ".")}
            with self._database(base) as database:
                references = {
                    SOURCE + t["name"]: [
                        Reference(r["columns"], SOURCE + r["table"], r["to"])
                        for r in t["references"]
                    ]
                    for t in database.schema()
                }
        filters = [Filter(SOURCE + w["table"], w.get("where"), w.get("limit")) for w in wanted]
        return Subset(filters, references)

    def _specs(self, params: Params) -> list[MappingSpec]:
        return [MappingSpec.model_validate(m) for m in params["mappings"]]

    def ping(self, params: Params) -> dict:
        return {"version": __version__}

    @contextmanager
    def _database(self, params: Params) -> Iterator[DatabaseTarget]:
        from relay_engine.io.database import DatabaseTarget

        entry = params["connection"] | {"table": "-"}
        catalog = parse_sources({"connection": entry}, Path(params.get("base", ".")))
        with tunnels(catalog) as reached:
            config = reached["connection"]
            assert isinstance(config, DatabaseSource)
            yield DatabaseTarget(config.database)

    def connect(self, params: Params) -> dict:
        """Reach a connection: a database lists its tables, a file its columns."""
        entry = params["connection"]
        base = Path(params.get("base", "."))
        if "database" in entry:
            with self._database(params) as database:
                return {"tables": database.tables()}
        source = CatalogSource(parse_sources({"connection": entry}, base))
        return {"columns": list(source.schema("connection")), "rows": source.rows("connection")}

    def schema(self, params: Params) -> dict:
        """Map a connection: its tables, columns, volumes, keys and links."""
        entry = params["connection"]
        base = Path(params.get("base", "."))
        if "database" in entry:
            with self._database(params) as database:
                return {"tables": database.schema()}
        source = CatalogSource(parse_sources({"connection": entry}, base))
        name = Path(next(v for k, v in entry.items() if k in ("csv", "parquet"))).stem
        return {"tables": [{
            "name": name, "rows": source.rows("connection"), "key": [], "references": [],
            "columns": [
                {"name": column, "type": str(dtype), "nullable": True}
                for column, dtype in source.schema("connection").items()
            ],
        }]}

    def suggest(self, params: Params) -> list[dict]:
        with tunnels(self._catalog(params)) as reached:
            source = CatalogSource(reached)
            tables = {t: source.head(t, SAMPLE_ROWS) for t in params["sources"] + params["targets"]}
        matches = suggest_tables(
            {t: tables[t] for t in params["sources"]}, {t: tables[t] for t in params["targets"]}
        )
        return [
            dataclasses.asdict(m) | {
                "mapping": to_mapping(m, tables[m.source], tables[m.target]).model_dump(
                    mode="json", exclude_defaults=True
                ),
            }
            for m in matches
        ]

    def propose(self, params: Params) -> dict:
        """Proposed mappings from every table of `source` (or `tables`) to `target`."""
        base = Path(params.get("base", "."))
        source_schema = {t["name"]: t for t in self._schema(params["source"], base)}
        target_schema = {t["name"]: t for t in self._schema(params["target"], base)}
        wanted = params.get("tables") or list(source_schema)
        names = {SOURCE + t for t in wanted} | {TARGET + t for t in target_schema}
        catalog = self._pair(params, names)
        with tunnels(catalog) as reached:
            read = CatalogSource(reached)
            sources = {t: read.head(SOURCE + t, SAMPLE_ROWS) for t in wanted}
            targets = {t: read.head(TARGET + t, SAMPLE_ROWS) for t in target_schema}
        keys = {SOURCE + t: s["key"] for t, s in source_schema.items()} | {
            TARGET + t: s["key"] for t, s in target_schema.items()
        }
        declared = {
            t: {c["name"]: c["type"] for c in s["columns"]} for t, s in source_schema.items()
        }
        links = {t: s["references"] for t, s in source_schema.items()}
        proposals = propose(sources, targets, keys, declared, links)
        return {"proposals": [p.as_dict() for p in proposals]}

    def plan(self, params: Params) -> dict:
        plan = plan_migration(
            self._specs(params), self._catalog(params), replace=params.get("replace", False),
            subset=self._subset(params),
        )
        return dataclasses.asdict(plan) | {"blocked": [t.table for t in plan.blocked]}

    def migrate(self, params: Params) -> dict:
        run_id = new_run_id()
        decided = read_decisions(self.decisions)
        summary = migrate(
            self._specs(params), self._catalog(params), LocalParquetStore(self.runs / run_id),
            run_id, decided, replace=params.get("replace", False), subset=self._subset(params),
        )
        report = write_report(self.runs / run_id, decided)
        return dataclasses.asdict(summary) | {"verdict": summary.verdict, "report": str(report)}

    def results(self, params: Params) -> dict:
        """A run's entities, and one page of its findings that are not PASS, in a stable order."""
        gold = self.runs / params["run_id"] / "gold"
        flagged = pl.scan_parquet(gold / "recon_finding" / "*.parquet").filter(
            pl.col("verdict").ne_missing("PASS")
        )
        page = flagged.sort(FINDING_ORDER, nulls_last=True).slice(
            int(params.get("offset", 0)), int(params.get("limit", 200))
        )
        return {
            "runs": pl.read_parquet(gold / "recon_run" / "*.parquet").to_dicts(),
            "findings": page.collect().to_dicts(),
            "total": flagged.select(pl.len()).collect().item(),
        }

    def decide(self, params: Params) -> dict:
        record_decision(self.decisions, params["finding_key"], params["decision"],
                        params["by"], params["reason"])
        return {"recorded": True}


def _json(value: object) -> object:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal | Path):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON")


def handle(service: Service, line: str) -> dict:
    """One request, one response; an error never stops the service."""
    request_id = None
    try:
        request = json.loads(line)
        request_id = request.get("id")
        name = request.get("method")
        if name not in METHODS:
            return {"id": request_id, "error": {"message": f"unknown method {name}"}}
        method: Callable[[Params], object] = getattr(service, name)
        return {"id": request_id, "result": method(request.get("params") or {})}
    except (MappingError, SourcesError) as error:
        if isinstance(error.__cause__, pl.exceptions.PolarsError):
            cause = error.__cause__
            print(f"{type(cause).__name__}: {without_credentials(str(cause))}", file=sys.stderr)
        problems = [without_credentials(p) for p in error.problems]
        return {"id": request_id, "error": {"message": "; ".join(problems), "problems": problems}}
    except Exception as error:
        return {"id": request_id, "error": {"message": describe(error)}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay local service (stdin/stdout, JSON lines)")
    parser.add_argument("--data", type=Path, required=True, help="where runs and decisions live")
    service = Service(parser.parse_args().data)
    for line in sys.stdin:
        if line.strip():
            print(json.dumps(handle(service, line), default=_json), flush=True)


if __name__ == "__main__":
    main()
