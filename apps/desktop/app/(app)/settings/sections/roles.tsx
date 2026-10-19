"use client";

import { cn } from "@relay/ui/lib/utils";
import { manages, useTeam } from "../../../account";
import { ENVIRONMENTS } from "../../../connections";
import { usePreferences } from "../../../preferences";
import { EnvironmentPill, Picker } from "../../../components/ui";
import { FOOTER, Group, SELECT, Setting } from "./common";

const APPROVERS: Record<string, string> = {
  Production: "approver", "Pre-production": "member", Test: "none", Development: "none",
};

export function Roles() {
  const { t } = usePreferences();
  const admin = manages(useTeam());
  return (
    <>
      <Group soon title={t.settings.approval} description={t.settings.approvalBody}
        caption={!admin && t.settings.adminsOnly} footer={<p className={cn(FOOTER, "justify-start")}>{t.settings.approvalHint}</p>}>
        {ENVIRONMENTS.map((environment) => (
          <Setting key={environment} label={<EnvironmentPill environment={environment} />}>
            <Picker size="sm" className={SELECT} disabled label={t.environments[environment] ?? environment}
              value={APPROVERS[environment] ?? "none"}
              options={Object.entries(t.settings.approvers).map(([value, label]) => ({ value, label }))}
              onChange={() => undefined} />
          </Setting>
        ))}
      </Group>
      <Group title={t.settings.rolesTitle}>
        {Object.entries(t.settings.roles).filter(([role]) => role !== "approver").map(([role, label]) => (
          <Setting key={role} label={label} help={t.settings.roleBodies[role]} />
        ))}
      </Group>
    </>
  );
}
