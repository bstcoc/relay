"use client";

import { Badge } from "@relay/ui/components/badge";
import { Button } from "@relay/ui/components/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@relay/ui/components/dialog";
import { Input } from "@relay/ui/components/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@relay/ui/components/table";
import { cn } from "@relay/ui/lib/utils";
import { useEffect, useState } from "react";
import { canEdit, useAccount, useTeam } from "../../account";
import { decide, type Finding, findings, type FindingsPage, type Migration } from "../../migrations";
import { errorMessage } from "../../engine";
import { usePreferences } from "../../preferences";
import { Field, Frame, StatusDot } from "../../components/ui";

type Decision = "accepted" | "rejected";

const HEAD = "caption h-10 px-4 font-normal text-muted-foreground";

const CELL = "h-12 px-4";

function Decide({ finding, decision, onDone, onClose }: {
  finding: Finding;
  decision: Decision;
  onDone: () => void;
  onClose: () => void;
}) {
  const { t } = usePreferences();
  const { account } = useAccount();
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const by = account.state === "signed-in" ? account.email : "";

  async function confirm() {
    try {
      await decide(finding, decision, by, reason.trim());
      onDone();
    } catch (failure) {
      setError(errorMessage(failure));
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent showCloseButton={false} className="gap-4 rounded-lg">
        <DialogHeader>
          <DialogTitle className="heading-3">{decision === "accepted" ? t.report.acceptTitle : t.report.rejectTitle}</DialogTitle>
          <DialogDescription>{finding.entity}.{finding.column ?? finding.check_family}</DialogDescription>
        </DialogHeader>
        <Field label={t.report.reason} hint={t.report.reasonHint}>
          <Input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        {error && <p className="text-sm text-danger">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t.report.cancel}</Button>
          <Button disabled={!reason.trim()} onClick={() => void confirm()}>
            {decision === "accepted" ? t.report.accept : t.report.reject}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ReportView({ migration }: { migration: Migration }) {
  const { t } = usePreferences();
  const [found, setFound] = useState<FindingsPage | null | "elsewhere">(null);
  const [loading, setLoading] = useState(false);
  const [decided, setDecided] = useState<Record<string, Decision>>({});
  const [deciding, setDeciding] = useState<{ finding: Finding; decision: Decision } | null>(null);
  const editor = canEdit(useTeam());

  useEffect(() => {
    if (!migration.run_id) {
      setFound("elsewhere");
      return;
    }
    findings(migration.run_id).then(setFound).catch(() => setFound("elsewhere"));
  }, [migration.run_id]);

  async function more(page: FindingsPage) {
    if (!migration.run_id) {
      return;
    }
    setLoading(true);
    try {
      const next = await findings(migration.run_id, page.findings.length);
      setFound({ findings: [...page.findings, ...next.findings], total: next.total });
    } finally {
      setLoading(false);
    }
  }

  const rows = migration.rows ?? 0;
  const page = found && found !== "elsewhere" ? found : null;
  const list = page?.findings ?? [];
  const open = page ? page.total - Object.keys(decided).length : migration.findings ?? 0;
  const failed = migration.status === "failed" && !migration.run_id;

  return (
    <div className="flex flex-col gap-4">
      <Frame>
        <div className="flex flex-col gap-2 p-6">
          <h2 className="heading-2">{failed ? t.report.failed : open ? t.report.review : t.report.verified}</h2>
          {!failed && <p className="text-sm text-muted-foreground">{t.report.summary(rows, open)}</p>}
        </div>
        {!failed && migration.tables.length > 0 && (
          <Table>
            <TableHeader className="bg-surface">
              <TableRow className="border-t hover:bg-transparent">
                <TableHead className={HEAD}>{t.wizard.table}</TableHead>
                <TableHead className={cn(HEAD, "text-right")}>{t.report.rows}</TableHead>
                <TableHead className={cn(HEAD, "text-right")}>{t.report.checks}</TableHead>
                <TableHead className={HEAD}>{t.migrations.status}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {migration.tables.map((table) => {
                const left = table.review + table.fail - table.accepted;
                return (
                  <TableRow key={table.entity} className="hover:bg-muted">
                    <TableCell className={CELL}>{table.table}</TableCell>
                    <TableCell className={cn(CELL, "text-right tabular-nums")}>{table.rows.toLocaleString(t.locale)}</TableCell>
                    <TableCell className={cn(CELL, "text-right tabular-nums")}>{table.passed.toLocaleString(t.locale)}</TableCell>
                    <TableCell className={CELL}>
                      {left > 0 ? <StatusDot tone="pending">{t.findings.count(left)}</StatusDot>
                        : <StatusDot tone="verified">{t.migrations.verified}</StatusDot>}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Frame>
      {!failed && found !== null && (found === "elsewhere" ? (
        <p className="text-sm text-muted-foreground">{t.report.elsewhere}</p>
      ) : list.length > 0 && (
        <Frame>
          <h3 className="border-b border-border bg-surface px-4 py-3 text-base font-medium">{t.report.findings}</h3>
          {list.map((finding) => {
            const decision = decided[finding.finding_key];
            const scope = [`${finding.entity}.${finding.column ?? finding.check_family}`, finding.match_key_value]
              .filter(Boolean).join(" · ");
            return (
              <div key={finding.finding_key} className={cn("box-border grid min-h-16 grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto_auto]",
                "items-center gap-4 border-b border-border bg-background px-4 py-3 transition-colors last:border-b-0 hover:bg-muted")}>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-sm">{finding.rule}</span>
                  <span className="truncate text-[13px] leading-4 text-muted-foreground">{scope}</span>
                </div>
                <div className="flex min-w-0 items-center gap-2 text-sm tabular-nums">
                  <span className="max-w-[24ch] truncate rounded-md bg-muted px-2 py-0.5"
                    title={finding.source_value ?? undefined}>{finding.source_value ?? "∅"}</span>
                  <span className="text-muted-foreground" aria-label={t.report.to}>→</span>
                  <span className={cn("max-w-[24ch] truncate rounded-md px-2 py-0.5",
                    decision === "accepted" ? "bg-muted" : "bg-danger-soft text-danger")}
                    title={finding.target_value ?? undefined}>{finding.target_value ?? "∅"}</span>
                </div>
                <div className="flex gap-2">
                  {!decision && editor && (
                    <>
                      <Button size="sm" variant="outline"
                        onClick={() => setDeciding({ finding, decision: "accepted" })}>{t.report.accept}</Button>
                      <Button size="sm" variant="ghost"
                        onClick={() => setDeciding({ finding, decision: "rejected" })}>{t.report.reject}</Button>
                    </>
                  )}
                </div>
                <Badge variant={decision === "accepted" ? "verified" : "danger"} className="justify-self-end">
                  {decision === "accepted" ? t.findings.accepted
                    : decision === "rejected" ? t.findings.rejected : t.report.mismatch}
                </Badge>
              </div>
            );
          })}
          {page && list.length < page.total && (
            <div className="border-t border-border px-4 py-3">
              <Button size="sm" variant="outline" disabled={loading} onClick={() => void more(page)}>
                {t.report.more(list.length, page.total)}
              </Button>
            </div>
          )}
        </Frame>
      ))}
      {deciding && (
        <Decide finding={deciding.finding} decision={deciding.decision} onClose={() => setDeciding(null)}
          onDone={() => {
            setDecided({ ...decided, [deciding.finding.finding_key]: deciding.decision });
            setDeciding(null);
          }} />
      )}
    </div>
  );
}
