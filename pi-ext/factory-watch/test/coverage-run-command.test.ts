import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import {
  findLatestStatus,
  formatCoverageStatus,
  parseFeatureIdFromArgs,
  readStatus,
} from "../src/coverage-run-command.js";

describe("parseFeatureIdFromArgs", () => {
  test("parses a bare feature id", () => {
    expect(parseFeatureIdFromArgs("FEAT-NAV-017")).toBe("FEAT-NAV-017");
  });
  test("parses a feat: ref", () => {
    expect(parseFeatureIdFromArgs("feat:FEAT-NAV-017")).toBe("FEAT-NAV-017");
  });
  test("rejects args without a feature id", () => {
    expect(parseFeatureIdFromArgs("--auto")).toBeNull();
  });
});

describe("findLatestStatus / readStatus", () => {
  function repoWithRun(): string {
    const root = mkdtempSync(join(tmpdir(), "coverage-"));
    const runDir = join(root, "coverage-reviews", "FEAT-001-r1");
    mkdirSync(runDir, { recursive: true });
    writeFileSync(
      join(runDir, "status.json"),
      JSON.stringify({
        run_id: "r1",
        feature: "FEAT-001",
        phase: "auditing",
        srs: { "SR-001": { state: "running" } },
      }),
    );
    return root;
  }

  test("finds the newest status file for a feature", () => {
    const root = repoWithRun();
    const path = findLatestStatus(root, "FEAT-001");
    expect(path).not.toBeNull();
    expect(path).toContain("FEAT-001-r1");
  });

  test("returns null when no run dir exists", () => {
    const root = mkdtempSync(join(tmpdir(), "coverage-empty-"));
    expect(findLatestStatus(root, "FEAT-001")).toBeNull();
  });

  test("reads and parses a status record", () => {
    const root = repoWithRun();
    const path = findLatestStatus(root, "FEAT-001");
    const status = readStatus(path!);
    expect(status?.phase).toBe("auditing");
    expect(status?.srs?.["SR-001"]?.state).toBe("running");
  });
});

describe("formatCoverageStatus", () => {
  test("renders phase, per-SR counts and gate", () => {
    const lines = formatCoverageStatus({
      feature: "FEAT-001",
      run_id: "r1",
      phase: "done",
      srs: {
        "SR-001": { state: "done" },
        "SR-002": { state: "failed" },
      },
      gate: { outcome: "degraded", failed: [], warned: ["SR-001"], degraded: ["SR-002"] },
    });
    expect(lines.join("\n")).toContain("phase: done");
    expect(lines.join("\n")).toContain("1 done");
    expect(lines.join("\n")).toContain("gate: degraded");
  });

  test("flags the human-decision phase", () => {
    const lines = formatCoverageStatus({
      feature: "FEAT-001",
      run_id: "r1",
      phase: "gates",
      proposed_requirements: [{ candidate_id: "SR-999" }],
    });
    expect(lines.join("\n")).toContain("human decision needed");
  });

  test("handles a null record", () => {
    expect(formatCoverageStatus(null).join("\n")).toContain("waiting for run");
  });
});
