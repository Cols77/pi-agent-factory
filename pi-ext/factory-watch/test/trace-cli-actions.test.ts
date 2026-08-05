import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import { loadNextGap, runTrace, runTraceCheck } from "../src/trace-cli.js";

const PROPOSAL = {
  gap: { node_id: "T-001", kind: "task_no_sr", detail: "task declares no satisfies", disposition: "pending" },
  node_title: "Bug Capture",
  node_excerpt: "body",
  pending_total: 45,
  candidates: [
    {
      id: "SR-001",
      title: "Preempt patrol",
      summary: "navigation shall preempt patrol when a shark is detected",
      shared_terms: ["shark"],
      score: 1,
    },
  ],
};

describe("loadNextGap", () => {
  test("parses a proposal including the statement and pending total", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(PROPOSAL), stderr: "" });
    const result = loadNextGap("/repo");
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.proposal?.pending_total).toBe(45);
      expect(result.proposal?.candidates[0]?.summary).toContain("preempt patrol");
    }
  });

  test("returns a null proposal when nothing is pending", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify({ gap: null }), stderr: "" });
    expect(loadNextGap("/repo")).toEqual({ ok: true, proposal: null });
  });

  test("reports a failure instead of throwing", () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "", stderr: "boom" });
    expect(loadNextGap("/repo").ok).toBe(false);
  });
});

describe("runTrace", () => {
  test("reports success", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "tasks/T-001.md", stderr: "" });
    expect(runTrace("/repo", ["link", "T-001", "--satisfies", "SR-001"])).toEqual({
      ok: true, status: 0, stdout: "tasks/T-001.md", stderr: "",
    });
  });

  test("reports a refusal from the CLI", () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "error: no such requirement: SR-999", stderr: "" });
    const result = runTrace("/repo", ["link", "T-001", "--satisfies", "SR-999"]);
    expect(result.ok).toBe(false);
    expect(result.stdout).toContain("no such requirement");
  });

  test("reports a missing binary instead of throwing", () => {
    spawnSync.mockReturnValue({ error: new Error("ENOENT"), status: null, stdout: "", stderr: "" });
    expect(runTrace("/repo", ["check"]).ok).toBe(false);
  });
});

describe("runTraceCheck", () => {
  test("passes when nothing is pending", () => {
    spawnSync.mockReturnValue({
      status: 0, stdout: "traceability health: 80%\n0 pending, 2 deferred, 1 exempt\n", stderr: "",
    });
    expect(runTraceCheck("/repo")).toMatchObject({ ok: true, pending: 0, deferred: 2, exempt: 1 });
  });

  test("fails when gaps are still undiscussed", () => {
    spawnSync.mockReturnValue({
      status: 1, stdout: "traceability health: 10%\n45 pending, 0 deferred, 0 exempt\n", stderr: "",
    });
    const result = runTraceCheck("/repo");
    expect(result.ok).toBe(false);
    expect(result.pending).toBe(45);
  });

  test("the exit code decides, not the parsed text", () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "surprise", stderr: "" });
    const result = runTraceCheck("/repo");
    expect(result.ok).toBe(false);
    expect(result.pending).toBe(0);
  });
});
