import { expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { callbackQuery, Callback } from "../electron/oauth";
import { openable, originOf, siteFile } from "../electron/site";

test("only the addresses Relay sends people to can be opened", () => {
  expect(openable("https://wjonadchmlrdiwvtpujf.supabase.co/auth/v1/authorize?provider=google")).toBe(true);
  expect(openable("https://supabase.com/dashboard/account/tokens")).toBe(true);
  expect(openable("https://console.neon.tech/app/settings/api-keys")).toBe(true);
  for (const refused of [
    "https://supabase.com/dashboard/project/abcd",
    "https://supabase.com.attacker.example/dashboard/account/tokens",
    "http://supabase.com/dashboard/account/tokens",
    "https://user@supabase.com/dashboard/account/tokens",
    "file:///etc/passwd",
    "not a url",
  ]) {
    expect(openable(refused)).toBe(false);
  }
});

test("the app serves its pages and nothing outside them", () => {
  const site = mkdtempSync(join(tmpdir(), "relay-site-"));
  mkdirSync(join(site, "login"));
  writeFileSync(join(site, "index.html"), "home");
  writeFileSync(join(site, "login", "index.html"), "login");
  writeFileSync(join(site, "login", "index.txt"), "payload");
  expect(siteFile(site, "/")).toBe(join(site, "index.html"));
  expect(siteFile(site, "/login/")).toBe(join(site, "login", "index.html"));
  expect(siteFile(site, "/login")).toBe(join(site, "login", "index.html"));
  expect(siteFile(site, "/login/index.txt")).toBe(join(site, "login", "index.txt"));
  expect(siteFile(site, "/missing/")).toBeNull();
  expect(siteFile(site, "/../../etc/passwd")).toBeNull();
  expect(siteFile(site, "/%2e%2e/%2e%2e/etc/passwd")).toBeNull();
  expect(siteFile(site, "/%E0%A4%A")).toBeNull();
  rmSync(site, { recursive: true });
});

test("only the callback request carries the login answer", () => {
  expect(callbackQuery("GET", "/callback?code=abc&state=x")).toBe("code=abc&state=x");
  expect(callbackQuery("GET", "/favicon.ico")).toBeNull();
  expect(callbackQuery("POST", "/callback?code=abc")).toBeNull();
});

test("the browser answer reaches the app and the browser gets the page", async () => {
  const callback = new Callback();
  const port = await callback.listen();
  const waiting = callback.wait("done");
  expect((await fetch(`http://127.0.0.1:${port}/favicon.ico`)).status).toBe(404);
  const browser = await fetch(`http://127.0.0.1:${port}/callback?code=42`);
  expect(await waiting).toBe("code=42");
  expect(await browser.text()).toBe("done");
  await expect(callback.wait("again")).rejects.toThrow("no login is waiting");
});

test("the page origin is read the same for the app scheme and the dev server", () => {
  expect(originOf("app://relay/connections/")).toBe("app://relay");
  expect(originOf("http://localhost:3210/login/")).toBe("http://localhost:3210");
  expect(originOf("app://relay.attacker/")).not.toBe("app://relay");
  expect(originOf("nonsense")).toBeNull();
});
