import { existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { app, BrowserWindow, dialog, ipcMain, type IpcMainInvokeEvent, net, protocol, session, shell } from "electron";
import { Accounts, providerOf } from "./accounts";
import { type Answer, CHANNELS, type FileFilter } from "./bridge";
import { catalogEntry, type Connection, connectionOf, localOf, Locals, Secrets, withLocal } from "./connections";
import { type Command, directRequest, Engine } from "./engine";
import { Http } from "./http";
import { Callback } from "./oauth";
import { CONTENT_SECURITY_POLICY, ORIGIN, openable, originOf, siteFile } from "./site";
import { Updates } from "./updates";
import { systemKeychain, Vault } from "./vault";

const DEVELOPMENT_URL = "http://localhost:3210";

if (!app.isPackaged) {
  app.setName("Relay");
}

protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

function dataDirectory() {
  const base = process.platform === "linux"
    ? process.env.XDG_DATA_HOME || join(homedir(), ".local", "share")
    : app.getPath("appData");
  return join(base, "app.relay.desktop");
}

function engineCommand(data: string): Command {
  if (!app.isPackaged) {
    const project = process.env.RELAY_ENGINE ?? join(app.getAppPath(), "..", "..", "engine");
    return { program: "uv", args: ["run", "--quiet", "--project", project, "relay-service", "--data", data] };
  }
  const program = join(process.resourcesPath, "engine", process.platform === "win32" ? "relay-service.exe" : "relay-service");
  if (!existsSync(program)) {
    throw new Error(`the engine is missing from this install: ${program}`);
  }
  return { program, args: ["--data", data] };
}

const data = dataDirectory();
mkdirSync(data, { recursive: true });
const vault = new Vault(join(data, "secrets.vault"), systemKeychain("app.relay.desktop", "vault"));
const secrets = new Secrets(vault);
const locals = new Locals(join(data, "on-this-computer.json"));
const accounts = new Accounts(join(data, "accounts.json"), vault, new Http((url, init) => net.fetch(url, init)), secrets);
const engine = new Engine(() => engineCommand(data));
const callback = new Callback();
const updates = new Updates((state) => {
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send(CHANNELS.update, state);
  }
});

type Args = Record<string, unknown>;

function given(value: unknown, name: string): string {
  if (typeof value !== "string") {
    throw new Error(`${name} is missing`);
  }
  return value;
}

const filled = (value: unknown) => (typeof value === "string" && value !== "" ? value : null);

async function entryOf(shared: unknown) {
  const connection = connectionOf(shared);
  const local = withLocal(connection, locals.get(connection.id));
  const [password, sshSecret] = await secrets.of(local);
  return catalogEntry(local, password, sshSecret);
}

async function askAbout(shared: unknown, method: string) {
  const { id } = connectionOf(shared);
  return engine.ask(method, { id: `${method}-${id}`, method, params: { connection: await entryOf(shared) } });
}

async function onThisComputer(connection: Connection) {
  const local = locals.get(connection.id);
  const [password, ssh] = await secrets.of(withLocal(connection, local)).catch(() => [null, null]);
  return { password: password !== null, ssh: ssh !== null, ...local };
}

const MIGRATION_STEPS = ["propose", "plan", "migrate"];

const commands: Record<string, (args: Args) => unknown> = {
  engine: ({ request }) => engine.ask(...directRequest(given(request, "request"))),
  connection_local: ({ connection }) => onThisComputer(connectionOf(connection)),
  connection_keep: async ({ connection, password, sshSecret }) => {
    const kept = connectionOf(connection);
    locals.put(kept.id, localOf(kept));
    await secrets.keep(kept, filled(password), filled(sshSecret));
  },
  connection_forget: async ({ id }) => {
    await secrets.forget(given(id, "id"));
    locals.remove(given(id, "id"));
  },
  connection_test: ({ connection }) => askAbout(connection, "connect"),
  connection_schema: ({ connection }) => askAbout(connection, "schema"),
  migration: async ({ source, target, method, params }) => {
    const step = given(method, "method");
    if (!MIGRATION_STEPS.includes(step)) {
      throw new Error(`${step} is not a migration step`);
    }
    const { catalog: _catalog, ...rest } = (typeof params === "object" && params !== null ? params : {}) as Args;
    const request = { ...rest, source: await entryOf(source), target: await entryOf(target) };
    return engine.ask(step, { id: step, method: step, params: request });
  },
  account_list: ({ provider }) => accounts.list(providerOf(given(provider, "provider"))),
  account_link: ({ provider, token }) => accounts.link(providerOf(given(provider, "provider")), given(token, "token")),
  account_forget: ({ account }) => accounts.forget(given(account, "account")),
  account_projects: ({ account }) => accounts.projects(given(account, "account")),
  account_supabase_endpoint: ({ account, project }) =>
    accounts.supabaseEndpoint(given(account, "account"), given(project, "project")),
  account_neon_project: ({ account, project }) =>
    accounts.neonProject(given(account, "account"), given(project, "project")),
  account_neon_branch: ({ account, project, parent, name }) => accounts.neonBranch(
    given(account, "account"), given(project, "project"), given(parent, "parent"), given(name, "name")),
  account_import: async ({ account, connection, project, branch, role }) => {
    const imported = connectionOf(connection);
    locals.put(imported.id, localOf(imported));
    await accounts.import(given(account, "account"), imported, given(project, "project"),
      filled(branch) ?? "", given(role, "role"));
  },
  session_read: ({ key }) => vault.get(`session:${given(key, "key")}`),
  session_write: ({ key, value }) => vault.set(`session:${given(key, "key")}`, given(value, "value")),
  session_forget: ({ key }) => vault.remove(`session:${given(key, "key")}`),
  oauth_listen: () => callback.listen(),
  oauth_wait: ({ page }) => callback.wait(given(page, "page")),
  update_state: () => updates.state,
  update_download: () => updates.download(),
  update_install: () => updates.install(() => engine.stop()),
};

const pageOrigins = () => (app.isPackaged ? [ORIGIN] : [ORIGIN, DEVELOPMENT_URL]);

function fromPage(event: IpcMainInvokeEvent) {
  const url = event.senderFrame?.url;
  return url !== undefined && pageOrigins().includes(originOf(url) ?? "");
}

async function answered<T>(event: IpcMainInvokeEvent, run: () => T | Promise<T>): Promise<Answer<T>> {
  if (!fromPage(event)) {
    return { error: "this page cannot reach Relay" };
  }
  try {
    return { value: await run() };
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
}

ipcMain.handle(CHANNELS.invoke, (event, command: unknown, args: unknown) => answered(event, () => {
  const run = typeof command === "string" && Object.hasOwn(commands, command) ? commands[command] : undefined;
  if (!run) {
    throw new Error(`${String(command)} is not a Relay command`);
  }
  return run(typeof args === "object" && args !== null ? (args as Args) : {});
}));

ipcMain.handle(CHANNELS.openUrl, (event, url: unknown) => answered(event, async () => {
  if (typeof url !== "string" || !openable(url)) {
    throw new Error("Relay does not open this address");
  }
  await shell.openExternal(url);
  return null;
}));

ipcMain.handle(CHANNELS.pickFile, async (event, filters: FileFilter[]) => {
  const window = BrowserWindow.fromWebContents(event.sender);
  if (!fromPage(event) || !window) {
    return null;
  }
  const chosen = await dialog.showOpenDialog(window, {
    properties: ["openFile"],
    filters: Array.isArray(filters) ? filters : [],
  });
  return chosen.canceled ? null : chosen.filePaths[0] ?? null;
});

function serveSite() {
  const site = join(app.getAppPath(), "out");
  protocol.handle("app", async (request) => {
    const file = siteFile(site, new URL(request.url).pathname);
    const missing = siteFile(site, "/404.html");
    const found = file ?? missing;
    const body = found ? await net.fetch(pathToFileURL(found).toString()) : null;
    const headers = new Headers(body?.headers);
    headers.set("Content-Security-Policy", CONTENT_SECURITY_POLICY);
    return new Response(body?.body ?? null, { status: file ? 200 : 404, headers });
  });
}

function open() {
  const window = new BrowserWindow({
    title: "Relay",
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    show: false,
    ...(process.platform === "darwin" ? { titleBarStyle: "hidden", trafficLightPosition: { x: 18, y: 22 } } : {}),
    webPreferences: {
      preload: join(app.getAppPath(), "dist-electron", "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  window.once("ready-to-show", () => window.show());
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, url) => {
    if (!pageOrigins().includes(originOf(url) ?? "")) {
      event.preventDefault();
    }
  });
  void window.loadURL(app.isPackaged ? `${ORIGIN}/` : DEVELOPMENT_URL);
}

app.enableSandbox();

app.whenReady().then(() => {
  if (!app.isPackaged && process.platform === "darwin") {
    app.dock?.setIcon(join(app.getAppPath(), "build", "icon.png"));
  }
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, allow) => allow(false));
  serveSite();
  open();
  updates.start();
});

app.on("window-all-closed", () => app.quit());

app.on("will-quit", () => engine.stop());
