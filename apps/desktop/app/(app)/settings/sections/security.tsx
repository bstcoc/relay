"use client";

import { Badge } from "@relay/ui/components/badge";
import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import { Laptop } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { supabase, useAccount } from "../../../account";
import { usePreferences } from "../../../preferences";
import { ConfirmDialog, Field, Panel, Switch } from "../../../components/ui";
import { CopyValue, Group, Setting } from "./common";

function TwoFactor() {
  const { t } = usePreferences();
  const [factor, setFactor] = useState<string | null>(null);
  const [enrolling, setEnrolling] = useState<{ id: string; qr: string; secret: string } | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [disabling, setDisabling] = useState(false);

  const load = useCallback(async () => {
    const factors = await supabase.auth.mfa.listFactors();
    setFactor(factors.data?.totp[0]?.id ?? null);
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function enroll() {
    setError("");
    const result = await supabase.auth.mfa.enroll({ factorType: "totp", friendlyName: "Relay" });
    if (result.error) {
      setError(result.error.message);
      return;
    }
    setEnrolling({ id: result.data.id, qr: result.data.totp.qr_code, secret: result.data.totp.secret });
  }

  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (!enrolling) {
      return;
    }
    const result = await supabase.auth.mfa.challengeAndVerify({ factorId: enrolling.id, code });
    if (result.error) {
      setError(t.login.errors[result.error.code ?? ""] ?? result.error.message);
      return;
    }
    setEnrolling(null);
    setCode("");
    await load();
  }

  async function disable() {
    if (!factor) {
      return;
    }
    setError("");
    const verified = await supabase.auth.mfa.challengeAndVerify({ factorId: factor, code });
    if (verified.error) {
      setError(t.login.errors[verified.error.code ?? ""] ?? verified.error.message);
      return;
    }
    const result = await supabase.auth.mfa.unenroll({ factorId: factor });
    if (result.error) {
      setError(result.error.message);
      return;
    }
    closeDisabling();
    await load();
  }

  function closeDisabling() {
    setDisabling(false);
    setCode("");
    setError("");
  }

  return (
    <>
      <Panel title={t.settings.twoFactor} description={t.settings.twoFactorBody}
        aside={factor ? <Badge variant="secondary" className="h-6">{t.settings.twoFactorOn}</Badge> : undefined}
        hint={!disabling && error && <span className="text-danger">{error}</span>}
        action={factor
          ? <Button size="sm" variant="outline" onClick={() => setDisabling(true)}>{t.settings.disable}</Button>
          : !enrolling && <Button size="sm" onClick={() => void enroll()}>{t.settings.enable}</Button>}>
        {enrolling && (
          <form className="flex items-start gap-6" onSubmit={(event) => void confirm(event)}>
            <img src={enrolling.qr} alt="" width={160} height={160} className="size-40 flex-none rounded-lg border border-border bg-background" />
            <div className="flex min-w-0 flex-col gap-4">
              <p className="text-sm text-muted-foreground">{t.settings.scan}</p>
              <Field label={t.settings.secretKey}>
                <CopyValue value={enrolling.secret} />
              </Field>
              <Field label={t.login.code}>
                <Input required autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}"
                  maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
              </Field>
              <div><Button size="sm" type="submit" disabled={code.length !== 6}>{t.login.verify}</Button></div>
            </div>
          </form>
        )}
      </Panel>
      {disabling && (
        <ConfirmDialog title={t.settings.disableTitle} body={t.settings.disableBody} action={t.settings.disable}
          ready={code.length === 6} error={error} onClose={closeDisabling} onConfirm={disable}>
          <Field label={t.login.code}>
            <Input required autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}"
              maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </Field>
        </ConfirmDialog>
      )}
    </>
  );
}

export function Security() {
  const { t } = usePreferences();
  const { account } = useAccount();
  return (
    <>
      {account.state === "signed-in" && <TwoFactor />}
      <Group>
        <Setting label={t.settings.credentials} help={t.settings.credentialsBody}>
          <Badge variant="secondary" className="h-6">{t.settings.keychain}</Badge>
        </Setting>
        <Setting soon label={t.settings.lock} help={t.settings.lockToggle}>
          <Switch checked disabled hideLabel onChange={() => undefined} label={t.settings.lockToggle} />
        </Setting>
      </Group>
      <Group soon title={t.settings.sessions}>
        <Setting label={<><Laptop size={16} />{t.settings.thisDevice}</>}>
          <span className="text-sm text-muted-foreground">macOS · Relay desktop</span>
        </Setting>
      </Group>
    </>
  );
}
