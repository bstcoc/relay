import { afterEach, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fromHex, setAside, Vault } from "../electron/vault";

const folders: string[] = [];

function place() {
  const folder = mkdtempSync(join(tmpdir(), "relay-vault-"));
  folders.push(folder);
  return join(folder, "secrets.vault");
}

afterEach(() => {
  for (const folder of folders.splice(0)) {
    rmSync(folder, { recursive: true, force: true });
  }
});

test("a secret survives a restart and never lies in clear", async () => {
  const path = place();
  await new Vault(path, Buffer.alloc(32, 1)).set("connection:erp", "S3cret-pass");
  expect(readFileSync(path).toString("latin1")).not.toContain("S3cret-pass");
  const again = new Vault(path, Buffer.alloc(32, 1));
  expect(await again.get("connection:erp")).toBe("S3cret-pass");
  await again.remove("connection:erp");
  expect(await new Vault(path, Buffer.alloc(32, 1)).get("connection:erp")).toBeNull();
});

test("another key cannot open the vault", async () => {
  const path = place();
  await new Vault(path, Buffer.alloc(32, 2)).set("session", "token");
  await expect(new Vault(path, Buffer.alloc(32, 3)).get("session")).rejects.toThrow("the key of this computer");
});

test("a vault sealed by the Rust shell opens", async () => {
  const path = place();
  await Bun.write(path, Buffer.from(
    "000102030405060708090a0b63a38252272baf6b0ae01d04d0a159094a057f4c6da98378e2", "hex"));
  expect(await new Vault(path, Buffer.alloc(32, 7)).get("k")).toBe("v");
});

test("a new vault key sets the old vault aside and keeps it", async () => {
  const path = place();
  await new Vault(path, Buffer.alloc(32, 4)).set("session", "token");
  let stored: string | null = null;
  const fresh = new Vault(path, { read: async () => stored, write: async (hex) => void (stored = hex) });
  expect(await fresh.get("session")).toBeNull();
  expect(existsSync(`${path}.lost`)).toBe(true);
  expect(fromHex(stored ?? "")).toHaveLength(32);
  setAside(join(tmpdir(), "relay-vault-that-does-not-exist"));
});

test("a damaged keychain key is refused", async () => {
  const vault = new Vault(place(), { read: async () => "zz", write: async () => undefined });
  await expect(vault.get("session")).rejects.toThrow("damaged");
  expect(fromHex("ab".repeat(32))).toEqual(Buffer.alloc(32, 0xab));
});
