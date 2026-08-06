import { describe, expect, test } from "vitest";
import {
  buildSystemContextTools,
  registerSystemContextTools,
} from "../src/system-context-tools.js";

const graph = {
  nodes: [
    { id: "T-001", kind: "task", title: "Implement", path: "tasks/T-001.md", exempt: false, deferred: null },
    { id: "SR-001", kind: "sr", title: "Requirement", path: "requirements/SR-001.md", exempt: false, deferred: null },
    { id: "T-OTHER", kind: "task", title: "Other", path: "tasks/T-OTHER.md", exempt: false, deferred: null },
  ],
  edges: [{ src: "T-001", dst: "SR-001", kind: "satisfies" }],
  gaps: [],
  validation: { "SR-001": { state: "passed", stale: false } },
  health: { percent: 100, satisfied: 1, expected: 1, dangling: 0, deferred: 0, classes: [] },
};

function dependencies(overrides: Record<string, unknown> = {}) {
  return {
    graph: () => ({ ok: true as const, graph }),
    taskEvidence: () => ({
      ok: true as const,
      value: {
        runs: [{
          schema_version: 1, run_id: "run-1", task_id: "T-001",
          started_at: "a", ended_at: "b", start_commit: "start", result_commit: "result",
          outcome: "completed" as const,
          implementation: { changed_files: [], patch: { sha256: "e".repeat(64), size: 0, media_type: "x" } },
          validation: [], reviews: [], decisions: [], publication: { state: "local" as const, errors: [] },
        }],
      },
    }),
    preflight: () => ({ ok: true as const, value: { ok: true, issues: [] } }),
    reconcile: () => ({ ok: true as const, value: { items: [] } }),
    ...overrides,
  };
}

async function execute(tool: { execute: Function }, params: unknown) {
  return tool.execute("call-1", params, undefined, undefined, { cwd: "/repo" });
}

function parsed(result: { content: Array<{ text: string }> }) {
  return JSON.parse(result.content[0]!.text);
}

describe("system context tools", () => {
  test("registers four read-only evidence tools", () => {
    const names: string[] = [];
    registerSystemContextTools({ registerTool: (tool) => names.push(tool.name) });
    expect(names).toEqual([
      "system_context",
      "implementation_history",
      "validation_status",
      "evidence_health",
    ]);
  });

  test("system_context returns only the exact node and declared one-hop neighbours", async () => {
    const [tool] = buildSystemContextTools(dependencies() as never);
    const value = parsed(await execute(tool!, { id: "T-001" }));
    expect(value.node.id).toBe("T-001");
    expect(value.neighbours.map((node: { id: string }) => node.id)).toEqual(["SR-001"]);
    expect(value.edges).toEqual([{ src: "T-001", dst: "SR-001", kind: "satisfies" }]);
    expect(value.evidence.runs[0]).toEqual({
      run_id: "run-1", outcome: "completed", start_commit: "start", result_commit: "result",
    });
  });

  test("missing context remains explicitly unknown", async () => {
    const deps = dependencies({ graph: () => ({ ok: false as const, error: "trace unavailable" }) });
    const [tool] = buildSystemContextTools(deps as never);
    const value = parsed(await execute(tool!, { id: "T-404" }));
    expect(value.status).toBe("unknown");
    expect(value.instruction).toContain("Do not infer");
  });

  test("history and health pass through Python-owned values", async () => {
    const tools = buildSystemContextTools(dependencies() as never);
    expect(parsed(await execute(tools[1]!, { task_id: "T-001" })).runs[0].run_id).toBe("run-1");
    expect(parsed(await execute(tools[3]!, { task_id: "T-001" }))).toEqual({ items: [] });
  });

  test("validation_status filters the declared requirement status", async () => {
    const tools = buildSystemContextTools(dependencies() as never);
    const value = parsed(await execute(tools[2]!, { id: "SR-001" }));
    expect(value.node.id).toBe("SR-001");
    expect(value.validation).toEqual({ state: "passed", stale: false });
  });
});
