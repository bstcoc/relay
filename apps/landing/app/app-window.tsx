"use client";

import { Badge } from "@relay/ui/components/badge";
import { Button } from "@relay/ui/components/button";
import { cn } from "@relay/ui/lib/utils";
import {
  Braces, ChevronsUpDown, Ellipsis, FingerprintPattern, Gauge, GitCompare, Logs, Route, Search, Settings,
  Target, Unplug, Waypoints,
} from "lucide-react";
import { type CSSProperties, type ReactNode, useState } from "react";
import { TeamArt } from "@relay/ui/components/team-art";
import { FOCUS } from "./classes";
import { CSV_MARK, Dot, EnvironmentPill } from "./fragments";
import { useLanguage } from "./i18n";
import { count } from "./words";

const NAV = [Target, Unplug, Waypoints, Route, Logs, GitCompare, null, FingerprintPattern, Braces, null, Gauge, Settings];

const PANEL = "overflow-hidden rounded-xl border border-border bg-background";

export type Screen = "overview" | "connections" | "map" | "migrations" | "findings";

const SCREEN_INDEX: Record<Screen, number> = { overview: 0, connections: 1, map: 2, migrations: 3, findings: 5 };

function Sidebar({ active }: { active: Screen }) {
  const { t } = useLanguage();
  let label = 0;
  return (
    <aside className="flex w-56 flex-none flex-col border-r border-border bg-sidebar text-sm @max-[900px]:hidden" aria-hidden="true">
      <div className="flex h-14 items-center gap-2 px-4">
        <TeamArt id={t.app.team} className="size-5 flex-none overflow-hidden rounded-full" />
        <span className="font-medium">{t.app.team}</span>
        <ChevronsUpDown className="ml-auto size-3.5 text-ink-muted" />
      </div>
      <div className="mx-2 flex h-9 items-center gap-2 rounded-full border border-input bg-field px-3 text-ink-muted">
        <Search className="size-3.5" />
        {t.app.find}
        <kbd className="caption ml-auto rounded-sm border border-border px-1 font-sans">F</kbd>
      </div>
      <nav className="mt-3 flex flex-col gap-0.5 px-2">
        {NAV.map((Icon, index) => {
          if (!Icon) {
            return <span key={index} className="my-2 h-px bg-border" />;
          }
          const position = label++;
          return (
            <span key={index} className={cn("flex h-8 items-center gap-2.5 rounded-lg px-2",
              position === SCREEN_INDEX[active] ? "bg-muted text-ink" : "text-ink-muted")}>
              <Icon className="size-4" />
              {t.app.nav[position]}
            </span>
          );
        })}
      </nav>
      <div className="mt-auto flex items-center gap-2 border-t border-border px-4 py-3">
        <span className="grid size-6 flex-none place-items-center rounded-full bg-surface-muted text-[10px] font-semibold text-ink">{t.app.initials}</span>
        {t.app.user}
        <Ellipsis className="ml-auto size-4 text-ink-muted" />
      </div>
    </aside>
  );
}

export function AppWindow({ active, title, className, children }: {
  active: Screen;
  title: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const { t } = useLanguage();
  return (
    <div className={cn("@container flex flex-col overflow-clip rounded-xl border border-border bg-surface text-left text-sm", className)}>
      <div className="flex min-h-0 flex-1">
        <Sidebar active={active} />
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-14 flex-none items-center justify-between gap-4 border-b border-border px-6">
            <span className="flex min-w-0 items-center gap-2 truncate">{title}</span>
          </div>
          <div className="min-h-0 flex-1 overflow-clip p-6 mask-[linear-gradient(to_bottom,black_calc(100%-96px),transparent)] @max-[600px]:p-4">{children}</div>
        </div>
      </div>
    </div>
  );
}

const CONNECTIONS = [
  { name: "Customer platform", where: "db-primary.eu-west.internal:5432/platform", kind: "PostgreSQL", environment: "Production", logo: "/logos/postgresql.svg" },
  { name: "Customer platform v2", where: "localhost:3306/platform_v2", kind: "MySQL", environment: "Test", logo: "/logos/mysql.svg" },
  { name: "Billing replica", where: "sql-replica.eu-west.internal:1433/billing", kind: "SQL Server", environment: "Staging", logo: "/logos/sqlserver.svg" },
  { name: "Contracts export", where: "~/Exports/contracts-2026-q3.csv", kind: "CSV", environment: "Development" },
  { name: "Product analytics", where: "db.kqzrtmvplx.supabase.co:5432/postgres", kind: "Supabase", environment: "Production", logo: "/logos/supabase.svg" },
  { name: "Data warehouse", where: "ep-quiet-sky-a1b2.eu-central-1.aws.neon.tech/warehouse", kind: "Neon", environment: "Staging", logo: "/logos/neon.svg" },
];

export function ConnectionCards({ limit = CONNECTIONS.length, className }: { limit?: number; className?: string }) {
  const { t } = useLanguage();
  return (
    <ul className={cn("grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-3", className)}>
      {CONNECTIONS.slice(0, limit).map((connection, index) => (
        <li key={connection.name} style={{ "--index": index } as CSSProperties}
          className="stagger flex flex-col gap-4 rounded-xl border border-border bg-background p-4 transition-colors duration-150 hover:border-border-strong motion-reduce:transition-none">
          <span className="flex min-w-0 items-center gap-3">
            <span className="grid size-9 flex-none place-items-center">
              {connection.logo
                ? <img src={connection.logo} alt="" width={30} height={30} className="size-7.5 object-contain" />
                : <span className={cn(CSV_MARK, "size-7 text-ink-muted")} />}
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="truncate font-medium">{connection.name}</span>
              <span className="truncate text-ink-muted">{connection.where}</span>
            </span>
          </span>
          <span className="flex items-center gap-2">
            <EnvironmentPill environment={connection.environment} label={t.environments[connection.environment]} />
            <span className="caption text-ink-muted">{connection.kind}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

const DAYS = [0, 1, 0, 2, 1, 0, 0, 3, 1, 2, 0, 1, 2, 0, 0, 1, 3, 2, 1, 0, 2, 4, 1, 0, 2, 3, 1, 2, 5, 3];
const REVIEW_DAYS = new Set([7, 16, 28]);
const FAILED_DAYS = new Set([21]);

function Activity() {
  const { t } = useLanguage();
  const words = t.app.overview;
  return (
    <div className={PANEL}>
      <div className="flex flex-col gap-1 px-4 pt-4">
        <span className="text-ink-muted">{words.rows}</span>
        <span className="heading-2 tabular-nums">{count(1284020)}</span>
        <span className="text-ink-muted">{words.trend}</span>
      </div>
      <div className="p-4">
        <div className="flex h-20 items-end gap-0.75 border-b border-border">
          {DAYS.map((total, index) => (
            <span key={index} style={{ "--index": index, height: total === 0 ? 2 : `${(100 * total) / 5}%` } as CSSProperties}
              className={cn("grow-bar flex-1 rounded-t-sm",
                total === 0 ? "bg-border" : FAILED_DAYS.has(index) ? "bg-status-danger"
                  : REVIEW_DAYS.has(index) ? "bg-status-pending" : "bg-status-verified")} />
          ))}
        </div>
        <div className="caption mt-2 flex justify-between text-ink-muted">
          <span>{words.start}</span>
          <span>{words.today}</span>
        </div>
        <div className="caption mt-3 flex gap-3 text-ink-muted">
          {words.legend.map((label, index) => (
            <span key={label} className={cn("inline-flex items-center gap-1 before:size-2 before:rounded-xs",
              ["before:bg-status-verified", "before:bg-status-pending", "before:bg-status-danger"][index])}>{label}</span>
          ))}
        </div>
      </div>
      <dl className="m-0 grid grid-cols-2 border-t border-border">
        {words.stats.map((term, index) => (
          <div key={term} className="flex flex-col gap-1 border-border px-4 py-3 odd:border-r nth-[n+3]:border-t">
            <dt className="text-ink-muted">{term}</dt>
            <dd className="heading-3 m-0 tabular-nums">{words.values[index]}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function OverviewScreen() {
  const { t } = useLanguage();
  const words = t.app.overview;
  return (
    <div className="flex flex-col gap-6">
      <span className="mx-auto flex h-11 w-full max-w-xl items-center gap-2 rounded-full border border-input bg-field px-4 text-ink-muted">
        <Search className="size-4" />
        {words.search}
      </span>
      <div className="grid grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start gap-6 @max-[900px]:grid-cols-1">
        <section>
          <h3 className="mb-3 px-1 text-base font-medium">{words.activity}</h3>
          <Activity />
        </section>
        <section>
          <h3 className="mb-3 px-1 text-base font-medium">{words.connections}</h3>
          <ConnectionCards />
        </section>
      </div>
    </div>
  );
}

const TABLES = [
  { name: "contacts", rows: 48912, at: { left: "3%", top: "10%" } },
  { name: "accounts", rows: 12480, at: { left: "27%", top: "10%" } },
  { name: "contracts", rows: 9304, at: { left: "53%", top: "10%" } },
  { name: "invoices", rows: 128402, at: { left: "53%", top: "58%" } },
  { name: "invoice_items", rows: 412870, at: { left: "77%", top: "10%" } },
];

const LINKS = [
  { left: 23, top: 27, width: 4 },
  { left: 47, top: 27, width: 6 },
  { left: 50, top: 27, height: 48 },
  { left: 50, top: 75, width: 3 },
  { left: 73, top: 75, width: 2 },
  { left: 75, top: 27, height: 48, up: true },
  { left: 75, top: 27, width: 2 },
];

export function MapScreen() {
  const { t } = useLanguage();
  const words = t.app.map;
  const [selected, setSelected] = useState("accounts");
  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-6 overflow-x-auto border-b border-border [scrollbar-width:none]">
        {[["Customer platform", `${t.environments.Production}, ${words.tables(5)}`], ["Customer platform v2", `${t.environments.Test}, ${words.tables(0)}`]]
          .map(([name, detail], index) => (
            <span key={name} className={cn("-mb-px flex flex-none items-baseline gap-2 border-b-2 pb-2 whitespace-nowrap",
              index === 0 ? "border-ink" : "border-transparent text-ink-muted")}>
              {name} <span className="caption text-ink-muted @max-[600px]:hidden">{detail}</span>
            </span>
          ))}
      </div>
      <div className="map-timeline overflow-x-auto rounded-xl border border-border [scrollbar-width:none]">
        <div className="relative aspect-[10/3] min-w-[560px] bg-surface bg-[radial-gradient(var(--border)_1px,transparent_1px)] bg-size-[16px_16px]">
          {LINKS.map((line, index) => (
            <span key={index} aria-hidden="true"
              style={{ left: `${line.left}%`, top: `${line.top}%`, width: line.width ? `${line.width}%` : 1, height: line.height ? `${line.height}%` : 1, "--index": index } as CSSProperties}
              className={cn("absolute bg-border-strong", line.width ? "draw-x" : line.up ? "draw-up" : "draw-down")} />
          ))}
          {TABLES.map((item, index) => (
            <button key={item.name} type="button" onClick={() => setSelected(item.name)} aria-pressed={item.name === selected}
              style={{ ...item.at, "--index": index } as CSSProperties}
              className={cn("pop-in absolute flex h-[34%] w-[20%] flex-col justify-center rounded-lg border bg-background px-3 text-left",
                "transition-[border-color,box-shadow] duration-200 motion-reduce:transition-none", FOCUS,
                item.name === selected ? "border-action shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_22%,transparent)]" : "border-border hover:border-border-strong")}>
              <span className="truncate font-medium">{item.name}</span>
              <span className="caption truncate text-ink-muted">{words.rows(count(item.rows))}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

type Decision = "accepted" | "rejected";

export function ReportScreen() {
  const { t } = useLanguage();
  const words = t.app.report;
  const [decisions, setDecisions] = useState<Record<number, Decision>>({});
  const open = words.findings.length - Object.keys(decisions).length;
  return (
    <div className="flex flex-col gap-4">
      <div className={PANEL}>
        <div className="flex flex-col gap-2 p-6 @max-[600px]:p-4">
          <Dot tone={open === 0 ? "verified" : "pending"}>{open === 0 ? words.settled : words.status}</Dot>
          <span className="heading-2">{open === 0 ? words.settledTitle : words.title}</span>
          <span className="text-ink-muted">{open === 0 ? words.settledSummary : words.summary}</span>
        </div>
        <dl className="m-0 grid grid-cols-3 border-t border-border @max-[600px]:grid-cols-1">
          {[[words.source, count(128402)], [words.target, count(128402)], [words.open, String(open)]].map(([term, value]) => (
            <div key={term} className="flex flex-col gap-1 border-border px-6 py-4 not-last:border-r @max-[600px]:flex-row @max-[600px]:items-baseline @max-[600px]:justify-between @max-[600px]:px-4 @max-[600px]:py-3 @max-[600px]:not-last:border-r-0 @max-[600px]:not-last:border-b">
              <dt className="caption text-ink-muted">{term}</dt>
              <dd className="heading-2 m-0 tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className={PANEL}>
        <div className="border-b border-border bg-surface px-4 py-3 text-base font-medium">{words.open}</div>
        {words.findings.map((finding, index) => {
          const decision = decisions[index];
          return (
            <div key={finding.title}
              className="grid min-h-16 grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto_auto] items-center gap-4 border-b border-border px-4 py-3 transition-colors last:border-b-0 hover:bg-surface-muted @max-[760px]:grid-cols-[minmax(0,1fr)_auto_auto] @max-[600px]:grid-cols-[minmax(0,1fr)_auto] @max-[600px]:gap-y-2">
              <span className="flex min-w-0 flex-col gap-0.5 @max-[600px]:col-span-2">
                <span className="truncate">{finding.title}</span>
                <span className="truncate text-[13px] leading-4 text-ink-muted">{finding.scope}</span>
              </span>
              <span className="flex items-center gap-2 tabular-nums @max-[760px]:hidden">
                <span className="rounded-md bg-surface-muted px-2 py-0.5">{finding.values[0]}</span>
                <span className="text-ink-muted" aria-hidden="true">→</span>
                <span className={cn("rounded-md px-2 py-0.5",
                  decision === "accepted" ? "bg-surface-muted" : "bg-danger-soft text-danger")}>{finding.values[1]}</span>
              </span>
              <span className="flex gap-2">
                {!decision && (
                  <>
                    <Button type="button" size="sm" variant="outline" onClick={() => setDecisions({ ...decisions, [index]: "accepted" })}>
                      {words.accept}
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => setDecisions({ ...decisions, [index]: "rejected" })}>
                      {words.reject}
                    </Button>
                  </>
                )}
              </span>
              <Badge variant={decision === "accepted" ? "verified" : "danger"} className="justify-self-end">
                {decision ? words[decision] : words.discrepancy}
              </Badge>
            </div>
          );
        })}
      </div>
    </div>
  );
}
