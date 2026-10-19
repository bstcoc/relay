"use client";

import { Checkbox } from "@relay/ui/components/checkbox";
import { cn } from "@relay/ui/lib/utils";
import { Frame } from "../../../components/ui";
import { usePreferences } from "../../../preferences";
import { Soon } from "./common";

const NOTIFY = cn("box-border grid min-h-12 grid-cols-[minmax(0,1fr)_96px_96px] items-center justify-items-center gap-4",
  "border-b border-border px-6 py-3 last:border-b-0 [&>:first-child]:justify-self-start");

export function Notifications() {
  const { t } = usePreferences();
  return (
    <Frame>
      <div className={cn(NOTIFY, "py-2 text-sm text-muted-foreground")}>
        <Soon />
        <span>{t.settings.desktop}</span>
        <span>{t.settings.emailChannel}</span>
      </div>
      {Object.keys(t.settings.events).map((event) => (
        <div key={event} className={NOTIFY}>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-sm font-medium">{t.settings.events[event]}</span>
            <span className="text-sm text-muted-foreground">{t.settings.eventBodies[event]}</span>
          </span>
          {(["desktop", "email"] as const).map((channel) => (
            <Checkbox key={channel} disabled className="border-border-strong bg-background"
              aria-label={`${t.settings.events[event]} ${channel === "desktop" ? t.settings.desktop : t.settings.emailChannel}`}
              checked={channel === "desktop" || event !== "finished"} />
          ))}
        </div>
      ))}
    </Frame>
  );
}
