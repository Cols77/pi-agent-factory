// test/process-control.test.ts
import { describe, expect, test } from "vitest";
import { buildListCommand, buildListJsonCommand, buildRunCommand, buildWindowsKillArgs } from "../src/process-control.js";

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

describe("buildListCommand", () => {
  test("builds the orchestrator list invocation", () => {
    const cmd = buildListCommand();
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual(["run", "python", "-m", "factory.orchestrator", "list"]);
  });
});

describe("buildWindowsKillArgs", () => {
  test("builds a forceful tree-kill for the given pid", () => {
    expect(buildWindowsKillArgs(12345)).toEqual(["/PID", "12345", "/T", "/F"]);
  });
});

describe("buildRunCommand with a task id", () => {
  test("appends --task when a task id is given", () => {
    const cmd = buildRunCommand("openrouter", "anthropic/claude-opus-4", "T-003");
    expect(cmd.args).toEqual([
      "run", "python", "-m", "factory.orchestrator", "run",
      "--provider", "openrouter",
      "--model", "anthropic/claude-opus-4",
      "--task", "T-003",
    ]);
  });
});

describe("buildListJsonCommand", () => {
  test("builds the orchestrator list --json invocation", () => {
    const cmd = buildListJsonCommand();
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual(["run", "python", "-m", "factory.orchestrator", "list", "--json"]);
  });
});
