// Increment B "V-cycle": exercises the two new panels (Story = forward,
// task -> runs -> requirements; Reverse = backward, file -> run -> task ->
// requirements) against a real DOM, following the same idiom
// system-page-dom.test.ts already established for the brief/matrix/
// timeline/guide panels (jsdom, runScripts: "dangerously", a mocked
// `fetch`, poll until the page's own async bootstrap settles). A second
// harness is deliberately not built here -- this file re-derives the same
// `loadPage` shape rather than importing it, because system-page-dom.test.ts
// does not export it.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderSystemPageHtml } from "../src/system-page.js";

const SCOPE_LIST = { scopes: [], errors: [] };

// Mirrors tests/unit/system/test_story.py's
// test_story_validates_against_the_response_schemas_story_member fixture
// shape: one manifest-sourced run, one session-sourced run with no
// changed_files/commit range (implementation always missing/n-a for a
// session record -- design increment B).
const STORY = {
  scope: { kind: "task", ref: "task:T-055" },
  task: { id: "T-055", title: "Wire the demo feature", status: "done" },
  runs: [
    {
      run_id: "r1",
      source: "manifest",
      outcome: "completed",
      started_at: "2026-08-01T00:00:00Z",
      ended_at: "2026-08-01T00:30:00Z",
      start_commit: "a".repeat(40),
      result_commit: "b".repeat(40),
      implementation: {
        kind: "recorded",
        text: "run r1: 1 changed file(s) recorded",
        citations: [{ kind: "manifest", path: "evidence/runs/r1.json", sha256: "c".repeat(64), anchor: null }],
        spans: [],
        freshness: { state: "fresh", reason: null, dependencies: [] },
        changed_files: ["src/a.py"],
      },
      citation: { kind: "manifest", path: "evidence/runs/r1.json", sha256: "c".repeat(64), anchor: null },
    },
    {
      run_id: "s1",
      source: "session",
      outcome: "completed",
      started_at: "2026-08-02T00:00:00Z",
      ended_at: "2026-08-02T00:30:00Z",
      start_commit: null,
      result_commit: null,
      implementation: {
        kind: "missing",
        text: "run s1: implementation not recorded",
        citations: [],
        spans: [],
        freshness: { state: "n/a", reason: "session records do not capture changed files or a commit range", dependencies: [] },
        changed_files: null,
      },
      citation: { kind: "session", path: "sessions/.factory-transcripts/s1/session.json", sha256: "d".repeat(64), anchor: null },
    },
  ],
  requirements: ["sr:SR-146"],
  degraded: true,
  degraded_reasons: ["1 run(s) have no recorded implementation detail (session record only, no evidence manifest)"],
};

// Mirrors tests/integration/system/test_vcycle.py's shape, but with
// stops_at: "satisfies" (the task resolved, its satisfies list did not).
const REVERSE = {
  scope: { kind: "file", ref: "file:src/a.py" },
  paths: [
    {
      file: "src/a.py",
      run: {
        run_id: "run-059",
        outcome: "completed",
        started_at: "2026-08-08T08:00:00Z",
        ended_at: "2026-08-08T09:00:00Z",
        start_commit: "a".repeat(40),
        result_commit: "b".repeat(40),
        implementation: {
          kind: "recorded",
          text: "run run-059: 1 changed file(s) recorded",
          citations: [{ kind: "manifest", path: "evidence/runs/run-059.json", sha256: "e".repeat(64), anchor: null }],
          spans: [],
          freshness: { state: "fresh", reason: null, dependencies: [] },
          changed_files: ["src/a.py"],
        },
        citation: { kind: "manifest", path: "evidence/runs/run-059.json", sha256: "e".repeat(64), anchor: null },
      },
      task: { id: "T-059", title: "Implement the demo feature", status: "done" },
      requirements: [],
      stops_at: "satisfies",
    },
  ],
  degraded: true,
  degraded_reasons: ["1 path(s) have no recorded satisfies requirement link"],
};

function jsonResponse(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

function mockFetch() {
  return vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/scope") return jsonResponse(SCOPE_LIST);
    if (url.pathname === "/api/system/story") return jsonResponse(STORY);
    if (url.pathname === "/api/system/reverse") return jsonResponse(REVERSE);
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}

/** Same idiom as system-page-dom.test.ts's own `loadPage`: loads the real
 * page document into jsdom, with `fetch` wired to the fixtures above, and
 * waits for the page's own async bootstrap to finish populating the DOM. */
async function loadPage(opts: { scope?: string } = {}): Promise<JSDOM> {
  const html = renderSystemPageHtml();
  const url = opts.scope
    ? `http://localhost/system?scope=${encodeURIComponent(opts.scope)}`
    : "http://localhost/system";
  const fetchMock = mockFetch();
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    resources: "usable",
    url,
    beforeParse(window) {
      (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
    },
  });
  await vi.waitFor(
    () => {
      const list = dom.window.document.getElementById("scopeList");
      expect(list).not.toBeNull();
    },
    { timeout: 2000, interval: 10 },
  );
  if (opts.scope) {
    await vi.waitFor(
      () => {
        expect(dom.window.document.getElementById("scopeWorkspace")?.hidden).toBe(false);
      },
      { timeout: 2000, interval: 10 },
    );
  }
  return dom;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("system-page.ts V-cycle panels, executed against a real DOM", () => {
  test("a session-sourced run is visibly distinguished from a manifest run", async () => {
    const dom = await loadPage({ scope: "task:T-055" });
    expect(dom.window.document.getElementById("tabStory")?.hidden).toBe(false);
    expect(dom.window.document.getElementById("tabBrief")?.hidden).toBe(true);
    expect(dom.window.document.getElementById("tabReverse")?.hidden).toBe(true);
    const rows = dom.window.document.querySelectorAll("#panelStory .run");
    expect(rows.length).toBe(2);
    expect(rows[0]?.querySelector(".source")?.textContent).toBe("manifest");
    expect(rows[1]?.querySelector(".source")?.textContent).toBe("session");
    // The session run states its implementation is missing rather than hiding it.
    expect(rows[1]?.textContent).toContain("missing");
  });

  test("a reverse path that stops early names the hop it stopped at", async () => {
    const dom = await loadPage({ scope: "file:src/a.py" });
    expect(dom.window.document.getElementById("tabReverse")?.hidden).toBe(false);
    expect(dom.window.document.getElementById("tabStory")?.hidden).toBe(true);
    const path = dom.window.document.querySelector("#panelReverse .path");
    expect(path?.textContent).toContain("satisfies");
  });
});
