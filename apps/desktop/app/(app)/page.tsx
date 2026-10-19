"use client";

import { Badge } from "@relay/ui/components/badge";
import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import { Progress } from "@relay/ui/components/progress";
import { cn } from "@relay/ui/lib/utils";
import { ArrowRight, Bell, Check, CircleAlert, Route, Search } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useState } from "react";
import { canEdit, useTeam } from "../account";
import { KINDS, useConnections, where } from "../connections";
import { TONES, useMigrations } from "../migrations";
import { usePreferences } from "../preferences";
import { Activity } from "../components/activity";
import { Empty, EnvironmentPill, Frame, KindLogo, ROWS, SECTION, SkeletonRows } from "../components/ui";
import { Page } from "../shell";

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [["day", 86_400_000], ["hour", 3_600_000], ["minute", 60_000]];

function ago(at: string, locale: string) {
  const elapsed = Date.parse(at) - Date.now();
  const [unit, size] = UNITS.find(([, size]) => Math.abs(elapsed) >= size) ?? ["minute", 60_000];
  return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(Math.round(elapsed / size), unit);
}

function Step({ number, done, title, body, children }: {
  number: number;
  done: boolean;
  title: string;
  body: string;
  children?: ReactNode;
}) {
  const { t } = usePreferences();
  return (
    <li className="flex flex-col items-start gap-1 rounded-xl border border-border bg-background p-4">
      <span className={cn("mb-2 grid size-6 place-items-center rounded-full border text-xs tabular-nums",
        done ? "border-status-verified bg-status-verified text-on-ink" : "border-border text-muted-foreground")}>
        {done ? <Check size={14} aria-label={t.overview.start.done} /> : number}
      </span>
      <span className="text-sm font-medium">{title}</span>
      <span className="text-sm text-muted-foreground">{body}</span>
      {children && <span className="mt-3">{children}</span>}
    </li>
  );
}

function GettingStarted({ team, editor }: { team: string; editor: boolean }) {
  const { t } = usePreferences();
  const done = 1;
  return (
    <section className="flex flex-col gap-3">
      <p className="m-0 text-sm text-muted-foreground">{editor ? t.overview.start.body : t.empty.readOnly}</p>
      <Frame className="flex-row items-center gap-4 px-4 py-3">
        <span className="text-sm font-medium">{t.overview.start.title}</span>
        <Progress value={(100 * done) / 3} aria-label={t.overview.start.title}
          className="h-1 flex-1 bg-muted *:data-[slot=progress-indicator]:bg-status-verified" />
        <span className="text-sm text-muted-foreground tabular-nums">{t.overview.start.progress(done, 3)}</span>
      </Frame>
      <ol className="m-0 grid list-none grid-cols-3 gap-4 p-0 max-[900px]:grid-cols-1">
        <Step number={1} done title={t.overview.start.team} body={t.overview.start.teamDone(team)} />
        <Step number={2} done={false} title={t.overview.start.connect} body={t.overview.start.connectBody}>
          {editor && <Button asChild size="sm"><Link href="/connections/new/" className="no-underline">{t.connections.add}</Link></Button>}
        </Step>
        <Step number={3} done={false} title={t.overview.start.dryRun} body={t.overview.start.dryRunBody}>
          <Button variant="outline" size="sm" disabled>{t.palette.newMigration}</Button>
        </Step>
      </ol>
    </section>
  );
}

export default function Overview() {
  const { t } = usePreferences();
  const { connections, error, reload } = useConnections();
  const [query, setQuery] = useState("");
  const team = useTeam();
  const { migrations } = useMigrations(team?.id ?? "");

  const all = connections ?? [];
  const shown = all.filter((c) =>
    `${c.name} ${where(c)}`.toLowerCase().includes(query.toLowerCase()));

  if (error && connections?.length === 0) {
    return (
      <Page title={t.nav.overview}>
        <Empty icon={<CircleAlert size={16} />} title={t.overview.loadFailed} body={<span className="text-danger">{error}</span>}>
          <Button variant="outline" size="sm" onClick={() => void reload()}>{t.map.retry}</Button>
        </Empty>
      </Page>
    );
  }

  if (connections?.length === 0) {
    return (
      <Page title={t.nav.overview}>
        <GettingStarted team={team?.name ?? ""} editor={canEdit(team)} />
      </Page>
    );
  }

  return (
    <Page title={t.nav.overview}>
      <label className="relative mx-auto w-full max-w-xl">
        <Search size={16} className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-muted-foreground" />
        <Input className="h-11 pl-10" placeholder={t.overview.search} value={query}
          onChange={(e) => setQuery(e.target.value)} />
      </label>
      <div className="mt-6 grid grid-cols-2 items-start gap-6 max-[1100px]:grid-cols-1">
        <div className="flex flex-col gap-8">
          <section>
            <h2 className={SECTION}>{t.overview.activity}</h2>
            {migrations === null || connections === null ? <SkeletonRows cells={[40, 10]} count={4} />
              : <Activity migrations={migrations} connections={all.length} />}
          </section>
          <section>
            <h2 className={SECTION}>{t.overview.alerts}</h2>
            <Empty icon={<Bell size={16} />} title={t.empty.alertsTitle} body={t.empty.alertsBody} />
          </section>
          <section>
            <h2 className={SECTION}>
              {t.overview.recent}
              {!!migrations?.length && (
                <Link href="/migrations/" className="text-sm font-normal text-muted-foreground no-underline hover:text-foreground">
                  {t.overview.all}
                </Link>
              )}
            </h2>
            {migrations === null ? (
              <SkeletonRows cells={[60, 15]} />
            ) : migrations.length === 0 ? (
              <Empty icon={<Route size={16} />} title={t.empty.migrationsTitle} body={t.empty.migrationsBody} />
            ) : (
              <Frame>
                <ul className={ROWS}>
                  {migrations.slice(0, 4).map((m) => (
                    <li key={m.id} className="border-b border-border last:border-b-0">
                      <Link href={`/migrations/report/#${m.id}`} className={cn("grid grid-cols-[minmax(0,1fr)_auto] items-center",
                        "gap-x-3 gap-y-1 px-4 py-3 no-underline transition-colors hover:bg-muted")}>
                        <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
                          <span className="truncate">{m.source_name}</span>
                          <ArrowRight size={14} className="shrink-0 text-muted-foreground" aria-hidden="true" />
                          <span className="truncate">{m.target_name}</span>
                        </span>
                        <Badge variant={TONES[m.status]} className="col-start-2 row-span-2">{t.migrations[m.status]}</Badge>
                        <span className="text-sm text-muted-foreground tabular-nums">
                          {[m.rows === null ? null : t.migrations.rows(m.rows), ago(m.created_at, t.locale)]
                            .filter(Boolean).join(" · ")}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </Frame>
            )}
          </section>
        </div>
        <section>
          <h2 className={SECTION}>{t.overview.connections}</h2>
          {connections === null ? (
            <SkeletonRows cells={[40, 10]} />
          ) : (
            <ul className={cn(ROWS, "grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4")}>
              {shown.map((c) => (
                <li key={c.id}>
                  <Link href="/connections/" className={cn("flex flex-col gap-4 rounded-xl border border-border bg-background p-4",
                    "no-underline transition-colors hover:border-border-strong",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring")}>
                    <span className="flex min-w-0 items-center gap-3">
                      <KindLogo kind={c.kind} size={36} />
                      <span className="flex min-w-0 flex-col text-sm">
                        <span className="truncate font-medium">{c.name}</span>
                        <span className="truncate text-muted-foreground">{where(c)}</span>
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      <EnvironmentPill environment={c.environment} />
                      <span className="text-xs font-medium text-muted-foreground">
                        {KINDS.find((k) => k.kind === c.kind)?.label}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Page>
  );
}
