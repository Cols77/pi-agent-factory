import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { traceCheckTool, traceLinkTool, traceNextTool } from "../src/trace-tools.js";

// No child_process mock: this drives the real `uv run python -m factory.trace`
// against this repo, which is the only thing that proves the tool layer and the
// CLI agree. Mirrors docs-server.integration.test.ts.
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const CTX = { cwd: REPO_ROOT };

function run(tool: { execute: Function }, params: unknown) {
  return tool.execute("call-1", params, undefined, undefined, CTX);
}

describe("trace tools against the real CLI", () => {
  test("trace_next hands back a real gap with full candidate statements", async () => {
    const { content } = await run(traceNextTool, {});
    // This repo has tasks declaring no satisfies, so a gap must come back.
    expect(content).toContain("Gap:");
    expect(content).toContain("Pending gaps remaining:");
    // The anti-truncation guarantee: the ordering caveat is always stated when
    // candidates exist, and never a "top 5" cut.
    expect(content).not.toContain("top 5");
  }, 120_000);

  test("trace_check reports the gate failing while gaps are pending", async () => {
    const { content } = await run(traceCheckTool, {});
    expect(content).toContain("GATE FAILED");
  }, 120_000);

  test("trace_link refuses a target that does not exist rather than writing it", async () => {
    const { content } = await run(traceLinkTool, { node_id: "T-051", satisfies: "SR-999" });
    expect(content).toContain("FAILED");
    expect(content).toContain("SR-999");
  }, 120_000);

  test("trace_link refuses ambiguous arguments without touching the CLI", async () => {
    const { content } = await run(traceLinkTool, { node_id: "T-051" });
    expect(content).toContain("exactly one");
  }, 120_000);
});
