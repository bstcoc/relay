import { expect, test } from "bun:test";
import { fromUrl } from "../app/connections";

test("a postgresql url fills every field and hands the password apart", () => {
  expect(fromUrl(" postgresql://relay%40corp:p%40ss%3Aw%2Frd@db.example.org:6432/erp?sslmode=verify-full ")).toEqual({
    connection: {
      kind: "postgresql",
      host: "db.example.org",
      port: 6432,
      database: "erp",
      user: "relay@corp",
      sslMode: "verify-full",
    },
    password: "p@ss:w/rd",
  });
});

test("a supabase pooler url becomes a supabase connection with ssl", () => {
  const parsed = fromUrl("postgresql://postgres.abcd:secret@aws-0-eu-west-3.pooler.supabase.com:6543/postgres");
  expect(parsed?.connection).toMatchObject({
    kind: "supabase",
    user: "postgres.abcd",
    port: 6543,
    sslMode: "require",
  });
  expect(parsed?.password).toBe("secret");
});

test("mysql and sql server urls keep their default port empty", () => {
  expect(fromUrl("mysql://root@localhost/shop")?.connection).toMatchObject({ kind: "mysql", port: null, database: "shop" });
  expect(fromUrl("mssql://sa:x@sql01:1433/master")?.connection.kind).toBe("sqlserver");
});

test("anything else is not a connection url", () => {
  expect(fromUrl("db.example.org")).toBeNull();
  expect(fromUrl("https://example.org/db")).toBeNull();
  expect(fromUrl("postgresql:///erp")).toBeNull();
});
