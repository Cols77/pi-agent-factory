import { beforeEach, describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

// The mock is module-level and shared, so "was never called" assertions need a
// clean slate per test rather than the accumulated calls of the whole file.
beforeEach(() => {
  vi.clearAllMocks();
});

import {
  registerTraceTools,
  traceCheckTool,
  traceDeferTool,
  traceExemptTool,
  traceLinkTool,
  traceNextTool,
} from "../src/trace-tools.js";

const CTX = { cwd: "/repo" };

async function run(tool: { execute: Function }, params: unknown) {
  const r = await tool.execute("call-1", params, undefined, undefined, CTX);
  // AgentToolResult.content is a block array; flatten it for assertions.
  return { ...r, content: r.content.map((c: { text: string }) => c.text).join("\n") };
}

const PROPOSAL = {
  gap: { node_id: "T-047", kind: "task_no_sr", detail: "d", disposition: "pending" },
  node_title: "Bug Capture",
  node_excerpt: "excerpt",
  pending_total: 45,
  candidates: [
    { id: "SR-001", title: "Preempt", summary: "shall preempt patrol", shared_terms: [], score: 0 },
  ],
};

const traceArgs = (...sub: string[]) => ["run", "python", "-m", "factory.trace", ...sub];

describe("registerTraceTools", () => {
  test("registers all five tools", () => {
    const names: string[] = [];
    registerTraceTools({ registerTool: (t: unknown) => names.push((t as { name: string }).name) });
    expect(names.sort()).toEqual([
      "trace_check",
      "trace_defer",
      "trace_exempt",
      "trace_link",
      "trace_next",
    ]);
  });
});

describe("trace_next", () => {
  test("returns the proposal with candidate statements", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(PROPOSAL), stderr: "" });
    const result = await run(traceNextTool, {});
    expect(result.content).toContain("shall preempt patrol");
    expect(result.content).toContain("45");
  });

  test("reports when nothing is pending", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify({ gap: null }), stderr: "" });
    expect((await run(traceNextTool, {})).content).toContain("No pending gaps");
  });

  test("surfaces a CLI failure rather than pretending there is nothing to do", async () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "", stderr: "boom" });
    expect((await run(traceNextTool, {})).content).toContain("boom");
  });
});

describe("trace_link", () => {
  test("links a task to a requirement", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "tasks/T-047.md", stderr: "" });
    await run(traceLinkTool, { node_id: "T-047", satisfies: "SR-001" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      traceArgs("link", "T-047", "--satisfies", "SR-001"),
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("links a plan to a spec", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "plans/p1.md", stderr: "" });
    await run(traceLinkTool, { node_id: "plan:p1.md", spec: "s1.md" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      traceArgs("link", "plan:p1.md", "--spec", "s1.md"),
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("links a task to its source plan", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "tasks/T-047.md", stderr: "" });
    await run(traceLinkTool, { node_id: "T-047", source_plan: "p1.md" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      traceArgs("link", "T-047", "--source-plan", "p1.md"),
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("requires exactly one link kind", async () => {
    const none = await run(traceLinkTool, { node_id: "T-047" });
    expect(none.content).toContain("exactly one");
    const both = await run(traceLinkTool, { node_id: "T-047", satisfies: "SR-001", spec: "s.md" });
    expect(both.content).toContain("exactly one");
    expect(spawnSync).not.toHaveBeenCalled();
  });

  test("reports a refusal from the CLI as a failure", async () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "error: no such requirement: SR-999", stderr: "" });
    const result = await run(traceLinkTool, { node_id: "T-047", satisfies: "SR-999" });
    expect(result.content).toContain("FAILED");
  });
});

describe("trace_exempt and trace_defer", () => {
  test("exempt passes the reason through", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "tasks/T-047.md", stderr: "" });
    await run(traceExemptTool, { node_id: "T-047", reason: "tooling task" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      traceArgs("exempt", "T-047", "--reason", "tooling task"),
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("defer passes the reason through", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "tasks/T-047.md", stderr: "" });
    await run(traceDeferTool, { node_id: "T-047", reason: "needs an SR split" });
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      traceArgs("defer", "T-047", "--reason", "needs an SR split"),
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("a blank reason is refused before anything is written", async () => {
    const result = await run(traceDeferTool, { node_id: "T-047", reason: "   " });
    expect(result.content).toContain("reason");
    expect(spawnSync).not.toHaveBeenCalled();
  });
});

describe("trace_check", () => {
  test("reports the gate passing", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "0 pending, 0 deferred, 0 exempt", stderr: "" });
    expect((await run(traceCheckTool, {})).content).toContain("GATE PASSED");
  });

  test("reports the gate failing", async () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "45 pending, 0 deferred, 0 exempt", stderr: "" });
    const result = await run(traceCheckTool, {});
    expect(result.content).toContain("GATE FAILED");
    expect(result.content).toContain("45");
  });
});

describe("tool result shape", () => {
  test("returns a content block array with details, as AgentToolResult requires", async () => {
    // Regression: returning { content: string } typechecked (registerTraceTools
    // took `unknown`) and crashed pi's renderer at result.content.filter().
    spawnSync.mockReturnValue({ status: 0, stdout: "0 pending, 0 deferred, 0 exempt", stderr: "" });
    const raw = await traceCheckTool.execute("id", {}, undefined, undefined, CTX);
    expect(Array.isArray(raw.content)).toBe(true);
    expect(raw.content[0]).toMatchObject({ type: "text" });
    expect(typeof raw.content[0]!.text).toBe("string");
    expect("details" in raw).toBe(true);
  });
});
