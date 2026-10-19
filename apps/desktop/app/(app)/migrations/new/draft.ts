"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTeam } from "../../../account";
import { known, recheck, useConnections } from "../../../connections";
import { errorMessage } from "../../../engine";
import {
  defaultMasks, type Filter, finish, get, linked, type Mapping, migrate, type Migration, outcome, plan, type Plan,
  propose, type Proposal, restore, type Review, reviewed, start,
} from "../../../migrations";
import type { Edit } from "./mapping-table";

export function useMigrationDraft() {
  const router = useRouter();
  const team = useTeam()?.id ?? "";
  const { connections, error: loadError } = useConnections();
  const [sourceId, setSourceId] = useState(() => known()?.[0]?.id ?? "");
  const [targetId, setTargetId] = useState(() => known()?.[1]?.id ?? "");
  const [anonymize, setAnonymize] = useState(true);
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [review, setReview] = useState<Record<string, Review>>({});
  const [openTables, setOpenTables] = useState<string[]>([]);
  const [filters, setFilters] = useState<Filter[]>([]);
  const [replay, setReplay] = useState<Migration | null>(null);
  const [dry, setDry] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    const id = /replay=([\w-]+)/.exec(window.location.hash)?.[1];
    if (id) {
      get(id).then((before) => {
        setReplay(before);
        if (before.source_id && before.target_id) {
          setSourceId(before.source_id);
          setTargetId(before.target_id);
        }
      }).catch((failure: unknown) => setError(errorMessage(failure)));
    }
  }, []);

  useEffect(() => {
    if (connections) {
      setSourceId((now) => (connections.some((c) => c.id === now) ? now : connections[0]?.id ?? ""));
      setTargetId((now) => (connections.some((c) => c.id === now) ? now : connections[1]?.id ?? ""));
    }
  }, [connections]);

  useEffect(() => {
    if (loadError) {
      setError(loadError);
    }
  }, [loadError]);

  const source = connections?.find((c) => c.id === sourceId);
  const target = connections?.find((c) => c.id === targetId);

  useEffect(() => {
    if (!source || !target) {
      return;
    }
    let current = true;
    setProposals(null);
    setDry(null);
    setError("");
    propose(source, target).then((found) => {
      if (!current) {
        return;
      }
      const fresh = Object.fromEntries(found.map((p) => [p.source, { off: [], masks: defaultMasks(p), targets: {} }]));
      const same = replay && replay.source_id === source.id && replay.target_id === target.id;
      const restored = same ? restore(found, replay) : null;
      setProposals(found);
      setSkipped(restored?.skipped ?? []);
      setReview({ ...fresh, ...restored?.review });
      setOpenTables(found.filter((p) => p.columns.some((m) => m.score < 0.75)).map((p) => p.source));
      setFilters(restored?.filters ?? []);
    }).catch((failure: unknown) => current && setError(errorMessage(failure)));
    return () => {
      current = false;
    };
  }, [source?.id, target?.id, replay?.id]);

  const outOfProduction = source?.environment === "Production" && target?.environment !== "Production";
  const masking = outOfProduction ? anonymize : false;
  const chosen = useMemo(() => (proposals ?? []).filter((p) => !skipped.includes(p.source)), [proposals, skipped]);
  const shaped = useMemo(() => new Map((proposals ?? []).map((p) => [p.source,
    reviewed(p, review[p.source] ?? { off: [], masks: {}, targets: {} }, masking)])), [proposals, review, masking]);
  const mappings = useMemo(() => linked(chosen.map((p) => shaped.get(p.source) as Mapping)), [chosen, shaped]);
  const kept = filters.filter((f) => f.table && chosen.some((p) => p.source === f.table));

  const edit = useCallback<Edit>((table, change) => {
    setDry(null);
    setReview((all) => ({ ...all, [table]: change(all[table] ?? { off: [], masks: {}, targets: {} }) }));
  }, []);

  function editFilter(index: number, change: Partial<Filter> | null) {
    setDry(null);
    setFilters((all) => change ? all.map((f, i) => (i === index ? { ...f, ...change } : f))
      : all.filter((_, i) => i !== index));
  }
  const masked = mappings.reduce((sum, m) => sum + m.columns.filter((c) => c.anonymize).length, 0);
  const rows = dry?.tables.reduce((sum, table) => sum + table.rows, 0) ?? 0;
  const blocked = dry?.blocked ?? [];
  const locked = busy || running !== null;

  async function dryRun() {
    if (!source || !target) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      setDry(await plan(source, target, mappings, kept));
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  async function launch() {
    if (!source || !target || !dry) {
      return;
    }
    setConfirming(false);
    setRunning(Date.now());
    setError("");
    let id = "";
    try {
      id = await start(team, source, target, mappings, masking, kept);
      const summary = await migrate(source, target, mappings, kept);
      await finish(id, outcome(summary), summary, dry);
      await recheck(target);
      router.push(`/migrations/report/#${id}`);
    } catch (failure) {
      setError(errorMessage(failure));
      setRunning(null);
      if (id) {
        await finish(id, "failed", null, null).catch(() => undefined);
      }
    }
  }

  return {
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
  };
}
