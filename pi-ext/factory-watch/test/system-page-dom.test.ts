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
import { PANELS_DATA } from "../src/system-vocabulary-data.js";

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

// No test in this file exercised /api/system/traversal before Fix round 1 --
// it fell through to mockFetch's `unmocked fetch` throw, which loadScope()'s
// try/catch swallows into "Traversal is unavailable for this scope." (see
// system-bootstrap.ts:634-648). That behaviour is preserved by default here
// (DEFAULT_TRAVERSAL renders four genuinely-empty steps, each "Not
// recorded" -- never an error, and no prior test asserted on the error
// text either) while letting tests opt into real traversal payloads via
// opts.traversal, the same style Task 11 established for opts.health.
const DEFAULT_TRAVERSAL = { requirement: [], tasks: [], design: [], files: [] };
const DEFAULT_LABELS = { labels: {}, aliases: {}, degraded: [] };

function mockFetch(
  guideFails = false,
  health: unknown = HEALTH,
  traversal: unknown = DEFAULT_TRAVERSAL,
  labels: unknown = DEFAULT_LABELS,
  labelsUnavailable = false,
) {
  return vi.fn((input: string | URL) => {
    const url = new URL(String(input), "http://localhost/");
    if (url.pathname === "/api/system/health") return jsonResponse(health);
    if (url.pathname === "/api/system/brief") return jsonResponse(BRIEF);
    if (url.pathname === "/api/system/matrix") return jsonResponse(MATRIX);
    if (url.pathname === "/api/system/timeline") return jsonResponse(TIMELINE);
    if (url.pathname === "/api/system/traversal") return jsonResponse(traversal);
    if (url.pathname === "/api/system/guide") {
      return guideFails
        ? jsonResponse({ error: "synthesis failed", kind: "RuntimeError" }, 503)
        : jsonResponse(GUIDE);
    }
    if (url.pathname === "/api/system/labels") {
      // Task 12: a failed labels fetch (not merely an empty index) -- setLabels
      // resolves this to null and the "label index unavailable" chip treatment.
      return labelsUnavailable
        ? jsonResponse({ error: "unavailable" }, 503)
        : jsonResponse(labels);
    }
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}

/** Loads the real page document into jsdom, with `fetch` wired to the
 * fixtures above, and waits for the page's own async bootstrap
 * (`loadScopes()` then, when `?scope=` is present, `loadScope()`) to finish
 * populating the DOM before handing control back to the test. */
async function loadPage(
  opts: {
    scope?: string;
    guideFails?: boolean;
    health?: unknown;
    traversal?: unknown;
    labels?: unknown;
    labelsUnavailable?: boolean;
  } = {},
): Promise<JSDOM> {
  const html = renderSystemPageHtml();
  const url = opts.scope
    ? `http://localhost/system?scope=${encodeURIComponent(opts.scope)}`
    : "http://localhost/system";
  const fetchMock = mockFetch(
    opts.guideFails ?? false,
    opts.health ?? HEALTH,
    opts.traversal ?? DEFAULT_TRAVERSAL,
    opts.labels ?? DEFAULT_LABELS,
    opts.labelsUnavailable ?? false,
  );
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

  // Task 11: renderHealthSummary is a closure inside systemBootstrap, not
  // exported -- exercised only through the real page via loadPage().
  test("health class labels render readable text with the raw name as metadata", async () => {
    const dom = await loadPage({
      health: {
        health: {
          classes: [{ name: "task->plan", satisfied: 21, expected: 21, exempt: 0 }],
          satisfied: 21, expected: 21, percent: 100, dangling: 0, deferred: 0, proposed: 0,
        },
        coverage: { total: 0, bundled: 0, unbundled: 0, kinds: [] },
        bundles: [], unbundled: { sr: ["sr:SR-999"] }, ordering_available: true, sr_listed: false, degraded: [],
      },
    });
    const metric = dom.window.document.querySelector(".health-metric")!;
    expect(metric.querySelector(".health-metric-label")?.textContent).toBe("Tasks linked to a plan");
    expect(metric.querySelector(".health-metric-raw")?.textContent).toBe("task->plan");
  });

  test("a health class with no VOCABULARY entry falls back to its raw name as the label", async () => {
    const dom = await loadPage({
      health: {
        health: {
          classes: [{ name: "not-a-real-class", satisfied: 1, expected: 1, exempt: 0 }],
          satisfied: 1, expected: 1, percent: 100, dangling: 0, deferred: 0, proposed: 0,
        },
        coverage: { total: 0, bundled: 0, unbundled: 0, kinds: [] },
        bundles: [], unbundled: { sr: ["sr:SR-999"] }, ordering_available: true, sr_listed: false, degraded: [],
      },
    });
    const metric = dom.window.document.querySelector(".health-metric")!;
    expect(metric.querySelector(".health-metric-label")?.textContent).toBe("not-a-real-class");
    expect(metric.querySelector(".health-metric-raw")?.textContent).toBe("not-a-real-class");
  });

  // Task 5 (legibility inc2): the landing states what the project is made
  // of, above the metric tiles, badged `derived` (reused withGloss) so its
  // provenance is as visible as any other claim's. `HEALTH` carries no
  // `shape` key at all -- the two tests above already exercise that guard
  // implicitly by rendering without it -- so this test opts a real `shape`
  // payload in explicitly.
  test("the shape sentence renders above the metric tiles with a derived badge", async () => {
    const dom = await loadPage({
      health: {
        ...HEALTH,
        shape: {
          sentence:
            "This project is described by 2 requirements, grouped into 1 feature. " +
            "1 task implements them, and 0 of those requirements have a passing validation.",
          parts: { requirements: 2, features: 1, tasks: 1, validated: 0 },
        },
      },
    });
    const doc = dom.window.document;
    const shapeEl = doc.querySelector("#healthSummary .shape-sentence");
    expect(shapeEl?.textContent).toContain(
      "This project is described by 2 requirements, grouped into 1 feature."
    );
    // It must precede the metric tiles, not follow them.
    expect(shapeEl?.nextElementSibling?.className).toContain("health-overall");
    expect(shapeEl?.querySelector(".badge")?.textContent).toBe("derived");
  });

  // Task 5 (legibility inc2): the denominator rule is the definition's
  // FIRST sentence only -- "SR satisfied" cites figures as "(e.g. 181)",
  // which would truncate mid-abbreviation on a naive split at every period.
  test("a metric tile's denominator rule stops at the real sentence boundary, not at 'e.g.'", async () => {
    const dom = await loadPage({
      health: {
        health: {
          classes: [{ name: "SR satisfied", satisfied: 3, expected: 5, exempt: 0 }],
          satisfied: 3, expected: 5, percent: 60, dangling: 0, deferred: 0, proposed: 0,
        },
        coverage: { total: 0, bundled: 0, unbundled: 0, kinds: [] },
        bundles: [], unbundled: { sr: ["sr:SR-999"] }, ordering_available: true, sr_listed: false, degraded: [],
      },
    });
    const metric = dom.window.document.querySelector(".health-metric")!;
    const rule = metric.querySelector(".health-metric-rule")?.textContent ?? "";
    expect(rule).toBe(
      "Denominator: every `sr` node in the trace graph -- the full repo-wide count, " +
      "including proposed SRs with no decided binding yet, which is why this denominator " +
      "(e.g. 181) is much larger than `SR validated`'s (e.g. 43): proposed SRs keep their " +
      "`SR satisfied` slot (a requirement with no task is a gap whether or not it is bound) " +
      "but lose their `SR validated` slot entirely (there is nothing to validate yet)."
    );
    expect(rule).not.toContain("Satisfied: at least one task");
  });

  // Fix round 1, Task 10: renderTraversal is a closure inside systemBootstrap,
  // not exported -- exercised only through the real page via loadPage(), the
  // same shape Task 11 used for renderHealthSummary above. boundedList's
  // cap/disclosure behaviour is already covered generically in
  // system-comprehension.test.ts; these two assert the real wiring at the
  // traversal-spine call site (system-bootstrap.ts:757-781), which had no
  // direct test.
  //
  // Title resolution is intentionally NOT asserted here: these traversal
  // fixtures below never seed a matching LABELS entry for the refs they use,
  // so every chip resolves through the real "not in the label index" path
  // (system-comprehension.ts's refChip absent branch) regardless. Title
  // resolution against a real labels payload IS covered elsewhere in this
  // file (Task 12 wired `setLabels` at system-bootstrap.ts:1314, awaited
  // before health) -- see "the scope heading is the title, with the ref as
  // metadata" and "a recorded description renders as the scope's lead
  // paragraph" below.
  test("the traversal spine caps a long requirement list at five chips with a real +N more disclosure", async () => {
    const refs = Array.from({ length: 7 }, (_, i) => `sr:SR-${101 + i}`);
    const dom = await loadPage({
      scope: "bundle:evidence-lifecycle",
      traversal: { requirement: refs, tasks: [], design: [], files: [] },
    });
    const doc = dom.window.document;
    const steps = Array.from(doc.querySelectorAll("#traversalPath .trace-spine-step"));
    const reqStep = steps.find((step) => step.querySelector(".trace-spine-label")?.textContent === "Requirement")!;
    expect(reqStep).toBeTruthy();
    const list = reqStep.querySelector(".trace-spine-value > .bounded-list")!;
    expect(list).toBeTruthy();
    const directChips = list.querySelectorAll(":scope > .ref-chip");
    expect(directChips.length).toBe(5);
    expect(Array.from(directChips).map((chip) => chip.querySelector(".chip-id")?.textContent)).toEqual([
      "sr:SR-101", "sr:SR-102", "sr:SR-103", "sr:SR-104", "sr:SR-105",
    ]);
    // Every direct chip is the real absent-ref rendering (no title index
    // wired up yet), not a guessed or blank label.
    expect(Array.from(directChips).every((chip) => chip.className.includes("is-absent"))).toBe(true);
    expect(directChips[0]!.querySelector(".chip-title")?.textContent).toBe("not in the label index");
    const details = list.querySelector(":scope > details")!;
    expect(details).toBeTruthy();
    expect(details.querySelector("summary")?.textContent).toBe("+ 2 more");
    const overflowChips = details.querySelectorAll(".ref-chip");
    expect(overflowChips.length).toBe(2);
    expect(Array.from(overflowChips).map((chip) => chip.querySelector(".chip-id")?.textContent)).toEqual([
      "sr:SR-106", "sr:SR-107",
    ]);
  });

  test("an empty traversal step renders \"Not recorded\", never an empty bounded list", async () => {
    const dom = await loadPage({
      scope: "bundle:evidence-lifecycle",
      traversal: { requirement: ["sr:SR-001"], tasks: ["task:T-001"], design: [], files: ["src/example.ts"] },
    });
    const doc = dom.window.document;
    const steps = Array.from(doc.querySelectorAll("#traversalPath .trace-spine-step"));
    const designStep = steps.find((step) => step.querySelector(".trace-spine-label")?.textContent === "Design")!;
    expect(designStep).toBeTruthy();
    const value = designStep.querySelector(".trace-spine-value")!;
    expect(value.querySelector(".bounded-list")).toBeNull();
    // The literal "Not recorded" text node is still present verbatim...
    const notRecordedNode = Array.from(value.childNodes).find(
      (node) => node.nodeType === 3 && node.textContent === "Not recorded"
    );
    expect(notRecordedNode).toBeTruthy();
    // ...paired with a Next step block (Task 13: REMEDIATION.states.no_traversal_step),
    // so the gap it names is never left as a bare, unactionable sentence.
    const nextStep = value.querySelector(".next-step");
    expect(nextStep).not.toBeNull();
    expect(nextStep?.textContent).toContain("NEXT STEP");
    // Sibling steps with data are unaffected by the empty one.
    const filesStep = steps.find((step) => step.querySelector(".trace-spine-label")?.textContent === "Files")!;
    expect(filesStep.querySelector(".trace-spine-value .bounded-list")).not.toBeNull();
  });

  // Task 3 (legibility increment 2): the four-column grid becomes a
  // full-width vertical ladder -- one row per step, its count right-aligned
  // on the label's rule, answerable without expanding the disclosure.
  test("the ladder is one full-width row per step with its count on the rule", async () => {
    const dom = await loadPage({
      scope: "bundle:b1",
      traversal: {
        requirement: ["sr:SR-030", "sr:SR-033", "sr:SR-038", "sr:SR-086", "sr:SR-087", "sr:SR-088", "sr:SR-089"],
        tasks: [], design: [], files: [],
      },
    });
    const doc = dom.window.document;
    const steps = doc.querySelectorAll(".trace-spine-step");
    expect(steps.length).toBe(4);
    expect(steps[0]!.querySelector(".trace-spine-count")?.textContent).toBe("7");
    expect(steps[0]!.querySelectorAll(".bounded-list > .ref-chip").length).toBe(5);
    expect(steps[0]!.querySelector("details summary")?.textContent).toBe("+ 2 more");
  });

  test("an empty step reads Not recorded and carries its next step inline", async () => {
    const dom = await loadPage({
      scope: "bundle:b1",
      traversal: { requirement: ["sr:SR-030"], tasks: [], design: [], files: [] },
    });
    const step = dom.window.document.querySelectorAll(".trace-spine-step")[2]!;
    expect(step.textContent).toContain("Not recorded");
    expect(step.querySelector(".next-step")).not.toBeNull();
    expect(step.querySelector(".trace-spine-count")?.textContent).toBe("0");
  });

  test("the Vocabulary header control opens a workspace view grouped by term group, with a Back to the landing page", async () => {
    const dom = await loadPage();
    const doc = dom.window.document;
    const toggle = doc.getElementById("vocabularyToggle") as HTMLButtonElement;
    expect(toggle).not.toBeNull();
    toggle.click();
    expect(doc.getElementById("vocabularyPanel")?.hidden).toBe(false);
    expect(doc.getElementById("landingPanel")?.hidden).toBe(true);
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    // Grouped by `group`, with the real badge rendered beside its definition.
    const groups = doc.querySelectorAll("#vocabularyGroups .vocab-group-title");
    expect(groups.length).toBeGreaterThan(1);
    const claimKindEntry = Array.from(doc.querySelectorAll("#vocabularyGroups .vocab-entry"))
      .find((el) => el.querySelector(".badge")?.textContent === "recorded");
    expect(claimKindEntry?.querySelector(".vocab-definition")?.textContent).toContain("verbatim");
    // Clicking again returns to the landing page.
    toggle.click();
    expect(doc.getElementById("vocabularyPanel")?.hidden).toBe(true);
    expect(doc.getElementById("landingPanel")?.hidden).toBe(false);
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });

  // Task 12: systemBootstrap now fetches /api/system/labels (via setLabels)
  // before health, so setScopeHeading's title inversion has real data to
  // read. setScopeHeading is a closure inside systemBootstrap -- exercised
  // only through the real page via loadPage(), same shape as Task 11's
  // renderHealthSummary/renderTraversal tests above.
  test("the scope heading is the title, with the ref as metadata", async () => {
    const dom = await loadPage({
      scope: "task:T-001",
      labels: {
        labels: {
          "task:T-001": {
            ref: "task:T-001", id: "T-001", kind: "task", title: "Load skills",
            description: null, description_source: null, deferral_reason: null,
            status: "done", relations: {}, path: "tasks/T-001.md", scope_href: null,
          },
        },
        aliases: { "task:T-001": "task:T-001" },
        degraded: [],
      },
    });
    const doc = dom.window.document;
    expect(doc.getElementById("scopeHeader")?.textContent).toBe("Load skills");
    expect(doc.getElementById("scopeRef")?.textContent).toBe("task:T-001");
  });

  // Task 12: a recorded description renders as the lead paragraph under the
  // ref metadata when the label index has one.
  test("a recorded description renders as the scope's lead paragraph", async () => {
    const dom = await loadPage({
      scope: "sr:SR-121",
      labels: {
        labels: {
          "sr:SR-121": {
            ref: "sr:SR-121", id: "SR-121", kind: "sr", title: "Battery-aware return",
            description: "The rover must return to base before battery falls below 15%.",
            description_source: "statement", deferral_reason: null,
            status: null, relations: {}, path: "requirements/SR-121.md", scope_href: null,
          },
        },
        aliases: { "sr:SR-121": "sr:SR-121" },
        degraded: [],
      },
    });
    const doc = dom.window.document;
    expect(doc.getElementById("scopeHeader")?.textContent).toBe("Battery-aware return");
    expect(doc.getElementById("scopeDescription")?.textContent).toBe(
      "The rover must return to base before battery falls below 15%.",
    );
  });

  // Task 12: "issue the labels fetch before health and await it in both
  // paths" -- the failure path. A non-ok /api/system/labels response resolves
  // to null; setLabels(null) leaves LABELS/ALIASES empty and marks the index
  // unavailable, so every chip degrades to "label index unavailable" rather
  // than the page blanking.
  test("an unavailable labels endpoint degrades chips instead of blanking the page", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle", labelsUnavailable: true });
    const doc = dom.window.document;
    // The rest of the page still renders -- it degrades, it never blanks.
    expect(doc.querySelectorAll("#panelBrief .claim").length).toBe(BRIEF.claims.length);
    const chip = doc.querySelector("#panelMatrix .matrix-subject .ref-chip")!;
    expect(chip.className).toContain("is-absent");
    expect(chip.querySelector(".chip-title")?.textContent).toBe("label index unavailable");
  });

  // Fix round 1 (Task 12): sidebar rows render the label and its readiness
  // counts as two separate block-level elements, never one wrapping
  // paragraph -- previously untested.
  test("sidebar rows render the label and its counts as two separate blocks", async () => {
    const dom = await loadPage();
    const doc = dom.window.document;
    const row = doc.querySelector('#scopeList .scope-item[data-kind="bundle"]') as HTMLElement;
    expect(row).not.toBeNull();
    const label = row.querySelector(":scope > .scope-label");
    const counts = row.querySelector(":scope > .readiness-counts");
    expect(label).not.toBeNull();
    expect(counts).not.toBeNull();
    expect(label?.textContent).toContain("Evidence lifecycle");
    expect(counts?.textContent).toContain("1 SR");
    // Exactly the two block children -- no stray text node makes it one
    // wrapping paragraph in disguise.
    expect(row.children.length).toBe(2);
    expect(row.childNodes.length).toBe(row.children.length);
  });

  // Fix round 1 (Task 12): the dismissible landing orientation strip --
  // previously untested. Shows by default, dismisses via "Hide this",
  // persists the single localStorage key, and a fresh load with that key
  // already set stays hidden.
  test("the orientation strip shows once, dismisses via \"Hide this\", and persists across a fresh load", async () => {
    const dom = await loadPage();
    const doc = dom.window.document;
    const strip = doc.getElementById("orientationStrip") as HTMLElement;
    expect(strip).not.toBeNull();
    expect(strip.hidden).toBe(false);
    const dismiss = doc.getElementById("orientationDismiss") as HTMLButtonElement;
    expect(dismiss?.textContent).toBe("Hide this");
    dismiss.click();
    expect(strip.hidden).toBe(true);
    expect(dom.window.localStorage.getItem("system-nav-orientation-dismissed")).toBe("1");

    // A fresh page load that already carries the dismissed key keeps the
    // strip hidden from the start -- the one localStorage key persisting.
    const html = renderSystemPageHtml();
    const fetchMock2 = mockFetch();
    const dom2 = new JSDOM(html, {
      runScripts: "dangerously",
      resources: "usable",
      url: "http://localhost/system",
      beforeParse(window) {
        (window as unknown as { fetch: typeof fetch }).fetch = fetchMock2 as unknown as typeof fetch;
        window.localStorage.setItem("system-nav-orientation-dismissed", "1");
      },
    });
    await vi.waitFor(() => {
      expect(dom2.window.document.getElementById("scopeList")?.children.length).toBeGreaterThan(0);
    });
    expect((dom2.window.document.getElementById("orientationStrip") as HTMLElement).hidden).toBe(true);
  });

  // Fix round 1 (Task 13): the readiness modifier must sit on the CONTAINER,
  // matching the established pattern (feature-row/scope-item) -- the CSS is
  // descendant-scoped (`.readiness-strong .feature-readiness`, `.readiness-medium
  // .feature-readiness`, system-shell.ts). Without it every rail reading fell
  // through to the base .feature-readiness colour (the weak colour) regardless
  // of the actual value. jsdom doesn't apply the real stylesheet, so this
  // asserts the class is present -- the thing that actually drives the colour
  // -- rather than a computed colour, which keeps it robust.
  test.each(["strong", "medium", "weak"] as const)(
    "the context rail's readiness section carries readiness-%s on its container",
    async (readiness) => {
      const dom = await loadPage({
        scope: "bundle:evidence-lifecycle",
        health: { ...HEALTH, bundles: [{ ...HEALTH.bundles[0], readiness }] },
      });
      const doc = dom.window.document;
      const readinessRow = doc.querySelector("#contextRail .context-rail-readiness");
      expect(readinessRow).not.toBeNull();
      expect(readinessRow?.className).toContain(`readiness-${readiness}`);
      expect(readinessRow?.querySelector(".feature-readiness")?.textContent).toBe(readiness);
    },
  );

  // Task 8 fix round: readiness is a contract word (vocabulary.py's
  // `readiness` group) and needs a gloss/trigger at every site it renders,
  // same as any other contract word on the page. The context rail is not
  // itself a clickable/toggling element, so it follows the full withGloss
  // precedent -- assert the real .info-trigger button is present, not just
  // that the word "weak"/"medium"/"strong" appears as text.
  test("the context rail's readiness word carries a definition trigger, not just bare text", async () => {
    const dom = await loadPage({
      scope: "bundle:evidence-lifecycle",
      health: { ...HEALTH, bundles: [{ ...HEALTH.bundles[0], readiness: "weak" }] },
    });
    const doc = dom.window.document;
    const readinessRow = doc.querySelector("#contextRail .context-rail-readiness");
    expect(readinessRow).not.toBeNull();
    const trigger = readinessRow?.querySelector(".info-trigger[data-term='weak']");
    expect(trigger, "no definition trigger beside the context rail's readiness word").not.toBeNull();
    expect(trigger?.getAttribute("aria-label")).toBe("What does weak mean?");
  });

  // Task 4 (Component 4): every tab gets a persistent one-line orientation
  // beneath the tab strip. KEY BY THE ELEMENT ID, NOT aria-label -- two tabs
  // disagree (id="tabVcycle" aria-label="V-cycle", id="tabSim" aria-label=
  // "Simulation"), and `id.slice(3)` is exactly the TABS_BY_KIND id for all
  // thirteen tabs.
  test("every rendered tab has an orientation line", async () => {
    const dom = await loadPage({ scope: "bundle:b1" });
    const doc = dom.window.document;
    doc.querySelectorAll('[role="tab"]').forEach((tab) => {
      const key = tab.id.slice(3);
      expect(PANELS_DATA.panels[key as keyof typeof PANELS_DATA.panels], `no orientation for tab ${key}`).toBeTruthy();
    });
  });

  test("the orientation line follows the active tab", async () => {
    const dom = await loadPage({ scope: "bundle:b1" });
    const doc = dom.window.document;
    const line = doc.getElementById("panelOrientation")!;
    expect(line.textContent).toContain("Every claim this scope makes");
    (doc.getElementById("tabMatrix") as HTMLElement).click();
    expect(line.textContent).toContain("validation has run");
  });
});
