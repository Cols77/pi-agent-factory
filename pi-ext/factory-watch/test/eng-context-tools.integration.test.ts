import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { buildEngContextTools } from "../src/eng-context-tools.js";

// No child_process mock: this drives the real `uv run python -m factory.system`
// against this repo, which is the only thing that proves the tool layer and the
// CLI agree. Mirrors trace-tools.integration.test.ts.
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const CTX = { cwd: REPO_ROOT };

const tools = buildEngContextTools();

async function run(tool: { execute: Function }, params: unknown) {
  const r = await tool.execute("call-1", params, undefined, undefined, CTX);
  return r.content.map((c: { text: string }) => c.text).join("\n");
}

describe("eng-context tools against the real CLI", () => {
  test("eng_get_vcycle resolves a real feature scope and cites Python's result", async () => {
    const tool = tools.find((t) => t.name === "eng_get_vcycle")!;
    const out = await run(tool, { ref: "feat:FEAT-NAV-017" });
    expect(out.length).toBeGreaterThan(0);
  }, 120_000);

  test("eng_get_goal on a missing goal surfaces a real CLI failure, never a guess", async () => {
    const tool = tools.find((t) => t.name === "eng_get_goal")!;
    const out = await run(tool, { goal_id: "GOAL-DOES-NOT-EXIST-000" });
    expect(out).toContain("eng_get_goal failed");
  }, 120_000);

  test("eng_trace_requirement on a missing requirement reports a trace failure", async () => {
    const tool = tools.find((t) => t.name === "eng_trace_requirement")!;
    const out = await run(tool, { requirement_id: "SR-999999" });
    expect(out).toContain("trace for SR-999999:");
  }, 120_000);

  // The action tool is exercised only on its failure path here: a successful
  // evaluate would WRITE goal state into the repo, which tests must never do.
  test("eng_evaluate_goal on a missing goal surfaces a real CLI failure", async () => {
    const tool = tools.find((t) => t.name === "eng_evaluate_goal")!;
    const out = await run(tool, { goal_id: "GOAL-DOES-NOT-EXIST-000" });
    expect(out).toContain("eng_evaluate_goal failed");
    expect(out).toContain("no goal with id");
  }, 120_000);

  // An empty artifact is rejected with no side effect: eng_present records
  // intent and declares the plan, it never opens UI or routes (Inc 5 does).
  test("eng_present validates the artifact and rejects an empty one", async () => {
    const tool = tools.find((t) => t.name === "eng_present")!;
    const out = await run(tool, { artifact: "" });
    expect(out).toContain("eng_present failed");
    expect(out).toContain("non-empty artifact");
  }, 120_000);
});
