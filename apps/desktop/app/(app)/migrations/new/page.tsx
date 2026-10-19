"use client";

import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import { cn } from "@relay/ui/lib/utils";
import { ArrowRight, ChevronRight, CircleCheck, LoaderCircle, Plus, Route, X } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import type { Connection } from "../../../connections";
import type { Mapping } from "../../../migrations";
import { usePreferences } from "../../../preferences";
import { Empty, EnvironmentPill, Field, Frame, KindLogo, Picker, SkeletonRows, StatusDot, Switch } from "../../../components/ui";
import { EditorsOnly, Page } from "../../../shell";
import { Confirm } from "./confirm";
import { useMigrationDraft } from "./draft";
import { MappingTable } from "./mapping-table";
import { TableReview } from "./table-review";

function Section({ title, meta, open, children }: {
  title: string;
  meta?: ReactNode;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="group border-b border-border" open={open}>
      <summary className={cn("flex cursor-pointer list-none items-center gap-2 px-6 py-4 transition-colors hover:bg-muted",
        "[&::-webkit-details-marker]:hidden")}>
        <ChevronRight size={16} className={cn("text-muted-foreground transition-transform group-open:rotate-90",
          "motion-reduce:transition-none")} />
        <span className="text-base font-medium">{title}</span>
        {meta && <span className="ml-auto text-right text-sm text-muted-foreground">{meta}</span>}
      </summary>
      <div className="px-6 pt-3 pb-6">{children}</div>
    </details>
  );
}

function Seconds({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return <span className="text-sm text-muted-foreground tabular-nums">{Math.floor((now - since) / 1000)} s</span>;
}

export default function NewMigration() {
  const { t } = usePreferences();
  return <EditorsOnly title={t.wizard.title}><MigrationWizard /></EditorsOnly>;
}

function MigrationWizard() {
  const { t } = usePreferences();
  const {
    connections,
    sourceId,
    setSourceId,
    targetId,
    setTargetId,
    anonymize,
    setAnonymize,
    proposals,
    skipped,
    setSkipped,
    openTables,
    setOpenTables,
    filters,
    setFilters,
    setDry,
    dry,
    busy,
    running,
    error,
    confirming,
    setConfirming,
    target,
    outOfProduction,
    masking,
    chosen,
    shaped,
    kept,
    edit,
    editFilter,
    masked,
    rows,
    blocked,
    locked,
    dryRun,
    launch,
    team,
  } = useMigrationDraft();

  const option = (c: Connection) => ({
    value: c.id,
    label: (
      <span className="flex min-w-0 items-center gap-2">
        <KindLogo kind={c.kind} size={16} />
        <span className="truncate">{c.name}</span>
        <EnvironmentPill environment={c.environment} />
      </span>
    ),
  });
  const options = (connections ?? []).map(option);

  if (connections && connections.length < 2) {
    return (
      <Page narrow title={t.wizard.title}>
        <Empty icon={<Route size={16} />} title={t.wizard.needTwoTitle} body={t.wizard.needTwo(connections.length)}>
          <Button asChild size="sm">
            <Link href="/connections/new/" className="no-underline">{t.connections.add}</Link>
          </Button>
        </Empty>
      </Page>
    );
  }

  return (
    <Page narrow title={t.wizard.title}>
      <div className="flex flex-col gap-4">
        <Frame className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-end gap-4 p-6">
          <Field label={t.wizard.source}>
            <Picker label={t.wizard.source} value={sourceId} options={options} disabled={!connections || locked}
              onChange={(next) => {
                setSourceId(next);
                if (next === targetId) {
                  setTargetId(connections?.find((c) => c.id !== next)?.id ?? "");
                }
              }} />
          </Field>
          <span className="grid h-9 w-8 place-items-center text-muted-foreground"><ArrowRight size={16} /></span>
          <Field label={t.wizard.target}>
            <Picker label={t.wizard.target} value={targetId} onChange={setTargetId} disabled={!connections || locked}
              options={options.filter((o) => o.value !== sourceId)} />
          </Field>
        </Frame>

        {running !== null && dry ? (
          <Frame>
            <header className="flex items-center justify-between border-b border-border px-6 py-4">
              <StatusDot tone="pending">{t.wizard.writing}</StatusDot>
              <Seconds since={running} />
            </header>
            <ul className="m-0 list-none py-2 pl-0">
              {dry.tables.map((table) => (
                <li key={table.table} className="grid grid-cols-[16px_minmax(0,1fr)_auto] items-center gap-3 px-6 py-2 text-sm">
                  <LoaderCircle size={16} className="animate-spin text-muted-foreground motion-reduce:animate-none" />
                  <span className="truncate" title={table.table}>{table.table}</span>
                  <span className="text-muted-foreground tabular-nums">{t.migrations.rows(table.rows)}</span>
                </li>
              ))}
            </ul>
          </Frame>
        ) : proposals === null ? (
          error ? <p className="text-sm text-danger">{error}</p>
            : <SkeletonRows cells={[40, 10]} />
        ) : (
          <Frame>
            <Section title={t.wizard.tables} open
              meta={t.wizard.reviewed(chosen.length, masked)}>
              <div className="flex flex-col gap-2">
                {proposals.map((proposal) => (
                  <TableReview key={proposal.source} proposal={proposal}
                    included={!skipped.includes(proposal.source)}
                    open={openTables.includes(proposal.source)}
                    onOpen={() => setOpenTables(openTables.includes(proposal.source)
                      ? openTables.filter((s) => s !== proposal.source) : [...openTables, proposal.source])}
                    onInclude={(on) => {
                      setDry(null);
                      setSkipped(on ? skipped.filter((s) => s !== proposal.source) : [...skipped, proposal.source]);
                    }}>
                    <MappingTable proposal={proposal} anonymize={masking}
                      mapping={shaped.get(proposal.source) as Mapping} onEdit={edit} />
                  </TableReview>
                ))}
              </div>
            </Section>
            {outOfProduction && (
              <Section title={t.wizard.anonymize}
                meta={anonymize ? t.wizard.on : <span className="text-danger">{t.wizard.anonymizeOff}</span>}>
                <Switch checked={anonymize} onChange={(on) => { setDry(null); setAnonymize(on); }} label={t.wizard.anonymize} />
              </Section>
            )}
            <Section title={t.wizard.subset} open={filters.length > 0}
              meta={kept.length ? kept.map((f) => f.table).join(", ") : t.wizard.allRows}>
              <div className="flex flex-col gap-3">
                {filters.map((filter, index) => (
                  <div key={index} className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)_120px_32px] items-end gap-3">
                    <Field label={t.wizard.subsetTable}>
                      <Picker label={t.wizard.subsetTable} value={filter.table}
                        options={chosen.map((p) => ({ value: p.source, label: p.source }))}
                        onChange={(table) => editFilter(index, { table })} />
                    </Field>
                    <Field label={t.wizard.subsetWhere}>
                      <Input placeholder="site = '00412'" value={filter.where ?? ""}
                        onChange={(e) => editFilter(index, { where: e.target.value || undefined })} />
                    </Field>
                    <Field label={t.wizard.subsetLimit}>
                      <Input type="number" min={1} value={filter.limit ?? ""}
                        onChange={(e) => editFilter(index, { limit: e.target.value ? Number(e.target.value) : undefined })} />
                    </Field>
                    <Button type="button" variant="outline" size="icon-sm" aria-label={t.wizard.removeFilter}
                      className="mb-0.5 rounded-full shadow-none" onClick={() => editFilter(index, null)}>
                      <X />
                    </Button>
                  </div>
                ))}
                <div>
                  <Button variant="outline" size="sm"
                    onClick={() => { setDry(null); setFilters([...filters, { table: chosen[0]?.source ?? "" }]); }}>
                    <Plus className="size-3.5" />{t.wizard.addFilter}
                  </Button>
                </div>
                {filters.length > 0 && <p className="text-sm text-muted-foreground">{t.wizard.subsetWhereHint}</p>}
              </div>
            </Section>

            <div className="flex flex-col gap-3 bg-surface p-6">
              {dry && (
                <div className="flex items-center gap-2">
                  <CircleCheck size={16} className="text-status-verified" />
                  <span className="text-sm">{t.wizard.dryDone(rows, dry.tables.filter((x) => x.create).length)}</span>
                </div>
              )}
              {blocked.length > 0 && <p className="text-sm text-danger">{t.wizard.blocked(blocked.join(", "))}</p>}
              {error && <p className="text-sm text-danger">{error}</p>}
              {dry ? (
                <Button className="self-end" disabled={busy || blocked.length > 0 || !team}
                  onClick={() => (target?.environment === "Production" ? setConfirming(true) : void launch())}>
                  {t.wizard.start}
                </Button>
              ) : (
                <Button className="self-end" disabled={busy || chosen.length === 0} onClick={() => void dryRun()}>
                  {busy ? <LoaderCircle className="animate-spin motion-reduce:animate-none" /> : null}{t.wizard.runDry}
                </Button>
              )}
            </div>
          </Frame>
        )}
      </div>

      {confirming && target && (
        <Confirm name={target.name} onConfirm={() => void launch()} onClose={() => setConfirming(false)} />
      )}
    </Page>
  );
}
