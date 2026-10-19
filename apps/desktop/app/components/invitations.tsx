"use client";

import { Button } from "@relay/ui/components/button";
import { useState } from "react";
import { supabase, useAccount } from "../account";
import { usePreferences } from "../preferences";

export function useInvitations() {
  const { t } = usePreferences();
  const { account, settle } = useAccount();
  const invitations = account.state === "signed-in" ? account.invitations : [];
  async function answer(invitation: string, accept: boolean) {
    const failure = await settle(supabase.rpc(accept ? "accept_invitation" : "decline_invitation", { invitation }));
    return failure && (t.welcome.errors[failure] ?? failure);
  }
  return { invitations, answer };
}

export function InvitationList({ onError }: { onError: (message: string) => void }) {
  const { t } = usePreferences();
  const { invitations, answer } = useInvitations();
  const [busy, setBusy] = useState("");

  async function respond(invitation: string, accept: boolean) {
    setBusy(invitation);
    onError(await answer(invitation, accept));
    setBusy("");
  }

  return (
    <ul className="m-0 flex w-full list-none flex-col rounded-lg border border-border p-0 text-left">
      {invitations.map((invitation) => (
        <li key={invitation.id} className="flex flex-col gap-3 border-b border-border p-3 last:border-b-0">
          <span className="flex min-w-0 flex-col text-sm">
            <span className="truncate font-medium" title={invitation.team}>{invitation.team}</span>
            <span className="text-muted-foreground">{t.settings.roles[invitation.role]}</span>
          </span>
          <div className="flex gap-2">
            <Button size="sm" className="flex-1" disabled={busy !== ""} onClick={() => void respond(invitation.id, true)}>
              {t.welcome.join(t.settings.roles[invitation.role] ?? invitation.role)}
            </Button>
            <Button size="sm" variant="ghost" className="text-muted-foreground" disabled={busy !== ""}
              onClick={() => void respond(invitation.id, false)}>
              {t.welcome.decline}
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
