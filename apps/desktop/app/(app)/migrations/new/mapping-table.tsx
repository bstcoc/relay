"use client";

import { Checkbox } from "@relay/ui/components/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@relay/ui/components/table";
import { cn } from "@relay/ui/lib/utils";
import { memo, useMemo } from "react";
import { fits, type Mapping, type Mask, MASKS, type Proposal, type Review } from "../../../migrations";
import { usePreferences } from "../../../preferences";
import { Picker, StatusDot } from "../../../components/ui";

const HEAD = "caption h-10 px-4 font-normal text-muted-foreground";

const CELL = "h-12 px-4";

const ROW = "hover:bg-muted";

export type Edit = (table: string, change: (now: Review) => Review) => void;

export const MappingTable = memo(function MappingTable({ proposal, mapping, anonymize, onEdit }: {
  proposal: Proposal;
  mapping: Mapping;
  anonymize: boolean;
  onEdit: Edit;
}) {
  const { t } = usePreferences();
  const key = new Set(mapping.match_key);
  const targets = Object.keys(proposal.target_columns);
  const original = useMemo(() => new Map(proposal.mapping.columns.filter((e) => typeof e.source === "string")
    .map((e) => [e.source as string, e])), [proposal]);
  const matches = useMemo(() => new Map(proposal.columns.map((m) => [`${m.source}\u0000${m.target}`, m])), [proposal]);
  const table = proposal.source;
  const onTarget = (column: string, next: string) => onEdit(table, (now) => ({
    ...now, off: now.off.filter((c) => c !== column), targets: { ...now.targets, [column]: next },
  }));
  const onToggle = (column: string, migrated: boolean) => onEdit(table, (now) => ({
    ...now, off: migrated ? now.off.filter((c) => c !== column) : [...now.off, column],
  }));
  const onMask = (column: string, mask: Mask | null) => onEdit(table, (now) => {
    const { [column]: _, ...rest } = now.masks;
    return { ...now, masks: mask ? { ...rest, [column]: mask } : rest };
  });
  return (
    <Table>
      <TableHeader className="bg-surface">
        <TableRow className="hover:bg-transparent">
          {proposal.create && <TableHead className={HEAD}>{t.wizard.migrate}</TableHead>}
          <TableHead className={HEAD}>{t.wizard.sourceColumn}</TableHead>
          <TableHead className={HEAD}>{t.wizard.targetColumn}</TableHead>
          <TableHead className={HEAD}>{t.wizard.confidence}</TableHead>
          <TableHead className={HEAD}>{t.wizard.reason}</TableHead>
          {anonymize && <TableHead className={HEAD}>{t.wizard.mask}</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {mapping.columns.map((entry) => {
          const source = typeof entry.source === "string" ? entry.source : "";
          const target = typeof entry.target === "string" ? entry.target : "";
          if (entry.target_only) {
            return (
              <TableRow key={`target-${target}`} className={ROW}>
                {proposal.create && <TableCell className={CELL} />}
                <TableCell className={cn(CELL, "text-muted-foreground")}>{t.wizard.leftEmpty}</TableCell>
                <TableCell className={CELL}>{target}</TableCell>
                <TableCell className={CELL}><StatusDot tone="neutral">{t.wizard.unmatched}</StatusDot></TableCell>
                <TableCell className={CELL} />
                {anonymize && <TableCell className={CELL} />}
              </TableRow>
            );
          }
          if (!source) {
            return null;
          }
          const migrated = !entry.exclude;
          const match = matches.get(`${source}\u0000${target}`);
          const byHand = entry.reason === "matched by hand";
          const isKey = migrated && key.has(target);
          const copyable = !original.get(source)?.exclude;
          return (
            <TableRow key={`source-${source}`} className={ROW}>
              {proposal.create && (
                <TableCell className={CELL}>
                  <Checkbox aria-label={`${t.wizard.migrate} ${source}`} className="translate-y-0 border-border-strong"
                    checked={migrated} disabled={!copyable || isKey}
                    onCheckedChange={(next) => onToggle(source, next === true)} />
                </TableCell>
              )}
              <TableCell className={CELL}>{source}</TableCell>
              <TableCell className={cn(CELL, !migrated && "text-muted-foreground")}>
                <span className="flex items-center gap-1">
                  {proposal.create ? (migrated ? target : t.wizard.notMigrated) : (
                    <Picker size="sm" label={`${t.wizard.targetColumn} ${source}`} value={migrated ? target : ""}
                      disabled={isKey} onChange={(next) => onTarget(source, next)} className="w-auto"
                      options={[{ value: "", label: t.wizard.notMigrated },
                        ...targets.map((name) => ({ value: name, label: name }))]} />
                  )}
                  {isKey && <span className="caption text-muted-foreground"> · {t.wizard.key}</span>}
                </span>
              </TableCell>
              <TableCell className={CELL}>
                {!migrated ? <StatusDot tone="neutral">{t.wizard.unmatched}</StatusDot>
                  : byHand ? <StatusDot tone="verified">{t.wizard.byHand}</StatusDot>
                    : (match?.score ?? 1) >= 0.75 ? <StatusDot tone="verified">{t.wizard.sure}</StatusDot>
                      : <StatusDot tone="pending">{t.wizard.doubtful}</StatusDot>}
              </TableCell>
              <TableCell className={cn(CELL, "min-w-50 py-3 whitespace-normal text-muted-foreground")}>
                {migrated && !byHand ? match?.reason : ""}
              </TableCell>
              {anonymize && (
                <TableCell className={CELL}>
                  {migrated && (
                    <Picker size="sm" label={`${t.wizard.mask} ${source}`} value={entry.anonymize ?? ""} className="w-auto"
                      onChange={(next) => onMask(source, next ? next as Mask : null)}
                      options={[{ value: "", label: t.wizard.noMask },
                        ...MASKS.filter((kind) => fits(kind, entry.type) === kind)
                          .map((kind) => ({ value: kind, label: t.wizard.masks[kind] }))]} />
                  )}
                </TableCell>
              )}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
});
