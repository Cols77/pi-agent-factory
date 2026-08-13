// Task 1 (system nav): the scope picker is searchable, grouped by scope.kind,
// and collapses to a compact "All scopes ▾" bar once a scope is loaded. These
// tests execute the real client script (jsdom `runScripts: "dangerously"`,
// the same harness as system-page-dom.test.ts) and assert on the rendered DOM.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderSystemPageHtml } from "../src/system-page.js";

const HEALTH = {
  // SP-B Task 7: the sidebar renders from the health payload, not list_scopes.
  health: { classes: [], satisfied: 0, expected: 0, percent: 0, dangling: 0, deferred: 0, proposed: 0 },
  coverage: { total: 1, bundled: 1, unbundled: [], kinds: [] },
  bundles: [
    {
      id: "evidence-lifecycle",
      label: "Evidence lifecycle",
      readiness: "weak",
      readiness_counts: { sr_total: 1, bound: 0, covered: 0, current: 0, deferred: 0, validated: 0 },
      members: 1,
    },
  ],
  unbundled: { sr: ["sr:SR-999"] },
  ordering_available: true,
  sr_listed: false,
  degraded: [],
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
    if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
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
  test("groups bundles by readiness with counts, unbundled visible, and a filter input", async () => {
    const dom = await loadPage();
    await vi.waitFor(
      () => expect(dom.window.document.querySelectorAll("#scopeList .scope-group").length).toBe(2),
      { timeout: 2000 },
    );
    const list = dom.window.document.getElementById("scopeList")!;
    expect(dom.window.document.getElementById("scopeFilter")).not.toBeNull();
    expect(dom.window.document.getElementById("searchGo")).not.toBeNull();
    // The bundle sits under its readiness group with its counts beside the
    // label, and the unbundled remainder renders at the bottom, visible.
    const weak = list.querySelector('[data-readiness="weak"]')!;
    expect(weak.textContent).toContain("Evidence lifecycle");
    expect(weak.textContent).toContain("1 SR");
    expect(list.textContent).toContain("sr:SR-999");
    expect(Array.from(list.querySelectorAll(".scope-group")).map((g) =>
      (g as HTMLElement).dataset.readiness ?? (g as HTMLElement).dataset.group))
      .toEqual(["weak", "unbundled"]);
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

  // Task 2 (system nav): SPA scope navigation. Clicking a scope item must
  // load the scope in-place through the SPA loader (no full page reload) and
  // update the URL via history.pushState to /system?scope=<ref> -- proven by
  // the scope loading (#content unhidden) while window.location.search also
  // carries scope=. The bundle/sr fixture kinds hit /brief /matrix /timeline
  // /guide, so the empty-stub fixtures above resolve them.
  test("scope items navigate via the SPA loader and pushState, not a full reload", async () => {
    const dom = await loadPage();
    await vi.waitFor(
      () => expect(dom.window.document.querySelectorAll("#scopeList .scope-item").length).toBe(2),
      { timeout: 2000 },
    );
    // The feature-first sidebar (Task 7) shows the one bundle plus the visible
    // unbundled remainder as scope-items; click the bundle specifically.
    const click = Array.from(dom.window.document.querySelectorAll("#scopeList .scope-item"))
      .find((el) => el.textContent.includes("Evidence lifecycle")) as unknown as HTMLElement;
    expect(click.textContent).toContain("Evidence lifecycle");
    click.click();
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("content")!.hidden).toBe(false),
      { timeout: 2000 },
    );
    expect(dom.window.location.search).toContain("scope=bundle%3Aevidence-lifecycle");
  });

  // Task 2 (system nav): per-tab URL hash + aria-controls. Each tab button
  // carries an aria-controls reference to its panel; clicking one selects it
  // (aria-selected="true") and writes the hash.
  test("tabs carry an aria-controls reference and reflect selection", async () => {
    const dom = await loadPage();
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("scopeList")).not.toBeNull(),
      { timeout: 2000 },
    );
    const tab = dom.window.document.getElementById("tabMatrix")!;
    expect(tab.getAttribute("aria-controls")).toBe("panelMatrix");
    tab.click();
    expect(tab.getAttribute("aria-selected")).toBe("true");
  });

  // Task 3 (system nav): the loaded scope surface exposes a loading status
  // element, a per-scope Refresh button, and a "loaded at" timestamp. Once
  // the scope loads (#content unhidden), all three elements exist and the
  // successful load has stamped a non-empty time string into #loadedAt.
  test("shows a loading status element, refresh button, and loaded-at timestamp", async () => {
    const dom = await loadPage("bundle:evidence-lifecycle");
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("content")!.hidden).toBe(false),
      { timeout: 2000 },
    );
    expect(dom.window.document.getElementById("loading")).not.toBeNull();
    expect(dom.window.document.getElementById("refresh")).not.toBeNull();
    expect(dom.window.document.getElementById("loadedAt")).not.toBeNull();
    // A successful load stamps #loadedAt with a non-empty time string.
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("loadedAt")!.textContent).not.toBe(""),
      { timeout: 2000 },
    );
  });

  // Task 4 (system nav): keyboard tab switching. Alt+2 (no ctrl/meta) on
  // the document selects the Matrix tab via the same showTab path a click
  // uses, flipping its aria-selected to "true".
  test("Alt+number switches tabs", async () => {
    const dom = await loadPage();
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("scopeList")).not.toBeNull(),
      { timeout: 2000 },
    );
    dom.window.document.dispatchEvent(
      new dom.window.KeyboardEvent("keydown", { key: "2", altKey: true, bubbles: true }),
    );
    expect(dom.window.document.getElementById("tabMatrix")!.getAttribute("aria-selected")).toBe("true");
  });

  // Task 4 (system nav): tabs are exposed as an ARIA tablist inside the
  // navigator, with each tab button carrying a role and an aria-label.
  // (aria-controls already landed in Task 2 and is asserted above.)
  test("tabs are exposed as a navigation landmark with labels", async () => {
    const dom = await loadPage();
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("scopeList")).not.toBeNull(),
      { timeout: 2000 },
    );
    const tabs = dom.window.document.getElementById("tabs")!;
    expect(tabs.getAttribute("role")).toBe("tablist");
    const matrix = dom.window.document.getElementById("tabMatrix")!;
    expect(matrix.getAttribute("role")).toBe("tab");
    expect(matrix.getAttribute("aria-label")).toBe("Matrix");
    // The tabs sit inside a labelled nav landmark.
    expect(tabs.closest("nav[aria-label='System navigator']")).not.toBeNull();
  });
});
