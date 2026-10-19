"use client";

import { Button } from "@relay/ui/components/button";
import { SidebarProvider } from "@relay/ui/components/sidebar";
import { cn } from "@relay/ui/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { canEdit, useGuard, useTeam } from "./account";
import { Palette, usePaletteShortcut } from "./components/palette";
import { Sidebar } from "./components/sidebar";
import { UpdateButton } from "./components/update";
import { ChevronRight, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { StatusDot } from "./components/ui";
import { useEngine } from "./hooks";
import { usePreferences } from "./preferences";

type Slots = { setTitle: (title: string) => void; bar: HTMLElement | null };

const FrameContext = createContext<Slots>({ setTitle: () => undefined, bar: null });

export function Page({ title, footnote, actions, bar, narrow = false, children }: {
  title: string;
  footnote?: ReactNode;
  actions?: ReactNode;
  bar?: ReactNode;
  narrow?: boolean;
  children: ReactNode;
}) {
  const slots = useContext(FrameContext);
  useLayoutEffect(() => slots.setTitle(title), [slots, title]);
  return (
    <div className={cn("flex w-full flex-col gap-4", narrow && "mx-auto max-w-240")}>
      {actions && <div className="flex flex-wrap items-center justify-end gap-2">{actions}</div>}
      {bar && slots.bar && createPortal(
        <div className="flex items-center gap-2 border-t border-border bg-background/80 px-6 py-3 backdrop-blur">{bar}</div>,
        slots.bar)}
      {children}
      {footnote && <p className="px-3 py-2 text-sm text-muted-foreground">{footnote}</p>}
    </div>
  );
}

export function EditorsOnly({ title, children }: { title: string; children: ReactNode }) {
  const { t } = usePreferences();
  return canEdit(useTeam()) ? children : (
    <Page narrow title={title}>
      <p className="text-sm text-muted-foreground">{t.empty.readOnly}</p>
    </Page>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { t } = usePreferences();
  const path = usePathname();
  const engine = useEngine();
  const [title, setTitle] = useState("");
  const [bar, setBar] = useState<HTMLElement | null>(null);
  const slots = useMemo(() => ({ setTitle, bar }), [bar]);
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => setCollapsed(localStorage.getItem("relay.sidebar") === "collapsed"), []);
  const show = (open: boolean) => {
    localStorage.setItem("relay.sidebar", open ? "open" : "collapsed");
    setCollapsed(!open);
  };
  const [finding, setFinding] = useState(false);
  const find = useCallback(() => setFinding(true), []);
  usePaletteShortcut(find);
  const label = collapsed ? t.topbar.expand : t.topbar.collapse;
  const toggle = (className?: string) => (
    <Button type="button" variant="ghost" size="icon-sm" aria-label={label} title={label}
      aria-expanded={!collapsed} onClick={() => show(collapsed)}
      className={cn("mr-1 size-7 text-muted-foreground hover:text-foreground", className)}>
      {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
    </Button>
  );
  const settings = path.startsWith("/settings");
  const [section = "", ...rest] = path.split("/").filter(Boolean);
  const nav: Record<string, string> = t.nav;
  const parent = settings ? { href: "/settings/", label: t.settings.title }
    : rest.length > 0 && nav[section] ? { href: `/${section}/`, label: nav[section] }
    : null;
  const team = useTeam()?.id;
  useGuard("/");

  if (!team) {
    return null;
  }

  return (
    <SidebarProvider open={!collapsed} onOpenChange={show}>
      <Sidebar engine={engine} toggle={toggle()} onFind={find} />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <header data-drag-region className={cn(
          "sticky top-0 z-20 box-border flex h-14 items-center justify-between gap-4 border-b border-border px-6",
          "bg-surface/80 backdrop-blur-md backdrop-saturate-180 select-none",
          collapsed && "in-data-[platform=mac]:pl-22")}>
          <nav className="flex min-w-0 items-center gap-1 text-sm" aria-label={t.topbar.trail}>
            {toggle(collapsed ? undefined : "in-data-[platform=mac]:hidden")}
            {parent && (
              <>
                <Link href={parent.href} className={cn("-ml-2 rounded-full px-2 py-1 text-muted-foreground no-underline",
                  "transition-colors hover:bg-muted hover:text-foreground")}>
                  {parent.label}
                </Link>
                {title && <ChevronRight size={14} className="shrink-0 text-muted-foreground" aria-hidden="true" />}
              </>
            )}
            <h1 aria-current="page" className="m-0 truncate text-sm font-medium text-foreground">{title}</h1>
          </nav>
          <span className="flex shrink-0 items-center gap-2">
            <UpdateButton />
          </span>
        </header>
        {engine.state === "unreachable" && (
          <div role="alert" className="flex items-center justify-between gap-4 border-b border-border bg-danger-soft px-6 py-2 text-sm">
            <StatusDot tone="danger">{t.engine.down}</StatusDot>
            <Button asChild variant="outline" size="xs">
              <Link href="/settings/#engine" className="no-underline">{t.engine.see}</Link>
            </Button>
          </div>
        )}
        <Palette open={finding} onClose={() => setFinding(false)} />
        <main key={team} className="mx-auto box-border flex w-full max-w-350 flex-col gap-4 px-6 pt-6 pb-12">
          <FrameContext value={slots}>{children}</FrameContext>
        </main>
        <div ref={setBar} className="sticky bottom-0 z-10 mt-auto" />
      </div>
    </SidebarProvider>
  );
}
