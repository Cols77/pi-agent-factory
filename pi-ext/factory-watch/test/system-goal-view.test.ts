// Inc 6 Task 3 -- the Goal/metric status widget (system-goal-view.ts).
//
// Pure data->DOM over query_goal's payload (eng_get_goal, Inc 4): contract,
// current state, requirement/metric/target, evidence run+commit, and the
// append-only history (spec 9.3). Every field renders from recorded payload
// values; absent evidence renders "not recorded", never a guess.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { boundedList, refChip } from "../src/system-comprehension.js";
import { clear, openAnchor } from "../src/system-renderers.js";
import { renderGoal } from "../src/system-goal-view.js";

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
  vi.stubGlobal("openAnchor", openAnchor);
  const el = dom.window.document.createElement("div");
  renderGoal(el, payload);
  return { el, dom };
}

// Mirrors query_goal output for a goal auto-evaluated in Inc 3: state,
// requirements, metric+target, evidence (run/commit), append-only history.
const GOAL = {
  id: "GOAL-NAV-003",
  title: "Reacquire within 2 seconds",
  state: "REACHED",
  version: 3,
  feature: ["FEAT-NAV-017"],
  requirements: ["SR-010", "SR-020"],
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

const GOAL_NO_EVIDENCE = {
  id: "GOAL-NAV-004",
  title: "Not yet evaluated",
  state: "DECLARED",
  version: 1,
  feature: [],
  requirements: [],
  metric: null,
  target: null,
  evidence: null,
  history: [],
  scope_errors: [],
};

function section(el: HTMLElement, title: string): HTMLElement | null {
  return Array.from(el.querySelectorAll(".goal-section")).find(
    (sec) => sec.querySelector(".goal-section-heading")?.textContent === title,
  ) as HTMLElement | null;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("system-goal-view.ts goal widget", () => {
  test("renders id, title, state class and the requirement/metric/target bindings", () => {
    const { el } = mount(GOAL);
    expect(el.querySelector(".goal-id")?.textContent).toBe("GOAL-NAV-003");
    expect(el.querySelector(".goal-title")?.textContent).toBe("Reacquire within 2 seconds");
    const state = el.querySelector(".goal-state");
    expect(state?.classList.contains("is-reached")).toBe(true);
    expect(state?.textContent).toBe("REACHED");
    const reqs = section(el, "Requirements");
    expect(reqs?.textContent).toContain("sr:SR-010");
    expect(reqs?.textContent).toContain("sr:SR-020");
    const metric = section(el, "Metric");
    expect(metric?.textContent).toContain("MET-NAV-004");
    expect(metric?.textContent).toContain("target ≤ 2 seconds");
  });

  test("renders recorded evidence run/commit and the history entries", () => {
    const { el } = mount(GOAL);
    const evidence = section(el, "Evidence");
    expect(evidence?.textContent).toContain("RUN-20260811-1702");
    expect(evidence?.textContent).toContain("1.7");
    expect(evidence?.textContent).toContain("c".repeat(8));
    const history = section(el, "History");
    expect(history?.textContent).toContain("DECLARED");
    expect(history?.textContent).toContain("REACHED");
    expect(history?.textContent).toContain("2026-08-11");
  });

  test("a goal with no evidence renders explicit 'not recorded' states", () => {
    const { el } = mount(GOAL_NO_EVIDENCE);
    expect(el.querySelector(".goal-state")?.textContent).toBe("DECLARED");
    const metric = section(el, "Metric");
    expect(metric?.textContent).toContain("none recorded");
    const evidence = section(el, "Evidence");
    expect(evidence?.textContent).toContain("not recorded");
    const history = section(el, "History");
    expect(history?.textContent).toContain("none recorded");
  });

  test("every state renders its recorded state text and a distinct class", () => {
    for (const state of ["REGRESSED", "BLOCKED", "NOT_REACHED", "ACTIVE"]) {
      const { el } = mount({ ...GOAL_NO_EVIDENCE, id: `G-${state}`, state });
      const badge = el.querySelector(".goal-state");
      expect(badge?.textContent).toBe(state);
      expect(badge?.className).toContain(state === "REGRESSED" ? "is-regressed" : state === "BLOCKED" ? "is-blocked" : state === "NOT_REACHED" ? "is-not-reached" : "is-active");
    }
  });
});