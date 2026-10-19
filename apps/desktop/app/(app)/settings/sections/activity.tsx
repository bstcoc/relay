"use client";

import { cn } from "@relay/ui/lib/utils";
import { History } from "lucide-react";
import { useEffect, useState } from "react";
import { supabase, useTeam } from "../../../account";
import { usePreferences } from "../../../preferences";
import { Empty, Frame, ROW, ROWS, SkeletonRows, UserAvatar } from "../../../components/ui";
import { teamMembers } from "./members";

type Event = { id: number; name: string; picture: string | null; text: string; at: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function Activity() {
  const { t } = usePreferences();
  const team = useTeam()?.id;
  const [events, setEvents] = useState<Event[] | null>(null);

  useEffect(() => {
    if (!team) {
      return;
    }
    void (async () => {
      const log = await supabase.from("audit_log").select("id, actor, action, detail, at")
        .eq("team_id", team).order("at", { ascending: false }).limit(100);
      const rows = log.data ?? [];
      const found = new Map((await teamMembers(team)).members.map((m) => [m.id, m]));
      const named = (value: unknown) =>
        typeof value === "string" && UUID.test(value) ? found.get(value)?.name ?? t.settings.someone : String(value);
      setEvents(rows.map((row) => ({
        id: row.id,
        name: found.get(row.actor)?.name ?? t.settings.formerMember,
        picture: found.get(row.actor)?.picture ?? null,
        text: t.settings.actions[row.action]?.(Object.fromEntries(Object.entries(row.detail ?? {})
          .map(([key, value]) => [key, named(value)]))) ?? row.action,
        at: row.at as string,
      })));
    })();
  }, [team, t]);

  if (events === null) {
    return <SkeletonRows cells={[60, 15]} />;
  }
  if (events.length === 0) {
    return <Empty icon={<History size={16} />} title={t.settings.noActivity} body={t.settings.noActivityBody} />;
  }
  return (
    <Frame>
      <ul className={ROWS}>
        {events.map((e) => (
          <li key={e.id} className={cn(ROW, "grid-cols-[24px_minmax(0,1fr)_auto] pr-4")}>
            <UserAvatar name={e.name} picture={e.picture} />
            <span className="truncate"><span className="font-medium">{e.name}</span> {e.text}</span>
            <span className="text-muted-foreground">{t.migrations.ago(e.at)}</span>
          </li>
        ))}
      </ul>
    </Frame>
  );
}
