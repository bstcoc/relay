"use client";

import { pickFile } from "../../../desktop";
import { FolderOpen } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import {
  blank,
  type Connection,
  ENVIRONMENTS,
  fromUrl,
  KINDS,
  type Kind,
  list,
  save,
  SSL_MODES,
  type SslMode,
} from "../../../connections";
import { errorMessage } from "../../../engine";
import { usePreferences } from "../../../preferences";
import { Field, KindLogo, Panel, Picker, Switch } from "../../../components/ui";
import { EditorsOnly, Page } from "../../../shell";

function PathInput({ value, onChange, extensions, required, placeholder }: {
  value: string;
  onChange: (path: string) => void;
  extensions?: string[];
  required?: boolean;
  placeholder?: string;
}) {
  const { t } = usePreferences();
  async function browse() {
    const chosen = await pickFile(extensions ? [{ name: extensions.join(", "), extensions }] : []);
    if (chosen) {
      onChange(chosen);
    }
  }
  return (
    <span className="flex gap-2">
      <Input required={required} value={value} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)} />
      <Button type="button" variant="outline" onClick={() => void browse()}>
        <FolderOpen /> {t.form.browse}
      </Button>
    </span>
  );
}

const FIELDS = "grid grid-cols-2 gap-4";

const WIDE = "col-span-full";

const FILE_TYPES: Partial<Record<Kind, string[]>> = {
  sqlite: ["db", "sqlite", "sqlite3"],
  csv: ["csv", "txt", "tsv"],
  parquet: ["parquet"],
};

export default function ConnectionPage() {
  const { t } = usePreferences();
  return <EditorsOnly title={t.form.addTitle}><ConnectionForm /></EditorsOnly>;
}

function ConnectionForm() {
  const { t } = usePreferences();
  const router = useRouter();
  const [connection, setConnection] = useState<Connection>({ ...blank(), environment: "" });
  const [initialName, setInitialName] = useState("");
  const [password, setPassword] = useState("");
  const [sshSecret, setSshSecret] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const kind = KINDS.find((k) => k.kind === connection.kind) ?? KINDS[0];
  const set = (change: Partial<Connection>) => setConnection({ ...connection, ...change });
  const supabase = connection.kind === "supabase" || connection.kind === "neon";
  const sslMode = supabase && connection.sslMode === "disable" ? "require" : connection.sslMode;
  const verifies = sslMode === "verify-ca" || sslMode === "verify-full";

  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (!id) {
      return;
    }
    list()
      .then((all) => {
        const found = all.find((c) => c.id === id);
        if (found) {
          setConnection(found);
          setInitialName(found.name);
        }
      })
      .catch((failure: unknown) => setError(errorMessage(failure)));
  }, []);

  function paste(text: string) {
    const parsed = fromUrl(text);
    if (!parsed) {
      setUrl(text);
      return;
    }
    set(parsed.connection);
    if (parsed.password) {
      setPassword(parsed.password);
    }
    setUrl("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const saved = await save({ ...connection, sslMode }, password, sshSecret);
      router.push(`/connections/#${saved.id}`);
    } catch (failure) {
      setError(errorMessage(failure));
    }
  }

  return (
    <Page narrow title={connection.id ? t.form.editTitle(initialName) : t.form.addTitle} bar={<>
      <Button asChild variant="outline" className="mr-auto">
        <Link href="/connections/" className="no-underline">{t.form.cancel}</Link>
      </Button>
      <Button type="submit" form="connection">{t.form.save}</Button>
    </>}>
      <form id="connection" className="flex flex-col gap-4" onSubmit={(event) => void submit(event)}>
        <Panel title={t.form.identity}>
          <div className={FIELDS}>
            <Field label={t.form.name} className={WIDE}>
              <Input required autoFocus value={connection.name}
                onChange={(e) => set({ name: e.target.value })} />
            </Field>
            <Field label={t.form.kind}>
              <Picker<Kind> label={t.form.kind} value={connection.kind}
                options={KINDS.map((k) => ({
                  value: k.kind,
                  label: <span className="inline-flex items-center gap-2"><KindLogo kind={k.kind} />{k.label}</span>,
                }))}
                onChange={(value) => set({ kind: value })} />
            </Field>
            <Field label={t.form.environment} hint={t.form.environmentHint}>
              <Picker label={t.form.environment} value={connection.environment} placeholder={t.form.choose} required
                options={ENVIRONMENTS.map((name) => ({ value: name, label: t.environments[name] ?? name }))}
                onChange={(value) => set({ environment: value })} />
            </Field>
          </div>
        </Panel>
        <Panel title={t.form.access}
          hint={<>{t.form.variables} <code className="mono">{"${DB_PASSWORD}"}</code></>}>
          <div className={FIELDS}>
            {kind?.server ? (
              <>
                <Field label={t.form.url} className={WIDE}
                  hint={url ? t.form.urlUnknown : t.form.urlHint}>
                  <Input value={url} autoComplete="off" spellCheck={false}
                    placeholder="postgresql://user:password@host:5432/database"
                    onChange={(e) => paste(e.target.value)} />
                </Field>
                <Field label={t.form.host}>
                  <Input required value={connection.host}
                    onChange={(e) => set({ host: e.target.value })} />
                </Field>
                <Field label={t.form.port}>
                  <Input inputMode="numeric" value={connection.port ?? ""}
                    placeholder={String(kind.port)}
                    onChange={(e) => set({ port: e.target.value ? Number(e.target.value) : null })} />
                </Field>
                <Field label={t.form.database}>
                  <Input required value={connection.database}
                    onChange={(e) => set({ database: e.target.value })} />
                </Field>
                <Field label={t.form.user}>
                  <Input value={connection.user} onChange={(e) => set({ user: e.target.value })} />
                </Field>
                <Field label={t.form.password} className={WIDE}
                  hint={connection.hasPassword ? t.form.keepPassword : t.form.newPassword}>
                  <Input type="password" value={password} autoComplete="new-password"
                    onChange={(e) => setPassword(e.target.value)} />
                </Field>
                <Field label={t.form.sslMode} className={verifies ? undefined : WIDE}
                  hint={t.form.sslHints[sslMode]}>
                  <Picker<SslMode> label={t.form.sslMode} value={sslMode}
                    options={SSL_MODES.filter((mode) => !supabase || mode !== "disable")
                      .map((mode) => ({ value: mode, label: t.form.sslModes[mode] }))}
                    onChange={(value) => set({ sslMode: value })} />
                </Field>
                {verifies && (
                  <Field label={t.form.sslCa} hint={t.form.sslCaHint}>
                    <PathInput value={connection.sslCa} extensions={["pem", "crt", "cer"]}
                      onChange={(sslCa) => set({ sslCa })} />
                  </Field>
                )}
              </>
            ) : (
              <>
                <Field label={t.form.path} className={WIDE}>
                  <PathInput required value={connection.path} extensions={FILE_TYPES[connection.kind]}
                    onChange={(path) => set({ path })} />
                </Field>
                {connection.kind === "csv" && (
                  <Field label={t.form.delimiter}>
                    <Input maxLength={1} value={connection.delimiter}
                      onChange={(e) => set({ delimiter: e.target.value })} />
                  </Field>
                )}
              </>
            )}
          </div>
        </Panel>
        {kind?.server && (
          <Panel title={t.form.tunnel} description={t.form.tunnelBody}
            aside={<Switch checked={connection.ssh} onChange={(ssh) => set({ ssh })} label={t.form.tunnelSwitch} />}>
            {connection.ssh && (
              <div className={FIELDS}>
                <Field label={t.form.sshHost}>
                  <Input required value={connection.sshHost}
                    onChange={(e) => set({ sshHost: e.target.value })} />
                </Field>
                <Field label={t.form.port}>
                  <Input inputMode="numeric" value={connection.sshPort ?? ""} placeholder="22"
                    onChange={(e) => set({ sshPort: e.target.value ? Number(e.target.value) : null })} />
                </Field>
                <Field label={t.form.sshUser}>
                  <Input required value={connection.sshUser}
                    onChange={(e) => set({ sshUser: e.target.value })} />
                </Field>
                <Field label={t.form.sshKey} hint={t.form.sshKeyHint}>
                  <PathInput value={connection.sshKey} placeholder="~/.ssh/id_ed25519"
                    onChange={(sshKey) => set({ sshKey })} />
                </Field>
                <Field label={connection.sshKey ? t.form.sshPassphrase : t.form.sshPassword} className={WIDE}
                  hint={connection.hasSshSecret ? t.form.keepPassword : t.form.newPassword}>
                  <Input type="password" value={sshSecret} autoComplete="new-password"
                    onChange={(e) => setSshSecret(e.target.value)} />
                </Field>
              </div>
            )}
          </Panel>
        )}
        {error && <p className="text-sm text-danger">{error}</p>}
      </form>
    </Page>
  );
}
