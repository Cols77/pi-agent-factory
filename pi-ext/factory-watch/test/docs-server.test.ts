import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import { ensureDocsServer, resolveDocPath, stopDocsServer } from "../src/docs-server.js";

const EMPTY_GRAPH = {
  nodes: [], edges: [], gaps: [], validation: {},
  health: { percent: 100, satisfied: 0, expected: 0, dangling: 0, deferred: 0, classes: [] },
};

function writeReviewArchive(root: string): void {
  const reviews = join(root, "sessions", ".factory-transcripts", "run-1", "reviews");
  mkdirSync(reviews, { recursive: true });
  writeFileSync(
    join(reviews, "review-001.json"),
    JSON.stringify({
      version: 1,
      reviewed_at: "2026-08-07T12:00:00Z",
      task_id: "T-001",
      start_commit: "abc123",
      decision: "reject",
      annotations: [{ file: "source.py", line: 4, side: "new", body: "cover this branch", severity: "must-fix" }],
      reviewed_files: ["source.py"],
      diff: "diff --git a/source.py b/source.py\\n+new\\n",
      diff_error: null,
    }),
  );
}

function writeDurableEvidence(root: string): { digest: string; manifest: Record<string, unknown> } {
  const patch = Buffer.from("diff --git a/source.py b/source.py\n+new\n");
  const digest = createHash("sha256").update(patch).digest("hex");
  const objects = join(root, ".factory", "artifacts", "objects", digest.slice(0, 2));
  mkdirSync(objects, { recursive: true });
  writeFileSync(join(objects, digest), patch);
  const runs = join(root, "evidence", "runs");
  mkdirSync(runs, { recursive: true });
  const manifest = {
    schema_version: 1,
    run_id: "run-1",
    task_id: "T-001",
    outcome: "completed",
    implementation: {
      changed_files: ["source.py"],
      patch: { sha256: digest, size: patch.length, media_type: "text/x-diff" },
    },
    validation: [], reviews: [], decisions: [], publication: { state: "local", errors: [] },
  };
  writeFileSync(join(runs, "run-1.json"), JSON.stringify(manifest));
  return { digest, manifest };
}

function repo(): string {
  const root = mkdtempSync(join(tmpdir(), "docs-server-"));
  mkdirSync(join(root, "tasks"), { recursive: true });
  writeFileSync(
    join(root, "tasks", "T-001.md"),
    "---\nid: T-001\n---\n\n# Task One\n\n- [x] a\n- [ ] b\n",
  );
  writeFileSync(join(root, "secret.txt"), "do not serve me");
  return root;
}

afterEach(() => {
  stopDocsServer();
  vi.clearAllMocks();
});

describe("resolveDocPath", () => {
  test("resolves a path inside the repo", () => {
    // resolve(), not join(): on Windows resolve() prepends the current drive
    // letter, so join() would compare against a differently-rooted string.
    expect(resolveDocPath("/repo", "tasks/T-001.md")).toBe(resolve("/repo", "tasks/T-001.md"));
  });

  test("rejects traversal out of the repo", () => {
    expect(resolveDocPath("/repo", "../../etc/passwd")).toBeNull();
  });

  test("rejects an absolute path outside the repo", () => {
    expect(resolveDocPath("/repo", "/etc/passwd")).toBeNull();
  });

  test("rejects a path that merely shares a prefix with the repo", () => {
    expect(resolveDocPath("/repo", "../repo-evil/x.md")).toBeNull();
  });
});

describe("ensureDocsServer", () => {
  test("serves the shell page on /", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(server.url);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("<!doctype html>");
  });

  test("serves the trace graph on /api/graph", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    const body = await (await fetch(`${server.url}/api/graph`)).json();
    expect(body.health.percent).toBe(100);
  });

  test("reports a trace CLI failure as json instead of crashing", async () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "", stderr: "nope" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/graph`);
    expect(res.status).toBe(503);
    expect((await res.json()).error).toContain("nope");
  });

  test("serves a laid-out graph on /api/layout", async () => {
    const graph = {
      ...EMPTY_GRAPH,
      nodes: [
        { id: "SR-001", kind: "sr", title: "s", path: "requirements/SR-001.md", exempt: false, deferred: null },
        { id: "T-001", kind: "task", title: "t", path: "tasks/T-001.md", exempt: false, deferred: null },
      ],
      edges: [{ src: "T-001", dst: "SR-001", kind: "satisfies" }],
    };
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(graph), stderr: "" });
    const server = await ensureDocsServer(repo());
    const full = await (await fetch(`${server.url}/api/layout`)).json();
    expect(full.nodes).toHaveLength(2);
    expect(full.edges).toHaveLength(1);
    const scoped = await (await fetch(`${server.url}/api/layout?root=SR-001&hops=1`)).json();
    expect(scoped.nodes.map((n: { id: string }) => n.id).sort()).toEqual(["SR-001", "T-001"]);
  });

  test("serves the combined dossier payload on /api/system/dossier via the fallback", async () => {
    const dossier = {
      scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
      brief: { scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, claims: [], degraded: false, degraded_reasons: [] },
      matrix: { scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, rows: [] },
      timeline: { scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, events: [], degraded: false, degraded_reasons: [] },
      guide: null,
      guide_error: null,
      vcycle: null,
      vcycle_error: null,
      validation: null,
      validation_error: null,
    };
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(dossier), stderr: "" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/system/dossier?scope=bundle%3Aevidence-lifecycle`);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(dossier);
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.system", "dossier", "--scope", "bundle:evidence-lifecycle", "--json"],
      expect.objectContaining({ cwd: expect.any(String) }),
    );
  });

  test("reports a dossier failure as 503 with the structured Python error", async () => {
    spawnSync.mockReturnValue({
      status: 1,
      stdout: "",
      stderr: JSON.stringify({ error: "bundle not found: 'missing'", kind: "ScopeNotFoundError" }),
    });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/system/dossier?scope=bundle%3Amissing`);
    expect(res.status).toBe(503);
    expect((await res.json()).error).toContain("bundle not found");
  });

  test("serves durable task evidence from the Python model", async () => {
    const root = repo();
    const { manifest } = writeDurableEvidence(root);
    spawnSync.mockReturnValue({
      status: 0, stdout: JSON.stringify({ runs: [manifest] }), stderr: "",
    });
    const server = await ensureDocsServer(root);
    const body = await (await fetch(`${server.url}/api/evidence/task?task=T-001`)).json();
    expect(body.runs[0]).toMatchObject({ run_id: "run-1", task_id: "T-001" });
  });

  test("serves Python-owned preflight, reconciliation, and run state", async () => {
    spawnSync
      .mockReturnValueOnce({ status: 2, stdout: JSON.stringify({ ok: false, issues: [{ code: "stale" }] }), stderr: "" })
      .mockReturnValueOnce({ status: 1, stdout: JSON.stringify({ items: [{ kind: "missing_blob" }] }), stderr: "" })
      .mockReturnValueOnce({ status: 0, stdout: JSON.stringify({ checkpoint: null, assessment: null }), stderr: "" });
    const server = await ensureDocsServer(repo());
    const preflight = await (await fetch(`${server.url}/api/preflight?task=T-001`)).json();
    expect(preflight.issues[0].code).toBe("stale");
    const reconciliation = await (await fetch(`${server.url}/api/reconcile?task=T-001`)).json();
    expect(reconciliation.items[0].kind).toBe("missing_blob");
    const runState = await (await fetch(`${server.url}/api/run-state`)).json();
    expect(runState.checkpoint).toBeNull();
  });

  test("smokes refreshed run and evidence transitions through the live server APIs", async () => {
    const root = repo();
    const { manifest } = writeDurableEvidence(root);
    const firstRunState = {
      checkpoint: { run_id: "run-1", task_id: "T-001" },
      assessment: { state: "resumable", reasons: ["dead pid"], actions: ["Inspect evidence"] },
    };
    const secondRunState = { checkpoint: null, assessment: null };
    const secondManifest = {
      ...manifest,
      run_id: "run-2",
      ended_at: "2026-08-07T12:05:00Z",
      start_commit: "def456",
      result_commit: "fedcba",
    };
    spawnSync
      .mockReturnValueOnce({ status: 0, stdout: JSON.stringify(firstRunState), stderr: "" })
      .mockReturnValueOnce({ status: 0, stdout: JSON.stringify({ runs: [manifest] }), stderr: "" })
      .mockReturnValueOnce({ status: 0, stdout: JSON.stringify(secondRunState), stderr: "" })
      .mockReturnValueOnce({ status: 0, stdout: JSON.stringify({ runs: [manifest, secondManifest] }), stderr: "" });
    const server = await ensureDocsServer(root);
    const initialRunState = await (await fetch(`${server.url}/api/run-state`)).json();
    expect(initialRunState.checkpoint.run_id).toBe("run-1");
    const initialEvidence = await (await fetch(`${server.url}/api/evidence/task?task=T-001`)).json();
    expect(initialEvidence.runs).toHaveLength(1);
    const refreshedRunState = await (await fetch(`${server.url}/api/run-state`)).json();
    expect(refreshedRunState.checkpoint).toBeNull();
    const refreshedEvidence = await (await fetch(`${server.url}/api/evidence/task?task=T-001`)).json();
    expect(refreshedEvidence.runs).toHaveLength(2);
  });

  test("routes explicit run actions only through the Python client", async () => {
    spawnSync.mockReturnValue({
      status: 0,
      stdout: JSON.stringify({ checkpoint: { run_id: "run-1" }, assessment: null, abandoned: true }),
      stderr: "",
    });
    const server = await ensureDocsServer(repo());
    const response = await fetch(`${server.url}/api/run-state/run-1/abandon`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reason: "superseded" }),
    });
    expect(response.status).toBe(200);
    expect(spawnSync.mock.calls[0]![1]).toContain("abandon");
    expect(spawnSync.mock.calls[0]![1]).toContain("superseded");
  });

  test("rejects malformed run actions before invoking Python", async () => {
    const server = await ensureDocsServer(repo());
    const blank = await fetch(`${server.url}/api/run-state/run-1/abandon`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reason: " " }),
    });
    expect(blank.status).toBe(400);
    const extra = await fetch(`${server.url}/api/run-state/run-1/resume`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ force: true }),
    });
    expect(extra.status).toBe(400);
    expect(spawnSync).not.toHaveBeenCalled();
  });

  test("maps Python recovery conflicts without optimistic success", async () => {
    spawnSync.mockReturnValue({ status: 3, stdout: '{"assessment":{"state":"conflict"}}', stderr: "" });
    const server = await ensureDocsServer(repo());
    const response = await fetch(`${server.url}/api/run-state/run-1/resume`, { method: "POST" });
    expect(response.status).toBe(409);
  });

  test("reports evidence CLI failure without taking down document browsing", async () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "", stderr: "evidence unavailable" });
    const server = await ensureDocsServer(repo());
    const response = await fetch(`${server.url}/api/evidence/task?task=T-001`);
    expect(response.status).toBe(503);
    expect((await response.json()).error).toContain("evidence unavailable");
  });

  test("serves only hash-verified artifacts referenced by a manifest", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const root = repo();
    const { digest } = writeDurableEvidence(root);
    const server = await ensureDocsServer(root);
    const good = await fetch(`${server.url}/api/artifact/${digest}`);
    expect(good.status).toBe(200);
    expect(await good.text()).toContain("+new");
    expect((await fetch(`${server.url}/api/artifact/${"0".repeat(64)}`)).status).toBe(404);
  });

  test("refuses a referenced artifact whose bytes do not match its hash", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const root = repo();
    const { digest } = writeDurableEvidence(root);
    writeFileSync(
      join(root, ".factory", "artifacts", "objects", digest.slice(0, 2), digest),
      "tampered",
    );
    const server = await ensureDocsServer(root);
    expect((await fetch(`${server.url}/api/artifact/${digest}`)).status).toBe(409);
  });

  test("returns retained review evidence for a task", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const root = repo();
    writeReviewArchive(root);
    const server = await ensureDocsServer(root);
    const body = await (await fetch(`${server.url}/api/reviews?task=T-001`)).json();
    expect(body.reviews).toHaveLength(1);
    expect(body.reviews[0]).toMatchObject({
      task_id: "T-001",
      decision: "reject",
      reviewed_files: ["source.py"],
      diff: expect.stringContaining("+new"),
    });
    expect(body.reviews[0].annotations[0]).toMatchObject({ file: "source.py", line: 4 });
  });

  test("renders a document on /api/doc", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    const body = await (await fetch(`${server.url}/api/doc?path=tasks/T-001.md`)).json();
    expect(body.html).toContain("Task One");
    expect(body.progress).toEqual({ done: 1, total: 2 });
    expect(body.toc[0].text).toBe("Task One");
  });

  test("refuses to serve a file outside the repo", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/doc?path=../../etc/passwd`);
    expect(res.status).toBe(403);
  });

  test("404s a document that does not exist", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    expect((await fetch(`${server.url}/api/doc?path=tasks/gone.md`)).status).toBe(404);
  });

  test("reuses the running server rather than starting a second one", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const root = repo();
    const first = await ensureDocsServer(root);
    const second = await ensureDocsServer(root);
    expect(second.port).toBe(first.port);
  });

  test("refuses to reuse a server for a different repository root", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    await ensureDocsServer(repo());
    await expect(ensureDocsServer(repo())).rejects.toThrow("refusing different root");
  });

  test("binds loopback only", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    expect(server.url).toContain("127.0.0.1");
  });

  test("stopDocsServer reports whether anything was running", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    await ensureDocsServer(repo());
    expect(stopDocsServer()).toBe(true);
    expect(stopDocsServer()).toBe(false);
  });
});

// Inc 3B Task 6: browser transport boundary coverage for goal_show/sim_run
// obligations fields. `system-worker.test.ts` already proves the additive
// fields survive the mocked persistent-worker protocol (system-worker.ts);
// these tests exercise the same `/api/system/goal` and `/api/system/sim/run`
// routes end to end through `docs-server.ts`, the same way every other test
// in this file does -- via the one-shot CLI fallback (`spawnSync` mocked,
// `spawn` left unmocked so the real worker process is unreachable in this
// sandbox and `systemRequest` falls back immediately). `docs-server.ts` never
// re-derives or reshapes a `value` field, so this pins the same "no
// reshaping" promise for the browser-facing routes that
// `test_dossier_mirrors_individual_commands` pins on the Python side.
describe("goal_show / sim_run obligations transport", () => {
  test("serves goal_show with its additive obligations fields intact", async () => {
    const goal = {
      id: "GOAL-CLI-001",
      title: "worker goal",
      state: "proposed",
      version: 1,
      feature: ["FEAT-CLI-001"],
      requirements: ["SR-001"],
      metric: null,
      target: ">=0.9",
      evidence: [],
      history: [],
      scope_errors: [],
      obligations_open: 0,
      obligations_error: null,
    };
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(goal), stderr: "" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/system/goal?id=GOAL-CLI-001`);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(goal);
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.system", "goal", "show", "GOAL-CLI-001", "--json"],
      expect.objectContaining({ cwd: expect.any(String) }),
    );
  });

  test("serves sim_run's unsupported run-scope obligations_error, stably across repeated calls", async () => {
    const simRun = {
      run: "RUN-3",
      experiment: "SIM-X",
      feature: "FEAT-CLI-001",
      requirements: [],
      goals: ["GOAL-CLI-001"],
      commit: "f92b005",
      result: "passed",
      scope_errors: [],
      metrics: {},
      recording: null,
      recorded_ts: null,
      obligations_open: 0,
      obligations_error: "policy scope unsupported for 'run:RUN-3': load_nodes exposes no run nodes",
    };
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(simRun), stderr: "" });
    const server = await ensureDocsServer(repo());
    const first = await (await fetch(`${server.url}/api/system/sim/run?id=RUN-3`)).json();
    const second = await (await fetch(`${server.url}/api/system/sim/run?id=RUN-3`)).json();
    // Same stable degraded shape both times -- no throw, no fabricated
    // presentation response, no drift between calls.
    expect(first).toEqual(simRun);
    expect(second).toEqual(simRun);
    expect(spawnSync).toHaveBeenCalledWith(
      "uv",
      ["run", "python", "-m", "factory.system", "sim", "run", "RUN-3", "--json"],
      expect.objectContaining({ cwd: expect.any(String) }),
    );
  });

  test("passes through a stale goal payload missing the additive obligations fields", async () => {
    // Simulates an older worker/CLI build that predates Task 3: the route
    // must serve exactly what it was given, not fabricate the missing keys
    // and not throw because they are absent.
    const staleGoal = {
      id: "GOAL-CLI-001",
      title: "worker goal",
      state: "proposed",
      version: 1,
      feature: ["FEAT-CLI-001"],
      requirements: ["SR-001"],
      metric: null,
      target: ">=0.9",
      evidence: [],
      history: [],
      scope_errors: [],
    };
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(staleGoal), stderr: "" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/system/goal?id=GOAL-CLI-001`);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual(staleGoal);
    expect(body).not.toHaveProperty("obligations_open");
    expect(body).not.toHaveProperty("obligations_error");
  });

  test("reports a malformed goal_show payload as a 503 instead of crashing", async () => {
    // Status 0 but unparseable stdout -- a corrupt/partial write, not a
    // reported Python failure. `parseCliResult` must still degrade to a
    // structured error rather than throwing out of the request handler.
    spawnSync.mockReturnValue({ status: 0, stdout: "not json at all", stderr: "" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/system/goal?id=GOAL-CLI-001`);
    expect(res.status).toBe(503);
    expect((await res.json()).error).toContain("could not parse");
  });

  test("reports sim_run's structured Python error (unresolvable run) as a 503", async () => {
    spawnSync.mockReturnValue({
      status: 1,
      stdout: "",
      stderr: JSON.stringify({ error: "no simulation run with id 'RUN-GONE'", kind: "ScopeNotFoundError" }),
    });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/system/sim/run?id=RUN-GONE`);
    expect(res.status).toBe(503);
    expect((await res.json()).error).toContain("no simulation run with id");
  });
});
