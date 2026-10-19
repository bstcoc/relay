"use client";

import { cn } from "@relay/ui/lib/utils";
import { useState } from "react";
import { type MigrationSummary as Migration, TONES } from "../migrations";
import { usePreferences } from "../preferences";
import { Frame } from "./ui";

const DAY = 86_400_000;
const TONE_ORDER = ["verified", "pending", "danger"] as const;
type Tone = (typeof TONE_ORDER)[number];

const KEY = "inline-flex items-center gap-1 before:size-2 before:rounded-[2px] before:content-['']";

const KEYS: Record<Tone, string> = {
  verified: "before:bg-status-verified", pending: "before:bg-status-pending", danger: "before:bg-status-danger",
};

const BARS: Record<Tone, string> = { verified: "bg-status-verified", pending: "bg-status-pending", danger: "bg-status-danger" };

type Day = { date: Date; rows: number; counts: Record<Tone, number>; total: number };

function days(migrations: Migration[], from: number): Day[] {
  return Array.from({ length: 30 }, (_, index) => {
    const date = new Date(from + index * DAY);
    const same = migrations.filter((m) => new Date(m.created_at).toDateString() === date.toDateString());
    const counts = { verified: 0, pending: 0, danger: 0 };
    for (const m of same) {
      counts[TONES[m.status]] += 1;
    }
    return { date, rows: same.reduce((sum, m) => sum + (m.rows ?? 0), 0), counts, total: same.length };
  });
}

export function Activity({ migrations, connections }: { migrations: Migration[]; connections: number }) {
  const { t } = usePreferences();
  const [hovered, setHovered] = useState<number | null>(null);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = today.getTime() - 29 * DAY;
  const current = migrations.filter((m) => Date.parse(m.created_at) >= start);
  const previous = migrations.filter((m) => {
    const at = Date.parse(m.created_at);
    return at >= start - 30 * DAY && at < start;
  });
  const rows = current.reduce((sum, m) => sum + (m.rows ?? 0), 0);
  const before = previous.reduce((sum, m) => sum + (m.rows ?? 0), 0);
  const trend = before === 0 ? null : t.overview.versus(Math.round(((rows - before) / before) * 100));
  const series = days(current, start);
  const peak = Math.max(1, ...series.map((day) => day.total));
  const verified = current.filter((m) => m.status === "verified").length;
  const open = current.reduce((sum, m) => sum + (m.findings ?? 0), 0);
  const format = (n: number) => n.toLocaleString(t.locale);
  const shown = hovered === null ? null : series[hovered];
  const tones: Record<Tone, string> = {
    verified: t.migrations.verified, pending: t.overview.pending, danger: t.migrations.failed,
  };

  return (
    <Frame>
      <div>
        <div className="flex flex-col gap-1 px-4 pt-4">
          <span className="text-sm text-muted-foreground">{t.overview.rowsLast30}</span>
          <span className="heading-2 tabular-nums">{format(rows)}</span>
          {trend && <span className="text-sm text-muted-foreground">{trend}</span>}
        </div>
        <div className="relative p-4">
          {shown && (
            <div role="status" className={cn("pointer-events-none absolute bottom-[calc(100%-8px)] z-5 flex min-w-30 -translate-x-1/2",
              "flex-col gap-0.5 rounded-lg bg-popover px-3 py-2 text-sm whitespace-nowrap text-foreground border border-border")}
              style={{ left: `calc(var(--space-4) + (100% - 2 * var(--space-4)) * ${((hovered ?? 0) + 0.5) / 30})` }}>
              <span className="font-medium">{shown.date.toLocaleDateString(t.locale, { day: "numeric", month: "short" })}</span>
              {shown.total === 0 ? <span className="text-muted-foreground">{t.overview.idle}</span> : (
                <>
                  {TONE_ORDER.filter((tone) => shown.counts[tone] > 0).map((tone) => (
                    <span key={tone} className={cn(KEY, KEYS[tone])}>
                      {tones[tone]} <span className="tabular-nums">{shown.counts[tone]}</span>
                    </span>
                  ))}
                  <span className="text-muted-foreground tabular-nums">{t.migrations.rows(shown.rows)}</span>
                </>
              )}
            </div>
          )}
          <div className="flex h-20 items-stretch gap-0.75 border-b border-border" role="img"
            aria-label={t.overview.chartLabel(current.length, rows)} onMouseLeave={() => setHovered(null)}>
            {series.map((day, index) => (
              <span key={day.date.toISOString()} onMouseEnter={() => setHovered(index)}
                className="flex flex-1 cursor-default flex-col-reverse gap-0.5 rounded-t-sm hover:bg-muted">
                {day.total === 0 ? <span className="h-0.5 bg-border" /> : TONE_ORDER.filter((tone) => day.counts[tone] > 0)
                  .map((tone) => (
                    <span key={tone} className={cn("min-h-1 rounded-t-sm [&+&]:rounded-none", BARS[tone])}
                      style={{ height: `${(100 * day.counts[tone]) / peak}%` }} />
                  ))}
              </span>
            ))}
          </div>
          <div className="caption mt-2 flex justify-between text-muted-foreground">
            <span>{new Date(start).toLocaleDateString(t.locale, { day: "numeric", month: "short" })}</span>
            <span>{t.overview.today}</span>
          </div>
          {current.length > 0 && (
            <div className="caption mt-3 flex flex-wrap gap-3 text-muted-foreground">
              {TONE_ORDER.map((tone) => (
                <span key={tone} className={cn(KEY, KEYS[tone])}>{tones[tone]}</span>
              ))}
            </div>
          )}
        </div>
      </div>
      <dl className="m-0 grid grid-cols-2 border-t border-border">
        {[
          [t.overview.migrations, format(current.length)],
          [t.overview.verifiedRate,
            current.length === 0 ? "–" : (verified / current.length).toLocaleString(t.locale, { style: "percent" })],
          [t.overview.findings, format(open)],
          [t.overview.connections, format(connections)],
        ].map(([term, value]) => (
          <div key={term} className="flex flex-col gap-1 px-4 py-3 border-border odd:border-r nth-[n+3]:border-t">
            <dt className="text-sm text-muted-foreground">{term}</dt>
            <dd className="heading-3 m-0 tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </Frame>
  );
}
