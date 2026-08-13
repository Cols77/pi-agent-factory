// SP-B Task 8 — member-of affordance on requirement/task pages.
//
// A requirement (or task) page now lists every bundle that contains it, so a
// shared requirement reads as shared instead of looking like it belongs only to
// whichever feature you happened to open. The `member_of` list is computed in
// Python (`queries.query_brief` + `bundles.bundles_containing`) and rendered
// here as a `#memberOf` text node -- absent on other scope kinds.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderSystemPageHtml } from "../src/system-page.js";

const HEALTH = {
  health: { classes: [], satisfied: 0, expected: 0, percent: 0, dangling: 0, deferred: 0, proposed: 0 },
  coverage: { total: 1, bundled: 1, unbundled: [], kinds: [] },
  bundles: [],
  unbundled: {},
  ordering_available: true,
  sr_listed: false,
  degraded: [],
};

function jsonResponse(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

async function loadSrPage(): Promise<JSDOM> {
  const fetchMock = vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
    if (url.pathname === "/api/system/scope")
      return jsonResponse({ scopes: [{ kind: "bundle", ref: "bundle:b1" }, { kind: "bundle", ref: "bundle:gamma" }], errors: [] });
    if (url.pathname === "/api/system/brief")
      return jsonResponse({
        scope: { kind: "sr", ref: "sr:SR-001" },
        member_of: ["b1", "gamma"],
        claims: [],
        degraded: false,
        degraded_reasons: [],
      });
    if (url.pathname === "/api/system/matrix")
      return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, rows: [] });
    if (url.pathname === "/api/system/timeline")
      return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, events: [], degraded: false, degraded_reasons: [] });
    if (url.pathname === "/api/system/guide")
      return jsonResponse({ scope: { kind: "sr", ref: "sr:SR-001" }, sections: [] });
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
  const dom = new JSDOM(renderSystemPageHtml(), {
    runScripts: "dangerously",
    resources: "usable",
    url: "http://localhost/system?scope=sr%3ASR-001",
    beforeParse(window) {
      (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
    },
  });
  await vi.waitFor(
    () => expect(dom.window.document.getElementById("memberOf")).not.toBeNull(),
    { timeout: 2000, interval: 10 },
  );
  return dom;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("member-of bundles on a requirement page", () => {
  test("requirement brief lists its member bundles", async () => {
    const dom = await loadSrPage();
    const member = dom.window.document.getElementById("memberOf");
    expect(member).not.toBeNull();
    expect(member!.textContent).toContain("b1");
    expect(member!.textContent).toContain("gamma");
  });
});
