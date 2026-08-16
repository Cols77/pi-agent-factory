import { describe, expect, test } from "vitest";
import { buildTaskPreamble } from "../src/task-preamble.js";
import type { TaskReadSurface } from "../src/task-preamble.js";

describe("task preamble (Inc 4, Task 4)", () => {
  test("calls the read tools in spec §26 order 1->4 and renders a compact block", () => {
    const order: string[] = [];
    const reads: TaskReadSurface = {
      featureContext: () => {
        order.push("featureContext");
        return "FEAT-NAV-017\nrequirements: SR-001";
      },
      requirements: () => {
        order.push("requirements");
        return "SR-001, SR-002";
      },
      goals: () => {
        order.push("goals");
        return "GOAL-NAV-003 [ACTIVE] Reacquire";
      },
      affectedDesign: () => {
        order.push("affectedDesign");
        return "design: ADR-001\ntasks: T-001\nfiles: src/a.py";
      },
    };

    const block = buildTaskPreamble("FEAT-NAV-017", reads);

    // The four read tools are called in the fixed §26 order 1->4.
    expect(order).toEqual(["featureContext", "requirements", "goals", "affectedDesign"]);

    // Section markers appear in order, each present.
    const markers = [
      "1. feature context",
      "2. requirements",
      "3. active goals",
      "4. affected design/code",
    ];
    const positions = markers.map((m) => block.indexOf(m));
    for (const p of positions) expect(p).toBeGreaterThan(-1);
    for (let i = 1; i < positions.length; i++) {
      expect(positions[i]! > positions[i - 1]!).toBe(true);
    }

    // The feature id threads through, and section content is indented.
    expect(block).toContain("task context for FEAT-NAV-017");
    expect(block).toContain("\n  SR-001, SR-002");
    expect(block).toContain("\n  GOAL-NAV-003 [ACTIVE] Reacquire");
    expect(block).toContain("\n  files: src/a.py");
  });
});
