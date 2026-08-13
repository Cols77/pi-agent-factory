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
});
