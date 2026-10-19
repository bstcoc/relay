"use client";

import { Badge } from "@relay/ui/components/badge";
import { Button } from "@relay/ui/components/button";
import { cn } from "@relay/ui/lib/utils";
import { ArrowRight, FingerprintPattern, Route } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { canEdit, useTeam } from "../../account";
import { ENVIRONMENTS, useConnections } from "../../connections";
import { TONES, useMigrations } from "../../migrations";
import { usePreferences } from "../../preferences";
import { FilterBar } from "../../components/filter-bar";
import { Empty, EnvironmentPill, Frame, MIGRATION, ROUTE, ROW, ROWS, SkeletonRows, TIME } from "../../components/ui";
import { Page } from "../../shell";

export default function Migrations() {
  const { t } = usePreferences();
  const team = useTeam();
  const { migrations, error } = useMigrations(team?.id ?? "");
  const { connections } = useConnections();
  const ready = connections === null || connections.length >= 2;
  const [filters, setFilters] = useState<Record<string, string>>({});
  const status = filters.status ?? "";
  const environment = filters.environment ?? "";

  const shown = (migrations ?? []).filter((m) =>
    (!status || m.status === status) && (!environment || m.target_environment === environment));

  return (
    <Page title={t.migrations.title}
      actions={canEdit(team) && <Button asChild>
        <Link href={ready ? "/migrations/new/" : "/connections/new/"} className="no-underline">
          {ready ? t.migrations.new : t.connections.add}
        </Link>
      </Button>}>
      {error && <p className="text-sm text-danger"><span className="font-medium">{t.migrations.failedToLoad}</span> {error}</p>}
      {migrations === null ? (
        <SkeletonRows cells={[40, 12, 14, 10, 10]} />
      ) : migrations.length === 0 ? (
        <Empty icon={<Route size={16} />} title={t.empty.migrationsTitle} body={t.empty.migrationsBody} />
      ) : (
        <>
          <FilterBar values={filters} onChange={(key, value) => setFilters({ ...filters, [key]: value })}
            fields={[
              { key: "status", label: t.migrations.status, all: t.connections.all,
                options: (["verified", "review", "failed", "running"] as const)
                  .map((s) => ({ value: s, label: t.migrations[s] })),
                suggestion: "review" },
              { key: "environment", label: t.connections.environment, all: t.connections.all,
                options: ENVIRONMENTS.map((name) => ({ value: name, label: t.environments[name] ?? name })),
                suggestion: "Production" },
            ]} />
          <Frame>
            <ul className={ROWS}>
              {shown.map((m) => (
                <li key={m.id} className={cn(ROW, MIGRATION)}>
                  <Link href={`/migrations/report/#${m.id}`} className={ROUTE}>
                    <span className="min-w-0 truncate" title={m.source_name}>{m.source_name}</span> <ArrowRight size={14} /> <span className="min-w-0 truncate" title={m.target_name}>{m.target_name}</span>
                    {m.anonymized && <FingerprintPattern size={14} aria-label={t.migrations.anonymized} />}
                  </Link>
                  <span><Badge variant={TONES[m.status]}>{t.migrations[m.status]}</Badge></span>
                  <span><EnvironmentPill environment={m.target_environment} /></span>
                  <span className="text-sm text-muted-foreground tabular-nums">{m.rows === null ? "" : t.migrations.rows(m.rows)}</span>
                  <span className={TIME}>{t.migrations.ago(m.created_at)}</span>
                </li>
              ))}
            </ul>
          </Frame>
        </>
      )}
    </Page>
  );
}
