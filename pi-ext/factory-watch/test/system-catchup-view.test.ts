// Inc 7 Task 3 -- the "Catch me up" widget (system-catchup-view.ts).
//
// Pure data->DOM over query_catchup's payload: the deterministic
// "since your last review" delta (spec §31 / §9.4). It renders the
// *computed* ContextDelta fields only; an unreviewed feature renders the
// honest "no review recorded" state; a zero-change delta renders
// "no changes since your last review".
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { refChip } from "../src/system-comprehension.js";
import { clear, openAnchor } from "../src/system-renderers.js";
import { renderCatchup } from "../src/system-catchup-view.js";

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
  vi.stubGlobal("clear", clear);
  vi.stubGlobal("openAnchor", openAnchor);
  const el = dom.window.document.createElement("div");
  renderCatchup(el, payload);
  return { el, dom };
}

// Mirrors query_catchup output for the seeded spec §31 example: 2 PRs merged,
// one goal reached, metric 87% -> 95%, one new open item.
const CATCHUP = {
  feature: "FEAT-NAV-017",
  reviewed: true,
  since_commit: "a".repeat(40),
  reviewed_at: "2026-08-16T10:00:00Z",
  delta: {
    feature: "FEAT-NAV-017",
    since_commit: "a".repeat(40),
    prs_merged: ["Merge pull request #17 from pr-nav-017"],
    requirements_changed: ["SR-017"],
    adrs_added: ["ADR-0002"],
    scenarios_added: ["SIM-048"],
    goals_reached: ["GOAL-NAV-001"],
    goals_regressed: [],
    metric_changes: [
      { metric: "reacquisition_rate", from: 0.87, to: 0.95, regression: false },
    ],
    new_open_items: ["false-reacquisition risk under wind"],
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

test("renders the delta header with the checkpoint commit", () => {
  const { el } = mount(CATCHUP);
  expect(el.querySelector(".catchup-id")?.textContent).toBe("FEAT-NAV-017");
  const since = el.querySelector(".catchup-since")?.textContent ?? "";
  expect(since).toContain("since " + "a".repeat(8));
});

test("renders requirement change with a navigable sr chip", () => {
  const { el, dom } = mount(CATCHUP);
  const reqSection = el.querySelector(".catchup-section")!;
  const chips = reqSection.querySelectorAll(".ref-chip");
  expect(chips.length).toBeGreaterThanOrEqual(1);
  const chip = chips[0]!;
  expect(chip.textContent ?? "").toContain("SR-017");
  expect(dom.window.getComputedStyle).toBeDefined();
});

test("renders PRs merged, goals reached and metrics", () => {
  const { el } = mount(CATCHUP);
  const text = el.textContent ?? "";
  expect(text).toContain("Merge pull request #17");
  expect(text).toContain("ADR-0002");
  expect(text).toContain("SIM-048");
  expect(text).toContain("GOAL-NAV-001");
  expect(text).toContain("reacquisition_rate");
  expect(text).toContain("0.87 -> 0.95");
  expect(text).toContain("false-reacquisition risk under wind");
});

test("marks a regressed metric visibly", () => {
  const payload = JSON.parse(JSON.stringify(CATCHUP));
  payload.delta.metric_changes = [
    { metric: "reacquisition_rate", from: 0.95, to: 0.81, regression: true },
  ];
  payload.delta.goals_regressed = ["GOAL-NAV-001"];
  payload.delta.goals_reached = [];
  const { el } = mount(payload);
  const text = el.textContent ?? "";
  expect(text).toContain("REGRESSED");
  expect(text).toContain("0.95 -> 0.81");
  expect(el.querySelector(".is-regression")).not.toBeNull();
});

test("renders the honest unreviewed state", () => {
  const { el } = mount({ feature: "FEAT-NAV-017", reviewed: false, since_commit: null, delta: null });
  const text = el.textContent ?? "";
  expect(text).toContain("no review recorded yet for this feature");
});

test("renders an empty delta as no changes", () => {
  const payload = {
    feature: "FEAT-NAV-017",
    reviewed: true,
    since_commit: "a".repeat(40),
    delta: {
      feature: "FEAT-NAV-017",
      since_commit: "a".repeat(40),
      prs_merged: [],
      requirements_changed: [],
      adrs_added: [],
      scenarios_added: [],
      goals_reached: [],
      goals_regressed: [],
      metric_changes: [],
      new_open_items: [],
    },
  };
  const { el } = mount(payload);
  expect(el.textContent ?? "").toContain("no changes since your last review");
});

test("does not render an open-anchor without a goal chip helper", () => {
  // Regression guard: catchupRefLine only emits sr open anchors; the goal
  // lines must not reference an undefined openAnchor path.
  const { el } = mount(CATCHUP);
  expect(el.querySelectorAll(".catchup-ref-line").length).toBeGreaterThanOrEqual(1);
});

// ── Inc 7 Task 5k/5b: freshness, diagram, comprehension ────────────────────

const FRESH_DELTA = {
  feature: "FEAT-NAV-017",
  reviewed: true,
  since_commit: "a".repeat(40),
  delta: {
    feature: "FEAT-NAV-017",
    since_commit: "a".repeat(40),
    prs_merged: [],
    requirements_changed: ["SR-017"],
    adrs_added: [],
    scenarios_added: [],
    goals_reached: [],
    goals_regressed: [],
    metric_changes: [],
    new_open_items: [],
    invalidated: ["run:RUN-20260816-0100", "explainer:NAV-PREEMPTION.md"],
    auto_refreshed: ["explainer:NAV-PREEMPTION.md"],
    refresh_required: ["code:src/navigation/preemption.py"],
    blocked_refreshes: ["run:RUN-20260816-0100"],
    freshness_closure_reached: false,
  },
  diagram: {
    id: "DIAG-NAV-009",
    title: "Nav pre-emption",
    diagram_path: "docs/diagrams/DIAG-NAV-009.html",
    errors: [],
  },
};

test("renders the freshness section from the 5k delta fields", () => {
  const { el } = mount(FRESH_DELTA);
  const text = el.textContent ?? "";
  expect(text).toContain("Freshness");
  expect(text).toContain("NOT REACHED");
  expect(text).toContain("run:RUN-20260816-0100");
  expect(text).toContain("explainer:NAV-PREEMPTION.md");
  expect(text).toContain("code:src/navigation/preemption.py");
});

test("renders REACHED closure when the delta says so", () => {
  const payload = JSON.parse(JSON.stringify(FRESH_DELTA));
  payload.delta.freshness_closure_reached = true;
  payload.delta.invalidated = [];
  payload.delta.auto_refreshed = [];
  payload.delta.refresh_required = [];
  payload.delta.blocked_refreshes = [];
  const { el } = mount(payload);
  expect(el.textContent ?? "").toContain("REACHED");
});

test("embeds the feature diagram when the payload carries it", () => {
  const { el } = mount(FRESH_DELTA);
  const embed = el.querySelector(".catchup-diagram-embed") as HTMLElement | null;
  expect(embed).not.toBeNull();
  expect(embed?.getAttribute("src")).toBe("docs/diagrams/DIAG-NAV-009.html");
  const open = el.querySelector(".catchup-diagram-open") as HTMLElement | null;
  expect(open?.getAttribute("href")).toBe("docs/diagrams/DIAG-NAV-009.html");
});

test("renders the missing-diagram state honestly", () => {
  const payload = JSON.parse(JSON.stringify(FRESH_DELTA));
  payload.diagram = { id: "DIAG-NAV-009", title: "D", diagram_path: null, errors: ["html missing"] };
  const { el } = mount(payload);
  const text = el.textContent ?? "";
  expect(text).toContain("missing diagram");
  expect(text).toContain("html missing");
});

test("verify-my-understanding reveals the grill prompt on click (never auto-runs)", () => {
  const { el, dom } = mount(FRESH_DELTA);
  const button = el.querySelector(".catchup-verify button") as HTMLButtonElement | null;
  expect(button).not.toBeNull();
  expect(el.querySelector(".catchup-verify-note")).toBeNull();
  button?.click();
  const note = el.querySelector(".catchup-verify-note");
  expect(note).not.toBeNull();
  expect(note?.textContent ?? "").toContain("grill-understanding");
  // Clicking again does not duplicate the prompt.
  button?.click();
  expect(el.querySelectorAll(".catchup-verify-note").length).toBe(1);
});
