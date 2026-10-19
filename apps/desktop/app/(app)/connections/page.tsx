"use client";

import { Button } from "@relay/ui/components/button";
import { ButtonGroup } from "@relay/ui/components/button-group";
import { cn } from "@relay/ui/lib/utils";
import { CloudDownload, Database, Plus, SearchX } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { canEdit, useTeam } from "../../account";
import { type Connection, ENVIRONMENTS, KINDS, remove, test, useConnections, where } from "../../connections";
import { errorMessage } from "../../engine";
import { usePreferences } from "../../preferences";
import { FilterBar } from "../../components/filter-bar";
import { Menu } from "../../components/menu";
import { Empty, EnvironmentPill, Frame, KindLogo, ROW, ROWS, SkeletonRows, StatusDot } from "../../components/ui";
import { Page } from "../../shell";

type Result =
  | { ok: true; at: string; tables?: number; columns?: number; rows?: number }
  | { ok: false; at: string; message: string };

type Check = { state: "testing" } | { state: "done"; result: Result };

const STORED = "relay.checks";

function stored(): Record<string, Check> {
  try {
    const results = JSON.parse(localStorage.getItem(STORED) ?? "{}") as Record<string, Result>;
    return Object.fromEntries(Object.entries(results).map(([id, result]) => [id, { state: "done", result }]));
  } catch {
    return {};
  }
}

function store(checks: Record<string, Check>) {
  const results = Object.fromEntries(Object.entries(checks).flatMap(([id, check]) =>
    check.state === "done" ? [[id, check.result]] : []));
  localStorage.setItem(STORED, JSON.stringify(results));
}

const VISIBLE_FOR = 400;

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export default function Connections() {
  const { t } = usePreferences();
  const { connections: loaded, error, reload } = useConnections();
  const connections = loaded ?? [];
  const router = useRouter();
  const [checks, setChecks] = useState<Record<string, Check>>({});
  const editor = canEdit(useTeam());

  function update(id: string, check: Check | null) {
    setChecks((all) => {
      const { [id]: _, ...rest } = all;
      const next = check ? { ...rest, [id]: check } : rest;
      store(next);
      return next;
    });
  }
  const [filters, setFilters] = useState<Record<string, string>>({});
  const kind = filters.kind ?? "";
  const environment = filters.environment ?? "";

  const [saved, setSaved] = useState("");

  useEffect(() => {
    setChecks(stored());
    setSaved(window.location.hash.slice(1));
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  const savedConnection = saved ? loaded?.find((c) => c.id === saved) : undefined;
  useEffect(() => {
    if (savedConnection) {
      setSaved("");
      void check(savedConnection);
    }
  }, [savedConnection]);

  async function check(connection: Connection) {
    const id = connection.id;
    update(id, { state: "testing" });
    const started = Date.now();
    const settled = () => pause(Math.max(0, VISIBLE_FOR - (Date.now() - started)));
    try {
      const reached = await test(connection);
      await settled();
      update(id, { state: "done", result: {
        ok: true, at: new Date().toISOString(),
        tables: reached.tables?.length, columns: reached.columns?.length, rows: reached.rows,
      } });
    } catch (failure) {
      await settled();
      update(id, { state: "done", result: { ok: false, at: new Date().toISOString(), message: errorMessage(failure) } });
    }
  }

  function when(at: string) {
    const date = new Date(at);
    return date.toDateString() === new Date().toDateString()
      ? date.toLocaleTimeString(t.locale, { hour: "2-digit", minute: "2-digit" })
      : date.toLocaleDateString(t.locale, { day: "numeric", month: "short" });
  }

  const shown = connections.filter((c) =>
    (!kind || c.kind === kind) && (!environment || c.environment === environment));

  return (
    <Page
      title={t.connections.title}
      actions={editor && (
        <ButtonGroup>
          <Button asChild><Link href="/connections/new/" className="no-underline"><Plus />{t.connections.add}</Link></Button>
          <Button asChild size="icon">
            <Link href="/connections/import/" aria-label={t.cloud.open} title={t.cloud.open}><CloudDownload /></Link>
          </Button>
        </ButtonGroup>
      )}
    >
      {error && <p className="text-sm text-danger">{error}</p>}
      {connections.length > 0 && (
        <FilterBar values={filters} onChange={(key, value) => setFilters({ ...filters, [key]: value })}
          fields={[
            { key: "kind", label: t.connections.kind, all: t.connections.all,
              options: KINDS.map((k) => ({ value: k.kind, label: k.label })) },
            { key: "environment", label: t.connections.environment, all: t.connections.all,
              options: ENVIRONMENTS.map((name) => ({ value: name, label: t.environments[name] ?? name })), suggestion: "Production" },
          ]} />
      )}
      {loaded === null ? (
        <SkeletonRows cells={[60, 70, 50, 60, 80, 0, 0]} />
      ) : connections.length === 0 ? (
        <Empty icon={<Database size={16} />} title={t.connections.emptyTitle} body={t.connections.emptyBody}>
          {editor && (
            <Button asChild variant="outline" size="sm">
              <Link href="/connections/new/" className="no-underline">{t.connections.add}</Link>
            </Button>
          )}
        </Empty>
      ) : shown.length === 0 ? (
        <Empty icon={<SearchX size={16} />} title={t.connections.noMatchTitle} body={t.connections.noMatch}>
          <Button type="button" variant="outline" size="sm" onClick={() => setFilters({})}>{t.connections.clearFilters}</Button>
        </Empty>
      ) : (
        <Frame>
          <ul className={ROWS}>
            {shown.map((connection) => {
              const status = checks[connection.id];
              const result = status?.state === "done" ? status.result : undefined;
              return (
                <li key={connection.id} className={cn(ROW,
                  "grid-cols-[minmax(0,1.4fr)_minmax(0,1.6fr)_140px_130px_minmax(0,1.2fr)_48px_32px]")}>
                  <span className="truncate text-sm font-medium">{connection.name}</span>
                  <span className="flex min-w-0" title={result && !result.ok ? result.message : ""}>
                    {!status && <StatusDot tone="neutral">{t.connections.untested}</StatusDot>}
                    {status?.state === "testing" && (
                      <StatusDot tone="pending">{t.connections.testing}</StatusDot>
                    )}
                    {result?.ok && (
                      <StatusDot tone="verified">
                        {result.tables !== undefined ? t.connections.connected : t.connections.readable}
                        {" "}
                        <span className="font-normal text-muted-foreground">
                          {result.tables !== undefined ? t.connections.tables(result.tables)
                            : t.connections.columnsRows(result.columns ?? 0, result.rows ?? 0)}
                        </span>
                      </StatusDot>
                    )}
                    {result && !result.ok && <StatusDot tone="danger">{result.message}</StatusDot>}
                  </span>
                  <span><EnvironmentPill environment={connection.environment} /></span>
                  <span className="flex items-center gap-2 text-sm text-muted-foreground">
                    <KindLogo kind={connection.kind} />
                    {KINDS.find((k) => k.kind === connection.kind)?.label}
                  </span>
                  <span className="truncate text-sm text-muted-foreground">{where(connection)}</span>
                  <span className="flex items-center justify-end text-sm whitespace-nowrap text-muted-foreground tabular-nums">
                    {result ? when(result.at) : ""}
                  </span>
                  <Menu label={t.connections.actions(connection.name)} items={[
                    { label: t.connections.test, onSelect: () => void check(connection),
                      disabled: status?.state === "testing" },
                    ...editor ? [
                      { label: t.connections.edit, onSelect: () => router.push(`/connections/new/#${connection.id}`) },
                      { label: t.connections.remove, danger: true,
                        onSelect: () => void remove(connection.id).then(() => {
                          update(connection.id, null);
                          return reload();
                        }) },
                    ] : [],
                  ]} />
                </li>
              );
            })}
          </ul>
        </Frame>
      )}
    </Page>
  );
}
