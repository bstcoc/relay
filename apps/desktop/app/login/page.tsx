"use client";

import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import { Label } from "@relay/ui/components/label";
import { GoogleLogo, MicrosoftLogo } from "@relay/ui/components/provider-logos";
import { Separator } from "@relay/ui/components/separator";
import { finishLogin, logInWith, type Provider, supabase, useAccount, useGuard } from "../account";
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

function Credentials() {
  const { t } = usePreferences();
  const { refresh } = useAccount();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const result = creating
      ? await supabase.auth.signUp({ email, password, options: { data: { full_name: name.trim() } } })
      : await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (result.error) {
      setError(t.login.errors[result.error?.code ?? ""] ?? result.error?.message ?? "");
    } else if (!result.data.session) {
      setSent(true);
      setCreating(false);
    } else {
      await refresh();
    }
  }

  return (
    <form className={FORM} onSubmit={(event) => void submit(event)}>
      {creating && (
        <div className={FIELD}>
          <Label htmlFor="login-name">{t.login.name}</Label>
          <Input id="login-name" required autoComplete="name" maxLength={64} value={name}
            onChange={(e) => setName(e.target.value)} />
        </div>
      )}
      <div className={FIELD}>
        <Label htmlFor="login-email">{t.login.email}</Label>
        <Input id="login-email" required autoFocus type="email" autoComplete="email" value={email}
          onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div className={FIELD}>
        <Label htmlFor="login-password">{t.login.password}</Label>
        <Input id="login-password" required type="password" minLength={10}
          autoComplete={creating ? "new-password" : "current-password"}
          value={password} onChange={(e) => setPassword(e.target.value)} />
        {creating && <p className="text-xs text-muted-foreground">{t.login.passwordHint}</p>}
      </div>
      {sent && <p className="text-sm text-muted-foreground">{t.login.checkEmail}</p>}
      {error && <p className="text-sm text-danger">{error}</p>}
      <Button type="submit" disabled={busy}>{creating ? t.login.signUp : t.login.signIn}</Button>
      <Button type="button" variant="link" className="text-muted-foreground" onClick={() => setCreating(!creating)}>
        {creating ? t.login.toSignIn : t.login.toSignUp}
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
  const { account, refresh } = useAccount();
  const [answerError, setAnswerError] = useState("");

  useEffect(() => {
    const answer = new URLSearchParams(location.search);
    if (answer.has("code") || answer.has("error")) {
      history.replaceState(null, "", location.pathname);
      void finishLogin(answer).then(refresh, (failure: Error) => setAnswerError(failure.message));
    }
  }, [refresh]);

  useGuard("/login/");

  return (
    <CenteredCard title={t.login.title}>
      {account.state === "verify" ? <SecondFactor /> : (
        <>
          <Credentials />
          <Separator />
          <Providers />
          {answerError && <p className="text-sm text-danger">{answerError}</p>}
        </>
      )}
    </CenteredCard>
  );
}
