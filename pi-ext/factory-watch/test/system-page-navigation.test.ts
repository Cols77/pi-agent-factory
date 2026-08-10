// Task 1 (system nav): the scope picker is searchable, grouped by scope.kind,
// and collapses to a compact "All scopes ▾" bar once a scope is loaded. These
// tests execute the real client script (jsdom `runScripts: "dangerously"`,
// the same harness as system-page-dom.test.ts) and assert on the rendered DOM.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderSystemPageHtml } from "../src/system-page.js";

const SCOPE_LIST = {
  scopes: [
    { kind: "bundle", ref: "bundle:evidence-lifecycle" },
    { kind: "sr", ref: "sr:SR-001" },
    { kind: "sr", ref: "sr:SR-002" },
    { kind: "task", ref: "task:T-001" },
    { kind: "file", ref: "file:src/a.py" },
  ],
  errors: [],
};
const EMPTY = { scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, rows: [] };
const EMPTY_TL = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  events: [],
  degraded: false,
  degraded_reasons: [],
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
    if (url.pathname === "/api/system/matrix") return jsonResponse(EMPTY);
    if (url.pathname === "/api/system/timeline") return jsonResponse(EMPTY_TL);
    if (url.pathname === "/api/system/guide") return jsonResponse({ scope: EMPTY.scope, sections: [] });
    if (url.pathname === "/api/system/brief")
      return jsonResponse({ scope: EMPTY.scope, claims: [], degraded: false, degraded_reasons: [] });
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}

async function loadPage(scope?: string): Promise<JSDOM> {
  const fetchMock = mockFetch();
  return new JSDOM(renderSystemPageHtml(), {
    runScripts: "dangerously",
    resources: "usable",
    url: scope ? `http://localhost/system?scope=${encodeURIComponent(scope)}` : "http://localhost/system",
    beforeParse(window) {
      (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
    },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("system-page navigation", () => {
  test("groups scopes by kind and provides a filter input", async () => {
    const dom = await loadPage();
    await vi.waitFor(
      () => expect(dom.window.document.querySelectorAll("#scopeList .scope-item").length).toBe(5),
      { timeout: 2000 },
    );
    const list = dom.window.document.getElementById("scopeList")!;
    expect(dom.window.document.getElementById("scopeFilter")).not.toBeNull();
    // Refs render in payload order, each exactly equal to the raw ref.
    expect(Array.from(list.querySelectorAll(".scope-item")).map((e) => e.textContent))
      .toEqual(["bundle:evidence-lifecycle", "sr:SR-001", "sr:SR-002", "task:T-001", "file:src/a.py"]);
    // Each group gets its own title in payload order.
    expect(Array.from(list.querySelectorAll(".scope-group-title")).map((e) => e.textContent))
      .toEqual(["bundle", "sr", "task", "file"]);
  });

  test("collapses the scope list into a compact bar once a scope loads", async () => {
    const dom = await loadPage("bundle:evidence-lifecycle");
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("content")!.hidden).toBe(false),
      { timeout: 2000 },
    );
    expect(dom.window.document.body.classList.contains("focus")).toBe(true);
    expect(dom.window.document.getElementById("scopeToggle")).not.toBeNull();
  });
});
