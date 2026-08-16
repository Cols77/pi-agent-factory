// Inc 6 Task 4 -- the Validation evidence widget (system-validation-view.ts).
//
// Pure data->DOM over query_validation's payload: the requirement's recorded
// validation state + staleness, its D5 goal-aware status, the goals that
// produced it, the validating simulation runs and the metrics they evaluate.
// Everything renders from recorded payload values; absent lists render
// "none recorded"; no goal-aware status renders "not recorded".
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { boundedList, refChip } from "../src/system-comprehension.js";
import { clear, openAnchor } from "../src/system-renderers.js";
import { renderValidation } from "../src/system-validation-view.js";

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
  renderValidation(el, payload);
  return { el, dom };
}

// Mirrors query_validation for a validated requirement (Inc 6 Task 4).
const VALIDATED = {
  scope: { kind: "sr", ref: "sr:NAV-REQ-021" },
  validation: {
    id: "NAV-REQ-021",
    raw_state: "passed",
    stale: false,
    error: null,
    goal_state: "VALIDATED",
    goals: [{ id: "GOAL-NAV-003", state: "REACHED" }],
    runs: ["RUN-20260811-1702"],
    metrics: ["MET-NAV-004"],
  },
};

const REGRESSED = {
  ...VALIDATED,
  scope: { kind: "sr", ref: "sr:SYS-SAFE-004" },
  validation: {
    ...VALIDATED.validation,
    id: "SYS-SAFE-004",
    raw_state: "failed",
    stale: true,
    goal_state: "REGRESSED",
    goals: [{ id: "GOAL-SAFE-001", state: "REGRESSED" }],
    runs: [],
    metrics: [],
  },
};

const NEVER = {
  ...VALIDATED,
  scope: { kind: "sr", ref: "sr:BR-009" },
  validation: {
    ...VALIDATED.validation,
    id: "BR-009",
    raw_state: "never_validated",
    stale: false,
    error: null,
    goal_state: null,
    goals: [],
    runs: [],
    metrics: [],
  },
};

function section(el: HTMLElement, title: string): HTMLElement | null {
  return Array.from(el.querySelectorAll(".validation-section")).find(
    (sec) => sec.querySelector(".validation-section-heading")?.textContent === title,
  ) as HTMLElement | null;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("system-validation-view.ts validation widget", () => {
  test("renders raw state, goal-aware status, goals, runs and metrics", () => {
    const { el } = mount(VALIDATED);
    expect(el.querySelector(".validation-id")?.textContent).toBe("NAV-REQ-021");
    const raw = el.querySelector(".validation-raw");
    expect(raw?.classList.contains("is-passed")).toBe(true);
    expect(raw?.textContent).toBe("passed");
    const goalState = el.querySelector(".validation-goal-state");
    expect(goalState?.classList.contains("is-validated")).toBe(true);
    expect(goalState?.textContent).toBe("VALIDATED");
    const goals = section(el, "Goals");
    expect(goals?.textContent).toContain("goal:GOAL-NAV-003");
    expect(goals?.textContent).toContain("REACHED");
    const runs = section(el, "Validating runs");
    expect(runs?.textContent).toContain("RUN-20260811-1702");
    const metrics = section(el, "Metrics");
    expect(metrics?.textContent).toContain("metric:MET-NAV-004");
  });

  test("a regressed stale requirement renders failed + stale + REGRESSED distinctly", () => {
    const { el } = mount(REGRESSED);
    const raw = el.querySelector(".validation-raw");
    expect(raw?.classList.contains("is-failed")).toBe(true);
    expect(raw?.textContent).toContain("failed");
    expect(raw?.textContent).toContain("stale");
    const goalState = el.querySelector(".validation-goal-state");
    expect(goalState?.classList.contains("is-regressed")).toBe(true);
    const runs = section(el, "Validating runs");
    expect(runs?.textContent).toContain("none recorded");
    const metrics = section(el, "Metrics");
    expect(metrics?.textContent).toContain("none recorded");
  });

  test("never-validated renders an explicit neutral state, never a pass", () => {
    const { el } = mount(NEVER);
    const raw = el.querySelector(".validation-raw");
    expect(raw?.classList.contains("is-never-validated")).toBe(true);
    expect(raw?.textContent).toBe("not validated");
    const goalState = el.querySelector(".validation-goal-state");
    expect(goalState?.textContent).toContain("not recorded");
    expect(goalState?.classList.contains("is-validated")).toBe(false);
  });
});