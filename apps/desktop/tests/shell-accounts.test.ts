import { expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  accountProvider, Accounts, drawnPassword, expect as pointsTo, neonBranches, safe, scopedProject, scramVerifier,
  supabaseEndpoint, supabaseProjects, supabaseRoleSql, supabaseUser,
} from "../electron/accounts";
import { connectionOf, Secrets } from "../electron/connections";
import { answer, Http } from "../electron/http";
import { Vault } from "../electron/vault";

test("supabase projects carry their organization and state", () => {
  const found = supabaseProjects([{ id: "org1", name: "Acme" }], [
    { id: "abcd", name: "ERP", organization_id: "org1", region: "eu-west-3", status: "ACTIVE_HEALTHY" },
    { id: "efgh", name: "Old", organization_id: "org1", region: "eu-west-3", status: "INACTIVE" },
  ]);
  expect(found[0]).toMatchObject({ group: "Acme", active: true });
  expect(found[1]?.active).toBe(false);
});

test("a supabase project is reached through its session pooler", () => {
  const poolers = [
    { db_host: "aws-0-eu-west-3.pooler.supabase.com", db_port: 6543, pool_mode: "transaction" },
    { db_host: "aws-0-eu-west-3.pooler.supabase.com", db_port: 5432, pool_mode: "session" },
  ];
  expect(supabaseEndpoint("abcd", poolers)).toEqual(["aws-0-eu-west-3.pooler.supabase.com", 5432]);
  expect(supabaseEndpoint("abcd", null)).toEqual(["db.abcd.supabase.co", 5432]);
});

test("a neon branch gets the host of its read-write endpoint", () => {
  const found = neonBranches(
    { branches: [{ id: "br-main", name: "main", default: true }, { id: "br-test", name: "test", default: false }] },
    { endpoints: [
      { branch_id: "br-main", type: "read_only", host: "ro.neon.tech" },
      { branch_id: "br-main", type: "read_write", host: "ep-main.neon.tech" },
    ] },
  );
  expect(found[0]).toMatchObject({ host: "ep-main.neon.tech", main: true });
  expect(found[1]?.host).toBe("");
});

test("a relay role is the only sql relay writes into a project", () => {
  const verifier = scramVerifier("Abc123", Buffer.from("0123456789abcdef"));
  const sql = supabaseRoleSql("relay_ab12", verifier);
  expect(sql).toStartWith(`begin; create role relay_ab12 login bypassrls password '${verifier}';`);
  expect(sql).not.toContain("Abc123");
  expect(sql).toEndWith("commit;");
  expect(sql).not.toContain("pg_write_all_data");
  expect(() => supabaseRoleSql("postgres", verifier)).toThrow();
  expect(() => supabaseRoleSql("relay_x; drop table y", verifier)).toThrow();
  expect(() => supabaseRoleSql("relay_ab12", "Abc123")).toThrow();
  expect(() => supabaseRoleSql("relay_ab12", "SCRAM-SHA-256$a'b")).toThrow();
  expect(() => safe("../organizations")).toThrow();
});

test("a secret is only kept for the database it was made for", () => {
  const host = "aws-0-eu-west-3.pooler.supabase.com";
  const user = supabaseUser(host, "relay_ab12", "abcd");
  const imported = connectionOf({
    name: "erp", kind: "supabase", host, port: 5432, user, database: "postgres", sslMode: "require",
  });
  expect(() => pointsTo(imported, "supabase", host, user, "postgres")).not.toThrow();
  for (const moved of [{ host: "attacker.example" }, { port: 6543 }, { user: "postgres" }, { sslMode: "disable" },
    { ssh: true }]) {
    expect(() => pointsTo({ ...imported, ...moved }, "supabase", host, user, "postgres")).toThrow();
  }
});

test("a neon key scoped to one project names it", () => {
  const error = "neon answered 404 on /projects not allowed to perform actions outside "
    + 'the project this key is scoped to; subject_project_id:"little-moon-97174594"';
  expect(scopedProject(error)).toBe("little-moon-97174594");
  expect(scopedProject("neon answered 500 on /projects")).toBeNull();
});

test("an account names its provider", () => {
  expect(accountProvider("neon:0a1b2c3d4e5f")).toBe("neon");
  expect(accountProvider("supabase")).toBe("supabase");
  expect(() => accountProvider("github:1")).toThrow();
});

test("a scram verifier matches postgres", () => {
  expect(scramVerifier("pencil", Buffer.from("0123456789abcdef"))).toBe(
    "SCRAM-SHA-256$4096:MDEyMzQ1Njc4OWFiY2RlZg==$"
    + "nQpbZ77WudtqufPwikHXGRt6g2QJ4zns8bZLw273DRM=:jn2amWP1q1h+jgjy0YTO14S6/F02SV7taipOeB7ef20=");
});

test("a drawn password is long and plain", () => {
  expect(drawnPassword()).toMatch(/^[A-Za-z0-9]{32}$/);
});

test("an api failure says where and why without the token", () => {
  expect(() => answer("neon", "/projects", 401, null)).toThrow("refused the token");
  expect(() => answer("neon", "/projects?org_id=org-1", 400, { message: "org_id is required" }))
    .toThrow("neon answered 400 on /projects org_id is required");
});

test("a linked account keeps its token in the vault, never in its file", async () => {
  const folder = mkdtempSync(join(tmpdir(), "relay-accounts-"));
  const vault = new Vault(join(folder, "secrets.vault"), Buffer.alloc(32, 7));
  const seen: string[] = [];
  const http = new Http(async (url, init) => {
    seen.push(`${url} ${new Headers(init.headers).get("Authorization")}`);
    return Response.json([{ id: "org1", name: "Acme" }]);
  });
  const accounts = new Accounts(join(folder, "accounts.json"), vault, http, new Secrets(vault));
  const linked = await accounts.link("supabase", "  sbp_token  ");
  expect(linked).toMatchObject({ provider: "supabase", kind: "personal", label: "Acme" });
  expect(linked.id).toMatch(/^supabase:[0-9a-f]{12}$/);
  expect(seen).toEqual(["https://api.supabase.com/v1/organizations Bearer sbp_token"]);
  expect(readFileSync(join(folder, "accounts.json"), "utf8")).not.toContain("sbp_token");
  expect(accounts.list("supabase")).toEqual([linked]);
  expect(accounts.list("neon")).toEqual([]);
  await accounts.forget(linked.id);
  expect(accounts.list("supabase")).toEqual([]);
  await expect(accounts.projects(linked.id)).rejects.toThrow("link the account again");
  rmSync(folder, { recursive: true });
});
