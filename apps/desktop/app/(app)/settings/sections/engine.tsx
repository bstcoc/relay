"use client";

import { usePreferences } from "../../../preferences";
import { EngineStatus } from "../../../components/ui";
import { useEngine } from "../../../hooks";
import { CopyValue, Group, Setting } from "./common";

export function Engine() {
  const { t } = usePreferences();
  const engine = useEngine();
  return (
    <>
      <Group title={t.settings.engineTitle} description={t.settings.engineBody}>
        <Setting label={t.settings.state}><EngineStatus engine={engine} /></Setting>
        <Setting label={t.settings.version}>
          <span className="text-sm tabular-nums">{engine.state === "ready" ? engine.detail : "—"}</span>
        </Setting>
        <Setting label={t.settings.workdir} help={t.settings.workdirBody}>
          <CopyValue value="~/Library/Application Support/app.relay.desktop" />
        </Setting>
      </Group>
      <section className="flex flex-col gap-1 px-1 text-xs text-muted-foreground">
        <h2 className="font-medium">{t.settings.legal}</h2>
        <p>{t.settings.trademarksBody}</p>
      </section>
    </>
  );
}
