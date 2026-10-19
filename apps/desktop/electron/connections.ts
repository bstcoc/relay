import { readFileSync, renameSync, writeFileSync } from "node:fs";
import type { Vault } from "./vault";

export type Connection = {
  id: string;
  name: string;
  kind: string;
  environment: string;
  host: string;
  port: number | null;
  database: string;
  user: string;
  path: string;
  delimiter: string;
  sslMode: string;
  sslCa: string;
  ssh: boolean;
  sshHost: string;
  sshPort: number | null;
  sshUser: string;
  sshKey: string;
};

export type Local = { path: string; sslCa: string; sshKey: string };

type Fields = Record<string, unknown>;

const text = (value: unknown) => (typeof value === "string" ? value : "");

const port = (value: unknown) =>
  typeof value === "number" && Number.isInteger(value) && value > 0 && value < 65536 ? value : null;

export function connectionOf(value: unknown): Connection {
  const fields = (typeof value === "object" && value !== null ? value : {}) as Fields;
  if (typeof fields.name !== "string" || typeof fields.kind !== "string") {
    throw new Error("the connection needs a name and a kind");
  }
  return {
    id: text(fields.id),
    name: fields.name,
    kind: fields.kind,
    environment: text(fields.environment),
    host: text(fields.host),
    port: port(fields.port),
    database: text(fields.database),
    user: text(fields.user),
    path: text(fields.path),
    delimiter: text(fields.delimiter),
    sslMode: text(fields.sslMode),
    sslCa: text(fields.sslCa),
    ssh: fields.ssh === true,
    sshHost: text(fields.sshHost),
    sshPort: port(fields.sshPort),
    sshUser: text(fields.sshUser),
    sshKey: text(fields.sshKey),
  };
}

export const localOf = (connection: Connection): Local => ({
  path: connection.path,
  sslCa: connection.sslCa,
  sshKey: connection.sshKey,
});

export const withLocal = (connection: Connection, local: Local): Connection => ({ ...connection, ...local });

export function save(path: string, text: string) {
  writeFileSync(`${path}.tmp`, text);
  renameSync(`${path}.tmp`, path);
}

export function readJson<T>(path: string, empty: T): T {
  try {
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return empty;
    }
    throw error;
  }
}

const NO_LOCAL: Local = { path: "", sslCa: "", sshKey: "" };

export class Locals {
  readonly #path: string;

  constructor(path: string) {
    this.#path = path;
  }

  #all() {
    return readJson<Record<string, Partial<Local>>>(this.#path, {});
  }

  get(id: string): Local {
    return { ...NO_LOCAL, ...this.#all()[id] };
  }

  put(id: string, local: Local) {
    save(this.#path, JSON.stringify({ ...this.#all(), [id]: local }, null, 2));
  }

  remove(id: string) {
    const all = this.#all();
    delete all[id];
    save(this.#path, JSON.stringify(all, null, 2));
  }
}

export const sshSecretId = (id: string) => `${id}:ssh`;

const destinationId = (id: string) => `${id}:destination`;

export function destination(connection: Connection): string {
  return JSON.stringify([
    connection.kind, connection.host, connection.port, connection.database, connection.user, connection.path,
    connection.sslMode, connection.sslCa, connection.ssh, connection.sshHost, connection.sshPort,
    connection.sshUser, connection.sshKey,
  ]);
}

export class Secrets {
  readonly #vault: Vault;

  constructor(vault: Vault) {
    this.#vault = vault;
  }

  set(id: string, password: string) {
    return this.#vault.set(`connection:${id}`, password);
  }

  get(id: string) {
    return this.#vault.get(`connection:${id}`);
  }

  async forgetOne(id: string) {
    await this.#vault.remove(`connection:${id}`).catch(() => undefined);
  }

  async #bound(connection: Connection) {
    return (await this.get(destinationId(connection.id))) === destination(connection);
  }

  async keep(connection: Connection, password: string | null, sshSecret: string | null) {
    const { id } = connection;
    if (!(await this.#bound(connection))) {
      if (password === null) {
        await this.forgetOne(id);
      }
      if (sshSecret === null) {
        await this.forgetOne(sshSecretId(id));
      }
    }
    if (password !== null) {
      await this.set(id, password);
    }
    if (sshSecret !== null) {
      await this.set(sshSecretId(id), sshSecret);
    }
    await this.set(destinationId(id), destination(connection));
  }

  async of(connection: Connection): Promise<[string | null, string | null]> {
    const password = await this.get(connection.id);
    const ssh = connection.ssh ? await this.get(sshSecretId(connection.id)) : null;
    if ((password !== null || ssh !== null) && !(await this.#bound(connection))) {
      throw new Error("this connection now points somewhere else than when you saved its password; "
        + "enter the password again before using it");
    }
    return [password, ssh];
  }

  async forget(id: string) {
    await this.forgetOne(id);
    await this.forgetOne(sshSecretId(id));
    await this.forgetOne(destinationId(id));
  }
}

function shared(value: string) {
  if (value.includes("${")) {
    throw new Error(`${value}: environment variables only work in passwords and in paths on this computer`);
  }
  return value;
}

export function expanded(value: string): string {
  let out = "";
  let rest = value;
  for (let start = rest.indexOf("${"); start !== -1; start = rest.indexOf("${")) {
    const end = rest.indexOf("}", start);
    if (end === -1) {
      throw new Error(`unclosed variable in ${value}`);
    }
    const name = rest.slice(start + 2, end);
    const variable = process.env[name];
    if (variable === undefined) {
      throw new Error(`environment variable ${name} is not set`);
    }
    out += rest.slice(0, start) + variable;
    rest = rest.slice(end + 1);
  }
  return out + rest;
}

export function encoded(value: string): string {
  return Array.from(Buffer.from(value, "utf8"), (byte) => {
    const char = String.fromCharCode(byte);
    return /[A-Za-z0-9\-._~]/.test(char) ? char : `%${byte.toString(16).toUpperCase().padStart(2, "0")}`;
  }).join("");
}

const SCHEMES: Record<string, [string, number]> = {
  postgresql: ["postgresql", 5432],
  supabase: ["postgresql", 5432],
  neon: ["postgresql", 5432],
  mysql: ["mysql", 3306],
  sqlserver: ["mssql", 1433],
};

function sslQuery(connection: Connection) {
  const managed = connection.kind === "supabase" || connection.kind === "neon";
  const mode = managed && (connection.sslMode === "" || connection.sslMode === "disable") ? "require" : connection.sslMode;
  const ca = expanded(connection.sslCa);
  if (mode === "") {
    return "";
  }
  if ((mode === "verify-ca" || mode === "verify-full") && ca !== "") {
    return `?sslmode=${mode}&sslrootcert=${encoded(ca)}`;
  }
  return `?sslmode=${mode}`;
}

function sshEntry(connection: Connection, secret: string | null) {
  return {
    host: shared(connection.sshHost),
    port: connection.sshPort ?? 22,
    user: shared(connection.sshUser),
    key: expanded(connection.sshKey),
    secret: secret === null ? "" : expanded(secret),
  };
}

export function catalogEntry(connection: Connection, password: string | null, sshSecret: string | null) {
  const path = expanded(connection.path);
  switch (connection.kind) {
    case "sqlite":
      return { database: `sqlite:///${path}` };
    case "csv":
      return { csv: path, delimiter: connection.delimiter === "" ? "," : shared(connection.delimiter) };
    case "parquet":
      return { parquet: path };
  }
  const scheme = SCHEMES[connection.kind];
  if (!scheme) {
    throw new Error(`unknown kind ${connection.kind}`);
  }
  const user = shared(connection.user);
  const secret = password === null ? null : expanded(password);
  const credentials = user === "" ? "" : secret === null ? `${encoded(user)}@` : `${encoded(user)}:${encoded(secret)}@`;
  const database = `${scheme[0]}://${credentials}${shared(connection.host)}:${connection.port ?? scheme[1]}/`
    + `${encoded(shared(connection.database))}${sslQuery(connection)}`;
  return connection.ssh ? { database, ssh: sshEntry(connection, sshSecret) } : { database };
}
