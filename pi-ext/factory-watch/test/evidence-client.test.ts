import { spawnSync } from "node:child_process";
import { beforeEach, describe, expect, test, vi } from "vitest";

vi.mock("node:child_process", () => ({ spawnSync: vi.fn() }));

import {
  listEvidence,
  loadCurrentRun,
  loadRunEvidence,
  loadTaskEvidence,
  requestRunAction,
  runPreflight,
  runReconcile,
} from "../src/evidence-client.js";

const mockedSpawn = vi.mocked(spawnSync);

beforeEach(() => mockedSpawn.mockReset());

describe("evidence client", () => {
  test("loads task evidence through the deterministic Python CLI", () => {
    mockedSpawn.mockReturnValue({
      status: 0, stdout: JSON.stringify({ runs: [{ run_id: "run-1" }] }), stderr: "",
    } as ReturnType<typeof spawnSync>);

    const result = loadTaskEvidence("/repo", "T-042");

    expect(result.ok).toBe(true);
    expect(mockedSpawn).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.evidence", "task", "T-042", "--repo", "/repo", "--json"],
      { cwd: "/repo", encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 },
    );
  });

  test("loads one run and lists all runs", () => {
    mockedSpawn.mockReturnValue({ status: 0, stdout: "{\"runs\":[]}", stderr: "" } as ReturnType<typeof spawnSync>);
    listEvidence("/repo");
    expect(mockedSpawn.mock.calls[0]![1]).toContain("list");
    loadRunEvidence("/repo", "run-1");
    expect(mockedSpawn.mock.calls[1]![1]).toContain("run-1");
  });

  test("wraps preflight, reconciliation, and run-state without policy duplication", () => {
    mockedSpawn.mockReturnValue({ status: 0, stdout: "{}", stderr: "" } as ReturnType<typeof spawnSync>);
    runPreflight("/repo", "T-042");
    expect(mockedSpawn.mock.calls[0]![1]).toEqual([
      "run", "python", "-m", "factory.preflight", "--task", "T-042", "--repo", "/repo", "--json",
    ]);
    runReconcile("/repo", "T-042");
    expect(mockedSpawn.mock.calls[1]![1]).toContain("reconcile");
    loadCurrentRun("/repo");
    expect(mockedSpawn.mock.calls[2]![1]).toContain("current");
    requestRunAction("/repo", "run-1", "abandon", "superseded");
    expect(mockedSpawn.mock.calls[3]![1]).toEqual([
      "run", "python", "-m", "factory.orchestrator", "run-state", "abandon", "run-1",
      "--reason", "superseded", "--repo", "/repo", "--json",
    ]);
  });

  test("parses documented nonzero report statuses", () => {
    mockedSpawn.mockReturnValue({ status: 2, stdout: '{"ok":false,"issues":[]}', stderr: "" } as ReturnType<typeof spawnSync>);
    expect(runPreflight("/repo", "T-001").ok).toBe(true);
    mockedSpawn.mockReturnValue({ status: 1, stdout: '{"items":[]}', stderr: "" } as ReturnType<typeof spawnSync>);
    expect(runReconcile("/repo").ok).toBe(true);
  });

  test("returns a structured nonzero failure", () => {
    mockedSpawn.mockReturnValue({ status: 2, stdout: "", stderr: "not found" } as ReturnType<typeof spawnSync>);
    expect(loadRunEvidence("/repo", "gone")).toEqual({ ok: false, status: 2, error: "not found" });
  });

  test("reports malformed JSON without throwing", () => {
    mockedSpawn.mockReturnValue({ status: 0, stdout: "not-json", stderr: "" } as ReturnType<typeof spawnSync>);
    const result = loadTaskEvidence("/repo", "T-001");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("could not parse");
  });

  test("reports executable failures", () => {
    mockedSpawn.mockReturnValue({
      status: null, stdout: "", stderr: "", error: new Error("spawn uv ENOENT"),
    } as ReturnType<typeof spawnSync>);
    expect(loadTaskEvidence("/repo", "T-001")).toEqual({
      ok: false, status: -1, error: "spawn uv ENOENT",
    });
  });
});
