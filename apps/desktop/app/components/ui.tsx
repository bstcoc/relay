"use client";

import { Badge } from "@relay/ui/components/badge";
import { Button } from "@relay/ui/components/button";
import { Card } from "@relay/ui/components/card";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@relay/ui/components/dialog";
import { RelayMark } from "@relay/ui/components/relay-mark";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@relay/ui/components/select";
import { Skeleton } from "@relay/ui/components/skeleton";
import { Switch as SwitchControl } from "@relay/ui/components/switch";
import { TeamArt } from "@relay/ui/components/team-art";
import { cn } from "@relay/ui/lib/utils";
import { Lock } from "lucide-react";
import { type ChangeEvent, type ComponentProps, type FormEvent, type ReactNode, useRef, useState } from "react";
import { initials, PICTURES } from "../account";
import type { Kind } from "../connections";
import type { Engine } from "../hooks";
import { usePreferences } from "../preferences";

const DOTS = {
  verified: "before:bg-status-verified",
  pending: "before:bg-status-pending before:animate-breathe motion-reduce:before:animate-none",
  danger: "truncate text-danger before:bg-status-danger",
  neutral: "before:bg-border-strong",
};

export function StatusDot({ tone, children }: {
  tone: "verified" | "danger" | "pending" | "neutral";
  children: ReactNode;
}) {
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-2 text-sm font-medium text-foreground",
      "before:size-2.5 before:shrink-0 before:rounded-full before:content-['']",
      "before:transition-[background-color] before:duration-(--duration-base) before:ease-out",
      "[&>span]:inline-flex [&>span]:items-center [&>span]:gap-1", DOTS[tone])}>
      {children}
    </span>
  );
}

export function EnvironmentPill({ environment }: { environment: string }) {
  const { t } = usePreferences();
  const production = environment === "Production";
  return (
    <Badge variant={production ? "production" : "secondary"} className="h-6 px-2.5">
      {production && <Lock strokeWidth={2.25} aria-hidden="true" />}
      {t.environments[environment] ?? environment}
    </Badge>
  );
}

export function Frame({ className, ...props }: ComponentProps<typeof Card>) {
  return <Card className={cn("gap-0 overflow-hidden py-0 shadow-none", className)} {...props} />;
}

export const ROWS = "m-0 list-none p-0";

export const MIGRATION = "grid-cols-[minmax(0,2fr)_minmax(120px,auto)_140px_minmax(120px,auto)_140px] pr-4 whitespace-nowrap";

export const ROUTE = cn("flex min-w-0 items-center gap-1 text-sm font-medium no-underline hover:underline [&_svg]:shrink-0",
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring");

export const TIME = "flex items-center justify-end text-sm whitespace-nowrap text-muted-foreground";

export const SECTION = "mb-3 flex items-baseline justify-between text-base font-medium";

export const ROW = cn("box-border grid min-h-[49px] items-center gap-6 border-b border-border py-2 pr-2 pl-3 transition-colors",
  "last:border-b-0 hover:bg-muted");

export function SkeletonRows({ cells, count = 3 }: { cells: number[]; count?: number }) {
  return (
    <Frame aria-busy="true">
      {Array.from({ length: count }, (_, row) => (
        <div key={row} className="box-border flex min-h-12 items-center gap-6 border-b border-border px-4 py-2 last:border-b-0">
          {cells.map((width, cell) => (
            <div key={cell} className="flex-1"><Skeleton className="h-4" style={{ width: `${width}%` }} /></div>
          ))}
        </div>
      ))}
    </Frame>
  );
}

const LOGOS: Record<Kind, string> = {
  postgresql: "/logos/postgresql.svg",
  supabase: "/logos/supabase.svg",
  neon: "/logos/neon.svg",
  sqlserver: "/logos/sqlserver.svg",
  mysql: "/logos/mysql.svg",
  sqlite: "/logos/sqlite.svg",
  csv: "/logos/csv.svg",
  parquet: "/logos/parquet.svg",
};

export function KindLogo({ kind, size = 20 }: { kind: Kind; size?: number }) {
  const inner = Math.round(size * 0.85);
  return (
    <span className="inline-grid shrink-0 place-items-center text-muted-foreground" style={{ width: size, height: size }}
      aria-hidden="true">
      {kind === "csv"
        ? <span className="block bg-current mask-contain mask-center mask-no-repeat"
          style={{ width: inner, height: inner, maskImage: `url(${LOGOS.csv})` }} />
        : <img src={LOGOS[kind]} alt="" width={inner} height={inner} className="block object-contain" />}
    </span>
  );
}

const AVATAR = "inline-grid size-6 shrink-0 place-items-center rounded-full text-[10px] font-semibold text-on-ink";
const LARGE = "size-14 text-base";

export function Avatar({ children }: { children: ReactNode }) {
  return <span className={cn(AVATAR, "bg-linear-135 from-pending to-danger")} aria-hidden="true">{children}</span>;
}

export function UserAvatar({ name, picture, large = false, className }: {
  name: string; picture?: string | null; large?: boolean; className?: string;
}) {
  const classes = cn(AVATAR, "bg-linear-135 from-verified to-action object-cover", large && LARGE, className);
  return picture && [PICTURES, "https://lh3.googleusercontent.com/"].some((origin) => picture.startsWith(origin))
    ? <img src={picture} alt="" className={classes} referrerPolicy="no-referrer" />
    : <span className={classes} aria-hidden="true">{initials(name)}</span>;
}

export function TeamAvatar({ id, picture, large = false, className }: {
  id: string; picture?: string | null; large?: boolean; className?: string;
}) {
  const classes = cn(AVATAR, "overflow-hidden object-cover", large && LARGE, className);
  if (picture?.startsWith(PICTURES)) {
    return <img src={picture} alt="" className={classes} />;
  }
  return <TeamArt id={id} className={classes} />;
}

export function PicturePicker({ avatar, editable, label, removeLabel, onPick, onRemove }: {
  avatar: ReactNode;
  editable: boolean;
  label: string;
  removeLabel: string;
  onPick: (file: File) => Promise<void>;
  onRemove?: () => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }
  function picked(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      void run(() => onPick(file));
    }
  }
  return (
    <span className="inline-flex flex-col items-center gap-1">
      <button type="button" aria-label={label} title={label} disabled={!editable || busy}
        onClick={() => input.current?.click()}
        className="cursor-pointer rounded-full border-0 bg-transparent p-0 transition-opacity enabled:hover:opacity-80 disabled:cursor-default">
        {avatar}
      </button>
      {editable && onRemove && (
        <Button type="button" variant="link" size="xs" disabled={busy} onClick={() => void run(onRemove)}
          className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground hover:no-underline">
          {removeLabel}
        </Button>
      )}
      <input ref={input} type="file" accept="image/png, image/jpeg, image/webp" hidden onChange={picked} />
    </span>
  );
}

export function Switch({ checked, onChange, label, hideLabel = false, disabled = false }: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  hideLabel?: boolean;
  disabled?: boolean;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-3 text-sm has-disabled:cursor-not-allowed">
      <SwitchControl checked={checked} onCheckedChange={onChange} disabled={disabled}
        className="data-[state=unchecked]:bg-border-strong dark:data-[state=unchecked]:bg-border-strong" />
      <span className={cn(hideLabel && "sr-only")}>{label}</span>
    </label>
  );
}

export function Field({ label, hint, className, children }: {
  label: ReactNode;
  hint?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span className="text-[13px] leading-4 font-medium text-foreground">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

const NONE = "\u0000";

export function Picker<T extends string>({ value, options, onChange, label, placeholder, required, size, disabled, className }: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (value: T) => void;
  label: string;
  placeholder?: string;
  required?: boolean;
  size?: "sm" | "default";
  disabled?: boolean;
  className?: string;
}) {
  return (
    <Select value={value || (placeholder ? "" : NONE)} required={required} disabled={disabled}
      onValueChange={(next) => onChange((next === NONE ? "" : next) as T)}>
      <SelectTrigger size={size} aria-label={label} className={cn("w-full min-w-0", className)}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent position="popper" className="max-h-72">
        {options.map((option) => (
          <SelectItem key={option.value || NONE} value={option.value || NONE}>{option.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function EngineStatus({ engine }: { engine: Engine }) {
  const { t } = usePreferences();
  return (
    <StatusDot tone={engine.state === "ready" ? "verified" : engine.state === "checking" ? "pending" : "danger"}>
      {t.engine[engine.state]}
    </StatusDot>
  );
}

export function Empty({ icon, title, body, children }: {
  icon: ReactNode;
  title: string;
  body: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-xl border border-dashed border-border px-6 py-8 text-center">
      <span className="mb-2 grid size-8 place-items-center rounded-lg bg-tile text-muted-foreground">
        {icon}
      </span>
      <h3 className="m-0 text-sm font-medium">{title}</h3>
      <p className="m-0 max-w-[48ch] text-sm text-muted-foreground">{body}</p>
      {children && <div className="mt-3 flex gap-2">{children}</div>}
    </div>
  );
}

export function Panel({ id, title, description, aside, hint, action, danger = false, children }: {
  id?: string;
  title: string;
  description?: ReactNode;
  aside?: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
  danger?: boolean;
  children?: ReactNode;
}) {
  return (
    <Frame id={id} className={cn(danger && "border-danger/40")}>
      <div className="flex flex-col gap-4 p-6">
        <div className="flex items-start justify-between gap-6">
          <div className="flex max-w-[72ch] flex-col gap-2">
            <h2 className="text-base font-semibold">{title}</h2>
            {description && <p className="text-sm text-muted-foreground">{description}</p>}
          </div>
          {aside}
        </div>
        {children}
      </div>
      {(hint || action) && (
        <div className="box-border flex min-h-14 items-center justify-between gap-4 border-t border-border bg-surface px-6 py-3">
          <span className="text-sm text-muted-foreground">{hint}</span>
          {action}
        </div>
      )}
    </Frame>
  );
}

export function CenteredCard({ title, body, children }: { title: string; body?: ReactNode; children: ReactNode }) {
  return (
    <div data-drag-region className="box-border grid min-h-screen place-items-center bg-surface p-6">
      <Card className="w-full max-w-sm items-center gap-8 px-6 py-8 text-center shadow-none">
        <RelayMark size={40} />
        <div className="flex flex-col gap-2">
          <h1 className="heading-2">{title}</h1>
          {body && <p className="text-sm text-muted-foreground">{body}</p>}
        </div>
        {children}
      </Card>
    </div>
  );
}

export function ConfirmDialog({ title, body, action, ready = true, error, destructive = true, onConfirm, onClose, children }: {
  title: string;
  body: ReactNode;
  action: string;
  ready?: boolean;
  error?: string;
  destructive?: boolean;
  onConfirm: () => Promise<void>;
  onClose: () => void;
  children?: ReactNode;
}) {
  const { t } = usePreferences();
  const [busy, setBusy] = useState(false);
  async function confirm(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent showCloseButton={false}>
        <form className="grid gap-4" onSubmit={(event) => void confirm(event)}>
          <DialogHeader>
            <DialogTitle className="heading-3">{title}</DialogTitle>
            <DialogDescription>{body}</DialogDescription>
          </DialogHeader>
          {children}
          {error && <p className="text-sm text-danger">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>{t.form.cancel}</Button>
            <Button type="submit" variant={destructive ? "destructive" : "default"} disabled={busy || !ready}>{action}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
