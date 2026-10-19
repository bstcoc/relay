"""The reconciliation report: one self-contained HTML file a client can read and sign.

Built from the gold layer only (recon_run, recon_finding) plus the decisions'
reasons. Printing it from a browser gives the PDF. Styles use the Relay theme
tokens, embedded so the file opens anywhere, offline included.
"""

from __future__ import annotations

from collections.abc import Collection
from html import escape
from importlib.resources import files
from pathlib import Path

import polars as pl

from relay_engine.decisions import latest_decisions

DETAIL_LIMIT = 500

_STATUS = {
    "FAIL": ("danger", "Failed"),
    "REVIEW": ("pending", "To review"),
    "PASS": ("verified", "Verified"),
    "accepted": ("neutral", "Accepted"),
}
_HEADLINE = {
    "PASS": "The migration is verified",
    "REVIEW": "The migration needs a review",
    "FAIL": "The migration has failures",
}
_FAMILIES = {
    "completeness": ("Completeness", "Does every source row reach the target?"),
    "fidelity": ("Fidelity", "Did the values survive the transformation?"),
    "referential": ("Referential integrity", "Are keys unique and relationships kept?"),
    "business_rule": ("Business rules", "Do the declared invariants hold?"),
}
_ORDER = {"FAIL": 0, "REVIEW": 1, "accepted": 2}

_CSS = """
body { margin: 0; background: var(--background); color: var(--ink); }
main { max-width: 1120px; margin: 0 auto; padding: var(--space-12) var(--space-8); }
header { display: flex; justify-content: space-between; align-items: baseline;
  padding-bottom: var(--space-4); border-bottom: 1px solid var(--border); }
section { margin-top: var(--space-12); }
h1, h2, p { margin: 0; }
h1 { margin-top: var(--space-8); }
h2 { margin-bottom: var(--space-2); }
p { max-width: 72ch; margin-top: var(--space-2); }
.muted { color: var(--ink-muted); }
table { width: 100%; border-collapse: collapse; margin-top: var(--space-4); }
th { text-align: left; color: var(--ink-muted); }
th, td { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--border);
  vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
code { font-family: var(--font-mono); background: var(--surface-muted);
  border-radius: var(--radius-sm); padding: 0 var(--space-1); overflow-wrap: anywhere; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 0 var(--space-2);
  border-radius: var(--radius-sm); white-space: nowrap; }
.badge::before { content: ""; width: 6px; height: 6px; border-radius: var(--radius-full);
  background: currentColor; }
.verified { background: var(--verified-soft); color: var(--verified); }
.danger { background: var(--danger-soft); color: var(--danger); }
.pending { background: var(--pending-soft); color: var(--pending); }
.neutral { background: var(--surface-muted); color: var(--ink-muted); }
.sign { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-8);
  margin-top: var(--space-6); }
.sign div { border-top: 1px solid var(--border-strong); padding-top: var(--space-2);
  min-height: var(--space-16); }
@media print { main { padding: 0; } section { break-inside: avoid-page; } }
"""
_PRINT_LIGHT = (
    "addEventListener('beforeprint',()=>document.documentElement.dataset.theme='light');"
    "addEventListener('afterprint',()=>delete document.documentElement.dataset.theme);"
)


def _n(value: int) -> str:
    """Exact count, thin space between thousands."""
    return f"{value:,}".replace(",", " ")


def _badge(status: str) -> str:
    tone, word = _STATUS[status]
    return f'<span class="badge caption {tone}">{word}</span>'


def _code(value: str | None) -> str:
    return "" if value is None else f'<code class="mono-small">{escape(value)}</code>'


def _table(head: list[str], rows: list[list[str]], numeric: Collection[int] = ()) -> str:
    def cells(tag: str, values: list[str]) -> str:
        return "".join(
            f"<{tag}{' class="num"' if i in numeric else ''}>{v}</{tag}>"
            for i, v in enumerate(values)
        )

    body = "".join(f"<tr>{cells('td', r)}</tr>" for r in rows)
    return (
        f'<table class="body-small"><thead><tr>{cells("th", head)}</tr></thead>'
        f"<tbody>{body}</tbody></table>"
    )


def _effective(found: pl.DataFrame) -> pl.DataFrame:
    """Each finding's status once decisions apply: accepted, or FAIL/REVIEW."""
    decision, verdict = pl.col("decision"), pl.col("verdict")
    status = (
        pl.when(decision == "accepted").then(pl.lit("accepted"))
        .when(decision == "rejected").then(pl.lit("FAIL"))
        .otherwise(verdict)
    )
    return found.with_columns(status.alias("status")).sort(
        pl.col("status").replace_strict(_ORDER, return_dtype=pl.Int8),
        "entity", "check_family", "match_key_value", "column", nulls_last=True,
    )


def _overview(runs: pl.DataFrame) -> str:
    verdict = max(runs.get_column("verdict"), key=["PASS", "REVIEW", "FAIL"].index)
    total = runs.select(pl.sum("total_rows_source", "total_rows_target", "fail", "review",
                               "accepted")).row(0, named=True)
    entities = runs.height
    return (
        f'<h1 class="heading-1">{_HEADLINE[verdict]}</h1>'
        f'<p class="body">{_badge(verdict)}</p>'
        f'<p class="body">{_n(entities)} {"entity" if entities == 1 else "entities"}, '
        f"{_n(total['total_rows_source'])} source rows, "
        f"{_n(total['total_rows_target'])} target rows. "
        f"{_n(total['fail'])} failed, {_n(total['review'])} to review, "
        f"{_n(total['accepted'])} accepted by a decision.</p>"
    )


def _entities(runs: pl.DataFrame) -> str:
    rows = [
        [escape(r["entity"]), _n(r["total_rows_source"]), _n(r["total_rows_target"]),
         _n(r["pass"]), _n(r["fail"]), _n(r["review"]), _n(r["accepted"]),
         _badge(r["verdict"]), _code(r["mapping_version"])]
        for r in runs.iter_rows(named=True)
    ]
    head = ["Entity", "Source rows", "Target rows", "Rows verified", "Failed", "To review",
            "Accepted", "Verdict", "Mapping"]
    return (
        '<section><h2 class="heading-2">Entities</h2>'
        '<p class="body-small muted">Rows verified are present on both sides and pass every '
        "check. The mapping fingerprint identifies the exact spec used.</p>"
        f"{_table(head, rows, numeric={1, 2, 3, 4, 5, 6})}</section>"
    )


def _families(found: pl.DataFrame) -> str:
    rows = []
    for family, (name, question) in _FAMILIES.items():
        mine = found.filter(pl.col("check_family") == family).get_column("status")
        counts = {s: int((mine == s).sum()) for s in ("FAIL", "REVIEW", "accepted")}
        status = next((s for s in ("FAIL", "REVIEW") if counts[s]), "PASS")
        rows.append([f"{name}<br><span class=\"muted\">{question}</span>",
                     _n(counts["FAIL"]), _n(counts["REVIEW"]), _n(counts["accepted"]),
                     _badge(status)])
    return (
        '<section><h2 class="heading-2">Checks</h2>'
        f'{_table(["Check", "Failed", "To review", "Accepted", "Result"], rows, {1, 2, 3})}'
        "</section>"
    )


def _groups(found: pl.DataFrame) -> str:
    if found.is_empty():
        return ""
    groups = (
        found.group_by("status", "entity", "column", "rule", maintain_order=True)
        .len()
        .sort("len", descending=True, maintain_order=True)
    )
    rows = [
        [_badge(g["status"]), escape(g["entity"]), _code(g["column"]) or "whole row",
         escape(g["rule"]), _n(g["len"])]
        for g in groups.iter_rows(named=True)
    ]
    return (
        '<section><h2 class="heading-2">Discrepancies by kind</h2>'
        f'{_table(["Status", "Entity", "Column", "Rule", "Count"], rows, {4})}</section>'
    )


def _detail(found: pl.DataFrame) -> str:
    if found.is_empty():
        return ""
    parts = ['<section><h2 class="heading-2">Discrepancies in detail</h2>']
    for (entity,), rows in found.group_by("entity", maintain_order=True):
        shown = rows.head(DETAIL_LIMIT)
        table = [
            [_badge(r["status"]), _FAMILIES[r["check_family"]][0], _code(r["match_key_value"]),
             _code(r["column"]), _code(r["source_value"]), _code(r["target_value"]),
             escape(r["rule"])]
            for r in shown.iter_rows(named=True)
        ]
        parts.append(f'<h3 class="heading-3">{escape(str(entity))}</h3>')
        if rows.height > shown.height:
            parts.append(
                f'<p class="body-small muted">First {_n(shown.height)} of '
                f"{_n(rows.height)}. The full list: <code>relay findings</code> on this run.</p>"
            )
        parts.append(_table(["Status", "Check", "Key", "Column", "Source", "Target", "Rule"],
                            table))
    parts.append("</section>")
    return "".join(parts)


def _decisions(found: pl.DataFrame, decisions: pl.DataFrame | None) -> str:
    decided = found.filter(pl.col("decision").is_not_null())
    if decided.is_empty():
        return ""
    if decisions is not None:
        reasons = latest_decisions(decisions).select("finding_key", "decided_by", "decided_at",
                                                     "reason")
        decided = decided.join(reasons, on="finding_key", how="left")
    else:
        decided = decided.with_columns(
            pl.lit(None, pl.String).alias(c) for c in ("decided_by", "decided_at", "reason")
        )
    rows = [
        [escape(r["decision"]), escape(r["entity"]), _code(r["match_key_value"]),
         _code(r["column"]), escape(r["reason"] or ""), escape(r["decided_by"] or ""),
         escape(str(r["decided_at"] or ""))]
        for r in decided.iter_rows(named=True)
    ]
    head = ["Decision", "Entity", "Key", "Column", "Reason", "By", "On (UTC)"]
    return (
        '<section><h2 class="heading-2">Decisions</h2>'
        '<p class="body-small muted">Discrepancies a person judged. Accepted ones no longer '
        f"weigh on the verdict.</p>{_table(head, rows)}</section>"
    )


def render_report(
    runs: pl.DataFrame, found: pl.DataFrame, decisions: pl.DataFrame | None = None
) -> str:
    """The HTML report of one run: recon_run rows, recon_finding rows, decisions recorded."""
    found = _effective(found)
    run_id = runs.item(0, "run_id")
    finished = runs.get_column("finished_at").max()
    tokens = files(__package__).joinpath("tokens.css").read_text(encoding="utf-8")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Relay — reconciliation report {escape(run_id)}</title>"
        f"<style>{tokens}{_CSS}</style><script>{_PRINT_LIGHT}</script></head>"
        '<body><main><header><span class="heading-3">Relay</span>'
        f'<span class="body-small muted">Reconciliation report · run {_code(run_id)} · '
        f"finished {escape(f'{finished:%Y-%m-%d %H:%M}')} UTC · "
        f"engine {escape(runs.item(0, 'engine_version'))}</span></header>"
        f"{_overview(runs)}{_entities(runs)}{_families(found)}{_groups(found)}"
        f"{_detail(found)}{_decisions(found, decisions)}"
        '<section><h2 class="heading-2">Sign-off</h2>'
        '<p class="body-small muted">By signing, you confirm you have read this report and '
        "accept the migration as it stands.</p>"
        '<div class="sign body-small"><div>Name</div><div>Date</div><div>Signature</div></div>'
        "</section></main></body></html>"
    )


def write_report(run_dir: Path, decisions: pl.DataFrame | None = None) -> Path:
    """Write `report.html` into a run directory, from its gold layer."""
    gold = run_dir / "gold"
    report = run_dir / "report.html"
    report.write_text(
        render_report(
            pl.read_parquet(gold / "recon_run" / "*.parquet"),
            pl.read_parquet(gold / "recon_finding" / "*.parquet"),
            decisions,
        ),
        encoding="utf-8",
    )
    return report
