"use client";

import { openUrl } from "../../../desktop";
import { ExternalLink, GitBranch, LoaderCircle, Plus } from "lucide-react";
import { cn } from "@relay/ui/lib/utils";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@relay/ui/components/badge";
import { Button } from "@relay/ui/components/button";
import { Checkbox } from "@relay/ui/components/checkbox";
import { Input } from "@relay/ui/components/input";
import { Skeleton } from "@relay/ui/components/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@relay/ui/components/tabs";
import {
  accounts, blank, type CloudAccount, type CloudProject, ENVIRONMENTS, importFrom, type NeonBranch, type Provider, relayRole,
} from "../../../connections";
import { errorMessage } from "../../../engine";
import { usePreferences } from "../../../preferences";
import { Field, Frame, KindLogo, Picker, ROWS, SkeletonRows, StatusDot } from "../../../components/ui";
import { EditorsOnly, Page } from "../../../shell";

const PROVIDERS: { id: Provider; label: string; tokens: string }[] = [
  { id: "supabase", label: "Supabase", tokens: "https://supabase.com/dashboard/account/tokens" },
  { id: "neon", label: "Neon", tokens: "https://console.neon.tech/app/settings/api-keys" },
];

function LinkAccount({ provider, onLinked, onCancel }: {
  provider: (typeof PROVIDERS)[number];
  onLinked: (account: CloudAccount) => void;
  onCancel?: () => void;
}) {
  const { t } = usePreferences();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function link() {
    setBusy(true);
    setError("");
    try {
      const account = await accounts.link(provider.id, token);
      setToken("");
      onLinked(account);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Frame className="items-center gap-3 px-8 py-12 text-center">
      <span className="grid size-16 place-items-center rounded-lg border border-border bg-background">
        <KindLogo kind={provider.id} size={40} />
      </span>
      <h2 className="text-base font-medium">{t.cloud.linkTitle(provider.label)}</h2>
      <p className="max-w-[48ch] text-sm text-muted-foreground">{t.cloud.linkBody(provider.label)}</p>
      <form className="mt-2 flex w-[min(480px,100%)] gap-2" onSubmit={(e) => { e.preventDefault(); void link(); }}>
        <Input type="password" autoComplete="off" placeholder={t.cloud.tokenPlaceholder} aria-label={t.cloud.token}
          value={token} onChange={(e) => setToken(e.target.value)} />
        <Button type="submit" disabled={busy || !token.trim()}>
          {busy ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : null}{t.cloud.link}
        </Button>
      </form>
      {error && <p className="text-sm text-danger">{error}</p>}
      <Button type="button" variant="link" onClick={() => void openUrl(provider.tokens)}
        className="h-auto gap-1 p-0 font-normal text-muted-foreground hover:text-foreground hover:no-underline">
        {t.cloud.createToken(provider.label)} <ExternalLink className="size-3.5" />
      </Button>
      {onCancel && <Button variant="ghost" size="sm" onClick={onCancel}>{t.form.cancel}</Button>}
    </Frame>
  );
}

export default function ImportConnection() {
  const { t } = usePreferences();
  return <EditorsOnly title={t.cloud.title}><ImportForm /></EditorsOnly>;
}

function ImportForm() {
  const { t } = usePreferences();
  const router = useRouter();
  const [provider, setProvider] = useState<Provider>("supabase");
  const [linked, setLinked] = useState<CloudAccount[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [projects, setProjects] = useState<Record<string, CloudProject[] | string>>({});
  const [owner, setOwner] = useState("");
  const [project, setProject] = useState<CloudProject | null>(null);
  const [branches, setBranches] = useState<NeonBranch[] | null>(null);
  const [branchId, setBranchId] = useState("");
  const [database, setDatabase] = useState("");
  const [role, setRole] = useState("");
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState("Production");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const relay = useMemo(relayRole, [project?.id]);
  const chosen = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0]!;
  const branch = branches?.find((b) => b.id === branchId);

  useEffect(() => {
    setLinked(null);
    setAdding(false);
    setProject(null);
    setError("");
    accounts.list(provider).then(setLinked).catch((failure: unknown) => setError(errorMessage(failure)));
  }, [provider]);

  useEffect(() => {
    for (const account of linked ?? []) {
      if (projects[account.id] !== undefined) {
        continue;
      }
      accounts.projects(account.id)
        .then((found) => setProjects((all) => ({ ...all, [account.id]: found })))
        .catch((failure: unknown) => setProjects((all) => ({ ...all, [account.id]: errorMessage(failure) })));
    }
  }, [linked, projects]);

  function pick(account: string, next: CloudProject) {
    setOwner(account);
    setProject(next);
    setName(next.name);
    setEnvironment("Production");
    setConsent(false);
    setBranches(null);
    setError("");
    if (provider === "neon") {
      accounts.neonProject(account, next.id).then((found) => {
        setBranches(found);
        const main = found.find((b) => b.main) ?? found[0];
        if (main) {
          choose(main, next.name);
        }
      }).catch((failure: unknown) => setError(errorMessage(failure)));
    }
  }

  function choose(next: NeonBranch, projectName = project?.name ?? "") {
    setBranchId(next.id);
    setDatabase(next.databases[0]?.name ?? "");
    setRole(next.databases[0]?.owner ?? next.roles[0] ?? "");
    setEnvironment(next.main ? "Production" : "Test");
    setName(next.main ? projectName : `${projectName} (${next.name})`);
  }

  async function testBranch() {
    if (!project || !branch) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
      await accounts.neonBranch(owner, project.id, branch.id, `${t.cloud.testBranchName}-${stamp}`);
      const found = await accounts.neonProject(owner, project.id);
      setBranches(found);
      const created = found.find((b) => b.name.endsWith(stamp));
      if (created) {
        choose(created);
      }
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!project) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      let saved;
      if (provider === "supabase") {
        const [host, port] = await accounts.supabaseEndpoint(owner, project.id);
        const user = host.endsWith(".pooler.supabase.com") ? `${relay}.${project.id}` : relay;
        saved = await importFrom(owner, {
          ...blank(), name, kind: "supabase", environment, host, port, database: "postgres", user, sslMode: "require",
        }, project.id, relay);
      } else {
        saved = await importFrom(owner, {
          ...blank(), name, kind: "neon", environment, host: branch?.host ?? "", port: 5432, database, user: role,
          sslMode: "require",
        }, project.id, role, branchId);
      }
      router.push(`/connections/#${saved.id}`);
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy(false);
    }
  }

  const ready = provider === "supabase" ? consent : !!(branch?.host && database && role);

  return (
    <Page narrow title={t.cloud.title}>
      <div className="flex flex-col gap-4">
        <Tabs value={provider} onValueChange={(next) => setProvider(next as Provider)}>
          <TabsList>
            {PROVIDERS.map((p) => (
              <TabsTrigger key={p.id} value={p.id}>
                <KindLogo kind={p.id} size={16} />
                {p.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {linked === null ? <SkeletonRows cells={[40, 10]} /> : linked.map((account) => {
          const found = projects[account.id];
          return (
            <Frame key={account.id}>
              <header className="flex items-center gap-2 border-b border-border py-3 pr-3 pl-6">
                <KindLogo kind={provider} size={20} />
                <span className="truncate text-sm font-medium">{account.label || chosen.label}</span>
                <Badge variant="secondary">{t.cloud.kinds[account.kind]}</Badge>
                <Button size="sm" variant="ghost" className="ml-auto" onClick={() => {
                  void accounts.forget(account.id).then(() => {
                    setLinked(linked.filter((a) => a.id !== account.id));
                    if (owner === account.id) {
                      setProject(null);
                    }
                  });
                }}>{t.cloud.unlink}</Button>
              </header>
              {found === undefined ? <SkeletonRows cells={[40, 10]} />
                : typeof found === "string" ? <p className="p-6 text-sm text-danger">{found}</p>
                  : found.length === 0 ? <p className="p-6 text-sm text-muted-foreground">{t.cloud.noProject}</p> : (
                    <ul className={ROWS}>
                  {found.map((p) => {
                    const open = owner === account.id && project?.id === p.id;
                    return (
                      <li key={p.id} className={cn("border-b border-border last:border-b-0", open && "bg-surface")}>
                        <div className="flex items-center gap-3 py-3 pr-4 pl-6">
                          <span className="flex min-w-0 flex-1 flex-col text-sm">
                            <span className="truncate font-medium">{p.name}</span>
                            <span className="truncate text-muted-foreground">{[p.group, p.region].filter(Boolean).join(" · ")}</span>
                          </span>
                          {!p.active && <StatusDot tone="pending">{t.cloud.paused}</StatusDot>}
                          {!open && (
                            <Button size="sm" variant="outline" disabled={busy || !p.active} onClick={() => pick(account.id, p)}>
                              {t.cloud.choose}
                            </Button>
                          )}
                        </div>
                        {open && (
                          <div className="flex flex-col gap-4 px-6 pt-3 pb-6">
                            <div className="grid grid-cols-2 gap-4">
                              <Field label={t.form.name}>
                                <Input value={name} onChange={(e) => setName(e.target.value)} />
                              </Field>
                              <Field label={t.connections.environment}>
                                <Picker label={t.connections.environment} value={environment} onChange={setEnvironment}
                                  options={ENVIRONMENTS.map((e) => ({ value: e, label: t.environments[e] ?? e }))} />
                              </Field>
                              {provider === "neon" && (branches === null
                                ? <Skeleton className="col-span-full h-9" /> : (
                                  <>
                                    <Field label={t.cloud.branch}>
                                      <Picker label={t.cloud.branch} value={branchId}
                                        onChange={(id) => { const next = branches.find((b) => b.id === id); if (next) choose(next); }}
                                        options={branches.map((b) => ({ value: b.id, label: b.name }))} />
                                    </Field>
                                    <Field label={t.cloud.database}>
                                      <Picker label={t.cloud.database} value={database} onChange={setDatabase}
                                        options={(branch?.databases ?? []).map((d) => ({ value: d.name, label: d.name }))} />
                                    </Field>
                                    <Field label={t.cloud.role}>
                                      <Picker label={t.cloud.role} value={role} onChange={setRole}
                                        options={(branch?.roles ?? []).map((r) => ({ value: r, label: r }))} />
                                    </Field>
                                    <div className="flex items-end">
                                      <Button variant="outline" disabled={busy || !branch}
                                        onClick={() => void testBranch()}>
                                        <GitBranch /> {t.cloud.testBranch}
                                      </Button>
                                    </div>
                                  </>
                                ))}
                            </div>
                            {provider === "supabase" && (
                              <label className={cn("flex cursor-pointer items-start gap-3 rounded-xl border border-border",
                                "bg-background p-4 text-sm")}>
                                <Checkbox checked={consent} onCheckedChange={(next) => setConsent(next === true)}
                                  className="mt-0.5 border-border-strong" />
                                <span>
                                  {t.cloud.consent(relay)}
                                  <span className="mt-1 block text-muted-foreground">{t.cloud.consentNeeded}</span>
                                </span>
                              </label>
                            )}
                            {error && <p className="text-sm text-danger">{error}</p>}
                            <div className="flex justify-end gap-2">
                              <Button variant="ghost" disabled={busy} onClick={() => setProject(null)}>{t.form.cancel}</Button>
                              <Button disabled={busy || !ready || !name.trim()} onClick={() => void finish()}>
                                {busy ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : null}{t.cloud.import}
                              </Button>
                            </div>
                          </div>
                        )}
                      </li>
                    );
                  })}
                    </ul>
                  )}
            </Frame>
          );
        })}

        {linked !== null && (linked.length === 0 || adding) && (
          <LinkAccount provider={chosen} onCancel={linked.length ? () => setAdding(false) : undefined}
            onLinked={(account) => { setLinked([...linked, account]); setAdding(false); }} />
        )}
        {linked !== null && linked.length > 0 && !adding && (
          <div>
            <Button variant="outline" onClick={() => setAdding(true)}>
              <Plus /> {t.cloud.another(chosen.label)}
            </Button>
          </div>
        )}

        {!project && error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Page>
  );
}
