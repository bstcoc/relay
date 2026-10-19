"use client";

import { type FormEvent, useState } from "react";
import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import { Label } from "@relay/ui/components/label";
import { supabase, useAccount, useGuard } from "../account";
import { InvitationList } from "../components/invitations";
import { CenteredCard } from "../components/ui";
import { usePreferences } from "../preferences";

export default function Welcome() {
  const { t } = usePreferences();
  const { account, settle, signOut } = useAccount();
  const [name, setName] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [own, setOwn] = useState(false);

  useGuard("/welcome/");
  const signedIn = account.state === "signed-in" ? account : null;
  const invitations = signedIn?.invitations ?? [];
  const invited = invitations.length > 0;
  const first = signedIn?.name.split(/[\s@]/)[0] ?? "";
  const chosen = name ?? (first ? t.welcome.suggested(first) : "");

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const failure = await settle(supabase.rpc("create_team", { team_name: chosen.trim() }));
    setBusy(false);
    setError(failure);
  }

  const title = !invited ? t.welcome.title
    : invitations.length === 1 ? t.welcome.invitedBy(invitations[0]?.team ?? "") : t.welcome.invitations(invitations.length);

  return (
    <CenteredCard title={title} body={invited ? t.welcome.invitedBody : t.welcome.body}>
      {invited && <InvitationList onError={setError} />}
      {invited && !own ? (
        <Button type="button" variant="link" className="text-muted-foreground" onClick={() => setOwn(true)}>
          {t.welcome.own}
        </Button>
      ) : (
        <form className="flex w-full flex-col gap-4 text-left" onSubmit={(event) => void create(event)}>
          <div className="flex flex-col gap-2">
            <Label htmlFor="welcome-name">{t.welcome.name}</Label>
            <Input id="welcome-name" required autoFocus={!invited} maxLength={64} autoComplete="organization"
              value={chosen} onChange={(e) => setName(e.target.value)} />
          </div>
          <Button type="submit" disabled={busy || !chosen.trim()}>{t.welcome.create}</Button>
        </form>
      )}
      {error && <p className="text-sm text-danger">{error}</p>}
      {!invited && signedIn && (
        <div className="flex flex-col items-center gap-1">
          <p className="text-xs text-muted-foreground">{t.welcome.signedInAs(signedIn.email)}</p>
          <Button type="button" variant="link" className="text-muted-foreground" onClick={() => void signOut()}>
            {t.welcome.switchAccount}
          </Button>
        </div>
      )}
    </CenteredCard>
  );
}
