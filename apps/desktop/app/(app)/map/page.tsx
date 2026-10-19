"use client";

import "./flow.css";
import { Button } from "@relay/ui/components/button";
import { Input } from "@relay/ui/components/input";
import { Skeleton } from "@relay/ui/components/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@relay/ui/components/tabs";
import { cn } from "@relay/ui/lib/utils";
import { Graph, layout } from "@dagrejs/dagre";
import {
  Background, BackgroundVariant, Controls, type Edge, type FitViewOptions, Handle, MiniMap, type Node, type NodeProps, Position,
  ReactFlow, ReactFlowProvider, useReactFlow,
} from "@xyflow/react";
import { KeyRound, Link2, Search, Table2, Unplug, Waypoints } from "lucide-react";
import Link from "next/link";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { canEdit, useTeam } from "../../account";
import { known, schema, type Table, useConnections } from "../../connections";
import { errorMessage } from "../../engine";
import { usePreferences } from "../../preferences";
import { Empty, KindLogo, SkeletonRows } from "../../components/ui";
import { Page } from "../../shell";

const CARD = { width: 264, header: 44, row: 30, shown: 12 };

const FIT: FitViewOptions = { padding: { top: "64px", right: "32px", bottom: "32px", left: "296px" } };

type Loaded = { state: "loading" } | { state: "ready"; tables: Table[] } | { state: "failed"; message: string };

type TableData = { table: Table; selected: boolean; dimmed: boolean };

function height(table: Table) {
  const rows = Math.min(table.columns.length, CARD.shown) + (table.columns.length > CARD.shown ? 1 : 0);
  return CARD.header + rows * CARD.row + 8;
}

const TableCard = memo(function TableCard({ data }: NodeProps<Node<TableData>>) {
  const { t } = usePreferences();
  const { table, selected, dimmed } = data;
  const shown = table.columns.slice(0, CARD.shown);
  return (
    <div className={cn("box-border w-66 overflow-hidden rounded-[10px] border border-border bg-background",
      "transition-[opacity,border-color,box-shadow] duration-(--duration-fast) hover:border-border-strong motion-reduce:transition-none",
      selected && "border-action shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_22%,transparent)] hover:border-action",
      dimmed && "opacity-35")}>
      <header className={cn("box-border flex h-11 items-center gap-2 border-b border-border bg-surface px-3 text-muted-foreground",
        selected && "bg-[color-mix(in_srgb,var(--accent)_8%,var(--surface))] text-action")}>
        <Table2 size={16} />
        <span className="flex-1 truncate text-sm font-medium text-foreground">{table.name}</span>
        <span className="rounded-full bg-muted px-1.5 text-xs leading-5 text-muted-foreground tabular-nums">
          {table.rows.toLocaleString(t.locale)}
        </span>
      </header>
      <ul className="m-0 list-none py-1 pl-0">
        {shown.map((c) => (
          <li key={c.name}
            className="relative grid h-7.5 grid-cols-[16px_minmax(0,1fr)_auto] items-center gap-2 px-3 text-[13px] hover:bg-surface">
            <Handle type="target" position={Position.Left} id={`${c.name}-in`} className={HANDLE} />
            <span className={cn("inline-grid place-items-center", c.key === "primary" ? "text-status-pending" : "text-action")}>
              {c.key === "primary" ? <KeyRound size={13} /> : c.references ? <Link2 size={13} /> : null}
            </span>
            <span className="truncate text-foreground">{c.name}</span>
            <span className="max-w-27.5 truncate text-xs text-muted-foreground">{c.type.toLowerCase()}</span>
            <Handle type="source" position={Position.Right} id={`${c.name}-out`} className={HANDLE} />
          </li>
        ))}
        {table.columns.length > CARD.shown && (
          <li className="flex h-7.5 items-center px-3 text-xs text-muted-foreground">
            {t.map.more(table.columns.length - CARD.shown)}
          </li>
        )}
      </ul>
    </div>
  );
});

const nodeTypes = { table: TableCard };

const HANDLE = "size-1.5 min-h-0 min-w-0 border-0 bg-transparent";

const FLOATING = "border border-border bg-background/88 backdrop-blur-md";

const FLOW = cn("bg-transparent [--xy-background-pattern-color:color-mix(in_srgb,var(--ink)_18%,transparent)]",
  "[--xy-edge-stroke:var(--border-strong)] [--xy-edge-stroke-width:1.5]",
  "[--xy-minimap-background-color:var(--background)]",
  "[--xy-minimap-mask-background-color:color-mix(in_srgb,var(--surface)_70%,transparent)]",
  "[--xy-minimap-node-background-color:var(--border)]",
  String.raw`[&_.react-flow\_\_node]:cursor-pointer`,
  String.raw`[&_.react-flow\_\_controls]:overflow-hidden [&_.react-flow\_\_controls]:rounded-xl [&_.react-flow\_\_controls]:border [&_.react-flow\_\_controls]:border-border`,
  String.raw`[&_.react-flow\_\_minimap]:overflow-hidden [&_.react-flow\_\_minimap]:rounded-xl [&_.react-flow\_\_minimap]:border [&_.react-flow\_\_minimap]:border-border`,
  String.raw`[&_.react-flow\_\_controls-button]:grid [&_.react-flow\_\_controls-button]:size-8`,
  String.raw`[&_.react-flow\_\_controls-button]:cursor-pointer [&_.react-flow\_\_controls-button]:place-items-center`,
  String.raw`[&_.react-flow\_\_controls-button]:border-0 [&_.react-flow\_\_controls-button]:border-b`,
  String.raw`[&_.react-flow\_\_controls-button]:border-solid [&_.react-flow\_\_controls-button]:border-border`,
  String.raw`[&_.react-flow\_\_controls-button]:bg-background [&_.react-flow\_\_controls-button]:p-0`,
  String.raw`[&_.react-flow\_\_controls-button]:text-foreground [&_.react-flow\_\_controls-button]:transition-colors`,
  String.raw`[&_.react-flow\_\_controls-button:hover]:bg-muted [&_.react-flow\_\_controls-button:last-child]:border-b-0`,
  String.raw`[&_.react-flow\_\_controls-button_svg]:size-3`);

const SCHEMA = "relative h-[max(520px,calc(100vh-300px))] overflow-hidden rounded-lg border border-border bg-surface";

const EDGE = "[&_path]:transition-[stroke,opacity] [&_path]:duration-(--duration-fast) motion-reduce:[&_path]:transition-none";

function place(tables: Table[], byName: Map<string, Table>) {
  const linked = new Set<string>();
  const graph = new Graph();
  graph.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 120 });
  graph.setDefaultEdgeLabel(() => ({}));
  for (const table of tables) {
    for (const c of table.columns) {
      if (c.references && c.references !== table.name && byName.has(c.references)) {
        linked.add(table.name);
        linked.add(c.references);
      }
    }
  }
  for (const table of tables.filter((x) => linked.has(x.name))) {
    graph.setNode(table.name, { width: CARD.width, height: height(table) });
  }
  for (const table of tables.filter((x) => linked.has(x.name))) {
    for (const c of table.columns) {
      if (c.references && linked.has(c.references) && c.references !== table.name) {
        graph.setEdge(c.references, table.name);
      }
    }
  }
  layout(graph);
  const positions = new Map<string, { x: number; y: number }>();
  let bottom = 0;
  for (const name of graph.nodes()) {
    const node = graph.node(name);
    const table = byName.get(name);
    if (node && table) {
      positions.set(name, { x: node.x - CARD.width / 2, y: node.y - height(table) / 2 });
      bottom = Math.max(bottom, node.y + height(table) / 2);
    }
  }
  const alone = tables.filter((x) => !linked.has(x.name));
  const perRow = Math.max(3, Math.ceil(Math.sqrt(alone.length)));
  let rowTop = linked.size ? bottom + 80 : 0;
  for (let start = 0; start < alone.length; start += perRow) {
    const row = alone.slice(start, start + perRow);
    row.forEach((table, i) => positions.set(table.name, { x: i * (CARD.width + 48), y: rowTop }));
    rowTop += Math.max(...row.map(height)) + 48;
  }
  return positions;
}

type Reference = { child: string; column: string; parent: string; to?: string };

function TableSearch({ tables, selected, onFocus }: {
  tables: Table[];
  selected: string;
  onFocus: (name: string) => void;
}) {
  const { t } = usePreferences();
  const [query, setQuery] = useState("");
  const matches = tables.filter((x) => x.name.toLowerCase().includes(query.toLowerCase()));
  return (
    <aside className={cn("absolute top-3 left-3 z-5 flex max-h-[calc(100%-140px)] w-62 flex-col overflow-hidden rounded-lg",
      FLOATING)}>
      <label className="relative border-b border-border">
        <Search size={16} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" />
        <Input placeholder={t.map.search} value={query} aria-label={t.map.search}
          className="h-10 rounded-none border-0 bg-transparent pl-9 shadow-none focus-visible:ring-0 dark:bg-transparent"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) onFocus(matches[0].name); }} />
      </label>
      <ul className="m-0 list-none overflow-y-auto p-1">
        {matches.length === 0 && <li className="p-3 text-sm text-muted-foreground">{t.map.noMatch}</li>}
        {matches.map((m) => (
          <li key={m.name}>
            <Button type="button" variant="ghost" aria-current={m.name === selected || undefined}
              onClick={() => onFocus(m.name)}
              className="w-full justify-between gap-2 px-3 font-normal aria-[current=true]:bg-border">
              <span className="truncate">{m.name}</span>
              <span className="text-muted-foreground tabular-nums">{m.rows.toLocaleString(t.locale)}</span>
            </Button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function Explorer({ tables }: { tables: Table[] }) {
  const { t } = usePreferences();
  const flow = useReactFlow();
  const [selected, setSelected] = useState("");
  const byName = useMemo(() => new Map(tables.map((x) => [x.name, x])), [tables]);
  const positions = useMemo(() => place(tables, byName), [tables, byName]);
  const links = useMemo<Reference[]>(() => tables.flatMap((child) => child.columns
    .filter((c) => c.references && c.references !== child.name && positions.has(c.references))
    .map((c) => ({ child: child.name, column: c.name, parent: c.references as string, to: c.referencesColumn }))),
  [tables, positions]);
  const neighbours = useMemo(() => {
    const around = new Map<string, string[]>();
    for (const l of links) {
      around.set(l.child, [...(around.get(l.child) ?? []), l.parent]);
      around.set(l.parent, [...(around.get(l.parent) ?? []), l.child]);
    }
    return around;
  }, [links]);

  const nodes = useMemo<Node<TableData>[]>(() => {
    const near = new Set(selected ? [selected, ...(neighbours.get(selected) ?? [])] : []);
    return tables.map((table) => ({
      id: table.name,
      type: "table",
      position: positions.get(table.name) ?? { x: 0, y: 0 },
      width: CARD.width,
      height: height(table),
      data: { table, selected: table.name === selected, dimmed: !!selected && !near.has(table.name) },
    }));
  }, [tables, positions, neighbours, selected]);

  const edges = useMemo<Edge[]>(() => links.map((l) => {
    const lit = l.child === selected || l.parent === selected;
    const parent = byName.get(l.parent);
    const from = l.to && parent?.columns.slice(0, CARD.shown).some((c) => c.name === l.to)
      ? l.to : parent?.columns[0]?.name;
    return {
      id: `${l.child}.${l.column}`,
      source: l.parent,
      sourceHandle: `${from}-out`,
      target: l.child,
      targetHandle: `${l.column}-in`,
      type: "smoothstep",
      animated: lit,
      className: cn(EDGE, lit ? "[&_path]:stroke-action [&_path]:stroke-2" : selected && "opacity-25"),
    };
  }), [links, byName, selected]);

  const focus = useCallback((name: string) => {
    setSelected(name);
    void flow.fitView({
      ...FIT, nodes: [{ id: name }, ...(neighbours.get(name) ?? []).map((id) => ({ id }))], duration: 400, maxZoom: 1.1,
    });
  }, [flow, neighbours]);

  const rows = useMemo(() => tables.reduce((sum, x) => sum + x.rows, 0), [tables]);

  return (
    <div className={SCHEMA}>
      <ReactFlow className={FLOW} nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={FIT} minZoom={0.1} maxZoom={1.6}
        nodesDraggable={false} nodesConnectable={false} onlyRenderVisibleElements proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => setSelected(node.id === selected ? "" : node.id)}
        onPaneClick={() => setSelected("")}>
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} />
        <Controls showInteractive={false} position="bottom-left" />
        <MiniMap pannable zoomable position="bottom-right" nodeBorderRadius={6}
          nodeColor={(node) => (node.id === selected ? "var(--accent)" : "var(--border-strong)")}
          maskColor="color-mix(in srgb, var(--surface) 60%, transparent)" />
      </ReactFlow>
      <TableSearch tables={tables} selected={selected} onFocus={focus} />
      <div className="caption absolute top-3 right-3 z-5 flex gap-1 text-muted-foreground">
        {[t.map.tables(tables.length), t.map.rows(rows), t.map.links(links.length)].map((label) => (
          <span key={label} className={cn("rounded-full px-2.5 py-1", FLOATING)}>{label}</span>
        ))}
      </div>
    </div>
  );
}

export default function MapPage() {
  const { t } = usePreferences();
  const { connections } = useConnections();
  const [current, setCurrent] = useState(() => known()?.[0]?.id ?? "");
  const [loaded, setLoaded] = useState<Record<string, Loaded>>({});
  const editor = canEdit(useTeam());

  useEffect(() => {
    if (connections) {
      setCurrent((now) => (connections.some((c) => c.id === now) ? now : connections[0]?.id ?? ""));
    }
  }, [connections]);

  useEffect(() => {
    const connection = connections?.find((c) => c.id === current);
    if (!connection || loaded[current]) {
      return;
    }
    setLoaded((all) => ({ ...all, [current]: { state: "loading" } }));
    schema(connection)
      .then((tables) => setLoaded((all) => ({ ...all, [current]: { state: "ready", tables } })))
      .catch((failure: unknown) => setLoaded((all) => ({
        ...all,
        [current]: { state: "failed", message: errorMessage(failure) },
      })));
  }, [current, loaded, connections]);

  const status = loaded[current];

  return (
    <Page title={t.map.title}>
      {connections === null ? (
        <SkeletonRows cells={[40, 10]} />
      ) : connections.length === 0 ? (
        <Empty icon={<Waypoints size={16} />} title={t.connections.emptyTitle} body={t.map.noConnection}>
          {editor && (
            <Button asChild size="sm">
              <Link href="/connections/new/" className="no-underline">{t.connections.add}</Link>
            </Button>
          )}
        </Empty>
      ) : (
        <div className="flex flex-col gap-4">
          <Tabs value={current} onValueChange={setCurrent}>
            <TabsList className="h-auto max-w-full flex-wrap justify-start">
              {connections.map((c) => (
                <TabsTrigger key={c.id} value={c.id} title={c.name} className="h-8 max-w-60 flex-none gap-2 px-3">
                  <KindLogo kind={c.kind} size={16} />
                  <span className="min-w-0 truncate">{c.name}</span>
                  <span className={cn("shrink-0 font-normal text-muted-foreground", c.environment === "Production" && "text-pending")}>
                    · {t.environments[c.environment] ?? c.environment}
                  </span>
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          {status?.state === "failed" ? (
            <Empty icon={<Unplug size={16} />} title={t.map.failed} body={<span className="text-danger">{status.message}</span>}>
              {editor && (
                <Button asChild variant="outline" size="sm">
                  <Link href={`/connections/new/#${current}`} className="no-underline">{t.connections.edit}</Link>
                </Button>
              )}
              <Button type="button" variant="ghost" size="sm"
                onClick={() => setLoaded((all) => {
                  const { [current]: _, ...rest } = all;
                  return rest;
                })}>
                {t.map.retry}
              </Button>
            </Empty>
          ) : status?.state !== "ready" ? (
            <div className={cn(SCHEMA, "grid p-4")}><Skeleton className="h-full" /></div>
          ) : status.tables.length === 0 ? (
            <Empty icon={<Table2 size={16} />} title={t.map.emptyTitle} body={t.map.empty} />
          ) : (
            <ReactFlowProvider key={current}>
              <Explorer tables={status.tables} />
            </ReactFlowProvider>
          )}
        </div>
      )}
    </Page>
  );
}
