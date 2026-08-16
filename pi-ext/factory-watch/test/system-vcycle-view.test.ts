// Inc 6 Task 2 -- the interactive V-cycle widget (system-vcycle-view.ts).
//
// Pure data->DOM: the payload is the Python projection of query_vcycle
// (slice + additive statuses map). The widget only renders it verbatim --
// order comes from the payload's side list, names from the labels index,
// colours/state text from the recorded statuses entry. It reuses SP-B's
// refChip click/card affordance for every node chip; it adds no nav of its
// own (Task 6 wires real navigation).
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { boundedList, refChip } from "../src/system-comprehension.js";
import { clear } from "../src/system-renderers.js";
import { renderVcycle } from "../src/system-vcycle-view.js";

function mount(payload: unknown): { el: HTMLElement; dom: JSDOM } {
  const dom = new JSDOM("<!doctype html><html><body></body></html>");
  const win = dom.window as unknown as Record<string, unknown>;
  for (const key of ["document", "window", "HTMLElement", "Node", "Element", "Event", "CustomEvent"]) {
    vi.stubGlobal(key, win[key]);
  }
  vi.stubGlobal("LABELS", {});
  vi.stubGlobal("ALIASES", {});
  vi.stubGlobal("LABELS_LOADED", true);
  vi.stubGlobal("refChip", refChip);
  vi.stubGlobal("boundedList", boundedList);
  vi.stubGlobal("clear", clear);
  const el = document.createElement("div");
  el.id = "panelVcycle";
  document.body.appendChild(el);
  renderVcycle(el, payload);
  return { el, dom };
}

function node(id: string, kind: string, title: string): any {
  return { id, kind, title, path: `path/${id}.md`, exempt: false, deferred: null, proposed: false, diagram_file: null };
}

// A complete feat: slice with a populated definition side, a partially
// populated verification side, goals/metrics, and statuses for a passed sr,
// a failed stale sr, a reached goal and a done task. Mirrors the Python
// manifest payload exactly (additive statuses key).
const VCYCLE = {
  scope: { kind: "feat", ref: "feat:FEAT-NAV-017" },
  vcycle: {
    anchor: "feat:FEAT-NAV-017",
    definition: [
      { label: "NEEDS", nodes: [node("BR-001", "br", "Detect visual loss")] },
      { label: "SYSTEM_REQUIREMENTS", nodes: [node("SR-010", "sr", "Reacquire target")] },
      { label: "SUBSYSTEM_REQUIREMENTS", nodes: [node("SR-020", "sr", "Keep plausible hypothesis")] },
      { label: "ARCHITECTURE_DESIGN", nodes: [node("ADR-012", "adr", "Reuse trace graph")] },
      { label: "DETAILED_DESIGN", nodes: [node("T-021", "task", "Implement reacquisition")] },
      { label: "CODE", nodes: [node("code:reacquisition.py", "code", "reacquisition.py")] },
    ],
    verification: [
      { label: "UNIT_VERIFICATION", nodes: [node("T-022", "task", "Unit test reacquisition")] },
      { label: "INTEGRATION_VERIFICATION", nodes: [] },
      { label: "SIMULATION_VERIFICATION", nodes: [node("GOAL-NAV-003", "goal", "Reacquire within 2s")] },
      { label: "SYSTEM_VALIDATION", nodes: [node("SR-010", "sr", "Reacquire target")] },
    ],
    goals: [node("GOAL-NAV-003", "goal", "Reacquire within 2s")],
    metrics: [node("MET-NAV-004", "metric", "reacquisition_rate")],
    runs: [],
  },
  statuses: {
    "SR-010": { kind: "validation", state: "passed", stale: false },
    "SR-020": { kind: "validation", state: "failed", stale: true },
    "BR-001": { kind: "validation", state: "never_validated", stale: false },
    "GOAL-NAV-003": { kind: "goal", state: "REACHED" },
    "T-021": { kind: "task", state: "done" },
    "T-022": { kind: "task", state: "todo" },
  },
};

function band(el: HTMLElement, label: string): HTMLElement | null {
  const bands = Array.from(el.querySelectorAll(".vcycle-band"));
  return (
    (bands.find(
      (bandNode) => bandNode.querySelector(".vcycle-band-label")?.textContent === label,
    ) as HTMLElement) ?? null
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("system-vcycle-view.ts vcycle widget", () => {
  test("renders the anchor, then definition and verification bands in payload order", () => {
    const { el } = mount(VCYCLE);
    expect(el.querySelector(".vcycle-anchor .chip-id")?.textContent).toBe("feat:FEAT-NAV-017");
    const def = band(el, "Needs");
    expect(def?.querySelector(".chip-id")?.textContent).toBe("br:BR-001");
    expect(band(el, "Code")?.querySelector(".chip-id")?.textContent).toBe("code:code:reacquisition.py");
    // Verification side follows the definition side with its own labels.
    expect(band(el, "Unit verification")?.querySelector(".chip-id")?.textContent).toBe("task:T-022");
    expect(band(el, "System validation")?.querySelector(".chip-id")?.textContent).toBe("sr:SR-010");
    // Order of the bands follows the payload, never alphabetical.
    const labels = Array.from(el.querySelectorAll(".vcycle-band-label")).map((n) => n.textContent);
    expect(labels[0]).toBe("Needs");
    expect(labels[1]).toBe("System requirements");
    expect(labels[2]).toBe("Subsystem requirements");
  });

  test("an empty band renders the explicit missing state, never a blank", () => {
    const { el } = mount(VCYCLE);
    const empty = band(el, "Integration verification");
    expect(empty?.classList.contains("is-missing")).toBe(true);
    expect(empty?.textContent).toContain("none recorded");
  });

  test("statuses colour failed/stale nodes distinctly with recorded text", () => {
    const { el } = mount(VCYCLE);
    const failed = band(el, "Subsystem requirements");
    const failedNode = failed?.querySelector(".vcycle-node") as HTMLElement;
    expect(failedNode.classList.contains("is-failed")).toBe(true);
    expect(failedNode.classList.contains("is-stale")).toBe(true);
    expect(failedNode.textContent).toContain("failed");
    expect(failedNode.textContent).toContain("stale");

    const passed = band(el, "System requirements");
    expect(passed?.querySelector(".vcycle-node")?.classList.contains("is-passed")).toBe(true);

    const reached = band(el, "Simulation verification");
    expect(reached?.querySelector(".vcycle-node")?.classList.contains("is-reached")).toBe(true);

    const done = band(el, "Detailed design");
    expect(done?.querySelector(".vcycle-node")?.classList.contains("is-done")).toBe(true);

    // A node with no status source stays neutral, with no state class.
    const neutral = band(el, "Architecture design");
    expect(neutral?.querySelector(".vcycle-node")?.classList.contains("is-neutral")).toBe(true);
  });

  test("goal, metric and run sections render their nodes with state text", () => {
    const { el } = mount(VCYCLE);
    expect(el.textContent).toContain("Goals");
    expect(el.textContent).toContain("REACHED");
    expect(el.textContent).toContain("Metrics");
    expect(el.textContent).toContain("metric:MET-NAV-004");
    expect(el.textContent).toContain("Runs");
    expect(el.textContent).toContain("none recorded");
  });
});