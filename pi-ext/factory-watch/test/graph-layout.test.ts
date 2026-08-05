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

  test("edge endpoints resolve to their node coordinates", () => {
    const nodes = [node("SR-001", "sr"), node("T-001", "task")];
    const edges: TraceEdge[] = [{ src: "T-001", dst: "SR-001", kind: "satisfies" }];
    const laid = layoutGraph(nodes, edges);
    const t = laid.nodes.find((n) => n.id === "T-001")!;
    const sr = laid.nodes.find((n) => n.id === "SR-001")!;
    expect(laid.edges[0]).toEqual({ src: "T-001", dst: "SR-001", x1: t.x, y1: t.y, x2: sr.x, y2: sr.y });
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

  test("reports a canvas size covering every node", () => {
    const laid = layoutGraph([node("SR-001", "sr"), node("SR-002", "sr")], []);
    expect(laid.width).toBeGreaterThan(0);
    expect(laid.height).toBeGreaterThanOrEqual(Math.max(...laid.nodes.map((n) => n.y)));
  });

  test("an empty graph lays out without error", () => {
    expect(layoutGraph([], [])).toEqual({ nodes: [], edges: [], width: 0, height: 0 });
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
