"use client";

import { Button } from "@relay/ui/components/button";
import Link from "next/link";
import { usePreferences } from "../../../preferences";
import { useAnonymizeByDefault } from "../../../components/anonymization";
import { Picker, SkeletonRows } from "../../../components/ui";
import { Group, SELECT, Setting } from "./common";

export function Privacy() {
  const { t } = usePreferences();
  const { team, admin, hint, control } = useAnonymizeByDefault();
  if (!team) {
    return <SkeletonRows cells={[60, 20]} count={2} />;
  }
  return (
    <Group caption={!admin && t.settings.adminsOnly}>
      <Setting label={t.anonymization.defaultTitle}
        help={<>{t.anonymization.defaultBody}<span className="mt-1 block">{hint}</span></>}>
        <Button asChild variant="outline" size="sm">
          <Link href="/anonymization/" className="no-underline">{t.settings.anonymizeLink}</Link>
        </Button>
        {control(true)}
      </Setting>
      <Setting soon label={t.settings.retention} help={t.settings.retentionBody}>
        <Picker className={SELECT} disabled label={t.settings.retention} value="90"
          options={[30, 90, 365].map((n) => ({ value: String(n), label: t.settings.days(n) }))}
          onChange={() => undefined} />
      </Setting>
    </Group>
  );
}
