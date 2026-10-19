"""What the command line prints: one sentence per error, findings grouped."""

from __future__ import annotations

import polars as pl


def describe(error: BaseException) -> str:
    """One readable line: the spec or catalog problems, or the first line of the error."""
    problems = getattr(error, "problems", None)
    if isinstance(problems, list) and problems:
        return "; ".join(str(p) for p in problems)
    lines = str(error).strip().splitlines()
    return lines[0] if lines else type(error).__name__


def summary_lines(found: pl.DataFrame, limit: int = 10, *, by_entity: bool = False) -> list[str]:
    """Findings counted by verdict, column and rule (and entity), most frequent first."""
    keys = ["entity"] * by_entity + ["verdict", "column", "rule"]
    groups = (
        found.group_by(keys, maintain_order=True)
        .len()
        .sort("len", descending=True, maintain_order=True)
    )
    width = max(map(len, found.get_column("entity").unique()), default=0) if by_entity else 0
    lines = [
        f"{row['len']:>9,}".replace(",", " ")
        + (f"  {row['entity']:<{width}}" if by_entity else "")
        + f"  {row['verdict']:<6}  {row['column'] or '(row)':<20}  {row['rule']}"
        for row in groups.head(limit).iter_rows(named=True)
    ]
    if groups.height > limit:
        lines.append(f"  … {groups.height - limit} more group(s)")
    return lines
