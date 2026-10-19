"use client";

import { Badge } from "@relay/ui/components/badge";
import { cn } from "@relay/ui/lib/utils";
import { Lock } from "lucide-react";
import type { ReactNode } from "react";
import { SMALL } from "./classes";
import { useLanguage } from "./i18n";

const FRAME_CARD = "overflow-hidden rounded-xl border border-border bg-background text-sm";

const ROW = "grid min-h-15 items-center gap-4 border-b border-border px-6 py-3 transition-colors duration-150 hover:bg-surface motion-reduce:transition-none max-[760px]:px-4";

export const CSV_MARK = "block bg-current [mask:url(/logos/csv.svg)_center/contain_no-repeat]";

export function EnvironmentPill({ environment, label = environment, className }: { environment: string; label?: string; className?: string }) {
  const production = environment === "Production";
  return (
    <Badge variant={production ? "production" : "secondary"} className={cn("h-6 px-2.5", className)}>
      {production && <Lock strokeWidth={2.25} aria-hidden="true" />}
      {label}
    </Badge>
  );
}

const TONES = {
  verified: "before:bg-status-verified",
  pending: "before:bg-status-pending before:animate-breathe motion-reduce:before:animate-none",
  danger: "text-danger before:bg-status-danger",
  neutral: "",
};

export function Dot({ tone, children }: { tone: keyof typeof TONES; children: ReactNode }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-2 whitespace-nowrap before:size-2 before:flex-none before:rounded-full before:bg-border before:transition-colors before:duration-300 motion-reduce:before:transition-none",
      TONES[tone],
    )}>
      {children}
    </span>
  );
}

type Confidence = "sure" | "doubtful" | "unmatched";

const MATCHES: { source: string; target: string | null; key?: boolean; confidence: Confidence }[] = [
  { source: "CUST_ID", target: "id", key: true, confidence: "sure" },
  { source: "CUST_NAME", target: "name", confidence: "sure" },
  { source: "CUST_BALANCE", target: "balance", confidence: "doubtful" },
  { source: "CUST_EMAIL", target: "email", confidence: "sure" },
  { source: "CUST_FAX", target: null, confidence: "unmatched" },
  { source: "CUST_REG_NO", target: "registration_number", confidence: "sure" },
];

const TONE: Record<Confidence, keyof typeof TONES> = { sure: "verified", doubtful: "pending", unmatched: "neutral" };

const MATCH_COLUMNS = "grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_120px_minmax(0,1.6fr)] max-[760px]:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto] max-[760px]:gap-3 max-[760px]:text-[13px]";

export function Mapping() {
  const { t } = useLanguage();
  const words = t.fragments;
  return (
    <div className={FRAME_CARD} role="table" aria-label={words.label}>
      <div role="row" className={cn("caption grid gap-4 border-b border-border bg-surface px-4 py-2.5 text-ink-muted", MATCH_COLUMNS)}>
        {words.head.map((label, index) => (
          <span key={label} role="columnheader" className={index === 3 ? "max-[760px]:hidden" : undefined}>{label}</span>
        ))}
      </div>
      {MATCHES.map((match, index) => (
        <div key={match.source} role="row" className={cn(ROW, "px-4 max-[760px]:px-4", MATCH_COLUMNS)}>
          <span role="cell" className="[overflow-wrap:anywhere]">{match.source}</span>
          <span role="cell" className={cn("[overflow-wrap:anywhere]", !match.target && "text-ink-muted")}>
            {match.target ?? words.notMigrated}
            {match.key && <span className="caption text-ink-muted"> · {words.key}</span>}
          </span>
          <span role="cell"><Dot tone={TONE[match.confidence]}>{words[match.confidence]}</Dot></span>
          <span role="cell" className={cn(SMALL, "text-ink-muted max-[760px]:hidden")}>{words.why[index]}</span>
        </div>
      ))}
    </div>
  );
}
