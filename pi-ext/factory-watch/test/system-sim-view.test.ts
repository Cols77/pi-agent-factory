// Inc 6 Task 5 -- the Simulation-run summaries widget (system-sim-view.ts).
//
// Pure data->DOM over query_simulation_run's payload (spec §20 fields plus
// the additive metrics map and recording link): experiment, feature,
// requirements, goals, commit, result, metrics, recording. A failed run
// renders distinctly; a run whose recording is missing degrades visibly
// (scope_errors surfaced, recording shown as "not recorded").
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { boundedList, refChip } from "../src/system-comprehension.js";
import { clear } from "../src/system-renderers.js";
import { renderSim } from "../src/system-sim-view.js";

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
  const el = dom.window.document.createElement("div");
  renderSim(el, payload);
  return { el, dom };
}

// Mirrors query_simulation_run (spec §20 fields + additive metrics/recording).
const RUN_PASSED = {
  run: "RUN-20260811-1702",
  experiment: "SIM-047",
  feature: "FEAT-NAV-017",
  requirements: ["NAV-REQ-021"],
  goals: ["GOAL-NAV-003"],
  commit: "f92b004a1b2c3d4e5f60718293a4b5c6d7e8f90a1",
  result: "passed",
  scope_errors: [],
  metrics: { target_reacquisition_rate: 0.93, false_reacquisition_rate: 0.01 },
  recording: "evidence/runs/RUN-20260811-1702/manifest.json",
  recorded_ts: "2026-08-11T17:02:00Z",
};

const RUN_FAILED = {
  ...RUN_PASSED,
  run: "RUN-20260811-1800",
  result: "failed",
  metrics: { target_reacquisition_rate: 0.41 },
};

const RUN_MISSING_RECORDING = {
  ...RUN_PASSED,
  run: "RUN-20260811-1900",
  recording: null,
  scope_errors: ["manifest file missing: evidence/runs/RUN-20260811-1900/manifest.json"],
};

function section(el: HTMLElement, title: string): HTMLElement | null {
  return Array.from(el.querySelectorAll(".sim-section")).find(
    (sec) => sec.querySelector(".sim-section-heading")?.textContent === title,
  ) as HTMLElement | null;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("system-sim-view.ts sim widget", () => {
  test("renders the spec §20 fields, metrics and the recording link", () => {
    const { el } = mount(RUN_PASSED);
    expect(el.querySelector(".sim-id")?.textContent).toBe("RUN-20260811-1702");
    expect(el.querySelector(".sim-result")?.classList.contains("is-passed")).toBe(true);
    expect(el.querySelector(".sim-result")?.textContent).toBe("passed");
    expect(el.querySelector(".sim-recorded")?.textContent).toContain("2026-08-11");
    const experiment = section(el, "Experiment");
    expect(experiment?.textContent).toContain("SIM-047");
    const feature = section(el, "Feature");
    expect(feature?.textContent).toContain("feat:FEAT-NAV-017");
    const requirements = section(el, "Requirements");
    expect(requirements?.textContent).toContain("sr:NAV-REQ-021");
    const goals = section(el, "Goals");
    expect(goals?.textContent).toContain("goal:GOAL-NAV-003");
    const commit = section(el, "Commit");
    expect(commit?.textContent).toContain("f92b004a");
    const metrics = section(el, "Metrics");
    expect(metrics?.textContent).toContain("target_reacquisition_rate");
    expect(metrics?.textContent).toContain("0.93");
    const recording = section(el, "Recording");
    expect(recording?.textContent).toContain("evidence/runs/RUN-20260811-1702/manifest.json");
  });

  test("a failed run renders its result distinctly", () => {
    const { el } = mount(RUN_FAILED);
    const result = el.querySelector(".sim-result");
    expect(result?.classList.contains("is-failed")).toBe(true);
    expect(result?.textContent).toBe("failed");
  });

  test("a run with a missing recording degrades visibly, never a blank", () => {
    const { el } = mount(RUN_MISSING_RECORDING);
    const recording = section(el, "Recording");
    expect(recording?.textContent).toContain("not recorded");
    expect(el.textContent).toContain("manifest file missing");
  });
});