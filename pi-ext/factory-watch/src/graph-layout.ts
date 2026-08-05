import type { TraceEdge, TraceNode, TraceNodeKind } from "./trace-cli.js";

export interface LaidOutNode {
  id: string;
  kind: TraceNodeKind;
  title: string;
  x: number;
  y: number;
}

export interface LaidOutEdge {
  src: string;
  dst: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface Layout {
  nodes: LaidOutNode[];
  edges: LaidOutEdge[];
  width: number;
  height: number;
}

// Rank is the node kind, so layer assignment is free -- only within-rank
// ordering needs a heuristic. Spec section 7.
const RANK: Record<TraceNodeKind, number> = { br: 0, sr: 1, task: 2, plan: 3, spec: 4 };

const COLUMN_WIDTH = 260;
const ROW_HEIGHT = 44;
const BARYCENTRE_PASSES = 4;

export function layoutGraph(nodes: TraceNode[], edges: TraceEdge[]): Layout {
  if (nodes.length === 0) return { nodes: [], edges: [], width: 0, height: 0 };

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

  const laidOut: LaidOutNode[] = [];
  for (const rank of ranks) {
    for (const node of columns.get(rank) ?? []) {
      laidOut.push({
        id: node.id,
        kind: node.kind,
        title: node.title,
        x: rank * COLUMN_WIDTH,
        y: (rowOf.get(node.id) ?? 0) * ROW_HEIGHT,
      });
    }
  }

  const positions = new Map(laidOut.map((n) => [n.id, n]));
  const laidOutEdges: LaidOutEdge[] = drawable.map((edge) => {
    const from = positions.get(edge.src)!;
    const to = positions.get(edge.dst)!;
    return { src: edge.src, dst: edge.dst, x1: from.x, y1: from.y, x2: to.x, y2: to.y };
  });

  return {
    nodes: laidOut,
    edges: laidOutEdges,
    width: Math.max(...laidOut.map((n) => n.x)) + COLUMN_WIDTH,
    height: Math.max(...laidOut.map((n) => n.y)) + ROW_HEIGHT,
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
