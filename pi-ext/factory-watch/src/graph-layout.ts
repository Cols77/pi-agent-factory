import type { TraceEdge, TraceNode, TraceNodeKind } from "./trace-cli.js";

export interface LaidOutNode {
  id: string;
  kind: TraceNodeKind;
  title: string;
  /** Box origin (top-left), not a text anchor. */
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LaidOutEdge {
  src: string;
  dst: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface LaidOutColumn {
  kind: TraceNodeKind;
  label: string;
  x: number;
}

export interface Layout {
  nodes: LaidOutNode[];
  edges: LaidOutEdge[];
  columns: LaidOutColumn[];
  width: number;
  height: number;
}

// Rank is the node kind, so layer assignment is free -- only within-rank
// ordering needs a heuristic. Spec section 7.
const RANK: Record<TraceNodeKind, number> = { br: 0, sr: 1, task: 2, plan: 3, spec: 4 };

const COLUMN_LABEL: Record<TraceNodeKind, string> = {
  br: "Business",
  sr: "Requirements",
  task: "Tasks",
  plan: "Plans",
  spec: "Specs",
};

const NODE_WIDTH = 200;
const NODE_HEIGHT = 34;
// Gutter between columns is where edges are drawn, so it must stay clear of boxes.
const COLUMN_WIDTH = NODE_WIDTH + 96;
const ROW_HEIGHT = NODE_HEIGHT + 12;
const HEADER_HEIGHT = 28;
const BARYCENTRE_PASSES = 4;

export function layoutGraph(nodes: TraceNode[], edges: TraceEdge[]): Layout {
  if (nodes.length === 0) return { nodes: [], edges: [], columns: [], width: 0, height: 0 };

  const present = new Set(nodes.map((n) => n.id));
  const drawable = edges.filter((e) => present.has(e.src) && present.has(e.dst));

  const columns = new Map<number, TraceNode[]>();
  for (const node of [...nodes].sort((a, b) => a.id.localeCompare(b.id))) {
    const rank = RANK[node.kind];
    const column = columns.get(rank) ?? [];
    column.push(node);
    columns.set(rank, column);
  }

  const rowOf = new Map<string, number>();
  for (const column of columns.values()) {
    column.forEach((node, i) => rowOf.set(node.id, i));
  }

  const neighboursOf = new Map<string, string[]>();
  for (const edge of drawable) {
    neighboursOf.set(edge.src, [...(neighboursOf.get(edge.src) ?? []), edge.dst]);
    neighboursOf.set(edge.dst, [...(neighboursOf.get(edge.dst) ?? []), edge.src]);
  }

  const ranks = [...columns.keys()].sort((a, b) => a - b);
  for (let pass = 0; pass < BARYCENTRE_PASSES; pass += 1) {
    for (const rank of ranks) {
      const column = columns.get(rank) ?? [];
      const barycentre = new Map<string, number>();
      for (const node of column) {
        const rows = (neighboursOf.get(node.id) ?? [])
          .map((id) => rowOf.get(id))
          .filter((r): r is number => r !== undefined);
        const mean =
          rows.length > 0
            ? rows.reduce((a, b) => a + b, 0) / rows.length
            : (rowOf.get(node.id) ?? 0);
        barycentre.set(node.id, mean);
      }
      // id is the final tiebreak, so the result never depends on input order.
      column.sort(
        (a, b) =>
          (barycentre.get(a.id) ?? 0) - (barycentre.get(b.id) ?? 0) || a.id.localeCompare(b.id),
      );
      column.forEach((node, i) => rowOf.set(node.id, i));
    }
  }

  // Ranks are packed left-to-right over the columns that actually exist, so an
  // empty kind leaves no dead gutter.
  const columnX = new Map<number, number>();
  ranks.forEach((rank, i) => columnX.set(rank, i * COLUMN_WIDTH));

  const laidOut: LaidOutNode[] = [];
  for (const rank of ranks) {
    for (const node of columns.get(rank) ?? []) {
      laidOut.push({
        id: node.id,
        kind: node.kind,
        title: node.title,
        x: columnX.get(rank) ?? 0,
        y: HEADER_HEIGHT + (rowOf.get(node.id) ?? 0) * ROW_HEIGHT,
        w: NODE_WIDTH,
        h: NODE_HEIGHT,
      });
    }
  }

  const positions = new Map(laidOut.map((n) => [n.id, n]));
  // Endpoints sit on the facing box edges, so an edge can never be drawn through
  // the label it connects. Which side is "facing" depends on relative rank, since
  // an edge may be declared in either direction (task->sr runs leftward,
  // task->plan rightward).
  const laidOutEdges: LaidOutEdge[] = drawable.map((edge) => {
    const from = positions.get(edge.src)!;
    const to = positions.get(edge.dst)!;
    const fromIsLeft = from.x <= to.x;
    return {
      src: edge.src,
      dst: edge.dst,
      x1: fromIsLeft ? from.x + from.w : from.x,
      y1: from.y + from.h / 2,
      x2: fromIsLeft ? to.x : to.x + to.w,
      y2: to.y + to.h / 2,
    };
  });

  const laidOutColumns: LaidOutColumn[] = ranks.map((rank) => {
    const kind = (columns.get(rank) ?? [])[0]!.kind;
    return { kind, label: COLUMN_LABEL[kind], x: columnX.get(rank) ?? 0 };
  });

  return {
    nodes: laidOut,
    edges: laidOutEdges,
    columns: laidOutColumns,
    width: Math.max(...laidOut.map((n) => n.x + n.w)),
    height: Math.max(...laidOut.map((n) => n.y + n.h)),
  };
}

export function neighbourhood(
  nodes: TraceNode[],
  edges: TraceEdge[],
  rootId: string,
  hops: number,
): { nodes: TraceNode[]; edges: TraceEdge[] } {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  if (!byId.has(rootId)) return { nodes: [], edges: [] };

  const reached = new Set([rootId]);
  let frontier = [rootId];
  for (let hop = 0; hop < hops; hop += 1) {
    const next: string[] = [];
    for (const edge of edges) {
      if (frontier.includes(edge.src) && byId.has(edge.dst) && !reached.has(edge.dst)) {
        reached.add(edge.dst);
        next.push(edge.dst);
      }
      if (frontier.includes(edge.dst) && byId.has(edge.src) && !reached.has(edge.src)) {
        reached.add(edge.src);
        next.push(edge.src);
      }
    }
    frontier = next;
  }

  return {
    nodes: nodes.filter((n) => reached.has(n.id)),
    edges: edges.filter((e) => reached.has(e.src) && reached.has(e.dst)),
  };
}
