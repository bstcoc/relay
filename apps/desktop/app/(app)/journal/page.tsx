"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@relay/ui/components/table";
import { Logs } from "lucide-react";
import { useEffect, useState } from "react";
import { supabase, useTeam } from "../../account";
import { usePreferences } from "../../preferences";
import { Empty, Frame, SkeletonRows, StatusDot } from "../../components/ui";
import { Page } from "../../shell";

type Line = { id: number; action: string; detail: Record<string, string>; at: string };

const LEVELS: Record<string, ["info" | "warning" | "error", "neutral" | "pending" | "danger"]> = {
  "migration.review": ["warning", "pending"],
  "migration.failed": ["error", "danger"],
};

export default function Journal() {
  const { t } = usePreferences();
  const team = useTeam()?.id;
  const [lines, setLines] = useState<Line[] | null>(null);

  useEffect(() => {
    if (!team) {
      return;
    }
    supabase.from("audit_log").select("id, action, detail, at").eq("team_id", team)
      .like("action", "migration.%").order("at", { ascending: false }).limit(200)
      .then(({ data }) => setLines((data ?? []) as Line[]));
  }, [team]);

  const time = (at: string) => new Date(at).toLocaleString(t.locale, {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });

  return (
    <Page title={t.journal.title}>
      {lines === null ? (
        <SkeletonRows cells={[60, 40, 70, 90]} />
      ) : lines.length === 0 ? (
        <Empty icon={<Logs size={16} />} title={t.empty.journalTitle} body={t.empty.journalBody} />
      ) : (
        <Frame>
          <Table className="table-fixed">
            <TableHeader className="bg-surface">
              <TableRow className="hover:bg-transparent">
                <TableHead className="caption h-9 w-36 pl-3 text-muted-foreground">{t.journal.time}</TableHead>
                <TableHead className="caption h-9 w-44 text-muted-foreground">{t.journal.level}</TableHead>
                <TableHead className="caption h-9 w-[30%] text-muted-foreground">{t.journal.migration}</TableHead>
                <TableHead className="caption h-9 pr-4 text-muted-foreground">{t.journal.message}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((line) => {
                const [level, tone] = LEVELS[line.action] ?? ["info", "neutral"];
                return (
                  <TableRow key={line.id} className="hover:bg-muted">
                    <TableCell className="h-10 pl-3 text-muted-foreground tabular-nums">{time(line.at)}</TableCell>
                    <TableCell><StatusDot tone={tone}>{t.journal.levels[level]}</StatusDot></TableCell>
                    <TableCell className="truncate font-medium">{[line.detail.source, line.detail.target].filter(Boolean).join(" → ") || "—"}</TableCell>
                    <TableCell className="truncate pr-4">
                      {t.journal.messages[line.action]?.(line.detail) ?? line.action}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Frame>
      )}
    </Page>
  );
}
