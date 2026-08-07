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
    scopes: () => ({ ok: true as const, value: { scopes: [], errors: [] } }),
    briefing: () => ({
      ok: true as const,
      value: {
        scope: { kind: "bundle" as const, ref: "bundle:evidence-lifecycle" },
        claims: [{
          kind: "recorded" as const,
          text: "Evidence lifecycle",
          citations: [],
          spans: [],
          freshness: { state: "fresh" as const, reason: null, dependencies: [] },
        }],
      },
    }),
    matrix: () => ({
      ok: true as const,
      value: { scope: { kind: "sr" as const, ref: "sr:SR-001" }, rows: [] },
    }),
    timeline: () => ({
      ok: true as const,
      value: {
        scope: { kind: "sr" as const, ref: "sr:SR-001" },
        events: [],
        degraded: false,
        degraded_reasons: [],
      },
    }),
    guide: () => ({
      ok: true as const,
      value: {
        scope: { kind: "bundle" as const, ref: "bundle:evidence-lifecycle" },
        sections: [
          {
            kind: "synthesized" as const,
            text: 'This guide covers the declared bundle "Evidence lifecycle".',
            citations: [],
            spans: [{ text: "Evidence lifecycle", citation_index: 0 }],
            freshness: { state: "fresh" as const, reason: null, dependencies: [] },
          },
        ],
      },
    }),
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
  test("registers the read-only evidence and navigator tools", () => {
    const names: string[] = [];
    registerSystemContextTools({ registerTool: (tool) => names.push(tool.name) });
    expect(names).toEqual([
      "system_context",
      "implementation_history",
      "validation_status",
      "evidence_health",
      "system_scopes",
      "system_briefing",
      "system_matrix",
      "system_timeline",
      "system_guide",
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

  test("system_scopes passes the Python-owned scope list straight through, including the honest empty state", async () => {
    const tools = buildSystemContextTools(dependencies() as never);
    const value = parsed(await execute(tools[4]!, {}));
    expect(value).toEqual({ scopes: [], errors: [] });
  });

  test("system_scopes surfaces a non-empty scope list without filtering it", async () => {
    const deps = dependencies({
      scopes: () => ({
        ok: true as const,
        value: {
          scopes: [{ kind: "bundle", ref: "bundle:evidence-lifecycle" }],
          errors: [{ path: "bundles/bad.yaml", bundle_id: "bad", error: "missing label" }],
        },
      }),
    });
    const tools = buildSystemContextTools(deps as never);
    const value = parsed(await execute(tools[4]!, {}));
    expect(value.scopes).toEqual([{ kind: "bundle", ref: "bundle:evidence-lifecycle" }]);
    expect(value.errors).toHaveLength(1);
  });

  test("system_briefing passes the Python-owned claim set straight through", async () => {
    const tools = buildSystemContextTools(dependencies() as never);
    const value = parsed(await execute(tools[5]!, { scope: "bundle:evidence-lifecycle" }));
    expect(value.claims[0]).toMatchObject({ kind: "recorded", text: "Evidence lifecycle" });
  });

  test("system_briefing on an unresolvable scope remains explicitly unknown", async () => {
    const deps = dependencies({
      briefing: () => ({ ok: false as const, error: "invalid scope ref: 'task:T-001'" }),
    });
    const tools = buildSystemContextTools(deps as never);
    const value = parsed(await execute(tools[5]!, { scope: "task:T-001" }));
    expect(value.status).toBe("unknown");
    expect(value.instruction).toContain("Do not infer");
  });

  test("system_matrix passes the Python-owned validation rows straight through", async () => {
    const tools = buildSystemContextTools(dependencies() as never);
    const value = parsed(await execute(tools[6]!, { scope: "sr:SR-001" }));
    expect(value).toEqual({ scope: { kind: "sr", ref: "sr:SR-001" }, rows: [] });
  });

  test("system_timeline passes the Python-owned degraded flag straight through", async () => {
    const deps = dependencies({
      timeline: () => ({
        ok: true as const,
        value: {
          scope: { kind: "sr", ref: "sr:SR-001" },
          events: [],
          degraded: true,
          degraded_reasons: ["1 run manifest(s) under evidence/runs could not be read"],
        },
      }),
    });
    const tools = buildSystemContextTools(deps as never);
    const value = parsed(await execute(tools[7]!, { scope: "sr:SR-001" }));
    expect(value.degraded).toBe(true);
    expect(value.degraded_reasons).toHaveLength(1);
  });

  test("system_guide passes the Python-owned sections straight through, whichever kind each is", async () => {
    const tools = buildSystemContextTools(dependencies() as never);
    const value = parsed(await execute(tools[8]!, { scope: "bundle:evidence-lifecycle" }));
    expect(value.sections[0]).toMatchObject({
      kind: "synthesized",
      spans: [{ text: "Evidence lifecycle", citation_index: 0 }],
    });
  });

  test("system_guide on an unresolvable scope remains explicitly unknown", async () => {
    const deps = dependencies({
      guide: () => ({ ok: false as const, error: "invalid scope ref: 'task:T-001'" }),
    });
    const tools = buildSystemContextTools(deps as never);
    const value = parsed(await execute(tools[8]!, { scope: "task:T-001" }));
    expect(value.status).toBe("unknown");
    expect(value.instruction).toContain("Do not infer");
  });
});
