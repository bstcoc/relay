import { createHash, createHmac, pbkdf2Sync, randomBytes } from "node:crypto";
import { type Connection, readJson, save, type Secrets } from "./connections";
import { type Http, type Json, type Provider } from "./http";
import type { Vault } from "./vault";

const NEON_PROJECTS = "/projects?limit=400";

export type Account = { id: string; provider: Provider; kind: string; label: string };

export function providerOf(name: string): Provider {
  if (name === "supabase" || name === "neon") {
    return name;
  }
  throw new Error(`unknown account provider ${name}`);
}

export const accountProvider = (account: string) => providerOf(account.split(":")[0] ?? "");

type Fields = { [key: string]: Json };

const fields = (value: Json | undefined): Fields =>
  typeof value === "object" && value !== null && !Array.isArray(value) ? value : {};

const text = (value: Json | undefined, key: string) => {
  const found = fields(value)[key];
  return typeof found === "string" ? found : "";
};

function list(value: Json | undefined, key = ""): Json[] {
  const object = fields(value);
  const inner = key !== "" && key in object ? object[key] : value;
  return Array.isArray(inner) ? inner : [];
}

export function safe(id: string): string {
  if (!/^[A-Za-z0-9_-]+$/.test(id)) {
    throw new Error(`${id} is not a valid identifier`);
  }
  return id;
}

export function scopedProject(error: string): string | null {
  const marker = 'subject_project_id:"';
  const start = error.indexOf(marker);
  if (start === -1) {
    return null;
  }
  const rest = error.slice(start + marker.length);
  const end = rest.indexOf('"');
  if (end === -1) {
    return null;
  }
  try {
    return safe(rest.slice(0, end));
  } catch {
    return null;
  }
}

export function supabaseProjects(organizations: Json, projects: Json) {
  const named = (id: string) => text(list(organizations).find((o) => fields(o).id === id), "name");
  return list(projects).map((p) => ({
    id: text(p, "id"),
    name: text(p, "name"),
    group: named(text(p, "organization_id")),
    region: text(p, "region"),
    active: text(p, "status") === "ACTIVE_HEALTHY",
  }));
}

export function supabaseEndpoint(reference: string, poolers: Json): [string, number] {
  const all = list(poolers);
  const host = fields(all.find((p) => fields(p).pool_mode === "session") ?? all[0]).db_host;
  return [typeof host === "string" ? host : `db.${reference}.supabase.co`, 5432];
}

export function neonProjects(projects: Json) {
  return list(projects, "projects").map((p) => ({
    id: text(p, "id"),
    name: text(p, "name"),
    group: text(p, "org_id"),
    region: text(p, "region_id"),
    active: true,
  }));
}

const readWriteHost = (endpoints: Json, branch: Json | undefined) => {
  const found = list(endpoints, "endpoints").find((e) => fields(e).branch_id === branch && fields(e).type === "read_write");
  return found === undefined ? null : text(found, "host");
};

export function neonBranches(branches: Json, endpoints: Json) {
  return list(branches, "branches").map((b) => {
    const branch = fields(b);
    const main = typeof branch.default === "boolean" ? branch.default
      : typeof branch.primary === "boolean" ? branch.primary : false;
    return { id: text(b, "id"), name: text(b, "name"), main, host: readWriteHost(endpoints, branch.id) ?? "" };
  });
}

export function drawnPassword() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  return Array.from(randomBytes(32), (byte) => alphabet[byte % alphabet.length]).join("");
}

const SCRAM_ITERATIONS = 4096;

export function scramVerifier(password: string, salt: Buffer) {
  const salted = pbkdf2Sync(password, salt, SCRAM_ITERATIONS, 32, "sha256");
  const hmac = (message: string) => createHmac("sha256", salted).update(message).digest();
  const stored = createHash("sha256").update(hmac("Client Key")).digest();
  return `SCRAM-SHA-256$${SCRAM_ITERATIONS}:${salt.toString("base64")}`
    + `$${stored.toString("base64")}:${hmac("Server Key").toString("base64")}`;
}

export function supabaseRoleSql(role: string, verifier: string) {
  if (!/^relay_[a-z0-9_]*$/.test(role)) {
    throw new Error(`${role} is not a Relay role name`);
  }
  if (!verifier.startsWith("SCRAM-SHA-256$") || !/^[A-Za-z0-9$:+/=-]+$/.test(verifier)) {
    throw new Error("the role password must be a SCRAM verifier");
  }
  return `begin; create role ${role} login bypassrls password '${verifier}'; `
    + `grant usage, create on schema public to ${role}; `
    + "grant select, insert, update, delete, truncate, references "
    + `on all tables in schema public to ${role}; `
    + `grant usage, select, update on all sequences in schema public to ${role}; `
    + "alter default privileges in schema public "
    + `grant select, insert, update, delete, truncate, references on tables to ${role}; `
    + "alter default privileges in schema public "
    + `grant usage, select, update on sequences to ${role}; `
    + "commit;";
}

export function expect(connection: Connection, kind: string, host: string, user: string, database: string) {
  const matches = connection.kind === kind
    && connection.host === host
    && (connection.port ?? 5432) === 5432
    && connection.user === user
    && connection.database === database
    && connection.sslMode === "require"
    && !connection.ssh;
  if (!matches) {
    throw new Error("this connection does not point to the imported database");
  }
}

export const supabaseUser = (host: string, role: string, reference: string) =>
  host.endsWith(".pooler.supabase.com") ? `${role}.${reference}` : role;

export class Accounts {
  readonly #path: string;
  readonly #vault: Vault;
  readonly #http: Http;
  readonly #secrets: Secrets;

  constructor(path: string, vault: Vault, http: Http, secrets: Secrets) {
    this.#path = path;
    this.#vault = vault;
    this.#http = http;
    this.#secrets = secrets;
  }

  #read() {
    return readJson<Account[]>(this.#path, []);
  }

  async #token(account: string) {
    const token = await this.#vault.get(`account:${account}`);
    if (token === null) {
      throw new Error("link the account again");
    }
    return token;
  }

  list(provider: Provider) {
    return this.#read().filter((account) => account.provider === provider);
  }

  async forget(id: string) {
    await this.#vault.remove(`account:${id}`).catch(() => undefined);
    save(this.#path, JSON.stringify(this.#read().filter((account) => account.id !== id), null, 2));
  }

  async link(provider: Provider, token: string): Promise<Account> {
    const trimmed = token.trim();
    const probed = await this.#probe(provider, trimmed);
    const account = { ...probed, id: `${provider}:${randomBytes(6).toString("hex")}` };
    await this.#vault.set(`account:${account.id}`, trimmed);
    save(this.#path, JSON.stringify([...this.#read(), account], null, 2));
    return account;
  }

  async #probe(provider: Provider, token: string): Promise<Account> {
    if (token === "") {
      throw new Error("paste the token first");
    }
    const named = (kind: string, label: string): Account => ({ id: "", provider, kind, label });
    const http = this.#http;
    if (provider === "supabase") {
      const organizations = await http.get(provider, token, "/organizations");
      return named("personal", list(organizations).map((o) => text(o, "name")).join(", "));
    }
    const me = await http.get(provider, token, "/users/me").catch(() => undefined);
    if (me !== undefined) {
      return named("personal", text(me, "email"));
    }
    try {
      const listed = await http.get(provider, token, NEON_PROJECTS);
      const first = list(listed, "projects")[0];
      return named("organization", first === undefined ? "" : text(first, "org_id"));
    } catch (error) {
      const project = scopedProject(String((error as Error).message));
      if (project === null) {
        throw error;
      }
      const found = await http.get(provider, token, `/projects/${project}`);
      return named("project", text(fields(found).project ?? null, "name"));
    }
  }

  async projects(account: string) {
    const provider = accountProvider(account);
    const token = await this.#token(account);
    const http = this.#http;
    if (provider === "supabase") {
      return supabaseProjects(await http.get(provider, token, "/organizations"), await http.get(provider, token, "/projects"));
    }
    let listed: Json = null;
    try {
      listed = await http.get(provider, token, NEON_PROJECTS);
    } catch (error) {
      const project = scopedProject((error as Error).message);
      if (project !== null) {
        const one = await http.get(provider, token, `/projects/${project}`);
        return neonProjects({ projects: [fields(one).project ?? null] });
      }
    }
    const found = neonProjects(listed);
    const organizations = await http.get(provider, token, "/users/me/organizations").catch(() => null);
    for (const organization of list(organizations, "organizations")) {
      const path = `${NEON_PROJECTS}&org_id=${text(organization, "id")}`;
      for (const project of neonProjects(await http.get(provider, token, path))) {
        if (!found.some((p) => p.id === project.id)) {
          found.push(project);
        }
      }
    }
    return found;
  }

  async neonProject(account: string, project: string) {
    const token = await this.#token(account);
    const id = safe(project);
    const http = this.#http;
    const branches = neonBranches(
      await http.get("neon", token, `/projects/${id}/branches`),
      await http.get("neon", token, `/projects/${id}/endpoints`),
    );
    const detailed = [];
    for (const branch of branches) {
      const base = `/projects/${id}/branches/${branch.id}`;
      const databases = await http.get("neon", token, `${base}/databases`);
      const roles = await http.get("neon", token, `${base}/roles`);
      detailed.push({
        ...branch,
        databases: list(databases, "databases").map((d) => ({ name: text(d, "name"), owner: text(d, "owner_name") })),
        roles: list(roles, "roles").filter((r) => fields(r).protected !== true).map((r) => text(r, "name")),
      });
    }
    return { branches: detailed };
  }

  async neonBranch(account: string, project: string, parent: string, name: string) {
    const token = await this.#token(account);
    const created = await this.#http.post("neon", token, `/projects/${safe(project)}/branches`, {
      branch: { parent_id: safe(parent), name },
      endpoints: [{ type: "read_write" }],
    });
    const endpoint = list(created, "endpoints")[0];
    return { id: text(fields(created).branch, "id"), host: endpoint === undefined ? "" : text(endpoint, "host") };
  }

  async supabaseEndpoint(account: string, reference: string) {
    const token = await this.#token(account);
    const id = safe(reference);
    const poolers = await this.#http.get("supabase", token, `/projects/${id}/config/database/pooler`).catch(() => null);
    return supabaseEndpoint(id, poolers);
  }

  async import(account: string, connection: Connection, project: string, branch: string, role: string) {
    if (accountProvider(account) === "supabase") {
      return this.#importSupabase(account, connection, project, role);
    }
    return this.#importNeon(account, connection, project, branch, role);
  }

  async #importSupabase(account: string, connection: Connection, reference: string, role: string) {
    const id = safe(reference);
    const [host] = await this.supabaseEndpoint(account, id);
    expect(connection, "supabase", host, supabaseUser(host, role, id), "postgres");
    const token = await this.#token(account);
    const secret = drawnPassword();
    const query = supabaseRoleSql(role, scramVerifier(secret, randomBytes(16)));
    await this.#http.post("supabase", token, `/projects/${id}/database/query`, { query });
    await this.#secrets.keep(connection, secret, null);
  }

  async #importNeon(account: string, connection: Connection, project: string, branch: string, role: string) {
    const token = await this.#token(account);
    const [projectId, branchId, roleName] = [safe(project), safe(branch), safe(role)];
    const http = this.#http;
    const host = readWriteHost(await http.get("neon", token, `/projects/${projectId}/endpoints`), branchId);
    if (host === null) {
      throw new Error("this branch has no read-write endpoint");
    }
    const databases = await http.get("neon", token, `/projects/${projectId}/branches/${branchId}/databases`);
    if (!list(databases, "databases").some((d) => fields(d).name === connection.database)) {
      throw new Error("this database is not in the imported branch");
    }
    expect(connection, "neon", host, roleName, connection.database);
    const path = `/projects/${projectId}/branches/${branchId}/roles/${roleName}/reveal_password`;
    const revealed = fields(await http.get("neon", token, path)).password;
    if (typeof revealed !== "string") {
      throw new Error("Neon did not reveal the password of this role");
    }
    await this.#secrets.keep(connection, revealed, null);
  }
}
