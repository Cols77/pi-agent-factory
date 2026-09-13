import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { buildExecutionTools } from "../src/execution-tools.js";

// No child_process mock and no injected runner: these tools are built with
// their DEFAULT runner, which executes the real `uv run coherence execution ...`
// command against this repo. That is the only thing that proves the Pi adapter
// and the Python CLI produce the same projection -- the unit test's stub proves
// the argv, not the payload. Mirrors eng-context-tools.integration.test.ts.
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const CTX = { cwd: REPO_ROOT };

// The same checked-in expectation the Python test
// (tests/unit/coherence/test_execution_cli.py) asserts byte-identity against.
const PARITY_FIXTURE = join(
  REPO_ROOT,
  "tests",
  "fixtures",
  "execution_legal_actions_parity.json",
);

function sorted(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sorted);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([key, item]) => [key, sorted(item)]),
    );
  }
  return value;
}

describe("execution tools against the real Python CLI", () => {
  test("the forwarded legal-action projection is the checked-in host expectation", async () => {
    const tool = (buildExecutionTools() as { name: string; execute: Function }[]).find(
      (entry) => entry.name === "execution_legal_actions",
    )!;

    const result = (await tool.execute(
      "call-1",
      { run_id: "feat013-parity", task_id: "T-013" },
      undefined,
      undefined,
      CTX,
    )) as { content: { text: string }[] };

    const forwarded = result.content.map((block) => block.text).join("");
    const expected = JSON.parse(readFileSync(PARITY_FIXTURE, "utf-8"));
    expect(sorted(JSON.parse(forwarded))).toEqual(sorted(expected));
    expect(JSON.parse(forwarded).starts_automatically).toBe(false);
  }, 120_000);
});
