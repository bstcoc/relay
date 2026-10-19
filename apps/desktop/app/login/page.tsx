"use client";

import { type FormEvent, useState } from "react";
import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import { Label } from "@relay/ui/components/label";
import { GoogleLogo, MicrosoftLogo } from "@relay/ui/components/provider-logos";
import { logInWith, type Provider, supabase, useAccount, useGuard } from "../account";
import { errorMessage } from "../engine";
import { usePreferences } from "../preferences";
import { CenteredCard } from "../components/ui";

const FORM = "flex w-full flex-col gap-4 text-left";
const FIELD = "flex flex-col gap-2";

function SecondFactor() {
  const { t } = usePreferences();
  const { refresh, signOut } = useAccount();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function verify(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const factors = await supabase.auth.mfa.listFactors();
    const factor = factors.data?.totp[0];
    const result = factor
      ? await supabase.auth.mfa.challengeAndVerify({ factorId: factor.id, code })
      : { error: factors.error };
    setBusy(false);
    if (result.error) {
      setError(t.login.errors[result.error?.code ?? ""] ?? result.error?.message ?? "");
      return;
    }
    await refresh();
  }

  return (
    <form className={FORM} onSubmit={(event) => void verify(event)}>
      <p className="text-sm text-muted-foreground">{t.login.codeBody}</p>
      <div className={FIELD}>
        <Label htmlFor="login-code">{t.login.code}</Label>
        <Input id="login-code" required autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}"
          maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      <Button type="submit" disabled={busy || code.length !== 6}>{t.login.verify}</Button>
      <Button type="button" variant="link" className="text-muted-foreground" onClick={() => void signOut()}>
        {t.login.back}
      </Button>
    </form>
  );
}

function Providers() {
  const { t } = usePreferences();
  const { refresh } = useAccount();
  const [waiting, setWaiting] = useState<Provider | null>(null);
  const [error, setError] = useState("");

  async function go(provider: Provider) {
    setWaiting(provider);
    setError("");
    try {
      await logInWith(provider, `<!doctype html><meta charset="utf-8"><title>Relay</title><p>${t.login.backToApp}</p>`);
      await refresh();
    } catch (failure) {
      setError(errorMessage(failure));
    }
    setWaiting(null);
  }

  return (
    <div className="flex w-full flex-col gap-3">
      <Button type="button" variant="outline" disabled={waiting !== null} onClick={() => void go("azure")}>
        <MicrosoftLogo />
        {waiting === "azure" ? t.login.inBrowser : t.login.microsoft}
      </Button>
      <Button type="button" variant="outline" disabled={waiting !== null} onClick={() => void go("google")}>
        <GoogleLogo />
        {waiting === "google" ? t.login.inBrowser : t.login.google}
      </Button>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}

export default function Login() {
  const { t } = usePreferences();
  const { account } = useAccount();

  useGuard("/login/");

  return (
    <CenteredCard title={t.login.title}>
      {account.state === "verify" ? <SecondFactor /> : (
        <>
          <Providers />
        </>
      )}
    </CenteredCard>
  );
}
