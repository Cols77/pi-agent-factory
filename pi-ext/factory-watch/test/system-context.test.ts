import { describe, expect, test } from "vitest";
import { buildSystemContext } from "../src/system-context.js";
import type { TraceGraph } from "../src/trace-cli.js";

const GRAPH: TraceGraph = {
  nodes: [
    { id: "T-001", kind: "task", title: "A task", path: "tasks/T-001-a.md", exempt: false, deferred: null },
    { id: "plan:p.md", kind: "plan", title: "A plan", path: "docs/superpowers/plans/p.md", exempt: false, deferred: null },
  ],
  edges: [{ src: "T-001", dst: "plan:p.md", kind: "source_plan" }],
  gaps: [],
  validation: {},
  health: { percent: 0, satisfied: 0, expected: 0, dangling: 0, deferred: 0, proposed: 0, classes: [] },
};

const deps = {
  graph: () => ({ ok: true as const, graph: GRAPH }),
  taskEvidence: () => ({ ok: true as const, value: { runs: [] } }),
  preflight: () => ({ ok: true as const, value: { findings: [] } }),
};

describe("buildSystemContext", () => {
  test("returns the node, its edges, and its neighbours", () => {
    const { context } = buildSystemContext("/repo", "T-001", deps as never);
    expect((context.node as { id: string }).id).toBe("T-001");
    expect(context.edges).toHaveLength(1);
    expect((context.neighbours as { id: string }[]).map((n) => n.id)).toEqual(["plan:p.md"]);
  });

  test("also returns the loaded graph so callers need not reload it", () => {
    const { graph } = buildSystemContext("/repo", "T-001", deps as never);
    expect(graph?.nodes).toHaveLength(2);
  });

  test("reports an unknown source rather than throwing when the graph fails", () => {
    const failing = { ...deps, graph: () => ({ ok: false as const, error: "uv missing" }) };
    const { context, graph } = buildSystemContext("/repo", "T-001", failing as never);
    expect(context.status).toBe("unknown");
    expect(context.source).toBe("trace");
    expect(graph).toBeNull();
  });

  test("reports an unknown source for an id that is not in the graph", () => {
    const { context } = buildSystemContext("/repo", "T-999", deps as never);
    expect(context.status).toBe("unknown");
    expect(String(context.error)).toContain("T-999");
  });
});
