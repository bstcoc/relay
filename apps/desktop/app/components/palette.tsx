"use client";

import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@relay/ui/components/command";
import { Dialog, DialogContent, DialogTitle } from "@relay/ui/components/dialog";
import { Kbd } from "@relay/ui/components/kbd";
import { cn } from "@relay/ui/lib/utils";
import { CornerDownLeft, Database, Languages, Plus, Route, Settings, SunMoon, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { canEdit, useTeam } from "../account";
import { useConnections } from "../connections";
import { useMigrations } from "../migrations";
import { usePreferences } from "../preferences";
import { navigation, SETTINGS } from "./sidebar";

type PaletteCommand = { id: string; group: string; label: string; detail?: string; icon: ReactNode; run: () => void };

export const plain = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

export function rank(command: Pick<PaletteCommand, "label" | "detail">, query: string) {
  const label = plain(command.label);
  const detail = plain(command.detail ?? "");
  if (label.startsWith(query)) {
    return 0;
  }
  if (label.split(/\s+/).some((word) => word.startsWith(query))) {
    return 1;
  }
  return label.includes(query) || detail.includes(query) ? 2 : -1;
}

export function usePaletteShortcut(open: () => void) {
  useEffect(() => {
    function listen(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, select, [contenteditable='true']");
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        open();
      } else if (!typing && !event.metaKey && !event.ctrlKey && !event.altKey && event.key.toLowerCase() === "f") {
        event.preventDefault();
        open();
      }
    }
    document.addEventListener("keydown", listen);
    return () => document.removeEventListener("keydown", listen);
  }, [open]);
}

export function Palette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = usePreferences();
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent data-instant showCloseButton={false} aria-describedby={undefined}
        className="top-16 flex max-h-[min(480px,calc(100vh-128px))] translate-y-0 flex-col gap-0 overflow-hidden border-0 p-0 sm:max-w-160">
        <DialogTitle className="sr-only">{t.search}</DialogTitle>
        <PaletteSearch onClose={onClose} />
      </DialogContent>
    </Dialog>
  );
}

function PaletteSearch({ onClose }: { onClose: () => void }) {
  const { t, theme, setTheme, language, setLanguage } = usePreferences();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const { connections } = useConnections();
  const team = useTeam();
  const editor = canEdit(team);
  const migrations = useMigrations(team?.id ?? "").migrations;

  const commands = useMemo(() => {
    const go = (href: string) => () => router.push(href);
    const pages: PaletteCommand[] = navigation(t).flat().map(({ href, label, icon: Icon }) => ({
      id: `page ${href}`, group: t.palette.pages, label, icon: <Icon />, run: go(href),
    }));
    const actions: PaletteCommand[] = [
      ...editor ? [
        { id: "add", group: t.palette.actions, label: t.connections.add, icon: <Plus />, run: go("/connections/new/") },
        { id: "import", group: t.palette.actions, label: t.palette.importAccount, icon: <Upload />,
          run: go("/connections/import/") },
        { id: "migrate", group: t.palette.actions, label: t.palette.newMigration, icon: <Route />,
          run: go("/migrations/new/") },
      ] : [],
      { id: "theme", group: t.palette.actions, label: t.palette.theme, icon: <SunMoon />,
        run: () => setTheme(theme === "dark" ? "light" : "dark") },
      { id: "language", group: t.palette.actions, label: t.palette.language, icon: <Languages />,
        run: () => setLanguage(language === "fr" ? "en" : "fr") },
    ];
    const saved: PaletteCommand[] = (connections ?? []).map((c) => ({
      id: `connection ${c.id}`, group: t.nav.connections, label: c.name, detail: t.environments[c.environment] ?? c.environment,
      icon: <Database />, run: go(editor ? `/connections/new/#${c.id}` : "/connections/"),
    }));
    const runs: PaletteCommand[] = (migrations ?? []).slice(0, 20).map((m) => ({
      id: `migration ${m.id}`, group: t.nav.migrations, label: `${m.source_name} → ${m.target_name}`,
      detail: t.migrations[m.status], icon: <Route />, run: go(`/migrations/report/#${m.id}`),
    }));
    const sections: PaletteCommand[] = SETTINGS.map((id) => ({
      id: `setting ${id}`, group: t.nav.settings, label: t.settings.sections[id as keyof typeof t.settings.sections] ?? id,
      icon: <Settings />, run: go(`/settings/#${id}`),
    }));
    return [...pages, ...actions, ...saved, ...runs, ...sections];
  }, [t, router, theme, setTheme, language, setLanguage, connections, migrations, editor]);

  const needle = plain(query.trim());
  const shown = needle
    ? commands.map((command) => ({ command, score: rank(command, needle) }))
      .filter((found) => found.score >= 0).sort((a, b) => a.score - b.score).map((found) => found.command)
    : commands.filter((command) => !command.id.startsWith("setting") && !command.id.startsWith("migration"));
  const groups = shown.reduce<PaletteCommand[][]>((all, command) => {
    const last = all.at(-1);
    if (last?.[0]?.group === command.group) {
      last.push(command);
    } else {
      all.push([command]);
    }
    return all;
  }, []);
  const [selected, setSelected] = useState("");

  function choose(command: PaletteCommand) {
    onClose();
    command.run();
  }

  return (
    <Command shouldFilter={false} value={selected} onValueChange={setSelected} label={t.search}
      className={cn("min-h-0 flex-1 **:data-[slot=command-input-wrapper]:m-2 **:data-[slot=command-input-wrapper]:h-12",
        "**:data-[slot=command-input-wrapper]:gap-3 **:data-[slot=command-input-wrapper]:rounded-full **:data-[slot=command-input-wrapper]:border",
        "**:data-[slot=command-input-wrapper]:border-input **:data-[slot=command-input-wrapper]:bg-field **:data-[slot=command-input-wrapper]:px-4")}>
      <div className="relative">
        <CommandInput value={query} placeholder={t.palette.placeholder} className="pr-12 text-base"
          onValueChange={(next) => { setQuery(next); setSelected(""); }} />
        <Kbd className="absolute top-1/2 right-4 -translate-y-1/2">Esc</Kbd>
      </div>
      <CommandList className="max-h-none min-h-0 flex-1 overscroll-contain p-2">
        <CommandEmpty className="px-2 py-6 text-center text-sm text-muted-foreground">{t.palette.nothing}</CommandEmpty>
        {groups.map((run) => (
          <CommandGroup key={run[0]?.id} heading={run[0]?.group} className="p-0 **:[[cmdk-group-heading]]:px-2 **:[[cmdk-group-heading]]:pt-3 **:[[cmdk-group-heading]]:pb-1">
            {run.map((command) => (
              <CommandItem key={command.id} value={command.id} onSelect={() => choose(command)}
                className="group/item h-10 cursor-pointer gap-3 px-2">
                {command.icon}
                <span className="truncate">{command.label}</span>
                {command.detail && <span className="shrink-0 text-xs font-medium text-muted-foreground">{command.detail}</span>}
                <CornerDownLeft className="ml-auto hidden size-3.5 group-data-[selected=true]/item:block" />
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </Command>
  );
}
