"use client";

import { useEffect, useState } from "react";
import { call, errorMessage } from "./engine";

type EngineState = "checking" | "ready" | "unreachable";

export type Engine = { state: EngineState; detail: string };

let ping: Promise<Engine> | null = null;

function pingOnce() {
  ping ??= call<{ version: string }>("ping").then(
    ({ version }): Engine => ({ state: "ready", detail: version }),
    (failure: unknown): Engine => ({ state: "unreachable", detail: errorMessage(failure) }),
  );
  return ping;
}

export function useEngine(): Engine {
  const [engine, setEngine] = useState<Engine>({ state: "checking", detail: "" });
  useEffect(() => {
    let current = true;
    void pingOnce().then((answer) => current && setEngine(answer));
    return () => {
      current = false;
    };
  }, []);
  return engine;
}

export function useHash(fallback: string) {
  const [hash, setHash] = useState(fallback);
  useEffect(() => {
    const read = () => setHash(window.location.hash.slice(1) || fallback);
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, [fallback]);
  return hash;
}
