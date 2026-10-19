"use client";

import { Input } from "@relay/ui/components/input";
import { manages, useTeam } from "../../../account";
import { usePreferences } from "../../../preferences";
import { Switch } from "../../../components/ui";
import { Group, INPUT, Setting } from "./common";

export function Migrations() {
  const { t, language } = usePreferences();
  const admin = manages(useTeam());
  return (
    <Group caption={!admin && t.settings.adminsOnly}>
      <Setting soon label={t.settings.dryRun} help={t.settings.dryRunBody}>
        <Switch checked disabled hideLabel onChange={() => undefined} label={t.settings.dryRunToggle} />
      </Setting>
      <Setting soon label={t.settings.transaction} help={t.settings.transactionBody}>
        <Switch checked disabled hideLabel onChange={() => undefined} label={t.settings.transactionToggle} />
      </Setting>
      <Setting soon label={t.settings.tolerance} help={t.settings.toleranceBody}>
        <Input className={INPUT} disabled inputMode="decimal" aria-label={t.settings.tolerance}
          value={(0.01).toLocaleString(language)} />
      </Setting>
      <Setting soon label={t.settings.batch}>
        <Input className={INPUT} disabled inputMode="numeric" aria-label={t.settings.batch}
          value={(5000).toLocaleString(language)} />
      </Setting>
    </Group>
  );
}
