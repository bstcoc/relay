import { createServer, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

const PATIENCE = 300_000;

type Arrival = { query: string; response: ServerResponse };

export function callbackQuery(method: string | undefined, url: string | undefined): string | null {
  if (method !== "GET" || !url?.startsWith("/callback?")) {
    return null;
  }
  return url.slice("/callback?".length);
}

function reply(response: ServerResponse, status: number, body: string) {
  response.writeHead(status, { "Content-Type": "text/html; charset=utf-8", Connection: "close" });
  response.end(body);
}

export class Callback {
  #waiting: { server: Server; arrival: Promise<Arrival> } | null = null;

  async listen(): Promise<number> {
    this.#close();
    let arrive: (arrival: Arrival) => void = () => undefined;
    const arrival = new Promise<Arrival>((resolve) => {
      arrive = resolve;
    });
    const server = createServer((request, response) => {
      const query = callbackQuery(request.method, request.url);
      if (query === null) {
        reply(response, 404, "");
        return;
      }
      arrive({ query, response });
    });
    await new Promise<void>((resolve, reject) => {
      server.once("error", (error) => reject(new Error(`cannot wait for the login answer: ${error.message}`)));
      server.listen(0, "127.0.0.1", resolve);
    });
    this.#waiting = { server, arrival };
    return (server.address() as AddressInfo).port;
  }

  async wait(page: string): Promise<string> {
    const waiting = this.#waiting;
    if (!waiting) {
      throw new Error("no login is waiting for an answer");
    }
    this.#waiting = null;
    let timer: NodeJS.Timeout | undefined;
    const late = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error("the login took too long; try again")), PATIENCE);
    });
    try {
      const { query, response } = await Promise.race([waiting.arrival, late]);
      reply(response, 200, page);
      return query;
    } finally {
      clearTimeout(timer);
      waiting.server.close();
      waiting.server.closeIdleConnections();
    }
  }

  #close() {
    this.#waiting?.server.close();
    this.#waiting = null;
  }
}
