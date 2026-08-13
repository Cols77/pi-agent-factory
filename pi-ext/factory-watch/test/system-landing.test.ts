// SP-B Task 6 — landing page health summary from the `health` payload.
//
// The `/system` landing used to be blank until a scope was chosen (`#content`
// hidden). Task 6 makes it open on project health: `loadHealth()` fetches the
// composed `health` projection (`factory.system health --json`) and renders
// `#healthSummary` (percent + each class, verbatim, including a
// denominator-of-one ratio shown truthfully, never as a checkmark) plus the
// bundle list, with `#content` shown before any scope is chosen.
//
// These tests execute the real inline client script (jsdom `runScripts:
// "dangerously"`, same harness as system-page-dom.test.ts). `fetch` is injected
// via `beforeParse` so it exists before the IIFE starts fetching during parse.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderSystemPageHtml } from "../src/system-page.js";

const SCOPE_LIST = {
  scopes: [{ kind: "bundle", ref: "bundle:evidence-lifecycle" }],
  errors: [],
};

// The plan's fixture: a single fully-satisfied class whose denominator is one,
// so the test asserts the tiny `1/1` renders verbatim -- not prettified into a
// green checkmark that would read as a pass.
const HEALTH = {
  health: {
    classes: [{ name: "SR validated", satisfied: 1, expected: 1, exempt: 0 }],
    satisfied: 1,
    expected: 1,
    percent: 100,
    dangling: 0,
    deferred: 0,
    proposed: 0,
  },
  coverage: { total: 4, bundled: 4, unbundled: [], kinds: [] },
  bundles: [],
  unbundled: {},
  ordering_available: true,
  sr_listed: false,
  degraded: [],
};

const BUNDLED_HEALTH = {
  ...HEALTH,
  bundles: [
    {
      id: "b1",
      label: "B1",
      readiness: "weak",
      readiness_counts: { sr_total: 4, bound: 0, covered: 0, current: 0, deferred: 1, validated: 0 },
      members: 4,
    },
  ],
};

// SP-B Task 7 fixture: three bundles spanning the readiness predicate plus an
// unbundled remainder. `bundles` arrive already ordered by recency (Python's
// health projection); the browser only groups the payload order and never
// sorts client-side.
const FEATURE_HEALTH = {
  ...HEALTH,
  sr_listed: false,
  bundles: [
    {
      id: "b1",
      label: "B1",
      readiness: "weak",
      readiness_counts: { sr_total: 4, bound: 0, covered: 0, current: 0, deferred: 1, validated: 0 },
      members: 4,
    },
    {
      id: "b3",
      label: "B3",
      readiness: "medium",
      readiness_counts: { sr_total: 1, bound: 1, covered: 1, current: 1, deferred: 0, validated: 0 },
      members: 1,
    },
    {
      id: "b2",
      label: "B2",
      readiness: "strong",
      readiness_counts: { sr_total: 2, bound: 2, covered: 2, current: 2, deferred: 0, validated: 2 },
      members: 2,
    },
  ],
  unbundled: { sr: ["sr:SR-999"] },
};

function jsonResponse(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

function mockFetch(health: unknown) {
  return vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/scope") return jsonResponse(SCOPE_LIST);
    if (url.pathname === "/api/system/health") return jsonResponse(health);
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}

async function renderWithHealth(health: unknown): Promise<Document> {
  const fetchMock = mockFetch(health);
  const dom = new JSDOM(renderSystemPageHtml(), {
    runScripts: "dangerously",
    resources: "usable",
    url: "http://localhost/system",
    beforeParse(window) {
      (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
    },
  });
  // The landing renders only after loadHealth() resolves -- the first thing
  // the IIFE does after loadScopes().
  await vi.waitFor(
    () => {
      const summary = dom.window.document.getElementById("healthSummary");
      expect(summary?.textContent).not.toBe("");
    },
    { timeout: 2000, interval: 10 },
  );
  return dom.window.document;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("system landing page", () => {
  test("landing shows the health summary with a verbatim small denominator", async () => {
    const doc = await renderWithHealth(HEALTH);
    const summary = doc.querySelector("#healthSummary");
    expect(summary).not.toBeNull();
    expect(summary!.textContent).toContain("SR validated");
    // The 1/1 denominator is rendered verbatim -- a genuine ratio, not a pass.
    expect(summary!.textContent).toContain("1/1");
  });

  test("landing shows the bundle list container and the navigation tabs", async () => {
    const doc = await renderWithHealth(BUNDLED_HEALTH);
    const list = doc.querySelector("#bundleList");
    expect(list).not.toBeNull();
    expect(list!.textContent).toContain("B1");
    // The existing navigation tabs render as part of the landing.
    expect(doc.querySelector("#tabs")).not.toBeNull();
    expect(doc.getElementById("tabMatrix")).not.toBeNull();
  });

  // SP-B Task 7: the sidebar is feature-first -- bundles grouped under
  // Weak/Medium/Strong in payload order, the readiness label always beside
  // the counts that produced it, and the unbundled remainder visible rather
  // than hidden.
  test("sidebar groups bundles by readiness with counts beside the label", async () => {
    const doc = await renderWithHealth(FEATURE_HEALTH);
    const sidebar = doc.querySelector("#scopeList")!;
    const weak = sidebar.querySelector('[data-readiness="weak"]');
    expect(weak).not.toBeNull();
    expect(weak!.textContent).toContain("B1");
    expect(weak!.textContent).toContain("4 SR");
    expect(weak!.textContent).toContain("0 bound");
    // The unbundled remainder is visible at the bottom, not hidden.
    expect(sidebar.textContent).toContain("sr:SR-999");
    const groups = Array.from(sidebar.querySelectorAll(".scope-group"));
    expect(groups.map((g) => (g as HTMLElement).dataset.readiness ?? (g as HTMLElement).dataset.group))
      .toEqual(["weak", "medium", "strong", "unbundled"]);
  });

  test("sidebar expands weak and collapses medium/strong but count-bearing titles", async () => {
    const doc = await renderWithHealth(FEATURE_HEALTH);
    const sidebar = doc.querySelector("#scopeList")!;
    const weak = sidebar.querySelector('[data-readiness="weak"]') as HTMLElement;
    const medium = sidebar.querySelector('[data-readiness="medium"]') as HTMLElement;
    const strong = sidebar.querySelector('[data-readiness="strong"]') as HTMLElement;
    // Weak is expanded by default; Medium/Strong are collapsed but their
    // title carries the group's bundle count.
    expect(weak.dataset.expanded).toBe("true");
    expect((weak.querySelector(".scope-row") as HTMLElement).style.display).not.toBe("none");
    expect(medium.dataset.expanded).toBe("false");
    expect((medium.querySelector(".scope-row") as HTMLElement).style.display).toBe("none");
    expect(strong.dataset.expanded).toBe("false");
    expect(strong.querySelector(".scope-group-title")!.textContent).toMatch(/Strong/);
    expect(strong.querySelector(".scope-group-title")!.textContent).toContain("· 1");
    // A click on a collapsed title expands its group (progressive disclosure).
    (strong.querySelector(".scope-group-title") as HTMLElement).click();
    expect(strong.dataset.expanded).toBe("true");
    expect((strong.querySelector(".scope-row") as HTMLElement).style.display).not.toBe("none");
  });

  test("search resolves a bundle label to its bundle scope", async () => {
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/scope") return jsonResponse(SCOPE_LIST);
      if (url.pathname === "/api/system/health") return jsonResponse(FEATURE_HEALTH);
      if (url.pathname === "/api/system/brief")
        return jsonResponse({ scope: { kind: "bundle", ref: "bundle:b1" }, claims: [], degraded: false, degraded_reasons: [] });
      if (url.pathname === "/api/system/matrix")
        return jsonResponse({ scope: { kind: "bundle", ref: "bundle:b1" }, rows: [] });
      if (url.pathname === "/api/system/timeline")
        return jsonResponse({ scope: { kind: "bundle", ref: "bundle:b1" }, events: [], degraded: false, degraded_reasons: [] });
      if (url.pathname === "/api/system/guide")
        return jsonResponse({ scope: { kind: "bundle", ref: "bundle:b1" }, sections: [] });
      throw new Error(`unmocked fetch: ${String(input)}`);
    });
    const dom = new JSDOM(renderSystemPageHtml(), {
      runScripts: "dangerously",
      resources: "usable",
      url: "http://localhost/system",
      beforeParse(window) {
        (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
      },
    });
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("healthSummary")!.textContent).not.toBe(""),
      { timeout: 2000, interval: 10 },
    );
    const doc = dom.window.document;
    const input = doc.querySelector("#scopeFilter") as HTMLInputElement;
    input.value = "B1";
    input.dispatchEvent(new dom.window.Event("input"));
    doc.querySelector<HTMLElement>("#searchGo")!.click();
    await vi.waitFor(
      () => expect(doc.getElementById("scopeHeader")!.textContent).toBe("bundle:b1"),
      { timeout: 2000, interval: 10 },
    );
    expect(dom.window.location.search).toContain("scope=bundle%3Ab1");
  });

  // SP-B Task 7: search resolves a bare artifact ref by posting the exact
  // ref (SR-137 -> sr:SR-137) to the docs server, which answers with the
  // scope it opens. The browser never invents matching logic.
  test("search resolves a bare artifact ref and posts the exact ref", async () => {
    let resolveCall: string | undefined;
    const fetchMock = vi.fn((input: string | URL) => {
      const url = new URL(String(input), "http://localhost/");
      if (url.pathname === "/api/system/scope") return jsonResponse(SCOPE_LIST);
      if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
      if (url.pathname === "/api/system/brief" || url.pathname === "/api/system/matrix" ||
          url.pathname === "/api/system/timeline" || url.pathname === "/api/system/guide") {
        return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-137" }, claims: [], rows: [], events: [], sections: [], degraded: false, degraded_reasons: [] });
      }
      resolveCall = String(input);
      return jsonResponse({ scope: { kind: "sr", ref: String(input) } });
    });
    const dom = new JSDOM(renderSystemPageHtml(), {
      runScripts: "dangerously",
      resources: "usable",
      url: "http://localhost/system",
      beforeParse(window) {
        (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
      },
    });
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("healthSummary")!.textContent).not.toBe(""),
      { timeout: 2000, interval: 10 },
    );
    const doc = dom.window.document;
    const input = doc.querySelector("#scopeFilter") as HTMLInputElement;
    input.value = "SR-137";
    input.dispatchEvent(new dom.window.Event("input"));
    // Go resolves the exact ref and opens the scope it maps to.
    doc.querySelector<HTMLElement>("#searchGo")!.click();
    await vi.waitFor(() => expect(resolveCall).toBe("sr:SR-137"), { timeout: 2000, interval: 10 });
    await vi.waitFor(
      () => expect(doc.getElementById("scopeHeader")!.textContent).toBe("sr:SR-137"),
      { timeout: 2000, interval: 10 },
    );
  });
});
