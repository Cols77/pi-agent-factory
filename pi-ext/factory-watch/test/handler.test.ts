import { spawnSync } from "node:child_process";
import { EventEmitter } from "node:events";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import factoryWatch from "../src/index.js";
import type { CommandDef, ExtCommandCtx, PiApi, UiApi } from "../src/pi-types.js";

vi.mock("node:child_process", () => ({
  spawn: vi.fn(() => {
    const child = new EventEmitter() as EventEmitter & { unref: () => void };
    child.unref = () => {};
    return child;
  }),
  spawnSync: vi.fn(),
}));
vi.mock("node:fs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs")>();
  return { ...actual, openSync: vi.fn(() => 0) };
});

function capture(): { commands: Map<string, CommandDef>; pi: PiApi } {
  const commands = new Map<string, CommandDef>();
  const pi: PiApi = {
    registerCommand: (name, def) => commands.set(name, def),
  };
  factoryWatch(pi);
  return { commands, pi };
}

function fakeCtx(overrides: Partial<ExtCommandCtx> = {}): ExtCommandCtx {
  const ui: UiApi = {
    notify: vi.fn(),
    setStatus: vi.fn(),
    setWidget: vi.fn(),
  };
  return {
    cwd: overrides.cwd ?? process.cwd(),
    ui: overrides.ui ?? ui,
    model:
      "model" in overrides ? overrides.model : { provider: "openrouter", id: "anthropic/claude-opus-4" },
  };
}

describe("factory-watch commands", () => {
  beforeEach(() => {
    vi.mocked(spawnSync).mockReset();
  });

  test("registers factory, factory-stop, and factory-tasks", () => {
    const { commands } = capture();
    expect(commands.has("factory")).toBe(true);
    expect(commands.has("factory-stop")).toBe(true);
    expect(commands.has("factory-tasks")).toBe(true);
  });

  test("/factory notifies an error and does nothing else when no model is active", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ model: undefined });
    await commands.get("factory")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no model"), "error");
  });

  test("/factory-stop notifies when nothing is running (no lock file)", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only" });
    await commands.get("factory-stop")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("not running"), "info");
  });

  test("/factory's poll loop stops instead of crashing once ctx goes stale", async () => {
    // Reproduces a real crash seen running `pi -p "/factory"`: in print mode
    // (and after ctx.newSession()/fork()/reload() in an interactive one),
    // ctx.ui becomes stale and throws on access. Before the fix, the next
    // setInterval tick threw uncaught and took the whole host process down.
    vi.useFakeTimers();
    try {
      const { commands } = capture();
      const setWidget = vi.fn(() => {
        throw new Error("This extension ctx is stale after session replacement or reload.");
      });
      const ui: UiApi = { notify: vi.fn(), setStatus: vi.fn(), setWidget };
      const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only", ui });

      await commands.get("factory")!.handler("", ctx);

      expect(() => vi.advanceTimersByTime(5_000)).not.toThrow();
      expect(setWidget).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  test("/factory-tasks renders the task board via a widget", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: "TODO (1)\n  T-001  Example task\n",
      stderr: "",
    } as ReturnType<typeof spawnSync>);

    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("factory-tasks")!.handler("", ctx);

    expect(ctx.ui.setWidget).toHaveBeenCalledWith("factory-tasks", [
      "TODO (1)",
      "  T-001  Example task",
    ]);
  });

  test("/factory-tasks notifies an error when the CLI call fails", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 1,
      stdout: "",
      stderr: "boom",
    } as ReturnType<typeof spawnSync>);

    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("factory-tasks")!.handler("", ctx);

    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("boom"), "error");
  });
});
