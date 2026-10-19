"use client";

import { Badge } from "@relay/ui/components/badge";
import { Button } from "@relay/ui/components/button";
import { cn } from "@relay/ui/lib/utils";
import { Check, Copy } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import { usePreferences } from "../../../preferences";
import { Frame, Panel } from "../../../components/ui";

export const INPUT = "w-full max-w-80";

export const SELECT = "w-48";

export const COPY = "flex h-9 max-w-120 min-w-0 items-center justify-between gap-3 rounded-full border border-input bg-field py-0 pr-1 pl-4 text-sm";

export const FOOTER = "box-border flex min-h-14 items-center justify-end gap-2 border-t border-border bg-surface px-6 py-3 text-sm text-muted-foreground";

export function Soon() {
  const { t } = usePreferences();
  return <Badge variant="outline" className="h-6 font-normal text-muted-foreground">{t.settings.soon}</Badge>;
}

export function Group({ title, description, caption, soon = false, footer, children }: {
  title?: string;
  description?: ReactNode;
  caption?: ReactNode;
  soon?: boolean;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Frame>
      {(title || description || caption) && (
        <div className="flex flex-col gap-1 border-b border-border px-6 py-4">
          {title && <h2 className="flex items-center gap-2 text-base font-semibold">{title}{soon && <Soon />}</h2>}
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
          {caption && <p className="text-sm text-muted-foreground">{caption}</p>}
        </div>
      )}
      <div>{children}</div>
      {footer}
    </Frame>
  );
}

export function Setting({ label, help, soon = false, children }: {
  label: ReactNode;
  help?: ReactNode;
  soon?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="box-border flex min-h-12 items-center justify-between gap-6 border-b border-border px-6 py-3 last:border-b-0">
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex items-center gap-2 text-sm font-medium">{label}{soon && <Soon />}</span>
        {help && <span className="text-sm text-muted-foreground">{help}</span>}
      </div>
      {children && <div className="flex min-w-0 flex-1 items-center justify-end gap-2">{children}</div>}
    </div>
  );
}

export function SaveBar({ status, dirty, valid = true, onCancel, onSave }: {
  status: { saving: boolean; saved: boolean; label: string; error: string };
  dirty: boolean;
  valid?: boolean;
  onCancel: () => void;
  onSave: () => void;
}) {
  const { t } = usePreferences();
  if (!dirty && !status.saved && !status.error) {
    return null;
  }
  return (
    <div className={FOOTER} aria-live="polite">
      <span className={cn("mr-auto", status.error && "text-danger")}>
        {status.error || (dirty ? t.settings.unsaved : t.settings.saved)}
      </span>
      {dirty && (
        <>
          <Button size="sm" variant="outline" disabled={status.saving} onClick={onCancel}>{t.settings.cancel}</Button>
          <Button size="sm" disabled={!valid || status.saving} onClick={onSave}>{status.label}</Button>
        </>
      )}
    </div>
  );
}

export function CopyValue({ value, className }: { value: string; className?: string }) {
  const { t } = usePreferences();
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);
  return (
    <div className={cn(COPY, className)}>
      <span className="truncate">{value}</span>
      <Button type="button" variant="ghost" size="icon-sm" className="text-muted-foreground" aria-label={t.settings.copy}
        title={copied ? t.settings.copied : t.settings.copy}
        onClick={() => void navigator.clipboard.writeText(value).then(() => setCopied(true))}>
        <span className="grid *:col-start-1 *:row-start-1 *:transition-[opacity,scale] *:duration-(--duration-fast) *:ease-out">
          <Copy className={copied ? "opacity-0 motion-safe:scale-80" : "opacity-100"} />
          <Check className={copied ? "opacity-100" : "opacity-0 motion-safe:scale-80"} />
        </span>
      </Button>
    </div>
  );
}

export function useSave() {
  const { t } = usePreferences();
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState("");
  useEffect(() => {
    if (state !== "saved") {
      return;
    }
    const timer = setTimeout(() => setState("idle"), 2000);
    return () => clearTimeout(timer);
  }, [state]);

  async function save(write: () => PromiseLike<{ error: { message: string } | null }>, then: () => Promise<void>) {
    setError("");
    setState("saving");
    const { error: refused } = await write();
    if (refused) {
      setError(refused.message);
      setState("idle");
      return;
    }
    await then();
    setState("saved");
  }

  const label = state === "saving" ? t.settings.saving : state === "saved" ? t.settings.saved : t.settings.save;
  return { save, saving: state === "saving", saved: state === "saved", label, error };
}

export function SignInFirst() {
  const { t } = usePreferences();
  return (
    <Panel title={t.settings.signIn} description={t.settings.signInFirst}
      action={<Button asChild size="sm"><Link href="/login/" className="no-underline">{t.settings.signIn}</Link></Button>} />
  );
}
