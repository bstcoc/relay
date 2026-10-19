import { invoke } from "./desktop";

export function errorMessage(failure: unknown): string {
  if (failure instanceof Error) {
    return failure.message;
  }
  if (typeof failure === "object" && failure !== null && "message" in failure) {
    return String(failure.message);
  }
  return String(failure);
}

export async function ask<T>(command: string, args: Record<string, unknown>): Promise<T> {
  const answer = JSON.parse(await invoke<string>(command, args)) as { result?: T; error?: { message: string } };
  if (answer.error) {
    throw new Error(answer.error.message);
  }
  return answer.result as T;
}

let next = 0;

export function call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  next += 1;
  return ask<T>("engine", { request: JSON.stringify({ id: next, method, params }) });
}
