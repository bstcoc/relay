"use client";

import { cn } from "@relay/ui/lib/utils";
import { ArrowRight, GitCompare } from "lucide-react";
import Link from "next/link";
import { useTeam } from "../../account";
import { useMigrations } from "../../migrations";
import { usePreferences } from "../../preferences";
import { Empty, EnvironmentPill, Frame, MIGRATION, ROUTE, ROW, ROWS, SkeletonRows, StatusDot, TIME } from "../../components/ui";
import { Page } from "../../shell";

export default function Findings() {
  const { t } = usePreferences();
  const { migrations } = useMigrations(useTeam()?.id ?? "");

  const open = (migrations ?? []).filter((m) => (m.findings ?? 0) > 0);

  return (
    <Page title={t.findings.title}>
      {migrations === null ? (
        <SkeletonRows cells={[40, 12, 14, 10, 10]} />
      ) : open.length === 0 ? (
        <Empty icon={<GitCompare size={16} />} title={t.empty.findingsTitle} body={t.empty.findingsBody} />
      ) : (
        <Frame>
          <ul className={ROWS}>
            {open.map((m) => (
              <li key={m.id} className={cn(ROW, MIGRATION)}>
                <Link href={`/migrations/report/#${m.id}`} className={ROUTE}>
                  <span className="min-w-0 truncate" title={m.source_name}>{m.source_name}</span> <ArrowRight size={14} /> <span className="min-w-0 truncate" title={m.target_name}>{m.target_name}</span>
                </Link>
                <StatusDot tone={m.status === "failed" ? "danger" : "pending"}>{t.migrations[m.status]}</StatusDot>
                <span><EnvironmentPill environment={m.target_environment} /></span>
                <span className="text-sm text-muted-foreground tabular-nums">{t.findings.count(m.findings ?? 0)}</span>
                <span className={TIME}>{t.migrations.ago(m.created_at)}</span>
              </li>
            ))}
          </ul>
        </Frame>
      )}
    </Page>
  );
}
