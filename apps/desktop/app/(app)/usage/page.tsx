"use client";

import { Skeleton } from "@relay/ui/components/skeleton";
import { useEffect, useState } from "react";
import { count, known } from "../../connections";
import { supabase, useTeam } from "../../account";
import { useMigrations } from "../../migrations";
import { usePreferences } from "../../preferences";
import { Frame, ROWS, SECTION } from "../../components/ui";
import { Page } from "../../shell";

const DAY = 86_400_000;

export default function Usage() {
  const { t } = usePreferences();
  const team = useTeam()?.id;
  const [connections, setConnections] = useState<number | null>(() => known()?.length ?? null);
  const [members, setMembers] = useState<number | null>(null);
  const { migrations } = useMigrations(team ?? "");
  const start = new Date().setHours(0, 0, 0, 0) - 29 * DAY;
  const recent = migrations?.filter((m) => Date.parse(m.created_at) >= start) ?? null;

  useEffect(() => {
    count().then(setConnections).catch(() => setConnections(0));
  }, []);

  useEffect(() => {
    if (team) {
      void supabase.from("members").select("user_id", { count: "exact", head: true }).eq("team_id", team)
        .then((result) => setMembers(result.count ?? 0));
    }
  }, [team]);

  const metrics = [
    { label: t.usage.rows, value: recent && recent.reduce((sum, m) => sum + (m.rows ?? 0), 0) },
    { label: t.usage.migrations, value: recent && recent.length },
    { label: t.usage.connections, value: connections },
    { label: t.usage.members, value: members },
  ];

  return (
    <Page title={t.usage.title}>
      <section>
        <h2 className={SECTION}>{t.usage.period}</h2>
        <Frame>
          <ul className={`${ROWS} p-2`}>
            {metrics.map((m) => (
              <li key={m.label} className="flex h-9 items-center gap-3 rounded-lg px-3 text-sm odd:bg-surface-muted">
                <span>{m.label}</span>
                {m.value === null ? <Skeleton className="ml-auto h-4 w-24" /> : (
                  <span className="ml-auto text-muted-foreground tabular-nums">
                    {m.value.toLocaleString(t.locale)} / {t.usage.unlimited}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Frame>
      </section>
    </Page>
  );
}
