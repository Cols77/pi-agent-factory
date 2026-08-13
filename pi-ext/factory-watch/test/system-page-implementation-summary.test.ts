// Fix-wave finding 1 (whole-branch review): Task 5 added
// `implementation_summary` to every bundle `task:` member claim in
// `query_brief` (design SS4.3 -- run count, latest outcome, changed-file
// count, latest validation result), but nothing rendered it. This file
// pins the render against a real DOM, following the same idiom
// system-page-dom.test.ts/system-page-vcycle.test.ts already established
// (jsdom, runScripts: "dangerously", a mocked `fetch`, poll until the
// page's own async bootstrap settles) -- never asserting on the generated
// source string.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderSystemPageHtml } from "../src/system-page.js";

const SCOPE_LIST = {
  scopes: [{ kind: "bundle", ref: "bundle:feat" }],
  errors: [],
};

// Mirrors tests/unit/system/test_queries.py's
// test_bundle_task_members_carry_an_implementation_summary and
// test_a_task_member_with_no_runs_summarises_as_none_not_zero fixture
// shapes: one task member with recorded runs (including a deliberately
// "stale" latest_validation -- the state this whole subsystem exists to
// keep distinct from a plain "passed"), one task member with zero runs
// where every field is `null`, never `0` or omitted.
const BRIEF = {
  scope: { kind: "bundle", ref: "bundle:feat" },
  claims: [
    {
      kind: "recorded",
      text: "task:T-100",
      citations: [{ kind: "task", path: "tasks/T-100.yaml", sha256: "a".repeat(64), anchor: null }],
      spans: [],
      freshness: { state: "fresh", reason: null, dependencies: [] },
      implementation_summary: {
        runs: 2,
        latest_outcome: "completed",
        changed_file_count: 3,
        latest_validation: "stale",
      },
    },
    {
      kind: "recorded",
      text: "task:T-101",
      citations: [{ kind: "task", path: "tasks/T-101.yaml", sha256: "b".repeat(64), anchor: null }],
      spans: [],
      freshness: { state: "fresh", reason: null, dependencies: [] },
      implementation_summary: {
        runs: 0,
        latest_outcome: null,
        changed_file_count: null,
        latest_validation: null,
      },
    },
  ],
  degraded: false,
  degraded_reasons: [],
};

const MATRIX = { scope: { kind: "bundle", ref: "bundle:feat" }, rows: [] };
const TIMELINE = { scope: { kind: "bundle", ref: "bundle:feat" }, events: [], degraded: false, degraded_reasons: [] };
const GUIDE = { scope: { kind: "bundle", ref: "bundle:feat" }, sections: [] };

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
    if (url.pathname === "/api/system/brief") return jsonResponse(BRIEF);
    if (url.pathname === "/api/system/matrix") return jsonResponse(MATRIX);
    if (url.pathname === "/api/system/timeline") return jsonResponse(TIMELINE);
    if (url.pathname === "/api/system/guide") return jsonResponse(GUIDE);
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}

/** Same idiom as system-page-dom.test.ts's own `loadPage`. */
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
      expect(dom.window.document.getElementById("scopeList")).not.toBeNull();
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

describe("system-page.ts renders implementation_summary on a bundle task: member claim", () => {
  test("a member with recorded runs shows its counts and a distinctly-styled stale verdict", async () => {
    const dom = await loadPage({ scope: "bundle:feat" });
    const claims = dom.window.document.querySelectorAll("#panelBrief .claim");
    expect(claims.length).toBe(2);

    const summary = claims[0]?.querySelector(".implementation-summary");
    expect(summary).not.toBeNull();
    expect(summary?.textContent).toContain("runs: 2");
    expect(summary?.textContent).toContain("latest outcome: completed");
    expect(summary?.textContent).toContain("changed files: 3");
    expect(summary?.textContent).toContain("latest validation:");
    expect(summary?.textContent).toContain("stale");

    // "stale" must never be styled the same as "passed" -- that flattening
    // is exactly what this subsystem exists to prevent.
    const validationEl = summary?.querySelector(".validation-stale");
    expect(validationEl).not.toBeNull();
    expect(validationEl?.textContent).toBe("stale");
    expect(summary?.querySelector(".validation-passed")).toBeNull();
  });

  test("a member with no runs renders every field plainly as not-recorded, never 0 or blank", async () => {
    const dom = await loadPage({ scope: "bundle:feat" });
    const claims = dom.window.document.querySelectorAll("#panelBrief .claim");
    const summary = claims[1]?.querySelector(".implementation-summary");
    expect(summary).not.toBeNull();
    expect(summary?.textContent).toContain("runs: 0");
    expect(summary?.textContent).toContain("latest outcome: not recorded");
    // changed_file_count is null (no runs), not 0 -- must render as
    // "not recorded", never as the digit 0.
    expect(summary?.textContent).toContain("changed files: not recorded");
    expect(summary?.textContent).not.toMatch(/changed files: 0\b/);
    expect(summary?.textContent).toContain("latest validation:");
    const validationEl = summary?.querySelector(".validation-none");
    expect(validationEl).not.toBeNull();
    expect(validationEl?.textContent).toBe("not recorded");
  });
});
