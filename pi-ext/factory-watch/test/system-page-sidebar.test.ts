import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderSystemPageHtml } from "../src/system-page.js";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => body } as Response);
}
function mockFetch() {
  return vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/scope") return jsonResponse({ scopes: [{ kind: "sr", ref: "sr:SR-001" }], errors: [] });
    if (url.pathname === "/api/system/brief") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, claims: [], degraded: false, degraded_reasons: [] });
    if (url.pathname === "/api/system/matrix") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, rows: [] });
    if (url.pathname === "/api/system/timeline") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, events: [], degraded: false, degraded_reasons: [] });
    if (url.pathname === "/api/system/guide") return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, sections: [] });
    if (url.pathname === "/api/system/labels") return jsonResponse({ labels: {}, aliases: {}, degraded: [] });
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}
async function loadPage(scope?: string): Promise<JSDOM> {
  const fetchMock = mockFetch();
  return new JSDOM(renderSystemPageHtml(), {
    runScripts: "dangerously", resources: "usable",
    url: scope ? `http://localhost/system?scope=${encodeURIComponent(scope)}` : "http://localhost/system",
    beforeParse(w: never) { (w as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch; },
  });
}
afterEach(() => vi.restoreAllMocks());

describe("system-page left sidebar", () => {
  test("places the scope picker and content in a two-column grid layout", async () => {
    const dom = await loadPage();
    await vi.waitFor(() => expect(dom.window.document.getElementById("scopeList")).not.toBeNull(), { timeout: 2000 });
    const layout = dom.window.document.getElementById("layout");
    expect(layout).not.toBeNull();
    expect(dom.window.document.getElementById("picker")!.parentElement!.id).toBe("layout");
    expect(dom.window.document.getElementById("content")!.parentElement!.id).toBe("layout");
  });

  test("the sidebar stays a distinct column when a scope is loaded", async () => {
    const dom = await loadPage("sr:SR-001");
    await vi.waitFor(() => expect(dom.window.document.getElementById("content")!.hidden).toBe(false), { timeout: 2000 });
    expect(dom.window.document.getElementById("picker")).not.toBeNull();
    expect(dom.window.document.getElementById("scopeList")).not.toBeNull();
  });
});
