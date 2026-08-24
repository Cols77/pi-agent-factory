import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import { buildCoherenceStatusCommand, loadCoherenceStatus } from "../src/coherence-status.js";
import type { StatusSnapshot } from "../src/coherence-status.js";

const SNAPSHOT: StatusSnapshot = {
  primary: {
    source: "register_check",
    outcome: "failing_gate",
    summary: "register check failed: 1 requirement(s) invalid",
    produced_by: "coherence.register.cli.cmd_check",
    resolve_cmd: ["coherence register check --project-root /repo"],
    observation_ref: "register:requirements",
  },
  exit_code: 1,
  lines: [
    {
      source: "register_check",
      outcome: "failing_gate",
      summary: "register check failed: 1 requirement(s) invalid",
      produced_by: "coherence.register.cli.cmd_check",
      resolve_cmd: ["coherence register check --project-root /repo"],
      observation_ref: "register:requirements",
    },
    {
      source: "trace_check",
      outcome: "nothing_pending",
      summary: "0 pending, 0 deferred, 0 exempt",
      produced_by: "coherence.trace.cli.cmd_check",
      resolve_cmd: null,
      observation_ref: "trace:graph",
    },
  ],
};

describe("buildCoherenceStatusCommand", () => {
  test("invokes the modern coherence module directly, not a factory.* shim", () => {
    expect(buildCoherenceStatusCommand()).toEqual({
      bin: "uv",
      args: ["run", "python", "-m", "coherence", "status", "--json"],
    });
  });
});

describe("loadCoherenceStatus", () => {
  test("parses the snapshot, exposing primary and its resolve_cmd unmodified", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(SNAPSHOT), stderr: "" });
    const result = loadCoherenceStatus("/repo");
    expect(result).toEqual({ ok: true, value: SNAPSHOT });
    if (result.ok) {
      expect(result.value.primary.resolve_cmd).toEqual([
        "coherence register check --project-root /repo",
      ]);
    }
  });

  test("invokes coherence status --json in the given cwd", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(SNAPSHOT), stderr: "" });
    loadCoherenceStatus("/repo");
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "coherence", "status", "--json"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("preserves lines worst-first, unreordered", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(SNAPSHOT), stderr: "" });
    const result = loadCoherenceStatus("/repo");
    if (result.ok) {
      expect(result.value.lines.map((l) => l.outcome)).toEqual(["failing_gate", "nothing_pending"]);
    }
  });

  test("surfaces a CLI failure as a structured error, not a thrown exception", () => {
    spawnSync.mockReturnValue({ status: 1, stdout: "", stderr: "boom" });
    const result = loadCoherenceStatus("/repo");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("boom");
    }
  });
});
