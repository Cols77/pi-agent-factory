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
