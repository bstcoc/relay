import { expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  catalogEntry, type Connection, connectionOf, destination, localOf, Locals, Secrets, withLocal,
} from "../electron/connections";
import { Vault } from "../electron/vault";

function connection(kind: string): Connection {
  return connectionOf({ name: "erp", kind, host: "db.example.org", database: "erp", user: "relay@corp" });
}

function secrets() {
  const folder = mkdtempSync(join(tmpdir(), "relay-secrets-"));
  return { kept: new Secrets(new Vault(join(folder, "secrets.vault"), Buffer.alloc(32, 7))), folder };
}

test("a database entry carries encoded credentials and its default port", () => {
  expect(catalogEntry(connection("postgresql"), "p@ss:w/rd", null).database)
    .toBe("postgresql://relay%40corp:p%40ss%3Aw%2Frd@db.example.org:5432/erp");
  expect(catalogEntry(connection("supabase"), "x", null).database).toEndWith(":5432/erp?sslmode=require");
  expect(catalogEntry(connection("sqlserver"), null, null).database).toBe("mssql://relay%40corp@db.example.org:1433/erp");
});

test("the ssl mode and its ca certificate go into the url", () => {
  const erp = { ...connection("postgresql"), sslMode: "verify-full", sslCa: "/certs/ca root.pem" };
  expect(catalogEntry(erp, null, null).database).toBe(
    "postgresql://relay%40corp@db.example.org:5432/erp?sslmode=verify-full&sslrootcert=%2Fcerts%2Fca%20root.pem");
  expect(catalogEntry({ ...erp, sslMode: "require" }, null, null).database).toEndWith("/erp?sslmode=require");
  expect(catalogEntry({ ...connection("supabase"), sslMode: "disable" }, null, null).database).toEndWith("?sslmode=require");
});

test("an ssh tunnel travels with its secret only when switched on", () => {
  const erp = { ...connection("mysql"), sshHost: "bastion.example.org", sshUser: "ops", sshKey: "/keys/id_ed25519" };
  expect(catalogEntry(erp, null, "phrase")).not.toHaveProperty("ssh");
  expect(catalogEntry({ ...erp, ssh: true }, null, "phrase")).toMatchObject({
    ssh: { host: "bastion.example.org", port: 22, user: "ops", key: "/keys/id_ed25519", secret: "phrase" },
  });
});

test("a secret is bound to where it goes not to how it is named", () => {
  const erp = connection("postgresql");
  expect(destination(erp)).toBe(destination({ ...erp, name: "ERP production", environment: "Test" }));
  for (const moved of [
    { host: "attacker.example" }, { port: 6543 }, { user: "other" }, { sslMode: "disable" },
    { sshHost: "bastion.attacker.example" },
  ]) {
    expect(destination({ ...erp, ...moved })).not.toBe(destination(erp));
  }
});

test("the destination reads like the one the Rust shell stored", () => {
  expect(destination(connection("postgresql")))
    .toBe('["postgresql","db.example.org",null,"erp","relay@corp","","","",false,"",null,"",""]');
});

test("a moved connection no longer sends its password", async () => {
  const { kept, folder } = secrets();
  const erp = { ...connection("postgresql"), id: "erp" };
  await kept.keep(erp, "S3cret", null);
  expect((await kept.of(erp))[0]).toBe("S3cret");
  const moved = { ...erp, host: "attacker.example" };
  await expect(kept.of(moved)).rejects.toThrow("points somewhere else");
  await kept.keep(moved, null, null);
  expect((await kept.of(moved))[0]).toBeNull();
  await kept.forget(erp.id);
  rmSync(folder, { recursive: true });
});

test("a file entry points to its file", () => {
  expect(catalogEntry({ ...connection("csv"), path: "/data/clients.csv", delimiter: ";" }, null, null))
    .toEqual({ csv: "/data/clients.csv", delimiter: ";" });
  expect(catalogEntry({ ...connection("sqlite"), path: "/data/erp.db" }, null, null))
    .toEqual({ database: "sqlite:////data/erp.db" });
});

test("environment variables are read before encoding", () => {
  const variable = `RELAY_TEST_SECRET_${process.pid}`;
  process.env[variable] = "a/b";
  const erp = connection("postgresql");
  expect(catalogEntry(erp, `\${${variable}}`, null).database)
    .toBe("postgresql://relay%40corp:a%2Fb@db.example.org:5432/erp");
  expect(() => catalogEntry(erp, "${RELAY_NOT_SET_ANYWHERE}", null))
    .toThrow("environment variable RELAY_NOT_SET_ANYWHERE is not set");
  expect(() => catalogEntry({ ...erp, host: "${AWS_SECRET_ACCESS_KEY}.attacker.example" }, null, null)).toThrow();
  delete process.env[variable];
});

test("paths stay on this computer", () => {
  const folder = mkdtempSync(join(tmpdir(), "relay-locals-"));
  const locals = new Locals(join(folder, "local.json"));
  const sqlite = { ...connection("sqlite"), id: "a", path: "/data/erp.db" };
  locals.put("a", localOf(sqlite));
  expect(withLocal({ ...sqlite, path: "/etc/passwd" }, locals.get("a")).path).toBe("/data/erp.db");
  locals.remove("a");
  expect(locals.get("a")).toEqual({ path: "", sslCa: "", sshKey: "" });
  rmSync(folder, { recursive: true });
});

test("a connection from the page keeps only the fields it knows", () => {
  const parsed = connectionOf({ name: "erp", kind: "postgresql", port: "5432", hasPassword: true, ssh: "yes" });
  expect(parsed.port).toBeNull();
  expect(parsed.ssh).toBe(false);
  expect(parsed).not.toHaveProperty("hasPassword");
  expect(() => connectionOf({ kind: "postgresql" })).toThrow();
});
