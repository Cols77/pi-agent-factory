// test/process-control.test.ts
import { describe, expect, test } from "vitest";
import {
  buildListCommand,
  buildListJsonCommand,
  buildPolishListCommand,
  buildRunCommand,
  buildSystemNavigatorUrl,
  buildWindowsKillArgs,
} from "../src/process-control.js";

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

  test("appends --force when force is set (resume a non-todo task)", () => {
    const cmd = buildRunCommand("openrouter", "anthropic/claude-opus-4", "T-003", true);
    expect(cmd.args).toEqual([
      "run", "python", "-m", "factory.orchestrator", "run",
      "--provider", "openrouter",
      "--model", "anthropic/claude-opus-4",
      "--task", "T-003",
      "--force",
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

describe("buildPolishListCommand", () => {
  test("builds the polish list --json invocation", () => {
    const cmd = buildPolishListCommand();
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual([
      "run", "python", "-m", "factory.polish", "list", "--json",
    ]);
  });
});

describe("buildSystemNavigatorUrl", () => {
  test("targets the /system route on the given server origin", () => {
    expect(buildSystemNavigatorUrl("http://127.0.0.1:54321")).toBe("http://127.0.0.1:54321/system");
  });

  test("always lands on /system regardless of the base URL's own path or query", () => {
    expect(buildSystemNavigatorUrl("http://127.0.0.1:54321/?task=T-042&run=run-7")).toBe(
      "http://127.0.0.1:54321/system",
    );
    expect(buildSystemNavigatorUrl("http://127.0.0.1:54321/some/other/path")).toBe(
      "http://127.0.0.1:54321/system",
    );
  });
});
