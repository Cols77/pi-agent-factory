// IMPORTANT 6: `system-page.ts`'s ~330-line client-side script was only ever
// grepped against its own source text (system-page.test.ts) -- no test
// actually executed it against a DOM, so a runtime error in `renderClaim`/
// `renderTimeline`/`loadScope` could ship undetected, and the "renders
// every claim kind distinctly" / "never hides missing rows" guarantees were
// unverified. This file evaluates the real script (via jsdom's
// `runScripts: "dangerously"`, the same document `renderSystemPageHtml()`
// returns) against the existing BRIEF/MATRIX/TIMELINE/GUIDE fixtures and
// asserts on the resulting DOM.
//
// jsdom was not already a dependency of this package (or its lockfile) --
// added here as a devDependency to make this test possible. Flagged in the
// fix-wave report rather than assumed approved.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderSystemPageHtml } from "../src/system-page.js";

const HEALTH = {
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

const BRIEF = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  claims: [
    {
      kind: "recorded",
      text: "Evidence lifecycle",
      citations: [{ kind: "bundle", path: "bundles/evidence-lifecycle.yaml", sha256: "a".repeat(64), anchor: null }],
      spans: [],
      freshness: { state: "fresh", reason: null, dependencies: [] },
    },
    {
      kind: "missing",
      text: "spec:2026-08-08-does-not-exist.md",
      citations: [],
      spans: [],
      freshness: { state: "n/a", reason: "bundle member does not exist in repo", dependencies: [] },
    },
    {
      kind: "derived",
      text: "SR-001: validation report is unreadable (corrupt or unparseable)",
      citations: [{ kind: "validation", path: "validation/validation-report.json", sha256: "c".repeat(64), anchor: null }],
      spans: [],
      freshness: { state: "degraded", reason: "validation report exists but could not be read", dependencies: [] },
    },
    {
      kind: "synthesized",
      text: 'This guide covers the declared bundle "Evidence lifecycle".',
      citations: [
        { kind: "bundle", path: "bundles/evidence-lifecycle.yaml", sha256: "a".repeat(64), anchor: null },
        { kind: "requirement", path: "requirements\\SR-034.md", sha256: "d".repeat(64), anchor: null },
      ],
      spans: [{ text: "Evidence lifecycle", citation_index: 0 }],
      freshness: { state: "fresh", reason: null, dependencies: [] },
    },
  ],
  degraded: true,
  degraded_reasons: ["1 declared member(s) do not exist in the repo"],
};

const MATRIX = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  rows: [
    {
      subject: { kind: "sr", ref: "sr:SR-001" },
      status: "unknown",
      evidence: ["validation/validation-report.json"],
      freshness: { state: "degraded", reason: "validation report exists but could not be read", dependencies: [] },
      summary: "validation report unreadable",
    },
  ],
};

const TIMELINE = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  events: [
    {
      at: null,
      sequence: 1,
      actor: "not-recorded",
      action: "not-recorded",
      subject: { kind: "task", ref: "task:T-001" },
      citation: { kind: "decision", path: "evidence/runs/run-1.json", sha256: "b".repeat(64), anchor: "reviews[0]" },
      freshness: { state: "degraded", reason: "no actor recorded", dependencies: [] },
    },
  ],
  degraded: true,
  degraded_reasons: ["1 event(s) do not have a recorded actor"],
};

const GUIDE = {
  scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" },
  sections: [
    {
      kind: "synthesized",
      text: 'This guide covers the declared bundle "Evidence lifecycle".',
      citations: [{ kind: "bundle", path: "bundles/evidence-lifecycle.json", sha256: "a".repeat(64), anchor: null }],
      spans: [{ text: "Evidence lifecycle", citation_index: 0 }],
      freshness: { state: "fresh", reason: null, dependencies: [] },
    },
    {
      kind: "derived",
      text: "- [missing] (n/a) task:T-001",
      citations: [],
      spans: [],
      freshness: { state: "degraded", reason: null, dependencies: [] },
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

function mockFetch(guideFails = false) {
  return vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/health") return jsonResponse(HEALTH);
    if (url.pathname === "/api/system/brief") return jsonResponse(BRIEF);
    if (url.pathname === "/api/system/matrix") return jsonResponse(MATRIX);
    if (url.pathname === "/api/system/timeline") return jsonResponse(TIMELINE);
    if (url.pathname === "/api/system/guide") {
      return guideFails
        ? jsonResponse({ error: "synthesis failed", kind: "RuntimeError" }, 503)
        : jsonResponse(GUIDE);
    }
    if (url.pathname === "/api/system/labels") return jsonResponse({ labels: {}, aliases: {}, degraded: [] });
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}

/** Loads the real page document into jsdom, with `fetch` wired to the
 * fixtures above, and waits for the page's own async bootstrap
 * (`loadScopes()` then, when `?scope=` is present, `loadScope()`) to finish
 * populating the DOM before handing control back to the test. */
async function loadPage(opts: { scope?: string; guideFails?: boolean } = {}): Promise<JSDOM> {
  const html = renderSystemPageHtml();
  const url = opts.scope
    ? `http://localhost/system?scope=${encodeURIComponent(opts.scope)}`
    : "http://localhost/system";
  const fetchMock = mockFetch(opts.guideFails ?? false);
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    resources: "usable",
    url,
    // Injects fetch before the document's inline <script> executes --
    // the script starts fetching immediately as an IIFE, so `window.fetch`
    // must already exist by the time jsdom runs it during parsing.
    beforeParse(window) {
      (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
    },
  });
  // The page's bootstrap is async (network round trips via microtasks/
  // macrotasks); poll until the scope list has rendered, which only
  // happens after loadScopes() resolves -- the first thing the IIFE does.
  await vi.waitFor(
    () => {
      const list = dom.window.document.getElementById("scopeList");
      expect(list?.children.length).toBeGreaterThan(0);
    },
    { timeout: 2000, interval: 10 },
  );
  if (opts.scope) {
    await vi.waitFor(
      () => {
        expect(dom.window.document.getElementById("content")?.hidden).toBe(false);
      },
      { timeout: 2000, interval: 10 },
    );
  }
  return dom;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("system-page.ts client script, executed against a real DOM", () => {
  test("renders the feature-first sidebar from the health payload", async () => {
    const dom = await loadPage();
    const doc = dom.window.document;
    const weak = doc.querySelector('#scopeList [data-readiness="weak"]');
    expect(weak).not.toBeNull();
    expect(weak?.textContent).toContain("Evidence lifecycle");
    // The readiness label always renders beside its counts.
    expect(weak?.textContent).toContain("1 SR");
    // The unbundled remainder is visible at the bottom, not hidden.
    expect(doc.querySelector('#scopeList [data-group="unbundled"]')?.textContent).toContain("sr:SR-999");
  });

  test("renders every brief claim kind distinctly, and never hides the missing row", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const doc = dom.window.document;
    const claims = doc.querySelectorAll("#panelBrief .claim");
    expect(claims.length).toBe(BRIEF.claims.length);

    const kinds = Array.from(claims).map((el) => el.querySelector(".badge")?.textContent);
    expect(kinds).toEqual(["recorded", "missing", "derived", "synthesized"]);

    // The missing row is present, visible, and labeled -- not filtered out.
    const missingClaim = doc.querySelector("#panelBrief .claim-missing");
    expect(missingClaim).not.toBeNull();
    expect(missingClaim?.querySelector(".claim-text")?.textContent).toBe(
      "spec:2026-08-08-does-not-exist.md",
    );
  });

  test("text-labels freshness state for every claim, not colour alone", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const doc = dom.window.document;
    const claims = doc.querySelectorAll("#panelBrief .claim");
    const states = Array.from(claims).map((el) => el.querySelector(".freshness")?.textContent);
    expect(states).toEqual(["fresh", "n/a", "degraded", "fresh"]);
  });

  test("renders the brief degraded banner from degraded_reasons, not an invented string", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const doc = dom.window.document;
    const banner = doc.querySelector("#panelBrief .degraded-banner");
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain("1 declared member(s) do not exist in the repo");
  });

  test("renders a synthesized claim's verbatim span", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const doc = dom.window.document;
    const synthesized = doc.querySelector("#panelBrief .claim-synthesized");
    expect(synthesized?.querySelector(".span")?.textContent).toContain("Evidence lifecycle");
  });

  test("groups citations and quoted spans in a counted native disclosure", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const claim = dom.window.document.querySelector("#panelBrief .claim-synthesized");
    const evidence = claim?.querySelector(".evidence-disclosure");
    expect(evidence?.tagName).toBe("DETAILS");
    expect(evidence?.querySelector("summary")?.textContent).toBe("Evidence · 3");
    expect(evidence?.textContent).toContain("requirements\\SR-034.md");
  });

  test("renders the matrix row with its status and freshness, including the unknown status", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const doc = dom.window.document;
    const row = doc.querySelector("#panelMatrix .matrix-row");
    expect(row?.querySelector(".matrix-subject .chip-id")?.textContent).toBe("sr:SR-001");
    expect(row?.querySelector(".matrix-subject .ref-chip")?.className).toContain("is-absent");
    expect(row?.querySelector(".matrix-status")?.textContent).toContain("unknown");
    expect(row?.querySelector(".matrix-summary")?.textContent).toBe("validation report unreadable");
    expect(row).not.toBeNull();
    expect(row?.querySelector(".badge")?.textContent).toBe("unknown");
    expect(row?.querySelector(".freshness")?.textContent).toBe("degraded");
    expect(row?.querySelector(".claim-text")?.textContent).toBe("validation report unreadable");
  });

  test("renders the timeline event and its degraded banner from degraded_reasons", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const doc = dom.window.document;
    const event = doc.querySelector("#panelTimeline .timeline-event");
    expect(event).not.toBeNull();
    expect(event?.textContent).toContain("not-recorded");
    expect(event?.textContent).toContain("sequence=1");
    const banner = doc.querySelector("#panelTimeline .degraded-banner");
    expect(banner?.textContent).toContain("1 event(s) do not have a recorded actor");
  });

  test("renders every guide section as a claim, including a derived bullets section", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const doc = dom.window.document;
    const sections = doc.querySelectorAll("#panelGuide .claim");
    expect(sections.length).toBe(2);
    const kinds = Array.from(sections).map((el) => el.querySelector(".badge")?.textContent);
    expect(kinds).toEqual(["synthesized", "derived"]);
  });

  test("a quoted span names the document it was copied from, not a citation index", async () => {
    // "(citation 0)" is a payload array index; a reader needs to know WHICH
    // source the words came from for the quote to mean anything.
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const span = dom.window.document.querySelector("#panelBrief .span");
    expect(span?.textContent).toContain("bundles/evidence-lifecycle.yaml");
    expect(span?.textContent).toContain('"Evidence lifecycle"');
    expect(span?.textContent).not.toContain("citation 0");
  });

  test("falls back to a plain notice, never a crash, when the guide fetch fails", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle", guideFails: true });
    const doc = dom.window.document;
    expect(doc.querySelectorAll("#panelGuide .claim").length).toBe(0);
    expect(doc.getElementById("panelGuide")?.textContent).toContain("Guide synthesis is unavailable");
    // Brief/matrix/timeline are unaffected by the guide-only failure.
    expect(doc.querySelectorAll("#panelBrief .claim").length).toBe(BRIEF.claims.length);
  });
});
