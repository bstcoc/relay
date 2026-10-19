"use client";

import { Badge } from "@relay/ui/components/badge";
import { cn } from "@relay/ui/lib/utils";
import { ArrowRight, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { type Proposal } from "../../../migrations";
import { usePreferences } from "../../../preferences";
import { Frame, Switch } from "../../../components/ui";

export function TableReview({ proposal, included, open, onOpen, onInclude, children }: {
  proposal: Proposal;
  included: boolean;
  open: boolean;
  onOpen: () => void;
  onInclude: (included: boolean) => void;
  children: ReactNode;
}) {
  const { t } = usePreferences();
  const columns = proposal.mapping.columns.filter((c) => !c.target_only).length;
  return (
    <Frame className={cn(!included && "opacity-60")}>
      <div className="flex items-center justify-between gap-4 py-2 pr-4 pl-2">
        <button type="button" aria-expanded={open && included} disabled={!included} onClick={onOpen}
          className={cn("group flex min-w-0 cursor-pointer items-center gap-2 rounded-lg border-0 bg-transparent p-2 text-sm",
            "text-foreground enabled:hover:bg-muted disabled:cursor-default",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring")}>
          <ChevronRight size={16} className={cn("shrink-0 text-muted-foreground transition-transform group-aria-expanded:rotate-90",
            "motion-reduce:transition-none")} />
          <span className="min-w-0 truncate font-medium" title={proposal.source}>{proposal.source}</span>
          <ArrowRight size={12} className="shrink-0 text-muted-foreground" />
          <span className="min-w-0 truncate font-medium" title={proposal.target}>{proposal.target}</span>
          {proposal.create && <Badge variant="secondary">{t.wizard.newTable}</Badge>}
          <span className="shrink-0 whitespace-nowrap text-muted-foreground tabular-nums">{t.map.columns(columns)}</span>
        </button>
        <Switch checked={included} onChange={onInclude} label={t.wizard.migrate} />
      </div>
      {open && included && <div className="border-t border-border">{children}</div>}
    </Frame>
  );
}
