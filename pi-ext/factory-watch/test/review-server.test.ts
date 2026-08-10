import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test, vi } from "vitest";

vi.mock("../src/review-diff.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/review-diff.js")>()),
  computeFileDiffText: vi.fn(() => "@@ -1,1 +1,1 @@\n-old\n+new\n"),
}));

import { buildReviewPageData } from "../src/review-server.js";
import type { FileStat } from "../src/review-diff.js";

const FILES: FileStat[] = [{ path: "a.py", status: "M", added: 1, removed: 1 }];
const dirs: string[] = [];

function repoWithTask(taskId = "T-001"): string {
  const root = mkdtempSync(join(tmpdir(), "review-server-"));
  dirs.push(root);
  mkdirSync(join(root, "tasks"));
  writeFileSync(
    join(root, "tasks", `${taskId}-example.md`),
    `---\nid: ${taskId}\ntitle: Review task\nstatus: in_progress\ndod:\n  - Show the task in the browser\n---\n\n# Implementation context\n\nThe reviewer needs this context.\n`,
  );
  return root;
}

afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("buildReviewPageData", () => {
  test("returns files, diff lines, and row meta per file", () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-1" });
    expect(data.taskId).toBe("T-1");
    expect(data.files).toHaveLength(1);
    expect(data.diffs["a.py"]!.lines).toContain("+new");
    // the "+new" row anchors to the new side
    const addIdx = data.diffs["a.py"]!.lines.findIndex((l) => l === "+new");
    expect(data.diffs["a.py"]!.meta[addIdx]!.side).toBe("new");
  });

  test("includes the task under review as rendered, structured context", () => {
    const data = buildReviewPageData(repoWithTask(), "abc", FILES, { taskId: "T-001" });
    expect(data.task).toMatchObject({
      path: "tasks/T-001-example.md",
      id: "T-001",
      title: "Review task",
      status: "in_progress",
      dod: ["Show the task in the browser"],
    });
    expect(data.task?.html).toContain("Implementation context");
  });

  test("keeps the diff review usable when its task file is unavailable", () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-missing" });
    expect(data.task).toBeNull();
  });
});

import { startReviewServer } from "../src/review-server.js";

async function post(url: string, body: unknown): Promise<Response> {
  return fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

describe("startReviewServer", () => {
  test("serves /api/review and accepts a decision, resolving the promise", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-9" });
    const srv = await startReviewServer(data, { cwd: "/repo" });
    try {
      const review = await (await fetch(`${srv.url}/api/review`)).json();
      expect(review.taskId).toBe("T-9");

      const payload = { decision: "approve", annotations: [], reviewedFiles: ["a.py"] };
      const res = await post(`${srv.url}/api/decision`, payload);
      expect((await res.json()).ok).toBe(true);

      const decided = await srv.decision;
      expect(decided).not.toBeNull();
      expect(decided!.decision).toBe("approve");
      expect(decided!.reviewedFiles).toEqual(["a.py"]);
    } finally {
      srv.close();
    }
  });

  test("close() before any post resolves the decision to null", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-0" });
    const srv = await startReviewServer(data, { cwd: "/repo" });
    srv.close();
    expect(await srv.decision).toBeNull();
  });

  test("malformed JSON body returns 400 without hanging or settling the decision", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-bad" });
    const srv = await startReviewServer(data, { cwd: "/repo" });
    try {
      const badRes = await fetch(`${srv.url}/api/decision`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "not json{{{",
      });
      expect(badRes.status).toBe(400);
      const badBody = await badRes.json();
      expect(badBody.error).toBeTruthy();

      // Prove the server is still alive and the decision promise is still unsettled:
      // a subsequent valid POST must still be able to resolve it.
      const payload = { decision: "approve", annotations: [], reviewedFiles: ["a.py"] };
      const goodRes = await post(`${srv.url}/api/decision`, payload);
      expect(goodRes.status).toBe(200);
      expect((await goodRes.json()).ok).toBe(true);

      const decided = await srv.decision;
      expect(decided).not.toBeNull();
      expect(decided!.decision).toBe("approve");
    } finally {
      srv.close();
    }
  }, 5000);
});

import { walkIntentChain } from "../src/review-intent.js";

const STORY_OK = {
  ok: true as const,
  value: {
    scope: { kind: "task", ref: "task:T-001" },
    task: { id: "T-001", title: "A task", status: "in-review", dod: ["ships"] },
    runs: [], requirements: ["sr:SR-014"],
    plan_section: { plan_path: "docs/superpowers/plans/p.md", heading: "Task 1: A task", body: "Do the thing." },
    degraded: false, degraded_reasons: [],
  },
};

const CONTEXT_OK = {
  context: {},
  graph: {
    nodes: [
      { id: "T-001", kind: "task", title: "A task", path: "tasks/T-001-a.md", exempt: false, deferred: null },
      { id: "plan:p.md", kind: "plan", title: "A plan", path: "docs/superpowers/plans/p.md", exempt: false, deferred: null },
    ],
    edges: [{ src: "T-001", dst: "plan:p.md", kind: "source_plan" }],
    gaps: [], validation: {},
    health: { percent: 0, satisfied: 0, expected: 0, dangling: 0, deferred: 0, proposed: 0, classes: [] },
  },
};

// No cast on the literal: `as never` here would type `okDeps` as `never`, and
// a `never` cannot be spread — every `{ ...okDeps }` below would fail to
// compile. Cast at the call site instead.
const okDeps = {
  story: () => STORY_OK,
  context: () => CONTEXT_OK,
  layout: () => ({ collapsed: [], zoomed: null }),
};

describe("buildReviewPageData intent", () => {
  test("carries the chain, the DoD and the rendered plan section", () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: okDeps as never });
    expect(data.intent?.chain.map((n) => n.id)).toEqual(["plan:p.md", "T-001"]);
    expect(data.intent?.stopsAt).toBe("satisfies");
    expect(data.intent?.dod).toEqual(["ships"]);
    expect(data.intent?.planSection?.html).toContain("Do the thing.");
  });

  test("a failing story leaves the page renderable without an intent", () => {
    const deps = { ...okDeps, story: () => ({ ok: false, error: "uv missing" }) };
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: deps as never });
    expect(data.intent).toBeNull();
    expect(data.files).toEqual(FILES);
  });

  test("a failing graph keeps the plan section and empties the chain", () => {
    const deps = { ...okDeps, context: () => ({ context: {}, graph: null }) };
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: deps as never });
    expect(data.intent?.chain).toEqual([]);
    expect(data.intent?.planSection?.heading).toBe("Task 1: A task");
  });

  test("a null plan section still yields a usable intent", () => {
    const story = { ...STORY_OK, value: { ...STORY_OK.value, plan_section: null } };
    const deps = { ...okDeps, story: () => story };
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: deps as never });
    expect(data.intent?.planSection).toBeNull();
    expect(data.intent?.dod).toEqual(["ships"]);
  });
});

describe("review server endpoints", () => {
  test("/api/why returns the reverse walk for a file", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: okDeps as never });
    const reverse = () => ({ ok: true as const, value: { scope: { kind: "file", ref: "file:a.ts" }, paths: [], degraded: false, degraded_reasons: [] } });
    const srv = await startReviewServer(data, { cwd: "/repo", reverse: reverse as never });
    const res = await fetch(`${srv.url}/api/why?file=a.ts`);
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ scope: { ref: "file:a.ts" } });
    srv.close();
  });

  test("/api/why reports the reason instead of failing the pane", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: okDeps as never });
    const reverse = () => ({ ok: false as const, error: "no manifest" });
    const srv = await startReviewServer(data, { cwd: "/repo", reverse: reverse as never });
    const body = await (await fetch(`${srv.url}/api/why?file=a.ts`)).json();
    expect(body).toMatchObject({ status: "unknown", source: "reverse" });
    srv.close();
  });

  test("/api/layout persists a posted layout", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: okDeps as never });
    const written: unknown[] = [];
    const srv = await startReviewServer(data, {
      cwd: "/repo",
      writeLayout: ((_cwd: string, state: unknown) => { written.push(state); }) as never,
    });
    await fetch(`${srv.url}/api/layout`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ collapsed: ["tree"], zoomed: null }),
    });
    expect(written).toEqual([{ collapsed: ["tree"], zoomed: null }]);
    srv.close();
  });
});
