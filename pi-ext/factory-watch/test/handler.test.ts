import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import factoryWatch from "../src/index.js";
import type { CommandDef, ExtCommandCtx, PiApi, UiApi } from "../src/pi-types.js";

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
  test("registers both factory and factory-stop", () => {
    const { commands } = capture();
    expect(commands.has("factory")).toBe(true);
    expect(commands.has("factory-stop")).toBe(true);
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
});
