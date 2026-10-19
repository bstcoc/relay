"use client";

import { Badge } from "@relay/ui/components/badge";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuSub,
  DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger,
} from "@relay/ui/components/dropdown-menu";
import { Input } from "@relay/ui/components/input";
import { Kbd } from "@relay/ui/components/kbd";
import {
  Sidebar as Frame, SidebarContent, SidebarFooter, SidebarGroup, SidebarHeader, SidebarMenu, SidebarMenuButton,
  SidebarMenuItem, SidebarSeparator,
} from "@relay/ui/components/sidebar";
import { ToggleGroup, ToggleGroupItem } from "@relay/ui/components/toggle-group";
import { cn } from "@relay/ui/lib/utils";
import {
  Braces, Check, ChevronLeft, ChevronRight, ChevronsUpDown, Ellipsis, FingerprintPattern, Gauge, GitCompare, Logs,
  LogOut, Mail, Monitor, Moon, Plus, Route, Search, Settings, Sun, Target, Unplug, Users, Waypoints,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";
import { supabase, useAccount, useTeam } from "../account";
import { type Engine, useHash } from "../hooks";
import { type Language, type Theme, usePreferences } from "../preferences";
import type { Words } from "../words/fr";
import { useInvitations } from "./invitations";
import { ConfirmDialog, EngineStatus, TeamAvatar, UserAvatar } from "./ui";

const ENTRANCE = "animate-in fade-in-0 blur-in-2 duration-(--duration-base) ease-out";

function useNavEntrance(mode: "main" | "settings") {
  const [shown, setShown] = useState(mode);
  const [entrance, setEntrance] = useState<string>();
  if (shown !== mode) {
    setShown(mode);
    setEntrance(cn(ENTRANCE, mode === "settings" ? "motion-safe:slide-in-from-right-2" : "motion-safe:slide-in-from-left-2"));
  }
  return entrance;
}

const SETTINGS_GROUPS = [
  ["you", ["account", "security", "notifications"]],
  ["team", ["general", "members", "roles", "activity"]],
  ["migrations", ["migrations", "privacy"]],
  ["app", ["engine"]],
] as const;

export const SETTINGS: string[] = SETTINGS_GROUPS.flatMap(([, ids]) => ids);

type Identity = { name: string; detail: string; picture: string | null };

function useIdentity(): Identity {
  const { account } = useAccount();
  return account.state === "signed-in"
    ? { name: account.name, detail: account.email, picture: account.avatar }
    : { name: "", detail: "", picture: null };
}

const MENU_ROW = "flex h-10 items-center justify-between px-2 text-sm";
const PILLS = "gap-0 rounded-full border border-border p-0.5";
const PILL = "h-6 min-w-7 rounded-full px-1 text-xs data-[state=on]:bg-muted";

function UserMenu({ engine }: { engine: Engine }) {
  const { t, theme, setTheme, language, setLanguage } = usePreferences();
  const { signOut } = useAccount();
  const who = useIdentity();
  const themes: { value: Theme; label: string; icon: ReactNode }[] = [
    { value: "system", label: t.user.system, icon: <Monitor /> },
    { value: "light", label: t.user.light, icon: <Sun /> },
    { value: "dark", label: t.user.dark, icon: <Moon /> },
  ];
  return (
    <DropdownMenuContent side="top" align="start" className="w-68 p-1 pb-0">
      <div className="flex items-center justify-between gap-2 px-2 py-3">
        <span className="flex min-w-0 flex-col text-sm">
          <span className="truncate font-medium">{who.name}</span>
          <span className="truncate text-muted-foreground">{who.detail}</span>
        </span>
        <DropdownMenuItem asChild className="size-8 justify-center rounded-full p-0">
          <Link href="/settings/#account" aria-label={t.user.account} title={t.user.account}>
            <Settings className="text-foreground" />
          </Link>
        </DropdownMenuItem>
      </div>
      <DropdownMenuSeparator />
      <DropdownMenuItem asChild className={cn(MENU_ROW, "no-underline")}>
        <Link href="/settings/">{t.user.team}<Users /></Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild className={cn(MENU_ROW, "no-underline")}>
        <Link href="/usage/">{t.user.usage}<Gauge /></Link>
      </DropdownMenuItem>
      <div className={MENU_ROW}>
        {t.user.theme}
        <ToggleGroup type="single" spacing={1} className={PILLS} aria-label={t.user.theme} value={theme}
          onValueChange={(value) => value && setTheme(value as Theme)}>
          {themes.map((item) => (
            <ToggleGroupItem key={item.value} value={item.value} title={item.label} aria-label={item.label}
              className={cn(PILL, "[&_svg:not([class*='size-'])]:size-3.5")}>
              {item.icon}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <div className={MENU_ROW}>
        {t.user.language}
        <ToggleGroup type="single" spacing={1} className={PILLS} aria-label={t.user.language} value={language}
          onValueChange={(value) => value && setLanguage(value as Language)}>
          {(["fr", "en"] as const).map((value) => (
            <ToggleGroupItem key={value} value={value} className={PILL}>{value.toUpperCase()}</ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <DropdownMenuItem variant="destructive" className={MENU_ROW} onSelect={() => void signOut()}>
        {t.user.signOut}
        <LogOut />
      </DropdownMenuItem>
      <DropdownMenuItem asChild className={cn(MENU_ROW,
        "-mx-1 mt-1 h-auto rounded-none rounded-b-xl border-t border-border bg-surface p-3 no-underline")}>
        <Link href="/settings/#engine">
          <EngineStatus engine={engine} />
          {engine.state === "ready" && <span className="text-muted-foreground">{t.user.version(engine.detail)}</span>}
        </Link>
      </DropdownMenuItem>
    </DropdownMenuContent>
  );
}

const NAV_ITEM = cn("h-9 gap-3 px-3 no-underline transition-none hover:bg-sidebar-accent/60",
  "data-[active=true]:hover:bg-sidebar-accent");

function SettingsNav({ entrance }: { entrance?: string }) {
  const { t } = usePreferences();
  const hash = useHash("general");
  const [picked, setPicked] = useState<{ from: string; id: string }>();
  const section = picked?.from === hash ? picked.id : hash;
  return (
    <nav aria-label={t.settings.title} className={entrance}>
      <SidebarMenuButton asChild className="grid h-10 grid-cols-[32px_1fr_32px] px-1 text-center no-underline">
        <Link href="/">
          <ChevronLeft aria-label={t.settings.back} />
          <span>{t.settings.title}</span>
        </Link>
      </SidebarMenuButton>
      {SETTINGS_GROUPS.map(([group, ids], index) => (
        <SidebarGroup key={group} className="gap-2 p-0 pt-2">
          {index > 0 && <SidebarSeparator className="mx-0" />}
          <SidebarMenu className="gap-0.5">
            {ids.map((id) => (
              <SidebarMenuItem key={id}>
                <SidebarMenuButton asChild isActive={section === id} className={NAV_ITEM}>
                  <a href={`#${id}`} aria-current={section === id ? "page" : undefined}
                    onClick={() => setPicked({ from: hash, id })}>{t.settings.sections[id]}</a>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      ))}
    </nav>
  );
}

function TeamSwitcher() {
  const { t } = usePreferences();
  const { account, choose, settle } = useAccount();
  const { invitations, answer } = useInvitations();
  const router = useRouter();
  const team = useTeam();
  const teams = account.state === "signed-in" ? account.teams : [];
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  async function respond(invitation: string, accept: boolean) {
    const failure = await answer(invitation, accept);
    setError(failure);
    if (!failure && accept) {
      router.push("/");
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SidebarMenuButton className="h-10 data-[state=open]:bg-sidebar-accent">
            {team ? <TeamAvatar id={team.id} picture={team.picture} className="size-5" />
              : <span className="size-5 shrink-0 rounded-full bg-muted" aria-hidden="true" />}
            <span className="truncate">{team?.name ?? "Relay"}</span>
            {invitations.length > 0 && (
              <Badge className="ml-auto h-5 min-w-5 px-1 tabular-nums" aria-label={t.switcher.invitations(invitations.length)}>
                {invitations.length}
              </Badge>
            )}
            <ChevronsUpDown className={cn("text-muted-foreground", invitations.length === 0 && "ml-auto")} />
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-(--radix-dropdown-menu-trigger-width) min-w-56">
          {teams.map((w) => (
            <DropdownMenuItem key={w.id} className="h-9"
              onSelect={() => void choose(w.id).then(() => router.push("/"))}>
              <TeamAvatar id={w.id} picture={w.picture} className="size-4" />
              <span className="truncate">{w.name}</span>
              {w.id === team?.id && <Check className="ml-auto text-foreground" />}
            </DropdownMenuItem>
          ))}
          {invitations.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                {t.switcher.invitations(invitations.length)}
              </DropdownMenuLabel>
              {invitations.map((invitation) => (
                <DropdownMenuSub key={invitation.id}>
                  <DropdownMenuSubTrigger className="h-9">
                    <Mail className="text-muted-foreground" />
                    <span className="truncate">{invitation.team}</span>
                    <span className="ml-auto pl-2 text-xs text-muted-foreground">{t.settings.roles[invitation.role]}</span>
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent>
                    <DropdownMenuItem className="h-9" onSelect={() => void respond(invitation.id, true)}>
                      {t.welcome.join(t.settings.roles[invitation.role] ?? invitation.role)}
                    </DropdownMenuItem>
                    <DropdownMenuItem className="h-9" onSelect={() => void respond(invitation.id, false)}>
                      {t.switcher.decline}
                    </DropdownMenuItem>
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
              ))}
            </>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem className="h-9" onSelect={() => { setName(""); setError(""); setCreating(true); }}>
            <Plus />
            {t.switcher.create}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {error && !creating && <p className="px-2 text-xs text-danger">{error}</p>}
      {creating && (
        <ConfirmDialog destructive={false} title={t.switcher.create} action={t.welcome.create} ready={name.trim() !== ""}
          body={t.welcome.body} error={error}
          onClose={() => setCreating(false)}
          onConfirm={async () => {
            const failure = await settle(supabase.rpc("create_team", { team_name: name.trim() }));
            setError(failure);
            if (!failure) {
              setCreating(false);
              router.push("/");
            }
          }}>
          <Input aria-label={t.welcome.name} placeholder={t.welcome.name} required maxLength={64}
            autoComplete="organization" value={name} onChange={(e) => setName(e.target.value)} />
        </ConfirmDialog>
      )}
    </>
  );
}

export function navigation(t: Words) {
  return [
    [
      { href: "/", label: t.nav.overview, icon: Target },
      { href: "/connections/", label: t.nav.connections, icon: Unplug },
      { href: "/map/", label: t.nav.map, icon: Waypoints },
      { href: "/migrations/", label: t.nav.migrations, icon: Route },
      { href: "/journal/", label: t.nav.journal, icon: Logs },
      { href: "/findings/", label: t.nav.findings, icon: GitCompare },
    ],
    [
      { href: "/anonymization/", label: t.nav.anonymization, icon: FingerprintPattern },
      { href: "/variables/", label: t.nav.variables, icon: Braces },
    ],
    [
      { href: "/usage/", label: t.nav.usage, icon: Gauge },
      { href: "/settings/", label: t.nav.settings, icon: Settings },
    ],
  ];
}

export function Sidebar({ engine, toggle, onFind }: { engine: Engine; toggle: ReactNode; onFind: () => void }) {
  const { t } = usePreferences();
  const path = usePathname();
  const settings = path.startsWith("/settings");
  const entrance = useNavEntrance(settings ? "settings" : "main");
  const who = useIdentity();
  const groups = navigation(t);
  const active = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href.slice(0, -1));

  return (
    <Frame>
      <SidebarHeader className="pb-0 in-data-[platform=mac]:pt-14">
        <div data-drag-region
          className="absolute inset-x-0 top-0 hidden h-14 items-center justify-end px-3 in-data-[platform=mac]:flex">
          {toggle}
        </div>
        <TeamSwitcher />
        <button type="button" aria-haspopup="dialog" onClick={onFind} className={cn(
          "box-border flex h-9 w-full cursor-pointer items-center gap-2 rounded-full border border-input bg-field",
          "pr-2 pl-3 text-left text-sm text-muted-foreground transition-colors hover:border-border-strong",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring")}>
          <Search className="size-4" />
          <span className="flex-1">{t.search}</span>
          <Kbd className="in-data-[platform=mac]:hidden">Ctrl K</Kbd>
          <Kbd className="hidden in-data-[platform=mac]:inline-flex">⌘K</Kbd>
        </button>
      </SidebarHeader>
      <SidebarContent className="px-2 pt-2">
        {settings ? <SettingsNav entrance={entrance} /> : (
          <nav aria-label="Relay" className={cn("flex flex-col gap-2 pt-1", entrance)}>
            {groups.map((group, index) => (
              <SidebarGroup key={group[0]?.href} className="gap-2 p-0">
                {index > 0 && <SidebarSeparator className="mx-0" />}
                <SidebarMenu className="gap-0.5">
                  {group.map(({ href, label, icon: Icon }) => (
                    <SidebarMenuItem key={href}>
                      <SidebarMenuButton asChild isActive={active(href)} className={NAV_ITEM}>
                        <Link href={href} aria-current={active(href) ? "page" : undefined}>
                          <Icon />
                          <span>{label}</span>
                          {href === "/settings/" && <ChevronRight className="ml-auto text-muted-foreground" />}
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroup>
            ))}
          </nav>
        )}
      </SidebarContent>
      <SidebarFooter className="gap-0 p-0">
        <div className="border-t border-border p-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <SidebarMenuButton className="h-10 data-[state=open]:bg-sidebar-accent">
                <UserAvatar name={who.name} picture={who.picture} />
                <span className="flex-1 truncate">{who.name}</span>
                <Ellipsis className="text-muted-foreground" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <UserMenu engine={engine} />
          </DropdownMenu>
        </div>
      </SidebarFooter>
    </Frame>
  );
}
