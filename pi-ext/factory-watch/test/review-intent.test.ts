import { describe, expect, test } from "vitest";
import { walkIntentChain } from "../src/review-intent.js";
import type { TraceEdge, TraceGraph, TraceNode } from "../src/trace-cli.js";

function node(id: string, kind: TraceNode["kind"], title: string): TraceNode {
  return { id, kind, title, path: `${id}.md`, exempt: false, deferred: null };
}

function graphOf(nodes: TraceNode[], edges: TraceEdge[]): TraceGraph {
  return {
    nodes, edges, gaps: [], validation: {},
    health: { percent: 0, satisfied: 0, expected: 0, dangling: 0, deferred: 0, proposed: 0, classes: [] },
  };
}

const FULL = graphOf(
  [
    node("T-001", "task", "A task"),
    node("plan:p.md", "plan", "A plan"),
    node("spec:s.md", "spec", "A spec"),
    node("SR-014", "sr", "A requirement"),
    node("BR-002", "br", "A business requirement"),
  ],
  [
    { src: "T-001", dst: "plan:p.md", kind: "source_plan" },
    { src: "plan:p.md", dst: "spec:s.md", kind: "spec_ref" },
    { src: "T-001", dst: "SR-014", kind: "satisfies" },
    { src: "SR-014", dst: "BR-002", kind: "upstream" },
  ],
);

describe("walkIntentChain", () => {
  test("orders a complete chain from business requirement down to task", () => {
    const { chain, stopsAt } = walkIntentChain(FULL, "T-001");
    expect(chain.map((n) => n.id)).toEqual(["BR-002", "SR-014", "spec:s.md", "plan:p.md", "T-001"]);
    expect(stopsAt).toBeNull();
  });

  test("reports satisfies as the stop when the task links no requirement", () => {
    const graph = graphOf(FULL.nodes, FULL.edges.filter((e) => e.kind !== "satisfies" && e.kind !== "upstream"));
    const { chain, stopsAt } = walkIntentChain(graph, "T-001");
    expect(chain.map((n) => n.id)).toEqual(["spec:s.md", "plan:p.md", "T-001"]);
    expect(stopsAt).toBe("satisfies");
  });

  test("reports source_plan as the stop when the requirement side is complete", () => {
    const graph = graphOf(FULL.nodes, FULL.edges.filter((e) => e.kind !== "source_plan" && e.kind !== "spec_ref"));
    const { chain, stopsAt } = walkIntentChain(graph, "T-001");
    expect(chain.map((n) => n.id)).toEqual(["BR-002", "SR-014", "T-001"]);
    expect(stopsAt).toBe("source_plan");
  });

  test("an edge pointing at a node that does not exist counts as unresolved", () => {
    const graph = graphOf(
      [node("T-001", "task", "A task")],
      [{ src: "T-001", dst: "plan:gone.md", kind: "source_plan" }],
    );
    const { chain, stopsAt } = walkIntentChain(graph, "T-001");
    expect(chain.map((n) => n.id)).toEqual(["T-001"]);
    expect(stopsAt).toBe("satisfies");
  });

  test("an unknown task id yields an empty chain stopping at task", () => {
    expect(walkIntentChain(FULL, "T-999")).toEqual({ chain: [], stopsAt: "task" });
  });

  test("a single-edge hop reports no alternatives", () => {
    const { chain } = walkIntentChain(FULL, "T-001");
    expect(chain.every((n) => n.alternatives === 0)).toBe(true);
  });

  test("a second satisfies edge is counted, not silently dropped", () => {
    const graph = graphOf(
      [...FULL.nodes, node("SR-020", "sr", "Another requirement")],
      [...FULL.edges, { src: "T-001", dst: "SR-020", kind: "satisfies" }],
    );
    const { chain } = walkIntentChain(graph, "T-001");
    const sr = chain.find((n) => n.id === "SR-014");
    expect(sr?.alternatives).toBe(1);
    // The chain still shows one requirement; the count is how the reviewer
    // learns a second one exists.
    expect(chain.filter((n) => n.kind === "sr")).toHaveLength(1);
  });

  test("a second spec_ref edge is counted on the spec it resolved to", () => {
    const graph = graphOf(
      [...FULL.nodes, node("spec:other.md", "spec", "Another spec")],
      [...FULL.edges, { src: "plan:p.md", dst: "spec:other.md", kind: "spec_ref" }],
    );
    const { chain } = walkIntentChain(graph, "T-001");
    expect(chain.find((n) => n.id === "spec:s.md")?.alternatives).toBe(1);
  });
});
