import { JSDOM } from "jsdom";
import { describe, expect, test } from "vitest";
import { renderReferencePage } from "../src/review-reference.js";
import type { ReviewPageData } from "../src/review-server.js";

const DATA: ReviewPageData = {
  taskId: "T-042",
  banner: "⚠ Grill warning: not-agreed.",
  implementing: false,
  guide: {
    confidence: "high",
    validation: [
      { gate: "unit", ok: true, summary: "163 passed" },
      { gate: "sim", ok: false, summary: "reacquisition_rate regressed" },
    ],
    verify: [
      { item: "reject a missing colon", file: "src/factory/cli/__main__.py", line: 22 },
      { item: "atomic writes under concurrent runs", file: "src/factory/status/store.py", line: 31 },
    ],
    addressed: ["status file path moved under sessions/ as agreed"],
  },
  files: [{ path: "a.py", status: "M", added: 1, removed: 1 }],
  diffs: { "a.py": { lines: [], meta: [] } },
  task: {
    id: "T-042",
    path: "tasks/T-042-example.md",
    title: "Example task",
    status: "human-review",
    dod: ["Show the task in the browser"],
    html: "<p>Task body.</p>",
  },
  intent: {
    chain: [
      { kind: "br", id: "BR-004", title: "Operators can see pipeline state", path: "", alternatives: 0 },
      { kind: "sr", id: "SR-007", title: "The reviewer sees intent", path: "requirements/SR-007.md", alternatives: 1 },
      { kind: "spec", id: "spec:2026-07-20-design.md", title: "Design spec", path: "docs/superpowers/specs/2026-07-20-design.md", alternatives: 0 },
      { kind: "plan", id: "plan:2026-07-20-plan.md", title: "Plan", path: "docs/superpowers/plans/2026-07-20-plan.md", alternatives: 0 },
      { kind: "task", id: "T-042", title: "Example task", path: "tasks/T-042-example.md", alternatives: 0 },
    ],
    stopsAt: null,
    planSection: {
      planPath: "docs/superpowers/plans/example.md",
      heading: "Task 3: Do the thing",
      html: "<p>Prose from the plan section.</p>",
    },
    dod: ["intent dod entry"],
    status: "human-review",
    requirements: ["SR-007"],
  },
  layout: { collapsed: [], zoomed: null, guide: false },
};

describe("task page", () => {
  const html = renderReferencePage("task", DATA, "/repo");
  const dom = new JSDOM(html);

  test("renders the intent chain, the fan-out marker, the DoD and the task body", () => {
    const chain = (dom.window.document.querySelector(".chain") as HTMLElement)?.textContent ?? "";
    expect(chain).toContain("sr · SR-007 — The reviewer sees intent");
    expect(chain).toContain("(+1 more)"); // the fan-out marker
    expect(html).toContain("T-042 — Example task");
    expect(html).toContain("intent dod entry");
    expect(html).toContain("Task body");
    expect(html).toContain("tasks/T-042-example.md");
  });
});

describe("plan page", () => {
  test("renders the plan section heading and prose", () => {
    const html = renderReferencePage("plan", DATA, "/repo");
    expect(html).toContain("From plan");
    expect(html).toContain("Task 3: Do the thing");
    expect(html).toContain("Prose from the plan section");
  });

  test("fallback when no plan section", () => {
    const noPlan = { ...DATA, intent: { ...DATA.intent!, planSection: null } };
    const html = renderReferencePage("plan", noPlan, "/repo");
    expect(html).toContain("(no plan section resolved for this task)");
  });
});

describe("spec page", () => {
  test("renders a spec node from the chain", () => {
    const html = renderReferencePage("spec", DATA, "/repo");
    expect(html).toContain("spec:2026-07-20-design.md");
    // The file doesn't exist in the fixture repo, so the spec body says
    // "could not read" -- falls back gracefully.
    expect(html).toMatch(/could not read|no spec linked/);
  });

  test("fallback when no spec node in chain", () => {
    const noSpec = { ...DATA, intent: { ...DATA.intent!, chain: [{ kind: "task" as const, id: "T-042", title: "Task", path: "tasks/T-042-example.md", alternatives: 0 }] } };
    const html = renderReferencePage("spec", noSpec, "/repo");
    expect(html).toContain("(no spec linked in the intent chain for this task)");
  });
});

describe("verify page", () => {
  const html = renderReferencePage("verify", DATA, "/repo");

  test("renders the banner, confidence, gates, verify items and addressed", () => {
    expect(html).toContain("⚠ Grill warning: not-agreed.");
    expect(html).toContain("Confidence: high");
    expect(html).toContain("unit 163 passed ✓");
    expect(html).toContain("sim");
    expect(html).toContain("Verify before approving");
    expect(html).toContain("reject a missing colon");
    expect(html).toContain("Already addressed");
    expect(html).toContain("status file path moved under sessions/");
  });

  test("fallback when no guidance", () => {
    const noGuide = { ...DATA, guide: null };
    const html = renderReferencePage("verify", noGuide, "/repo");
    expect(html).toContain("(no guidance recorded for this task)");
  });
});