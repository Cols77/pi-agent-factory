import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import {
  buildSystemCommand,
  loadSystemBriefing,
  loadSystemGuide,
  loadSystemMatrix,
  loadSystemScopes,
  loadSystemTimeline,
} from "../src/system-cli.js";
import type { SystemLabels } from "../src/system-cli.js";

const SCOPE_LIST = {
  scopes: [{ kind: "bundle", ref: "bundle:evidence-lifecycle" }],
  errors: [{ path: "bundles/bad.yaml", bundle_id: "bad", error: "missing label" }],
};

const BRIEF = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  claims: [
    {
      kind: "recorded",
      text: "Evidence lifecycle",
      citations: [{ kind: "bundle", path: "bundles/evidence-lifecycle.yaml", sha256: "a".repeat(64), anchor: null }],
      spans: [],
      freshness: { state: "fresh", reason: null, dependencies: [] },
    },
  ],
  degraded: false,
};

const MATRIX = {
  scope: { kind: "sr", ref: "sr:SR-001" },
  rows: [
    {
      subject: { kind: "sr", ref: "sr:SR-001" },
      status: "passed",
      evidence: ["validation/validation-report.json"],
      freshness: { state: "fresh", reason: null, dependencies: [] },
      summary: "metric=x assert=y value=1",
    },
  ],
};

const GUIDE = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  sections: [
    {
      kind: "synthesized",
      text: 'This guide covers the declared bundle "Evidence lifecycle".',
      citations: [{ kind: "bundle", path: "bundles/evidence-lifecycle.json", sha256: "a".repeat(64), anchor: null }],
      spans: [{ text: "Evidence lifecycle", citation_index: 0 }],
      freshness: { state: "fresh", reason: null, dependencies: [] },
    },
    {
      kind: "recorded",
      text: "- task:T-001",
      citations: [],
      spans: [],
      freshness: { state: "degraded", reason: null, dependencies: [] },
    },
  ],
};

const TIMELINE = {
  scope: { kind: "sr", ref: "sr:SR-001" },
  events: [
    {
      at: null,
      sequence: 1,
      actor: "not-recorded",
      action: "not-recorded",
      subject: { kind: "task", ref: "task:T-001" },
      citation: { kind: "decision", path: "evidence/runs/run-1.json", sha256: "b".repeat(64), anchor: "reviews[0]" },
      freshness: { state: "degraded", reason: "no actor recorded", dependencies: [] },
    },
  ],
  degraded: true,
  degraded_reasons: ["1 event(s) do not have a recorded actor"],
};

describe("buildSystemCommand", () => {
  test("runs the system module through uv, mirroring buildTraceCommand", () => {
    expect(buildSystemCommand(["scope", "--json"])).toEqual({
      bin: "uv",
      args: ["run", "python", "-m", "factory.system", "scope", "--json"],
    });
  });

  test("labels command is built as a factory.system subcommand", () => {
    const cmd = buildSystemCommand(["labels", "--json"]);
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual(["run", "python", "-m", "factory.system", "labels", "--json"]);
  });

  test("label entries expose title, description and scope_href", () => {
    const entry: SystemLabels["labels"][string] = {
      ref: "task:T-060", id: "T-060", kind: "task", title: "Wire the governor",
      description: null, description_source: null, deferral_reason: null,
      status: "done", relations: { satisfies: ["sr:SR-121"] },
      path: "tasks/T-060.md", scope_href: "/system?scope=task%3AT-060",
    };
    expect(entry.title).toBe("Wire the governor");
  });
});

describe("loadSystemScopes", () => {
  test("parses the scope list including bundle load errors", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(SCOPE_LIST), stderr: "" });
    const result = loadSystemScopes("/repo");
    expect(result).toEqual({ ok: true, value: SCOPE_LIST });
  });

  test("renders the legitimate empty state, not an error", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify({ scopes: [], errors: [] }), stderr: "" });
    const result = loadSystemScopes("/repo");
    expect(result).toEqual({ ok: true, value: { scopes: [], errors: [] } });
  });

  test("invokes scope --json", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "{}", stderr: "" });
    loadSystemScopes("/repo");
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.system", "scope", "--json"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });
});

describe("loadSystemBriefing", () => {
  test("parses claims for a resolved scope", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(BRIEF), stderr: "" });
    const result = loadSystemBriefing("/repo", "bundle:evidence-lifecycle");
    expect(result).toEqual({ ok: true, value: BRIEF });
  });

  test("invokes brief --scope <ref> --json", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "{}", stderr: "" });
    loadSystemBriefing("/repo", "bundle:evidence-lifecycle");
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.system", "brief", "--scope", "bundle:evidence-lifecycle", "--json"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("surfaces the structured Python error on a bad scope ref", () => {
    spawnSync.mockReturnValue({
      status: 1,
      stdout: "",
      stderr: JSON.stringify({ error: "invalid scope ref: 'task:T-001' (expected bundle:<id> or sr:<id>)", kind: "ScopeKindError" }),
    });
    const result = loadSystemBriefing("/repo", "task:T-001");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("invalid scope ref");
      expect(result.error).toContain("ScopeKindError");
    }
  });
});

describe("loadSystemMatrix", () => {
  test("parses validation rows", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(MATRIX), stderr: "" });
    const result = loadSystemMatrix("/repo", "sr:SR-001");
    expect(result).toEqual({ ok: true, value: MATRIX });
  });

  test("invokes matrix --scope <ref> --json", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "{}", stderr: "" });
    loadSystemMatrix("/repo", "sr:SR-001");
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.system", "matrix", "--scope", "sr:SR-001", "--json"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });
});

describe("loadSystemTimeline", () => {
  test("parses degraded events without reordering them", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(TIMELINE), stderr: "" });
    const result = loadSystemTimeline("/repo", "sr:SR-001");
    expect(result).toEqual({ ok: true, value: TIMELINE });
  });

  test("invokes timeline --scope <ref> --json", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "{}", stderr: "" });
    loadSystemTimeline("/repo", "sr:SR-001");
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.system", "timeline", "--scope", "sr:SR-001", "--json"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });
});

describe("loadSystemGuide", () => {
  test("parses guide sections, whichever kind Python chose for each", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(GUIDE), stderr: "" });
    const result = loadSystemGuide("/repo", "bundle:evidence-lifecycle");
    expect(result).toEqual({ ok: true, value: GUIDE });
  });

  test("invokes guide --scope <ref> --json (never --export -- that is CLI-only, never invoked from the browser)", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "{}", stderr: "" });
    loadSystemGuide("/repo", "bundle:evidence-lifecycle");
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.system", "guide", "--scope", "bundle:evidence-lifecycle", "--json"],
      expect.objectContaining({ cwd: "/repo" }),
    );
  });

  test("surfaces the structured Python error on a bad scope ref", () => {
    spawnSync.mockReturnValue({
      status: 1,
      stdout: "",
      stderr: JSON.stringify({ error: "invalid scope ref: 'task:T-001' (expected bundle:<id> or sr:<id>)", kind: "ScopeKindError" }),
    });
    const result = loadSystemGuide("/repo", "task:T-001");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("invalid scope ref");
    }
  });
});
