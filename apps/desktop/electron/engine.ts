import { type ChildProcessByStdio, spawn } from "node:child_process";
import { createInterface } from "node:readline";
import type { Readable, Writable } from "node:stream";

export type Command = { program: string; args: string[] };

export class Service {
  readonly #child: ChildProcessByStdio<Writable, Readable, null>;
  readonly #lines: string[] = [];
  #waiting: { resolve: (line: string) => void; reject: (error: Error) => void } | null = null;
  #failure: Error | null = null;

  constructor({ program, args }: Command) {
    this.#child = spawn(program, args, { stdio: ["pipe", "pipe", "inherit"], windowsHide: true });
    this.#child.stdin.on("error", () => undefined);
    this.#child.once("error", (error) => this.#fail(new Error(`cannot start the engine: ${error.message}`)));
    const lines = createInterface({ input: this.#child.stdout, crlfDelay: Infinity });
    lines.on("line", (line) => {
      if (this.#waiting) {
        this.#waiting.resolve(line.trimEnd());
        this.#waiting = null;
      } else {
        this.#lines.push(line.trimEnd());
      }
    });
    lines.once("close", () => this.#fail(new Error("the engine stopped")));
  }

  #fail(error: Error) {
    this.#failure ??= error;
    this.#waiting?.reject(this.#failure);
    this.#waiting = null;
  }

  call(request: string): Promise<string> {
    if (this.#failure) {
      return Promise.reject(this.#failure);
    }
    this.#child.stdin.write(`${request.trim()}\n`);
    const ready = this.#lines.shift();
    if (ready !== undefined) {
      return Promise.resolve(ready);
    }
    return new Promise<string>((resolve, reject) => {
      this.#waiting = { resolve, reject };
    });
  }

  stop() {
    this.#child.kill();
  }
}

const LONG_METHODS = ["migrate", "plan", "propose", "suggest"];

type Slot = { service: Service | null; queue: Promise<unknown> };

export class Engine {
  readonly #command: () => Command;
  readonly short: Slot = { service: null, queue: Promise.resolve() };
  readonly long: Slot = { service: null, queue: Promise.resolve() };

  constructor(command: () => Command) {
    this.#command = command;
  }

  ask(method: string, request: unknown): Promise<string> {
    const long = LONG_METHODS.includes(method);
    const slot = long ? this.long : this.short;
    const answer = slot.queue.then(async () => {
      slot.service ??= new Service(this.#command());
      const service = slot.service;
      try {
        return await service.call(JSON.stringify(request));
      } catch (error) {
        service.stop();
        slot.service = null;
        throw error;
      } finally {
        if (long && slot.service) {
          slot.service.stop();
          slot.service = null;
        }
      }
    });
    slot.queue = answer.catch(() => undefined);
    return answer;
  }

  stop() {
    for (const slot of [this.short, this.long]) {
      slot.service?.stop();
      slot.service = null;
    }
  }
}

const DIRECT_METHODS = ["ping", "results", "decide"];

export function directRequest(request: string): [string, unknown] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(request);
  } catch {
    throw new Error("the engine request is not valid JSON");
  }
  const method = typeof parsed === "object" && parsed !== null && "method" in parsed ? parsed.method : undefined;
  if (typeof method !== "string") {
    throw new Error("the engine request names no method");
  }
  if (!DIRECT_METHODS.includes(method)) {
    throw new Error(`${method} cannot be called directly; use the connection and migration commands`);
  }
  return [method, parsed];
}
