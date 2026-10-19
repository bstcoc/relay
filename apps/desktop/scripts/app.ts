import { spawn } from "node:child_process";
import electron from "electron";

const PAGE = "http://localhost:3210";

const run = (command: string, args: string[], env = process.env) =>
  spawn(command, args, { stdio: "inherit", env });

const page = run("bun", ["run", "dev"]);

while (!(await fetch(PAGE).then(() => true, () => false))) {
  await Bun.sleep(300);
}

const shell = run("bun", ["run", "shell"]);
await new Promise((resolve) => shell.once("exit", resolve));

const { ELECTRON_RUN_AS_NODE: _node, ...env } = process.env;
const app = run(electron as unknown as string, ["."], env);
app.once("exit", (code) => {
  page.kill();
  process.exit(code ?? 0);
});
