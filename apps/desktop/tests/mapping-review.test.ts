import { expect, test } from "bun:test";
import { defaultMasks, linked, type Proposal, restore, reviewed } from "../app/migrations";

const proposal: Proposal = {
  source: "workers",
  target: "workers",
  create: true,
  score: 1,
  columns: [],
  unmatched_source: [],
  unmatched_target: [],
  mapping: {
    version: 1,
    entity: "workers",
    source: { table: "source.workers" },
    target: { table: "target.workers" },
    match_key: ["full_name"],
    columns: [
      { source: "full_name", target: "full_name", type: "string" },
      { source: "email", target: "email", type: "string" },
      { source: "phone", target: "phone", type: "integer" },
      { source: "site", target: "site", type: "string" },
    ],
  },
  personal: { full_name: "full_name", email: "email", phone: "full_name" },
  target_columns: {},
};

const existing: Proposal = {
  ...proposal,
  create: false,
  target: "employees",
  mapping: {
    ...proposal.mapping,
    target: { table: "target.employees" },
    match_key: ["id"],
    columns: [
      { source: "id", target: "id", type: "integer" },
      { source: "client", target: "client_id", type: "string" },
      { source: "notes", exclude: true, reason: "no target column suggested" },
      { target: "code_client", target_only: true, reason: "no source column suggested" },
    ],
  },
  personal: {},
  target_columns: { id: "integer", client_id: "string", code_client: "string" },
};

const none = { off: [], masks: {}, targets: {} };

test("a key column gets a mask that keeps it unique", () => {
  expect(defaultMasks(proposal)).toEqual({ full_name: "pseudonym", email: "email", phone: "full_name" });
});

test("a mask that does not fit the column type falls back to one that does", () => {
  const columns = reviewed(proposal, { ...none, off: ["site"], masks: defaultMasks(proposal) }, true).columns;
  expect(columns).toEqual([
    { source: "full_name", target: "full_name", type: "string", anonymize: "pseudonym" },
    { source: "email", target: "email", type: "string", anonymize: "email" },
    { source: "phone", target: "phone", type: "integer", anonymize: "pseudonym" },
    { source: "site", exclude: true, reason: "excluded in review" },
  ]);
});

test("switching anonymization off sends every column in clear", () => {
  const columns = reviewed(proposal, { ...none, masks: defaultMasks(proposal) }, false).columns;
  expect(columns.some((c) => c.anonymize)).toBe(false);
});

test("a column matched by hand takes its target, and the target it left stays empty", () => {
  const columns = reviewed(existing, { ...none, targets: { client: "code_client" } }, false).columns;
  expect(columns).toEqual([
    { source: "id", target: "id", type: "integer" },
    { source: "client", target: "code_client", type: "string", reason: "matched by hand" },
    { source: "notes", exclude: true, reason: "no target column suggested" },
    { target: "client_id", target_only: true, reason: "no source column chosen" },
  ]);
});

test("taking a target from another column leaves that column out", () => {
  const columns = reviewed(existing, { ...none, targets: { notes: "client_id" } }, false).columns;
  expect(columns.find((c) => c.source === "client")).toEqual({ source: "client", exclude: true, reason: "excluded in review" });
  expect(columns.find((c) => c.source === "notes")?.target).toBe("client_id");
});

test("a link to a table left out or a column excluded is dropped", () => {
  const child = { ...proposal.mapping, entity: "factures", target: { table: "target.factures" },
    references: [
      { column: "site", table: "target.sites", key: "code" },
      { column: "email", table: "target.workers", key: "email" },
      { column: "phone", table: "target.workers", key: "phone" },
    ] };
  const reviewedChild = { ...child, columns: child.columns.map((c) => (c.source === "phone" ? { source: "phone", exclude: true } : c)) };
  const [, kept] = linked([proposal.mapping, reviewedChild]);
  expect(kept?.references).toEqual([{ column: "email", table: "target.workers", key: "email" }]);
});

test("running a migration again never sends in clear a column masked by default", () => {
  const before = {
    id: "m", source_id: "s", target_id: "t", source_name: "s", target_name: "t", target_environment: "Test",
    anonymized: false, status: "verified" as const, rows: 1, findings: 0, run_id: null, tables: [],
    created_by: null, created_at: "2026-10-05T00:00:00Z", subsets: [],
    mappings: [{ ...proposal.mapping, columns: [{ source: "email", target: "email", type: "string" }] }],
  };
  const { review } = restore([proposal], before);
  expect(review.workers?.masks).toEqual(defaultMasks(proposal));
});
