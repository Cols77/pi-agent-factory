import { resolve } from "node:path";
import { describe, expect, test } from "vitest";
import {
  buildPlanGateCommand,
  parsePlanGateArgs,
  validatePlanGatePath,
} from "../src/plan-gate-command.js";

describe("plan-gate command", () => {
  test("parses four safe root-relative arguments", () => {
    expect(parsePlanGateArgs(".intent/intent.json docs/spec.md docs/plan.md run-001")).toEqual({
      intent: ".intent/intent.json",
      spec: "docs/spec.md",
      plan: "docs/plan.md",
      runId: "run-001",
    });
  });

  test("rejects absolute and traversal paths", () => {
    expect(validatePlanGatePath("C:/outside/intent.json")).toBe(false);
    expect(validatePlanGatePath("docs/../outside.md")).toBe(false);
    expect(validatePlanGatePath("docs/spec\u0000.md")).toBe(false);
  });

  test("builds an argv-only backend bootstrap command", () => {
    expect(
      buildPlanGateCommand("C:/repo", {
        intent: ".intent/intent.json",
        spec: "docs/spec.md",
        plan: "docs/plan.md",
        runId: "run-001",
      }),
    ).toEqual({
      bin: "uv",
      args: [
        "run",
        "coherence",
        "plan",
        "bootstrap",
        "--project-root",
        resolve("C:/repo"),
        "--intent",
        ".intent/intent.json",
        "--spec",
        "docs/spec.md",
        "--plan",
        "docs/plan.md",
        "--run-id",
        "run-001",
        "--decompose",
        "--json",
      ],
    });
  });
});
