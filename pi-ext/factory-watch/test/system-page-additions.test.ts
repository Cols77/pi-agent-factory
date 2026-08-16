// Inc 6 -- system-page.ts additive tab tests.
//
// Loads the real page into jsdom (same idiom as system-page-dom.test.ts /
// system-page-vcycle.test.ts) with mocked fetches, and asserts the new Inc 6
// tabs render their Python-derived payloads and that the pre-existing tab
// behaviour is unchanged for bundle:/sr: scopes (D3 additive rule). Each
// task's tab gets its assertions appended here as it lands.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderSystemPageHtml } from "../src/system-page.js";

const SCOPE_LIST = { scopes: [], errors: [] };

// Mirrors src/factory/system/feature.py's feature_context payload (Inc 1),
// served as /api/system/brief?scope=feat:... (cmd_brief dispatches feat:).
const DOSSIER = {
  scope: { kind: "feat", ref: "feat:FEAT-NAV-017" },
  dossier: {
    id: "FEAT-NAV-017",
    title: "Target reacquisition",
    intent: "Maintain a plausible shark hypothesis across temporary visual loss.",
    requirements: [{ id: "NAV-REQ-021", kind: "sr", title: "Reacquire target", path: "requirements/NAV-REQ-021.md" }],
    design_records: [{ id: "ADR-012", kind: "adr", title: "Reuse trace graph", path: "docs/adr/ADR-012.md" }],
    implementation: [],
    implementation_files: ["src/navigation/reacquisition.py"],
    verification: [{ id: "NAV-REQ-021", state: "passed", stale: false }],
    goal_ids: ["GOAL-NAV-003"],
    metric_ids: ["MET-NAV-004"],
    latest_simulation_evidence: null,
    recent_changes: [{ commit: "a".repeat(40), authored_at: "2026-08-10T00:00:00Z", subject: "PR #207 reacquisition" }],
  },
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
  ],
  degraded: false,
  degraded_reasons: [],
};

const MATRIX = { scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, rows: [] };
const TIMELINE = { scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, events: [], degraded: false, degraded_reasons: [] };
const GUIDE = { scope: { kind: "bundle", ref: "bundle:evidence-lifecycle" }, sections: [] };
const SIM_RUN_DATA = {
  run: "RUN-20260811-1702",
  experiment: "SIM-047",
  feature: "FEAT-NAV-017",
  requirements: ["SR-010"],
  goals: ["GOAL-NAV-003"],
  commit: "f92b004a1b2c3d4e5f60718293a4b5c6d7e8f90a1",
  result: "passed",
  scope_errors: [],
  metrics: { target_reacquisition_rate: 0.93 },
  recording: "evidence/runs/RUN-20260811-1702/manifest.json",
  recorded_ts: "2026-08-11T17:02:00Z",
};

const VALIDATION_DATA = {
  scope: { kind: "sr", ref: "sr:SR-010" },
  validation: {
    id: "SR-010",
    raw_state: "passed",
    stale: false,
    error: null,
    goal_state: "VALIDATED",
    goals: [{ id: "GOAL-NAV-003", state: "REACHED" }],
    runs: ["RUN-20260811-1702"],
    metrics: ["MET-NAV-004"],
  },
};

const GOAL_DATA = {
  id: "GOAL-NAV-003",
  title: "Reacquire within 2 seconds",
  state: "REACHED",
  version: 3,
  feature: ["FEAT-NAV-017"],
  requirements: ["SR-010"],
  metric: { id: "MET-NAV-004", operator: "lte", unit: "seconds", source_experiment: "reacquire-sim" },
  target: { value: 2, unit: "seconds" },
  evidence: {
    state: "REACHED",
    passed: true,
    value: 1.7,
    target: 2,
    operator: "lte",
    run: "RUN-20260811-1702",
    commit: "c".repeat(40),
    blocked_reason: null,
  },
  history: [
    { state: "DECLARED", recorded_at: "2026-08-01T00:00:00Z", run: null, commit: null },
    { state: "REACHED", recorded_at: "2026-08-11T17:02:00Z", run: "RUN-20260811-1702", commit: "c".repeat(40) },
  ],
  scope_errors: [],
};

const HEALTH = {
  health: { classes: [], satisfied: 0, expected: 0, percent: 0, dangling: 0, deferred: 0, proposed: 0 },
  coverage: { total: 0, bundled: 0, unbundled: 0, kinds: [] },
  bundles: [],
  unbundled: {},
  ordering_available: true,
  sr_listed: true,
  degraded: [],
};

const VNODE = (id: string, kind: string, title: string) => ({
  id,
  kind,
  title,
  path: `path/${id}.md`,
  exempt: false,
  deferred: null,
  proposed: false,
  diagram_file: null,
});

// Mirrors query_vcycle: slice + additive statuses map.
const VCYCLE = {
  scope: { kind: "feat", ref: "feat:FEAT-NAV-017" },
  vcycle: {
    anchor: "feat:FEAT-NAV-017",
    definition: [
      { label: "NEEDS", nodes: [VNODE("BR-001", "br", "Detect visual loss")] },
      { label: "SYSTEM_REQUIREMENTS", nodes: [VNODE("SR-010", "sr", "Reacquire target")] },
    ],
    verification: [
      { label: "UNIT_VERIFICATION", nodes: [VNODE("T-022", "task", "Unit test reacquisition")] },
      { label: "SYSTEM_VALIDATION", nodes: [VNODE("SR-010", "sr", "Reacquire target")] },
    ],
    goals: [VNODE("GOAL-NAV-003", "goal", "Reacquire within 2s")],
    metrics: [],
    runs: [],
  },
  statuses: {
    "SR-010": { kind: "validation", state: "passed", stale: false },
    "BR-001": { kind: "validation", state: "failed", stale: true },
    "GOAL-NAV-003": { kind: "goal", state: "REACHED" },
    "T-022": { kind: "task", state: "todo" },
  },
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
    if (url.pathname === "/api/system/labels") return jsonResponse({ labels: {}, aliases: {}, degraded: [] });
    if (url.pathname === "/api/system/brief") {
      const scope = url.searchParams.get("scope") ?? "";
      return jsonResponse(scope.startsWith("feat:") ? DOSSIER : BRIEF);
    }
    if (url.pathname === "/api/system/vcycle") {
      return jsonResponse(VCYCLE);
    }
    if (url.pathname === "/api/system/validation") {
      return jsonResponse(VALIDATION_DATA);
    }
    if (url.pathname === "/api/system/sim/run") {
      return jsonResponse(SIM_RUN_DATA);
    }
    if (url.pathname === "/api/system/diagram") {
      const id = url.searchParams.get("id") ?? "";
      return jsonResponse(
        id === "DIAG-NAV-002"
          ? { id, title: "Missing", diagram_path: null, errors: ["diagram file missing"] }
          : { id, title: "Reacquisition state machine", diagram_path: "docs/diagrams/DIAG-NAV-001.html", errors: [] },
      );
    }
    if (url.pathname === "/api/system/goal") {
      return jsonResponse(GOAL_DATA);
    }
    if (url.pathname === "/api/system/matrix") return jsonResponse(MATRIX);
    if (url.pathname === "/api/system/timeline") return jsonResponse(TIMELINE);
    if (url.pathname === "/api/system/guide") return jsonResponse(GUIDE);
    if (url.pathname === "/api/system/traversal") {
      return jsonResponse({ requirement: [], tasks: [], design: [], files: [] });
    }
    throw new Error(`unmocked fetch: ${String(input)}`);
  });
}

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
      expect(dom.window.document.getElementById("content")?.getAttribute("aria-busy")).toBe("false");
    },
    { timeout: 2000, interval: 10 },
  );
  return dom;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Inc 6 tabs registered in the /system page", () => {
  test("a feat: scope shows the Feature dossier tab with the payload's sections", async () => {
    const dom = await loadPage({ scope: "feat:FEAT-NAV-017" });
    const doc = dom.window.document;
    expect(doc.getElementById("tabFeature")?.hidden).toBe(false);
    expect(doc.getElementById("tabFeature")?.getAttribute("aria-selected")).toBe("true");
    const panel = doc.getElementById("panelFeature");
    expect(panel?.textContent).toContain("FEAT-NAV-017");
    expect(panel?.textContent).toContain("Target reacquisition");
    expect(panel?.textContent).toContain("Maintain a plausible shark hypothesis");
    expect(panel?.textContent).toContain("src/navigation/reacquisition.py");
    expect(panel?.textContent).toContain("PR #207 reacquisition");
    // latest_simulation_evidence is null in this fixture: the section states
    // it explicitly rather than hiding.
    expect(panel?.textContent).toContain("not recorded");
  });

  test("a bundle: scope keeps its exact pre-existing tab set (D3)", async () => {
    const dom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    const doc = dom.window.document;
    expect(doc.getElementById("tabBrief")?.hidden).toBe(false);
    expect(doc.getElementById("tabMatrix")?.hidden).toBe(false);
    expect(doc.getElementById("tabTimeline")?.hidden).toBe(false);
    expect(doc.getElementById("tabGuide")?.hidden).toBe(false);
    expect(doc.getElementById("tabFeature")?.hidden).toBe(true);
    expect(doc.getElementById("tabVcycle")?.hidden).toBe(true);
    expect(doc.getElementById("tabStory")?.hidden).toBe(true);
    expect(doc.getElementById("tabReverse")?.hidden).toBe(true);
    expect(doc.getElementById("panelBrief")?.textContent).toContain("Evidence lifecycle");
  });

  test("feat: and sr: scopes show the V-cycle tab rendering the Python slice", async () => {
    const dom = await loadPage({ scope: "feat:FEAT-NAV-017" });
    const doc = dom.window.document;
    expect(doc.getElementById("tabVcycle")?.hidden).toBe(false);
    const panel = doc.getElementById("panelVcycle");
    expect(panel?.textContent).toContain("System requirements");
    expect(panel?.textContent).toContain("sr:SR-010");
    expect(panel?.textContent).toContain("br:BR-001");
    expect(panel?.textContent).toContain("Goals");
    expect(panel?.textContent).toContain("REACHED");
    // Recorded state renders, never derived: BR-001 failed + stale.
    const failed = Array.from(panel?.querySelectorAll(".vcycle-node") ?? []).find(
      (n) => n.textContent?.includes("BR-001"),
    );
    expect(failed?.classList.contains("is-failed")).toBe(true);
    expect(failed?.classList.contains("is-stale")).toBe(true);
    expect(failed?.textContent).toContain("stale");

    const srDom = await loadPage({ scope: "sr:SR-010" });
    expect(srDom.window.document.getElementById("tabVcycle")?.hidden).toBe(false);
  });

  test("a goal: scope shows the Goal tab with contract, evidence and history", async () => {
    const dom = await loadPage({ scope: "goal:GOAL-NAV-003" });
    const doc = dom.window.document;
    expect(doc.getElementById("tabGoal")?.hidden).toBe(false);
    expect(doc.getElementById("tabGoal")?.getAttribute("aria-selected")).toBe("true");
    const panel = doc.getElementById("panelGoal");
    expect(panel?.textContent).toContain("Reacquire within 2 seconds");
    expect(panel?.textContent).toContain("REACHED");
    expect(panel?.textContent).toContain("sr:SR-010");
    expect(panel?.textContent).toContain("RUN-20260811-1702");
    expect(panel?.textContent).toContain("2026-08-11");
    // Other tabs do not appear for a goal: scope.
    expect(doc.getElementById("tabBrief")?.hidden).toBe(true);
    expect(doc.getElementById("tabFeature")?.hidden).toBe(true);
    expect(doc.getElementById("tabVcycle")?.hidden).toBe(true);
  });

  test("an sr: scope shows the Validation tab with goal-aware status and evidence", async () => {
    const dom = await loadPage({ scope: "sr:SR-010" });
    const doc = dom.window.document;
    expect(doc.getElementById("tabValidation")?.hidden).toBe(false);
    const panel = doc.getElementById("panelValidation");
    expect(panel?.textContent).toContain("SR-010");
    expect(panel?.textContent).toContain("VALIDATED");
    expect(panel?.textContent).toContain("goal:GOAL-NAV-003");
    expect(panel?.textContent).toContain("RUN-20260811-1702");
    expect(panel?.textContent).toContain("metric:MET-NAV-004");
    const raw = panel?.querySelector(".validation-raw");
    expect(raw?.classList.contains("is-passed")).toBe(true);
    // A bundle: scope never shows the tab.
    const bundleDom = await loadPage({ scope: "bundle:evidence-lifecycle" });
    expect(bundleDom.window.document.getElementById("tabValidation")?.hidden).toBe(true);
  });

  test("a sim: scope shows the Simulation tab with the run summary", async () => {
    const dom = await loadPage({ scope: "sim:RUN-20260811-1702" });
    const doc = dom.window.document;
    expect(doc.getElementById("tabSim")?.hidden).toBe(false);
    expect(doc.getElementById("tabSim")?.getAttribute("aria-selected")).toBe("true");
    const panel = doc.getElementById("panelSim");
    expect(panel?.textContent).toContain("RUN-20260811-1702");
    expect(panel?.textContent).toContain("SIM-047");
    expect(panel?.textContent).toContain("feat:FEAT-NAV-017");
    expect(panel?.textContent).toContain("sr:SR-010");
    expect(panel?.textContent).toContain("0.93");
    expect(panel?.textContent).toContain("evidence/runs/RUN-20260811-1702/manifest.json");
    const result = panel?.querySelector(".sim-result");
    expect(result?.classList.contains("is-passed")).toBe(true);
    // A feat: scope never shows the Simulation tab.
    const featDom = await loadPage({ scope: "feat:FEAT-NAV-017" });
    expect(featDom.window.document.getElementById("tabSim")?.hidden).toBe(true);
  });

  test("the page inlines the feature widget as a plain function (no module imports)", () => {
    const html = renderSystemPageHtml();
    expect(html).toContain("function renderFeature(");
    expect(html.indexOf("function renderFeature(")).toBeGreaterThan(html.indexOf("var LABELS ="));
  });

  test("a diag: scope shows the Diagram tab embedding the committed HTML", async () => {
    const dom = await loadPage({ scope: "diag:DIAG-NAV-001" });
    const doc = dom.window.document;
    expect(doc.getElementById("tabDiagram")?.hidden).toBe(false);
    expect(doc.getElementById("tabDiagram")?.getAttribute("aria-selected")).toBe("true");
    const panel = doc.getElementById("panelDiagram");
    expect(panel?.textContent).toContain("DIAG-NAV-001");
    const embed = panel?.querySelector("iframe.diagram-embed");
    expect(embed?.getAttribute("src")).toBe("docs/diagrams/DIAG-NAV-001.html");
    // A missing diagram degrades visibly.
    const missingDom = await loadPage({ scope: "diag:DIAG-NAV-002" });
    const missingPanel = missingDom.window.document.getElementById("panelDiagram");
    expect(missingPanel?.textContent).toContain("missing diagram");
  });

  test("the dossier offers the explicit verify-understanding entry point (D8)", async () => {
    const dom = await loadPage({ scope: "feat:FEAT-NAV-017" });
    const doc = dom.window.document;
    const button = doc.querySelector("button[data-feature='FEAT-NAV-017']");
    expect(button?.textContent).toBe("Verify my understanding");
  });

  test("scope-open anchors navigate within the SPA: requirement -> V-cycle (AC-02/AC-09)", async () => {
    const dom = await loadPage({ scope: "feat:FEAT-NAV-017" });
    const doc = dom.window.document;
    const srAnchor = doc.querySelector("a.scope-open[data-scope='sr:SR-010']") as HTMLElement | null;
    expect(srAnchor).not.toBeNull();
    expect(srAnchor?.getAttribute("data-tab")).toBe("vcycle");
    srAnchor?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));
    await vi.waitFor(
      () => {
        const busy = doc.getElementById("content")?.getAttribute("aria-busy");
        const heading = doc.getElementById("scopeHeader")?.textContent ?? "";
        expect(busy).toBe("false");
        expect(heading + " " + doc.getElementById("scopeKind")?.textContent).toContain("SR-010");
      },
      { timeout: 2000, interval: 20 },
    );
    // AC-09: the tab intent lands on the V-cycle view for the requirement.
    expect(doc.getElementById("tabVcycle")?.getAttribute("aria-selected")).toBe("true");
    expect(doc.getElementById("panelVcycle")?.textContent).toContain("sr:SR-010");
  });

  test("dossier-as-hub: goal chip's open anchor navigates to the goal scope", async () => {
    const dom = await loadPage({ scope: "feat:FEAT-NAV-017" });
    const doc = dom.window.document;
    const goalAnchor = doc.querySelector("a.scope-open[data-scope='goal:GOAL-NAV-003']") as HTMLElement | null;
    expect(goalAnchor).not.toBeNull();
    goalAnchor?.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));
    await vi.waitFor(
      () => {
        const busy = doc.getElementById("content")?.getAttribute("aria-busy");
        const heading = doc.getElementById("scopeHeader")?.textContent ?? "";
        expect(busy).toBe("false");
        expect(heading + " " + doc.getElementById("scopeKind")?.textContent).toContain("GOAL-NAV-003");
      },
      { timeout: 2000, interval: 20 },
    );
    expect(doc.getElementById("tabGoal")?.getAttribute("aria-selected")).toBe("true");
    expect(doc.getElementById("panelGoal")?.textContent).toContain("Reacquire within 2 seconds");
  });
});
