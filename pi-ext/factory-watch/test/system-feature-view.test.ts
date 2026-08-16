// Inc 6 Task 1 -- Feature Dossier widget.
//
// Pure data->DOM tests: the widget renders `factory.system brief --scope
// feat:X` JSON (query_feature_context's dossier) into a container element,
// with every dossier section present and every absent section rendered as an
// explicit "not recorded" note -- never blank, never hidden (spec §9.2, and
// the Inc 6 global constraint "missing links/states render as explicitly
// missing"). The widget is tested here directly against a jsdom document, no
// docs server involved.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderFeature } from "../src/system-feature-view.js";
import { boundedList, refChip } from "../src/system-comprehension.js";
import { openAnchor } from "../src/system-renderers.js";

// The dossier shape mirrors src/factory/system/feature.py's feature_context:
// only facts recorded in the trace graph, with intent/requirements/design/
// implementation/verification/goal ids/recent changes. `open_questions` is
// deliberately absent from the payload -- the widget must say so explicitly.
const DOSSIER = {
  scope: { kind: "feat", ref: "feat:FEAT-NAV-017" },
  dossier: {
    id: "FEAT-NAV-017",
    title: "Target reacquisition",
    intent: "Maintain a plausible shark hypothesis across temporary visual loss.",
    requirements: [
      { id: "NAV-REQ-021", kind: "sr", title: "Reacquire target", path: "requirements/NAV-REQ-021.md" },
      { id: "SYS-SAFE-004", kind: "br", title: "Stay safe", path: "requirements/SYS-SAFE-004.md" },
    ],
    design_records: [
      { id: "ADR-012", kind: "adr", title: "Reuse trace graph", path: "docs/adr/ADR-012.md" },
    ],
    implementation: [
      {
        task: { id: "T-021", title: "Wire reacquisition", status: "done", dod: [] },
        runs: [
          {
            run_id: "run-021",
            source: "manifest",
            outcome: "completed",
            started_at: null,
            ended_at: null,
            start_commit: null,
            result_commit: null,
            implementation: {
              kind: "recorded",
              text: "run run-021: 1 changed file(s) recorded",
              citations: [],
              spans: [],
              freshness: { state: "fresh", reason: null, dependencies: [] },
              changed_files: ["src/navigation/reacquisition.py"],
            },
            citation: { kind: "manifest", path: "evidence/runs/run-021.json", sha256: null, anchor: null },
          },
        ],
      },
    ],
    implementation_files: ["src/navigation/reacquisition.py", "src/memory/target_memory.py"],
    verification: [
      { id: "NAV-REQ-021", state: "passed", stale: false },
      { id: "SYS-SAFE-004", state: "failed", stale: true },
    ],
    goal_ids: ["GOAL-NAV-003"],
    metric_ids: ["MET-NAV-004"],
    latest_simulation_evidence: null,
    recent_changes: [
      { commit: "a".repeat(40), authored_at: "2026-08-10T00:00:00Z", subject: "PR #207 reacquisition" },
    ],
  },
};

function mount(): { el: HTMLElement; dom: JSDOM } {
  const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>");
  const win = dom.window as unknown as Record<string, unknown>;
  for (const key of ["document", "window", "HTMLElement", "Node", "Element", "Event", "CustomEvent"]) {
    vi.stubGlobal(key, win[key]);
  }
  // The page-scope label bindings refChip/boundedList read (system-shell.ts
  // preamble defines these as `var`s in the page; the widget test stubs the
  // same empty state so chips render their absent-ref treatment). The chips
  // themselves are the REAL implementations (stubbed as globals, exactly as
  // the page inlines them), so their absent-ref rendering is exercised too.
  vi.stubGlobal("LABELS", {});
  vi.stubGlobal("ALIASES", {});
  vi.stubGlobal("LABELS_LOADED", true);
  vi.stubGlobal("clear", (target: HTMLElement) => {
    target.innerHTML = "";
  });
  vi.stubGlobal("refChip", refChip);
  vi.stubGlobal("openAnchor", openAnchor);
  vi.stubGlobal("boundedList", boundedList);
  const el = dom.window.document.getElementById("root") as HTMLElement;
  return { el, dom };
}

function section(el: HTMLElement, title: string): HTMLElement | null {
  return Array.from(el.querySelectorAll(".dossier-section")).find(
    (sec) => sec.querySelector(".dossier-section-heading")?.textContent === title,
  ) as HTMLElement | null;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("system-feature-view.ts dossier widget", () => {
  test("renders every dossier section from the payload", () => {
    const { el } = mount();
    renderFeature(el, DOSSIER);

    expect(section(el, "Intent")?.textContent).toContain("Maintain a plausible shark hypothesis");
    const requirements = section(el, "Requirements");
    // With no label index, chips render their exact raw ref (kind prefix
    // included) -- the ids the widget mapped from the payload facts.
    expect(Array.from(requirements?.querySelectorAll(".ref-chip") ?? []).map((chip) => chip.querySelector(".chip-id")?.textContent))
      .toEqual(["sr:NAV-REQ-021", "br:SYS-SAFE-004"]);
    const design = section(el, "Design");
    expect(design?.textContent).toContain("ADR-012");
    const code = section(el, "Code");
    expect(code?.textContent).toContain("src/navigation/reacquisition.py");
    expect(code?.textContent).toContain("src/memory/target_memory.py");
    const tasks = section(el, "Tasks");
    expect(tasks?.textContent).toContain("T-021");
    expect(tasks?.textContent).toContain("done");
    expect(tasks?.textContent).toContain("run-021");
    const tests = section(el, "Tests");
    expect(tests?.textContent).toContain("NAV-REQ-021");
    expect(tests?.textContent).toContain("passed");
    expect(tests?.textContent).toContain("SYS-SAFE-004");
    expect(tests?.textContent).toContain("failed");
    const goals = section(el, "Goals");
    expect(goals?.textContent).toContain("GOAL-NAV-003");
    const changes = section(el, "Recent changes");
    expect(changes?.textContent).toContain("PR #207 reacquisition");
    // Verification staleness is a payload fact, rendered verbatim, never
    // inferred client-side: the stale row says stale, the fresh one does not.
    expect(tests?.textContent).toContain("stale");
  });

  test("a missing section renders as an explicit note, never blank or hidden", () => {
    const { el } = mount();
    renderFeature(el, DOSSIER);

    // latest_simulation_evidence is null in the payload.
    expect(section(el, "Simulations")?.textContent).toContain("not recorded");
    // open_questions is not even a payload key.
    expect(section(el, "Open questions")?.textContent).toContain("not recorded");
    // The sections themselves are present (not dropped).
    expect(section(el, "Simulations")).not.toBeNull();
    expect(section(el, "Open questions")).not.toBeNull();
  });

  test("an empty section (payload key present, no records) renders 'none recorded'", () => {
    const { el } = mount();
    const empty = {
      scope: { kind: "feat", ref: "feat:FEAT-EMPTY" },
      dossier: {
        id: "FEAT-EMPTY",
        title: "Empty feature",
        intent: "",
        requirements: [],
        design_records: [],
        implementation: [],
        implementation_files: [],
        verification: [],
        goal_ids: [],
        metric_ids: [],
        latest_simulation_evidence: null,
        recent_changes: [],
      },
    };
    renderFeature(el, empty);

    expect(section(el, "Intent")?.textContent).toContain("not recorded");
    expect(section(el, "Requirements")?.textContent).toContain("none recorded");
    expect(section(el, "Design")?.textContent).toContain("none recorded");
    expect(section(el, "Code")?.textContent).toContain("none recorded");
    expect(section(el, "Tasks")?.textContent).toContain("none recorded");
    expect(section(el, "Tests")?.textContent).toContain("none recorded");
    expect(section(el, "Goals")?.textContent).toContain("none recorded");
    expect(section(el, "Recent changes")?.textContent).toContain("none recorded");
  });

  test("renders payload text via text nodes only, never raw innerHTML interpolation", () => {
    const { el } = mount();
    const hostile = {
      scope: { kind: "feat", ref: "feat:FEAT-XSS" },
      dossier: {
        id: "FEAT-XSS",
        title: "<img src=x onerror=alert(1)>",
        intent: "<script>alert(1)</script>",
        requirements: [],
        design_records: [],
        implementation: [],
        implementation_files: ["<img src=x onerror=alert(1)>"],
        verification: [],
        goal_ids: [],
        metric_ids: [],
        latest_simulation_evidence: null,
        recent_changes: [],
      },
    };
    renderFeature(el, hostile);

    expect(el.querySelector("img")).toBeNull();
    expect(el.querySelector("script")).toBeNull();
    expect(section(el, "Intent")?.textContent).toContain("<script>alert(1)</script>");
    expect(section(el, "Code")?.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
