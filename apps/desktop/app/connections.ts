import { invoke } from "./desktop";
import { useCallback, useEffect, useState } from "react";
import { supabase } from "./account";
import { ask, errorMessage } from "./engine";

let chosen = Promise.withResolvers<string>();

let cached: { space: string; connections: Connection[] } | null = null;

export function known(): Connection[] | null {
  return cached?.connections ?? null;
}

export function scope(space: string) {
  if (cached?.space !== space) {
    cached = null;
  }
  chosen.resolve(space);
  chosen = Promise.withResolvers<string>();
  chosen.resolve(space);
}

export type Column = {
  name: string;
  type: string;
  key?: "primary" | "foreign";
  references?: string;
  referencesColumn?: string;
};

export type Table = { name: string; rows: number; columns: Column[] };

export type Kind = "postgresql" | "supabase" | "neon" | "sqlserver" | "mysql" | "sqlite" | "csv" | "parquet";

export type Connection = {
  id: string;
  name: string;
  kind: Kind;
  environment: string;
  host: string;
  port: number | null;
  database: string;
  user: string;
  path: string;
  delimiter: string;
  sslMode: SslMode;
  sslCa: string;
  hasPassword: boolean;
  ssh: boolean;
  sshHost: string;
  sshPort: number | null;
  sshUser: string;
  sshKey: string;
  hasSshSecret: boolean;
};

export const SSL_MODES = ["disable", "require", "verify-ca", "verify-full"] as const;

export type SslMode = (typeof SSL_MODES)[number];

const SCHEMES: Record<string, Kind> = {
  postgresql: "postgresql",
  postgres: "postgresql",
  mysql: "mysql",
  mssql: "sqlserver",
  sqlserver: "sqlserver",
};

export function fromUrl(text: string): { connection: Partial<Connection>; password: string } | null {
  let url: URL;
  try {
    url = new URL(text.trim());
  } catch {
    return null;
  }
  const kind = SCHEMES[url.protocol.slice(0, -1)];
  if (!kind || !url.hostname) {
    return null;
  }
  const supabase = /\.supabase\.(co|com)$/.test(url.hostname);
  const neon = /\.neon\.tech$/.test(url.hostname);
  const sslMode = SSL_MODES.find((mode) => mode === url.searchParams.get("sslmode"));
  return {
    connection: {
      kind: kind === "postgresql" && supabase ? "supabase" : kind === "postgresql" && neon ? "neon" : kind,
      host: url.hostname,
      port: url.port ? Number(url.port) : null,
      database: decodeURIComponent(url.pathname.slice(1)),
      user: decodeURIComponent(url.username),
      ...(sslMode ? { sslMode } : supabase || neon ? { sslMode: "require" as const } : {}),
    },
    password: decodeURIComponent(url.password),
  };
}

export const KINDS: { kind: Kind; label: string; server: boolean; port?: number }[] = [
  { kind: "postgresql", label: "PostgreSQL", server: true, port: 5432 },
  { kind: "supabase", label: "Supabase", server: true, port: 5432 },
  { kind: "neon", label: "Neon", server: true, port: 5432 },
  { kind: "sqlserver", label: "SQL Server", server: true, port: 1433 },
  { kind: "mysql", label: "MySQL", server: true, port: 3306 },
  { kind: "sqlite", label: "SQLite", server: false },
  { kind: "csv", label: "CSV", server: false },
  { kind: "parquet", label: "Parquet", server: false },
];

export const ENVIRONMENTS = ["Production", "Pre-production", "Test", "Development"];

export function blank(): Connection {
  return {
    id: "",
    name: "",
    kind: "postgresql",
    environment: "Production",
    host: "",
    port: null,
    database: "",
    user: "",
    path: "",
    delimiter: ",",
    sslMode: "disable",
    sslCa: "",
    hasPassword: false,
    ssh: false,
    sshHost: "",
    sshPort: null,
    sshUser: "",
    sshKey: "",
    hasSshSecret: false,
  };
}

export function where(connection: Connection) {
  if (connection.path) {
    return connection.path;
  }
  const port = connection.port ? `:${connection.port}` : "";
  return `${connection.host}${port}/${connection.database}`;
}

export type Reached = { tables?: string[]; columns?: string[]; rows?: number };

type Row = { id: string; name: string; kind: Kind; environment: string; definition: Partial<Connection> };

type OnThisComputer = { password: boolean; ssh: boolean; path: string; sslCa: string; sshKey: string };

const locals = new Map<string, { definition: string; local: Promise<OnThisComputer> }>();

function onThisComputer(connection: Connection) {
  const definition = JSON.stringify(connection);
  const known = locals.get(connection.id);
  if (known?.definition === definition) {
    return known.local;
  }
  const local = invoke<OnThisComputer>("connection_local", { connection });
  locals.set(connection.id, { definition, local });
  local.catch(() => locals.delete(connection.id));
  return local;
}

async function withSecrets(row: Row): Promise<Connection> {
  const shared = { ...blank(), ...row.definition, id: row.id, name: row.name, kind: row.kind, environment: row.environment };
  const local = await onThisComputer(shared);
  return {
    ...shared, path: local.path, sslCa: local.sslCa, sshKey: local.sshKey,
    hasPassword: local.password, hasSshSecret: local.ssh,
  };
}

export async function list(): Promise<Connection[]> {
  const space = await chosen.promise;
  const { data, error } = await supabase.from("connections").select("id, name, kind, environment, definition")
    .eq("team_id", space).order("name");
  if (error) {
    throw new Error(error.message);
  }
  const connections = await Promise.all((data as Row[]).map(withSecrets));
  cached = { space, connections };
  return connections;
}

export function useConnections() {
  const [connections, setConnections] = useState<Connection[] | null>(known);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    try {
      const all = await list();
      setConnections(all);
      setError("");
    } catch (failure) {
      setConnections((now) => now ?? []);
      setError(errorMessage(failure));
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { connections, error, reload };
}

export async function count(): Promise<number> {
  const { count: total, error } = await supabase.from("connections").select("id", { count: "exact", head: true })
    .eq("team_id", await chosen.promise);
  if (error) {
    throw new Error(error.message);
  }
  return total ?? 0;
}

export async function save(connection: Connection, password: string, sshSecret: string): Promise<Connection> {
  const {
    id, name, kind, environment, path: _path, sslCa: _sslCa, sshKey: _sshKey,
    hasPassword: _password, hasSshSecret: _ssh, ...definition
  } = connection;
  const fields = { name: name.trim(), kind, environment, definition };
  const { data, error } = id
    ? await supabase.from("connections").update(fields).eq("id", id).select("id, name, kind, environment, definition").single()
    : await supabase.from("connections").insert({ ...fields, team_id: await chosen.promise })
      .select("id, name, kind, environment, definition").single();
  if (error) {
    throw new Error(error.message);
  }
  cached = null;
  locals.delete(data.id);
  await invoke("connection_keep", {
    connection: { ...connection, id: data.id }, password: password || null, sshSecret: sshSecret || null,
  });
  return withSecrets(data as Row);
}

export async function remove(id: string) {
  const { error } = await supabase.from("connections").delete().eq("id", id);
  if (error) {
    throw new Error(error.message);
  }
  cached = null;
  locals.delete(id);
  await invoke("connection_forget", { id });
}

export async function test(connection: Connection): Promise<Reached> {
  return (await ask<Reached | undefined>("connection_test", { connection })) ?? {};
}

type SchemaTable = {
  name: string;
  rows: number;
  key: string[];
  references: { columns: string[]; table: string; to: string[] }[];
  columns: { name: string; type: string; nullable: boolean }[];
};

export async function schema(connection: Connection): Promise<Table[]> {
  const answer = await ask<{ tables: SchemaTable[] } | undefined>("connection_schema", { connection });
  return (answer?.tables ?? []).map((table) => ({
    name: table.name,
    rows: table.rows,
    columns: table.columns.map((column) => {
      const link = table.references.find((r) => r.columns.includes(column.name));
      return {
        name: column.name,
        type: column.type,
        key: table.key.includes(column.name) ? "primary" : link ? "foreign" : undefined,
        references: link?.table,
        referencesColumn: link?.to[link.columns.indexOf(column.name)],
      };
    }),
  }));
}

export async function recheck(connection: Connection) {
  const at = new Date().toISOString();
  const result = await test(connection).then(
    (reached) => ({ ok: true, at, tables: reached.tables?.length, columns: reached.columns?.length, rows: reached.rows }),
    (failure: unknown) => ({ ok: false, at, message: errorMessage(failure) }),
  );
  const all = JSON.parse(localStorage.getItem("relay.checks") ?? "{}") as Record<string, unknown>;
  localStorage.setItem("relay.checks", JSON.stringify({ ...all, [connection.id]: result }));
}

export type Provider = "supabase" | "neon";

export type CloudProject = { id: string; name: string; group: string; region: string; active: boolean };

export type NeonBranch = {
  id: string;
  name: string;
  main: boolean;
  host: string;
  databases: { name: string; owner: string }[];
  roles: string[];
};

export type CloudAccount = { id: string; provider: Provider; kind: "personal" | "organization" | "project"; label: string };

export const accounts = {
  list: (provider: Provider) => invoke<CloudAccount[]>("account_list", { provider }),
  link: (provider: Provider, token: string) => invoke<CloudAccount>("account_link", { provider, token }),
  forget: (account: string) => invoke<void>("account_forget", { account }),
  projects: (account: string) => invoke<CloudProject[]>("account_projects", { account }),
  supabaseEndpoint: (account: string, project: string) =>
    invoke<[string, number]>("account_supabase_endpoint", { account, project }),
  neonProject: async (account: string, project: string) =>
    (await invoke<{ branches: NeonBranch[] }>("account_neon_project", { account, project })).branches,
  neonBranch: (account: string, project: string, parent: string, name: string) =>
    invoke<{ id: string; host: string }>("account_neon_branch", { account, project, parent, name }),
};

export function relayRole() {
  const bytes = crypto.getRandomValues(new Uint8Array(4));
  return `relay_${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

export async function importFrom(account: string, connection: Connection, project: string,
  role: string, branch?: string): Promise<Connection> {
  const saved = await save(connection, "", "");
  try {
    await invoke("account_import", { account, connection: saved, project, branch: branch ?? null, role });
  } catch (failure) {
    await remove(saved.id).catch(() => undefined);
    throw failure;
  }
  cached = null;
  locals.delete(saved.id);
  return saved;
}
