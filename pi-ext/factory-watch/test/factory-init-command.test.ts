// Command-wiring tests for /factory-init's sibling diagnostics commands.
//
// Task 5 (coherence increment 5): /factory-doctor is renamed to
// /factory-selfcheck. /factory-doctor is kept as a deprecated forwarder --
// it still runs the full diagnostic afterward, it does not become a dead
// end. These tests exercise the actual pi.registerCommand wiring (not just
// the pure factory-init.ts helpers, which factory-init.test.ts already
// covers) via a fake PiApi, the same pattern coherence-command.test.ts uses.
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test, vi } from "vitest";

import { registerFactoryInit } from "../src/factory-init-command.js";
import type { CommandDef, ExtCommandCtx, PiApi, UiApi } from "../src/pi-types.js";

function capture(): { commands: Map<string, CommandDef> } {
  const commands = new Map<string, CommandDef>();
  const pi: PiApi = {
    registerCommand: (name, def) => commands.set(name, def),
    registerTool: () => {},
    on: () => {},
  };
  registerFactoryInit(pi);
  return { commands };
}

function fakeCtx(overrides: Partial<ExtCommandCtx> = {}): ExtCommandCtx {
  const ui: UiApi = {
    notify: vi.fn(),
    setStatus: vi.fn(),
    setWidget: vi.fn(),
    select: vi.fn(),
    confirm: vi.fn(async () => true),
    editor: vi.fn(async () => undefined),
    custom: vi.fn(),
  };
  return {
    cwd: overrides.cwd ?? mkdtempSync(join(tmpdir(), "pif-cmd-")),
    ui: overrides.ui ?? ui,
    hasUI: overrides.hasUI ?? true,
    reload: overrides.reload ?? vi.fn(async () => undefined),
    model: "model" in overrides ? overrides.model : undefined,
    newSession: overrides.newSession ?? vi.fn(async () => ({ cancelled: false })),
  };
}

function notifiedLines(ui: UiApi): string[] {
  return vi.mocked(ui.notify).mock.calls.map((call) => call[0] as string);
}

describe("/factory-selfcheck", () => {
  test("is registered", () => {
    const { commands } = capture();
    expect(commands.has("factory-selfcheck")).toBe(true);
  });

  test("performs the current bootstrap diagnostics (root/profile/AGENTS.md/tools/subagent metadata)", async () => {
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("factory-selfcheck")!.handler("", ctx);

    const lines = notifiedLines(ctx.ui);
    expect(lines.some((l) => l.includes("root resolution:"))).toBe(true);
    expect(lines.some((l) => l.includes("profile present:"))).toBe(true);
    expect(lines.some((l) => l.includes("AGENTS.md block:"))).toBe(true);
    expect(lines.some((l) => l.includes("subagent metadata:"))).toBe(true);
    expect(lines.some((l) => l.includes("tools aligned:"))).toBe(true);
    expect(lines.some((l) => l.includes("summary:"))).toBe(true);
    // No deprecation warning on the renamed command itself.
    expect(lines.some((l) => l.includes("deprecated"))).toBe(false);
  });

  test("has the same description text /factory-doctor used to have", () => {
    const { commands } = capture();
    expect(commands.get("factory-selfcheck")!.description).toBe(
      "Diagnose the project bootstrap: root, profile, AGENTS.md block, essential tools, subagent metadata",
    );
  });
});

describe("/factory-doctor (deprecated forwarder)", () => {
  test("is still registered", () => {
    const { commands } = capture();
    expect(commands.has("factory-doctor")).toBe(true);
  });

  test("prints exactly one deprecation line naming /factory-selfcheck, as a warning", async () => {
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("factory-doctor")!.handler("", ctx);

    const warningCalls = vi.mocked(ctx.ui.notify).mock.calls.filter((call) => call[1] === "warning");
    expect(warningCalls.length).toBe(1);
    expect(warningCalls[0][0]).toContain("factory-doctor");
    expect(warningCalls[0][0]).toContain("factory-selfcheck");
    expect(warningCalls[0][0].toLowerCase()).toContain("deprecat");
  });

  test("still forwards: runs the full diagnostic after the deprecation line (not a dead end)", async () => {
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("factory-doctor")!.handler("", ctx);

    const lines = notifiedLines(ctx.ui);
    // The deprecation line, plus the full diagnostic report that
    // /factory-selfcheck itself would have produced.
    expect(lines.some((l) => l.includes("root resolution:"))).toBe(true);
    expect(lines.some((l) => l.includes("profile present:"))).toBe(true);
    expect(lines.some((l) => l.includes("AGENTS.md block:"))).toBe(true);
    expect(lines.some((l) => l.includes("subagent metadata:"))).toBe(true);
    expect(lines.some((l) => l.includes("summary:"))).toBe(true);
  });

  test("produces the identical diagnostic report /factory-selfcheck produces (same underlying handler)", async () => {
    const { commands } = capture();
    const root = mkdtempSync(join(tmpdir(), "pif-cmd-"));

    const selfcheckCtx = fakeCtx({ cwd: root });
    await commands.get("factory-selfcheck")!.handler("", selfcheckCtx);
    const selfcheckLines = notifiedLines(selfcheckCtx.ui);

    const doctorCtx = fakeCtx({ cwd: root });
    await commands.get("factory-doctor")!.handler("", doctorCtx);
    const doctorLines = notifiedLines(doctorCtx.ui);
    // Drop the leading deprecation warning; the rest must match verbatim.
    const doctorReportLines = doctorLines.slice(1);

    expect(doctorReportLines).toEqual(selfcheckLines);
  });

  test("has the same description text as /factory-selfcheck", () => {
    const { commands } = capture();
    expect(commands.get("factory-doctor")!.description).toBe(
      commands.get("factory-selfcheck")!.description,
    );
  });
});
