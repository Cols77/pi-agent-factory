// test/process-control.test.ts
import { describe, expect, test } from "vitest";
import { buildRunCommand, buildWindowsKillArgs } from "../src/process-control.js";

describe("buildRunCommand", () => {
  test("builds the orchestrator invocation with the given provider/model", () => {
    const cmd = buildRunCommand("openrouter", "anthropic/claude-opus-4");
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual([
      "run", "python", "-m", "factory.orchestrator", "run",
      "--provider", "openrouter",
      "--model", "anthropic/claude-opus-4",
    ]);
  });
});

describe("buildWindowsKillArgs", () => {
  test("builds a forceful tree-kill for the given pid", () => {
    expect(buildWindowsKillArgs(12345)).toEqual(["/PID", "12345", "/T", "/F"]);
  });
});
