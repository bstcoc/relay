"use client";

import { AuthClient, type Session } from "@supabase/auth-js";
import { PostgrestClient } from "@supabase/postgrest-js";
import { invoke, isDesktop, openUrl } from "./desktop";
import { useRouter } from "next/navigation";
import { scope } from "./connections";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

const keychain = {
  getItem: (key: string) => invoke<string | null>("session_read", { key }),
  setItem: (key: string, value: string) => invoke<void>("session_write", { key, value }),
  removeItem: (key: string) => invoke<void>("session_forget", { key }),
};

const PROJECT = "wjonadchmlrdiwvtpujf";
const ENDPOINT = `https://${PROJECT}.supabase.co`;
const KEY = "sb_publishable_S8mooSf38UUGCqfKGWaYYg_2DMhanF9";

const auth = new AuthClient({
  url: `${ENDPOINT}/auth/v1`,
  headers: { Authorization: `Bearer ${KEY}`, apikey: KEY },
  storageKey: `sb-${PROJECT}-auth-token`,
  storage: isDesktop() ? keychain : undefined,
  autoRefreshToken: true,
  persistSession: true,
  detectSessionInUrl: false,
  flowType: "pkce",
});

const rest = new PostgrestClient(`${ENDPOINT}/rest/v1`, {
  fetch: async (input, init) => {
    const headers = new Headers(init?.headers);
    const { data } = await auth.getSession();
    headers.set("apikey", KEY);
    headers.set("Authorization", `Bearer ${data.session?.access_token ?? KEY}`);
    return fetch(input, { ...init, headers });
  },
});

export const supabase = {
  auth,
  from: (relation: string) => rest.from(relation),
  rpc: (name: string, args?: Record<string, unknown>) => rest.rpc(name, args),
};

export const LANDING = "http://localhost:3220";

export const inviteLink = (invitation: string) => `${LANDING}/invite/?id=${invitation}`;

export const PICTURES = `${ENDPOINT}/storage/v1/object/public/avatars/`;

export const pictureUrl = (path: string | null | undefined) => (path ? PICTURES + path : null);

async function squared(file: File, size = 256): Promise<Blob> {
  const image = await createImageBitmap(file);
  const side = Math.min(image.width, image.height);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  canvas.getContext("2d")?.drawImage(image, (image.width - side) / 2, (image.height - side) / 2, side, side,
    0, 0, size, size);
  image.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("cannot read this picture"))), "image/webp", 0.85));
}

async function storage(path: string, init: RequestInit) {
  const { data } = await auth.getSession();
  const response = await fetch(`${ENDPOINT}/storage/v1/object/avatars/${path}`, {
    ...init,
    headers: { ...init.headers, apikey: KEY, Authorization: `Bearer ${data.session?.access_token ?? KEY}` },
  });
  if (!response.ok) {
    const answer = (await response.json().catch(() => null)) as { message?: string } | null;
    throw new Error(answer?.message ?? response.statusText);
  }
}

export async function uploadPicture(folder: string, file: File): Promise<string> {
  const blob = await squared(file);
  const path = `${folder}/${crypto.randomUUID()}.${blob.type === "image/webp" ? "webp" : "png"}`;
  await storage(path, { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
  return path;
}

export async function removePicture(path: string) {
  await storage(path, { method: "DELETE" });
}

export type Provider = "azure" | "google";

export async function finishLogin(answer: URLSearchParams) {
  const failure = answer.get("error_description") ?? answer.get("error");
  if (failure) {
    throw new Error(failure);
  }
  const code = answer.get("code");
  if (!code) {
    throw new Error("the login answer carries no code");
  }
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    throw error;
  }
}

export async function logInWith(provider: Provider, page: string) {
  const scopes = provider === "azure" ? "email" : undefined;
  if (!isDesktop()) {
    const { error } = await supabase.auth.signInWithOAuth({
      provider, options: { scopes, redirectTo: `${location.origin}/login/` },
    });
    if (error) {
      throw error;
    }
    return;
  }
  const port = await invoke<number>("oauth_listen");
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider, options: { scopes, redirectTo: `http://127.0.0.1:${port}/callback`, skipBrowserRedirect: true },
  });
  if (error) {
    throw error;
  }
  await openUrl(data.url);
  await finishLogin(new URLSearchParams(await invoke<string>("oauth_wait", { page })));
}

export type Role = "owner" | "admin" | "approver" | "member" | "viewer";

export type Team = {
  id: string; name: string; role: Role; picture: string | null; path: string | null; anonymize: boolean;
};

export type Invitation = { id: string; role: Role; team: string };

export const manages = (team: Team | null) => team?.role === "owner" || team?.role === "admin";

export const canEdit = (team: Team | null) => !!team && team.role !== "viewer";

export const GIVEN_ROLES: Role[] = ["admin", "member", "viewer"];

type Account =
  | { state: "loading" }
  | { state: "signed-out" }
  | { state: "verify"; session: Session }
  | { state: "signed-in"; session: Session; name: string; email: string; avatar: string | null;
      avatarPath: string | null; teams: Team[]; team: Team | null; invitations: Invitation[] };

type Context = {
  account: Account;
  refresh: () => Promise<void>;
  choose: (team: string) => Promise<void>;
  settle: (call: PromiseLike<{ data: unknown; error: { message: string } | null }>) => Promise<string>;
  signOut: () => Promise<void>;
};

const AccountContext = createContext<Context | null>(null);

const CHOSEN = "relay.team";

async function load(session: Session | null): Promise<Account> {
  if (!session) {
    return { state: "signed-out" };
  }
  const level = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  if (level.data?.nextLevel === "aal2" && level.data.currentLevel !== "aal2") {
    return { state: "verify", session };
  }
  const [profile, memberships, invited] = await Promise.all([
    supabase.from("profiles").select("display_name, avatar_url, avatar_path").eq("user_id", session.user.id).single(),
    supabase.from("members").select("role, teams(id, name, avatar_path, anonymize_by_default)")
      .eq("user_id", session.user.id),
    supabase.from("invitations").select("id, role, teams(name)").eq("email", (session.user.email ?? "").toLowerCase())
      .is("accepted_at", null).gt("expires_at", new Date().toISOString()),
  ]);
  const teams = (memberships.data ?? []).flatMap((row): Team[] => {
    const team = row.teams as unknown as {
      id: string; name: string; avatar_path: string | null; anonymize_by_default: boolean;
    } | null;
    return team ? [{
      id: team.id, name: team.name, role: row.role as Role, picture: pictureUrl(team.avatar_path), path: team.avatar_path,
      anonymize: team.anonymize_by_default,
    }] : [];
  });
  const chosen = localStorage.getItem(CHOSEN);
  return {
    state: "signed-in",
    session,
    name: profile.data?.display_name || session.user.email || "",
    email: session.user.email ?? "",
    avatar: pictureUrl(profile.data?.avatar_path) ?? profile.data?.avatar_url ?? null,
    avatarPath: profile.data?.avatar_path ?? null,
    teams,
    team: teams.find((team) => team.id === chosen) ?? teams[0] ?? null,
    invitations: (invited.data ?? []).map((row) => ({
      id: row.id as string, role: row.role as Role, team: (row.teams as unknown as { name: string } | null)?.name ?? "",
    })),
  };
}

export function AccountProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account>({ state: "loading" });

  const enter = useCallback(async (next: Account) => {
    if (next.state === "signed-in" && next.team) {
      scope(next.team.id);
    }
    setAccount(next);
  }, []);

  const refresh = useCallback(async () => {
    const { data } = await supabase.auth.getSession();
    await enter(await load(data.session));
  }, [enter]);

  useEffect(() => {
    void refresh();
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_OUT") {
        void enter({ state: "signed-out" });
      }
    });
    return () => data.subscription.unsubscribe();
  }, [refresh, enter]);

  const choose = useCallback(async (team: string) => {
    localStorage.setItem(CHOSEN, team);
    if (account.state === "signed-in") {
      await enter({ ...account, team: account.teams.find((t) => t.id === team) ?? account.team });
    }
  }, [account, enter]);

  const settle = useCallback(async (call: PromiseLike<{ data: unknown; error: { message: string } | null }>) => {
    const result = await call;
    if (result.error) {
      return result.error.message;
    }
    if (typeof result.data === "string") {
      localStorage.setItem(CHOSEN, result.data);
    }
    await refresh();
    return "";
  }, [refresh]);

  const signOut = useCallback(async () => {
    localStorage.removeItem(CHOSEN);
    await supabase.auth.signOut();
    await enter({ state: "signed-out" });
  }, [enter]);

  return (
    <AccountContext value={{ account, refresh, choose, settle, signOut }}>
      {children}
    </AccountContext>
  );
}

export function useAccount() {
  const context = useContext(AccountContext);
  if (!context) {
    throw new Error("useAccount needs an AccountProvider");
  }
  return context;
}

type Landing = "/" | "/login/" | "/welcome/";

function landing(account: Account): Landing | null {
  if (account.state === "loading") {
    return null;
  }
  if (account.state !== "signed-in") {
    return "/login/";
  }
  return account.team ? "/" : "/welcome/";
}

export function useGuard(page: Landing) {
  const { account } = useAccount();
  const router = useRouter();
  const target = landing(account);
  useEffect(() => {
    if (target && target !== page) {
      router.replace(target);
    }
  }, [target, page, router]);
}

export function useTeam(): Team | null {
  const { account } = useAccount();
  return account.state === "signed-in" ? account.team : null;
}

const graphemes = new Intl.Segmenter(undefined, { granularity: "grapheme" });

export function initials(name: string) {
  const words = name.split(/\s+/).filter(Boolean);
  return words.filter((_, index) => index === 0 || index === words.length - 1)
    .map((word) => [...graphemes.segment(word)][0]?.segment.toUpperCase() ?? "").join("");
}
