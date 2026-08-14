import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderSystemPageHtml } from "../src/system-page.js";

const GRAPH = {
  nodes: [
    { id: "BR-002", kind: "br", title: "Swimmer safety", path: "requirements/BR-002.md", exempt: false, deferred: null },
    { id: "SR-086", kind: "sr", title: "Common planner protocol", path: "requirements/SR-086.md", exempt: false, deferred: null },
    { id: "T-059", kind: "task", title: "Common Planner Protocol", path: "tasks/T-059.md", exempt: false, deferred: null },
    { id: "plan:2026-08-06-paad-increment-1-deterministic-vertical-slice.md", kind: "plan", title: "PAAD increment 1", path: "docs/superpowers/plans/2026-08-06-paad-increment-1-deterministic-vertical-slice.md", exempt: false, deferred: null },
    { id: "spec:docs/superpowers/specs/2026-08-06-paad-mvp-system-specification-v0.1.md", kind: "spec", title: "PAAD MVP spec", path: "docs/superpowers/specs/2026-08-06-paad-mvp-system-specification-v0.1.md", exempt: false, deferred: null },
  ],
  edges: [
    { src: "T-059", dst: "SR-086", kind: "satisfies" },
    { src: "SR-086", dst: "BR-002", kind: "upstream" },
    { src: "T-059", dst: "plan:2026-08-06-paad-increment-1-deterministic-vertical-slice.md", kind: "source_plan" },
    { src: "plan:2026-08-06-paad-increment-1-deterministic-vertical-slice.md", dst: "spec:docs/superpowers/specs/2026-08-06-paad-mvp-system-specification-v0.1.md", kind: "spec_ref" },
  ],
};
function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => body } as Response);
}
function mockFetch() {
  return vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/scope") return jsonResponse({ scopes: [{ kind: "sr", ref: "sr:SR-086" }], errors: [] });
    if (url.pathname === "/api/system/brief") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-086" }, claims: [], degraded: false, degraded_reasons: [] });
    if (url.pathname === "/api/system/matrix") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-086" }, rows: [] });
    if (url.pathname === "/api/system/timeline") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-086" }, events: [], degraded: false, degraded_reasons: [] });
    if (url.pathname === "/api/system/guide") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-086" }, sections: [] });
    if (url.pathname === "/api/graph") return jsonResponse(GRAPH);
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}
async function loadPage(): Promise<JSDOM> {
  const fetchMock = mockFetch();
  return new JSDOM(renderSystemPageHtml(), {
    runScripts: "dangerously", resources: "usable",
    url: "http://localhost/system?scope=sr%3ASR-086",
    beforeParse(w: never) { (w as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch; },
  });
}
afterEach(() => vi.restoreAllMocks());

describe("system-page Trace tab", () => {
  test("a Trace tab exists for the scope", async () => {
    const dom = await loadPage();
    await vi.waitFor(() => expect(dom.window.document.getElementById("content")!.hidden).toBe(false), { timeout: 2000 });
    expect(dom.window.document.getElementById("tabTrace")).not.toBeNull();
    expect(dom.window.document.getElementById("panelTrace")).not.toBeNull();
  });

  test("clicking Trace lazily fetches /api/graph and renders the task + plan + spec chain", async () => {
    const dom = await loadPage();
    const fetchMock = dom.window.fetch as unknown as ReturnType<typeof mockFetch>;
    await vi.waitFor(() => expect(dom.window.document.getElementById("tabTrace")).not.toBeNull(), { timeout: 2000 });
    dom.window.document.getElementById("tabTrace")!.click();
    await vi.waitFor(() => {
      expect(dom.window.document.getElementById("panelTrace")!.textContent).toContain("T-059");
    }, { timeout: 2000 });
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/graph"));
    // The chain names the satisfying task, its plan, and its spec.
    expect(dom.window.document.getElementById("panelTrace")!.textContent).toContain("paad-increment-1");
    expect(dom.window.document.getElementById("panelTrace")!.textContent).toContain("paad-mvp-system-specification");
  });
});
