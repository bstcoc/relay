export type Provider = "supabase" | "neon";

export const API: Record<Provider, string> = {
  supabase: "https://api.supabase.com/v1",
  neon: "https://console.neon.tech/api/v2",
};

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export type Fetch = (url: string, init: RequestInit) => Promise<Response>;

export function answer(provider: Provider, path: string, status: number, body: Json): Json {
  if (status >= 200 && status < 300) {
    return body;
  }
  if (status === 401 || status === 403) {
    throw new Error(`${provider} refused the token; create a new one and link the account again`);
  }
  const detail = typeof body === "object" && body !== null && !Array.isArray(body) && typeof body.message === "string"
    ? body.message
    : "";
  const route = path.split("?")[0];
  throw new Error(`${provider} answered ${status} on ${route} ${detail}`.trimEnd());
}

export class Http {
  readonly #fetch: Fetch;

  constructor(fetch: Fetch) {
    this.#fetch = fetch;
  }

  async #send(provider: Provider, token: string, path: string, init: RequestInit): Promise<Json> {
    let response: Response;
    try {
      response = await this.#fetch(`${API[provider]}${path}`, {
        ...init,
        headers: { Authorization: `Bearer ${token}`, Accept: "application/json", ...init.headers },
      });
    } catch (error) {
      throw new Error(`cannot reach ${provider}: ${error instanceof Error ? error.message : String(error)}`);
    }
    const body = (await response.json().catch(() => null)) as Json;
    return answer(provider, path, response.status, body);
  }

  get(provider: Provider, token: string, path: string) {
    return this.#send(provider, token, path, { method: "GET" });
  }

  post(provider: Provider, token: string, path: string, body: Json) {
    return this.#send(provider, token, path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
}
