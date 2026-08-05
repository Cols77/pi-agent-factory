import { describe, expect, test } from "vitest";
import { layoutGraph, neighbourhood } from "../src/graph-layout.js";
import type { TraceEdge, TraceNode } from "../src/trace-cli.js";

function node(id: string, kind: TraceNode["kind"]): TraceNode {
  return { id, kind, title: id, path: `${id}.md`, exempt: false, deferred: null };
}

describe("layoutGraph", () => {
  test("assigns columns by node kind", () => {
    const nodes = [node("SR-001", "sr"), node("T-001", "task"), node("plan:p.md", "plan")];
    const laid = layoutGraph(nodes, []);
    const byId = new Map(laid.nodes.map((n) => [n.id, n]));
    expect(byId.get("SR-001")!.x).toBeLessThan(byId.get("T-001")!.x);
    expect(byId.get("T-001")!.x).toBeLessThan(byId.get("plan:p.md")!.x);
  });

  test("is deterministic regardless of input order", () => {
    const nodes = [node("T-002", "task"), node("T-001", "task"), node("SR-001", "sr")];
    const edges: TraceEdge[] = [{ src: "T-001", dst: "SR-001", kind: "satisfies" }];
    const a = layoutGraph(nodes, edges);
    const b = layoutGraph([...nodes].reverse(), edges);
    expect(a.nodes).toEqual(b.nodes);
  });

  test("nodes are boxes, not bare points", () => {
    const laid = layoutGraph([node("T-001", "task")], []);
    expect(laid.nodes[0]!.w).toBeGreaterThan(0);
    expect(laid.nodes[0]!.h).toBeGreaterThan(0);
  });

  test("rows are spaced by at least the box height so boxes never overlap", () => {
    const laid = layoutGraph([node("T-001", "task"), node("T-002", "task")], []);
    const [a, b] = [...laid.nodes].sort((p, q) => p.y - q.y);
    expect(b!.y - a!.y).toBeGreaterThanOrEqual(a!.h);
  });

  test("endpoints sit on the facing box edges, never inside a label", () => {
    // (x1,y1) is always the SRC endpoint and (x2,y2) the DST endpoint, so the
    // direction survives for arrowheads. Here src is the task, which sits to the
    // RIGHT of the requirement, so the edge leaves the task's left edge.
    const nodes = [node("SR-001", "sr"), node("T-001", "task")];
    const edges: TraceEdge[] = [{ src: "T-001", dst: "SR-001", kind: "satisfies" }];
    const laid = layoutGraph(nodes, edges);
    const t = laid.nodes.find((n) => n.id === "T-001")!;
    const sr = laid.nodes.find((n) => n.id === "SR-001")!;
    const e = laid.edges[0]!;

    expect(e.x1).toBe(t.x);
    expect(e.x2).toBe(sr.x + sr.w);
    expect(e.y1).toBe(t.y + t.h / 2);
    expect(e.y2).toBe(sr.y + sr.h / 2);
    // and the span between them is the clear gutter, not across a box
    expect(e.x1).toBeGreaterThan(e.x2);
  });

  test("edge endpoints are orientation-correct whichever way the edge was declared", () => {
    const nodes = [node("T-001", "task"), node("plan:p.md", "plan")];
    const forward: TraceEdge[] = [{ src: "T-001", dst: "plan:p.md", kind: "source_plan" }];
    const laid = layoutGraph(nodes, forward);
    const t = laid.nodes.find((n) => n.id === "T-001")!;
    const p = laid.nodes.find((n) => n.id === "plan:p.md")!;

    // task is the lower rank here, so the task box is on the left.
    expect(laid.edges[0]!.x1).toBe(t.x + t.w);
    expect(laid.edges[0]!.x2).toBe(p.x);
  });

  test("reports the occupied columns so the page can label them", () => {
    const laid = layoutGraph([node("SR-001", "sr"), node("T-001", "task")], []);
    expect(laid.columns.map((c) => c.kind)).toEqual(["sr", "task"]);
    expect(laid.columns[0]!.x).toBeLessThan(laid.columns[1]!.x);
    expect(laid.columns.every((c) => c.label.length > 0)).toBe(true);
  });

  test("an empty column is not reported", () => {
    const laid = layoutGraph([node("T-001", "task")], []);
    expect(laid.columns.map((c) => c.kind)).toEqual(["task"]);
  });

  test("edges pointing at absent nodes are dropped from the drawing", () => {
    const laid = layoutGraph([node("SR-001", "sr")], [{ src: "SR-001", dst: "BR-002", kind: "upstream" }]);
    expect(laid.edges).toEqual([]);
  });

  test("barycentre ordering pulls a connected node toward its neighbour", () => {
    // T-002 links to SR-002 (row 1); T-001 links to SR-001 (row 0). Ordering the
    // task column by barycentre should put T-001 above T-002, uncrossing them.
    const nodes = [node("SR-001", "sr"), node("SR-002", "sr"), node("T-002", "task"), node("T-001", "task")];
    const edges: TraceEdge[] = [
      { src: "T-002", dst: "SR-002", kind: "satisfies" },
      { src: "T-001", dst: "SR-001", kind: "satisfies" },
    ];
    const laid = layoutGraph(nodes, edges);
    const t1 = laid.nodes.find((n) => n.id === "T-001")!;
    const t2 = laid.nodes.find((n) => n.id === "T-002")!;
    expect(t1.y).toBeLessThan(t2.y);
  });

  test("reports a canvas size covering every node box", () => {
    const laid = layoutGraph([node("SR-001", "sr"), node("SR-002", "sr")], []);
    expect(laid.width).toBeGreaterThanOrEqual(Math.max(...laid.nodes.map((n) => n.x + n.w)));
    expect(laid.height).toBeGreaterThanOrEqual(Math.max(...laid.nodes.map((n) => n.y + n.h)));
  });

  test("an empty graph lays out without error", () => {
    expect(layoutGraph([], [])).toEqual({ nodes: [], edges: [], columns: [], width: 0, height: 0 });
  });
});

describe("neighbourhood", () => {
  const nodes = [node("SR-001", "sr"), node("T-001", "task"), node("plan:p.md", "plan"), node("T-999", "task")];
  const edges: TraceEdge[] = [
    { src: "T-001", dst: "SR-001", kind: "satisfies" },
    { src: "T-001", dst: "plan:p.md", kind: "source_plan" },
  ];

  test("one hop returns the root and its direct neighbours in both directions", () => {
    const sub = neighbourhood(nodes, edges, "T-001", 1);
    expect(sub.nodes.map((n) => n.id).sort()).toEqual(["SR-001", "T-001", "plan:p.md"]);
  });

  test("follows edges backwards too", () => {
    const sub = neighbourhood(nodes, edges, "SR-001", 1);
    expect(sub.nodes.map((n) => n.id).sort()).toEqual(["SR-001", "T-001"]);
  });

  test("an unconnected root returns just itself", () => {
    expect(neighbourhood(nodes, edges, "T-999", 1).nodes.map((n) => n.id)).toEqual(["T-999"]);
  });

  test("an unknown root returns nothing", () => {
    expect(neighbourhood(nodes, edges, "T-404", 1).nodes).toEqual([]);
  });
});
