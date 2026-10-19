"use client";

import { type ReactNode, useState } from "react";
import { manages, supabase, useAccount, useTeam } from "../account";
import { usePreferences } from "../preferences";
import { ConfirmDialog, Panel, SkeletonRows, Switch } from "./ui";

export function useAnonymizeByDefault() {
  const { t } = usePreferences();
  const { refresh } = useAccount();
  const team = useTeam();
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const enabled = team?.anonymize ?? true;

  async function save(next: boolean) {
    if (!team) {
      return;
    }
    setError("");
    const { error: refused } = await supabase.from("teams").update({ anonymize_by_default: next }).eq("id", team.id);
    if (refused) {
      setError(refused.message);
      return;
    }
    await refresh();
  }

  const hint = error ? <span className="text-danger">{error}</span> : enabled ? t.anonymization.defaultOn : t.anonymization.defaultOff;
  const control = (hideLabel: boolean) => (
    <>
      <Switch checked={enabled} disabled={!manages(team)} hideLabel={hideLabel} label={t.anonymization.defaultTitle}
        onChange={(next) => (next ? void save(true) : setAsking(true))} />
      {asking && (
        <ConfirmDialog title={t.anonymization.offTitle} body={t.anonymization.offBody} action={t.anonymization.offConfirm}
          onClose={() => setAsking(false)}
          onConfirm={async () => {
            await save(false);
            setAsking(false);
          }} />
      )}
    </>
  );
  return { team, enabled, admin: manages(team), hint, control };
}

export function AnonymizeByDefault({ action }: { action?: ReactNode }) {
  const { t } = usePreferences();
  const { team, enabled, hint, control } = useAnonymizeByDefault();
  if (!team) {
    return <SkeletonRows cells={[60, 20]} count={2} />;
  }
  return (
    <Panel title={t.anonymization.defaultTitle} description={t.anonymization.defaultBody}
      hint={hint} danger={!enabled} action={action}>
      {control(false)}
    </Panel>
  );
}
