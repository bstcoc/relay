import type { Answer, Bridge, FileFilter, UpdateState } from "../electron/bridge";

export type { UpdateState };

declare global {
  interface Window {
    relay?: Bridge;
  }
}

function bridge(): Bridge {
  if (typeof window === "undefined" || !window.relay) {
    throw new Error("Relay runs in its desktop app");
  }
  return window.relay;
}

export const isDesktop = () => typeof window !== "undefined" && window.relay !== undefined;

function settled<T>(answer: Answer<unknown>): T {
  if ("error" in answer) {
    throw new Error(answer.error);
  }
  return answer.value as T;
}

export async function invoke<T = void>(command: string, args: Record<string, unknown> = {}): Promise<T> {
  return settled<T>(await bridge().invoke(command, args));
}

export async function openUrl(url: string) {
  settled(await bridge().openUrl(url));
}

export function pickFile(filters: FileFilter[] = []) {
  return bridge().pickFile(filters);
}

export function onUpdate(listener: (state: UpdateState) => void) {
  return bridge().onUpdate(listener);
}
