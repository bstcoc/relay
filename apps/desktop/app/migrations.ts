import { useEffect, useState } from "react";
import { supabase } from "./account";
import { ask, call, errorMessage } from "./engine";
import type { Connection } from "./connections";

export type Entry = {
  source?: string | string[];
  target?: string | string[];
  type?: string;
  exclude?: boolean;
  target_only?: boolean;
  anonymize?: Mask;
  reason?: string;
  [rest: string]: unknown;
};

export type Mapping = {
  version: 1;
  entity: string;
  source: { table: string };
  target: { table: string };
  match_key: string[];
  columns: Entry[];
  [rest: string]: unknown;
};

export type Match = { source: string; target: string; score: number; reason: string };

export type Proposal = {
  source: string;
  target: string;
  create: boolean;
  score: number;
  columns: Match[];
  unmatched_source: string[];
  unmatched_target: string[];
  mapping: Mapping;
  personal: Record<string, Mask>;
  target_columns: Record<string, string | null>;
};

export const MASKS = [
  "pseudonym", "email", "phone", "first_name", "last_name", "full_name", "address", "city",
  "postal_code", "birth_date", "iban", "ssn", "blank",
] as const;

export type Mask = (typeof MASKS)[number];

const MASKS_BY_TYPE: Record<string, readonly Mask[]> = {
  string: MASKS,
  integer: ["pseudonym", "phone", "postal_code", "ssn", "blank"],
  date: ["birth_date", "blank"],
  datetime: ["birth_date", "blank"],
};

const UNIQUE: readonly Mask[] = ["pseudonym", "email", "phone", "postal_code", "iban", "ssn"];

export function fits(mask: Mask, type: string | undefined): Mask | null {
  const allowed = MASKS_BY_TYPE[type ?? "string"] ?? ["blank"];
  return allowed.includes(mask) ? mask : allowed[0] ?? null;
}

export type Review = { off: string[]; masks: Record<string, Mask>; targets: Record<string, string> };

export function defaultMasks(proposal: Proposal): Record<string, Mask> {
  const key = new Set(proposal.mapping.match_key);
  return Object.fromEntries(Object.entries(proposal.personal).flatMap(([column, mask]) => {
    const entry = proposal.mapping.columns.find((e) => e.source === column);
    if (typeof entry?.target !== "string" || !key.has(entry.target) || UNIQUE.includes(mask)) {
      return [[column, mask]];
    }
    return fits("pseudonym", entry.type) === "pseudonym" ? [[column, "pseudonym"]] : [];
  }));
}

function sourceOf(entry: Entry) {
  return typeof entry.source === "string" ? entry.source : "";
}

export function reviewed(proposal: Proposal, review: Review, anonymize: boolean): Mapping {
  const plain = proposal.mapping.columns.filter((e) => typeof e.source === "string" && !e.target_only);
  const other = proposal.mapping.columns.filter((e) => e.target_only !== true && typeof e.source !== "string");
  const assigned = new Map<string, string>();
  for (const entry of plain) {
    if (!entry.exclude && typeof entry.target === "string") {
      assigned.set(sourceOf(entry), entry.target);
    }
  }
  for (const [source, target] of Object.entries(review.targets)) {
    for (const [other, taken] of assigned) {
      if (taken === target) {
        assigned.delete(other);
      }
    }
    if (target) {
      assigned.set(source, target);
    } else {
      assigned.delete(source);
    }
  }
  const columns = plain.map((entry): Entry => {
    const source = sourceOf(entry);
    const target = assigned.get(source);
    if (review.off.includes(source) || !target) {
      return { source, exclude: true, reason: entry.exclude ? entry.reason : "excluded in review" };
    }
    const kept = entry.target === target && !entry.exclude;
    const type = kept ? entry.type : proposal.target_columns[target] ?? entry.type;
    const base: Entry = kept ? entry : { source, target, ...(type ? { type } : {}), reason: "matched by hand" };
    const mask = anonymize && review.masks[source] ? fits(review.masks[source], type) : null;
    return mask ? { ...base, anonymize: mask } : base;
  });
  const written = new Set(assigned.values());
  const empty = Object.keys(proposal.target_columns)
    .filter((target) => !written.has(target))
    .map((target): Entry => ({ target, target_only: true, reason: "no source column chosen" }));
  return { ...proposal.mapping, columns: [...columns, ...other, ...empty] };
}

export function restore(proposals: Proposal[], migration: Migration) {
  const before = new Map(migration.mappings.map((m) => [m.entity, m]));
  const review: Record<string, Review> = {};
  for (const proposal of proposals) {
    const mapping = before.get(proposal.source);
    if (!mapping) {
      continue;
    }
    const entries = mapping.columns.filter((e) => typeof e.source === "string");
    review[proposal.source] = {
      off: entries.filter((e) => e.exclude && e.reason === "excluded in review").map(sourceOf),
      masks: {
        ...defaultMasks(proposal),
        ...Object.fromEntries(entries.filter((e) => e.anonymize).map((e) => [sourceOf(e), e.anonymize as Mask])),
      },
      targets: Object.fromEntries(entries.filter((e) => typeof e.target === "string" && e.reason === "matched by hand")
        .map((e) => [sourceOf(e), e.target as string])),
    };
  }
  return {
    skipped: proposals.filter((p) => !before.has(p.source)).map((p) => p.source),
    review,
    filters: migration.subsets.map((s) => ({ table: s.table, limit: s.limit })),
  };
}

export function linked(mappings: Mapping[]): Mapping[] {
  const tables = new Set(mappings.map((m) => m.target.table));
  return mappings.map((m) => {
    const references = m.references as { column: string; table: string; key: string }[] | undefined;
    if (!references) {
      return m;
    }
    const written = new Set(m.columns.filter((c) => !c.exclude && !c.target_only)
      .flatMap((c) => (typeof c.target === "string" ? [c.target] : c.target ?? [])));
    return { ...m, references: references.filter((r) => tables.has(r.table) && written.has(r.column)) };
  });
}

export type Filter = { table: string; where?: string; limit?: number };

export type TablePlan = {
  entity: string;
  table: string;
  rows: number;
  existing_rows: number;
  columns: string[];
  create: string | null;
};

export type Plan = { database: string; tables: TablePlan[]; replace: boolean; blocked: string[] };

export type EntitySummary = {
  run_id: string;
  entity: string;
  verdict: "PASS" | "REVIEW" | "FAIL";
  passed: number;
  review: number;
  fail: number;
  accepted: number;
};

export type Summary = { run_id: string; entities: EntitySummary[]; verdict: EntitySummary["verdict"]; report: string };

export type Finding = {
  entity: string;
  check_family: string;
  match_key_value: string | null;
  column: string | null;
  source_value: string | null;
  target_value: string | null;
  verdict: "PASS" | "REVIEW" | "FAIL";
  rule: string;
  finding_key: string;
};

export type Status = "running" | "verified" | "review" | "failed";

export const TONES: Record<Status, "verified" | "pending" | "danger"> = {
  verified: "verified", review: "pending", failed: "danger", running: "pending",
};

export type Migration = {
  id: string;
  source_name: string;
  target_name: string;
  target_environment: string;
  anonymized: boolean;
  status: Status;
  rows: number | null;
  findings: number | null;
  run_id: string | null;
  source_id: string | null;
  target_id: string | null;
  mappings: Mapping[];
  subsets: { table: string; limit?: number }[];
  tables: { entity: string; table: string; rows: number; passed: number; review: number; fail: number; accepted: number }[];
  created_by: string | null;
  created_at: string;
};

function step<T>(method: string, source: Connection, target: Connection, params: Record<string, unknown>) {
  return ask<T>("migration", { source, target, method, params });
}

export async function propose(source: Connection, target: Connection) {
  return (await step<{ proposals: Proposal[] }>("propose", source, target, {})).proposals;
}

export function plan(source: Connection, target: Connection, mappings: Mapping[], subset: Filter[]) {
  return step<Plan>("plan", source, target, { mappings, subset });
}

export function migrate(source: Connection, target: Connection, mappings: Mapping[], subset: Filter[]) {
  return step<Summary>("migrate", source, target, { mappings, subset });
}

export type FindingsPage = { findings: Finding[]; total: number };

export function findings(runId: string, offset = 0, limit = 200) {
  return call<FindingsPage>("results", { run_id: runId, offset, limit });
}

export function decide(finding: Finding, decision: "accepted" | "rejected", by: string, reason: string) {
  return call("decide", { finding_key: finding.finding_key, decision, by, reason });
}

export function outcome(summary: Summary): Status {
  return summary.verdict === "PASS" ? "verified" : summary.verdict === "REVIEW" ? "review" : "failed";
}

const FIELDS = "id, source_id, target_id, source_name, target_name, target_environment, anonymized, status, rows, findings, run_id, mappings, subsets, tables, created_by, created_at";

const SUMMARY_FIELDS = "id, source_name, target_name, target_environment, anonymized, status, rows, findings, created_at";

export type MigrationSummary = Pick<Migration, "id" | "source_name" | "target_name" | "target_environment" | "anonymized"
  | "status" | "rows" | "findings" | "created_at">;

let cached: { team: string; migrations: MigrationSummary[] } | null = null;

export function known(team: string): MigrationSummary[] | null {
  return cached?.team === team ? cached.migrations : null;
}

export async function list(team: string): Promise<MigrationSummary[]> {
  const { data, error } = await supabase.from("migrations").select(SUMMARY_FIELDS)
    .eq("team_id", team).order("created_at", { ascending: false });
  if (error) {
    throw new Error(error.message);
  }
  cached = { team, migrations: data as MigrationSummary[] };
  return cached.migrations;
}

export function useMigrations(team: string) {
  const [migrations, setMigrations] = useState<MigrationSummary[] | null>(() => known(team));
  const [error, setError] = useState("");
  useEffect(() => {
    if (team) {
      list(team).then(setMigrations).catch((failure: unknown) => {
        setMigrations([]);
        setError(errorMessage(failure));
      });
    }
  }, [team]);
  return { migrations, error };
}

export async function get(id: string): Promise<Migration> {
  const { data, error } = await supabase.from("migrations").select(FIELDS).eq("id", id).single();
  if (error) {
    throw new Error(error.message);
  }
  return data as Migration;
}

function shared(mapping: Mapping) {
  const { source_scope: _scope, business_rules: _rules, ...rest } = mapping;
  return rest;
}

export async function start(team: string, source: Connection, target: Connection, mappings: Mapping[],
  anonymized: boolean, filters: Filter[]): Promise<string> {
  const { data, error } = await supabase.from("migrations").insert({
    team_id: team,
    source_id: source.id,
    target_id: target.id,
    source_name: source.name,
    target_name: target.name,
    target_environment: target.environment,
    mappings: mappings.map(shared),
    anonymized,
    subsets: filters.map(({ table, limit }) => (limit ? { table, limit } : { table })),
  }).select("id").single();
  if (error) {
    throw new Error(error.message);
  }
  return data.id as string;
}

export async function finish(id: string, status: Status, summary: Summary | null, plan: Plan | null) {
  const rows = plan?.tables.reduce((sum, t) => sum + t.rows, 0) ?? null;
  const open = summary?.entities.reduce((sum, e) => sum + e.review + e.fail, 0) ?? null;
  const tables = summary?.entities.map((e) => ({
    entity: e.entity,
    table: plan?.tables.find((t) => t.entity === e.entity)?.table ?? e.entity,
    rows: plan?.tables.find((t) => t.entity === e.entity)?.rows ?? 0,
    passed: e.passed, review: e.review, fail: e.fail, accepted: e.accepted,
  })) ?? [];
  const { error } = await supabase.from("migrations")
    .update({ status, rows, findings: open, tables, run_id: summary?.run_id ?? null }).eq("id", id);
  if (error) {
    throw new Error(error.message);
  }
}
