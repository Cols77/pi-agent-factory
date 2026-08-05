import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import { buildTraceCommand, loadTraceGraph } from "../src/trace-cli.js";

const GRAPH = {
  nodes: [{ id: "T-001", kind: "task", title: "t", path: "tasks/T-001.md", exempt: false, deferred: null }],
  edges: [],
  gaps: [],
  validation: {},
  health: { percent: 50, satisfied: 1, expected: 2, dangling: 0, deferred: 0, classes: [] },
};

describe("buildTraceCommand", () => {
  test("runs the trace module through uv, matching process-control.ts", () => {
    expect(buildTraceCommand(["graph", "--json"])).toEqual({
      bin: "uv",
      args: ["run", "python", "-m", "factory.trace", "graph", "--json"],
    });
  });
});

describe("loadTraceGraph", () => {
  test("parses stdout into a graph", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(GRAPH), stderr: "" });
    const result = loadTraceGraph("/repo");
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.graph.health.percent).toBe(50);
  });

  test("reports a non-zero exit instead of throwing", () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "", stderr: "boom" });
    const result = loadTraceGraph("/repo");
    expect(result).toEqual({ ok: false, error: "factory trace exited 2: boom" });
  });

  test("reports unparsable stdout instead of throwing", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "not json", stderr: "" });
    const result = loadTraceGraph("/repo");
    expect(result.ok).toBe(false);
  });

  test("reports a missing uv binary instead of throwing", () => {
    spawnSync.mockReturnValue({ error: new Error("spawnSync uv ENOENT"), status: null, stdout: "", stderr: "" });
    const result = loadTraceGraph("/repo");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("ENOENT");
  });
});
