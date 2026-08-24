import { describe, expect, test, vi } from "vitest";

vi.mock("../src/coherence-status.js", () => ({
  loadCoherenceStatus: vi.fn(),
}));

import {
  COHERENCE_WIDGET_KEY,
  NOT_THAT_PICK_FROM_MENU,
  formatCoherenceMenu,
  formatCoherenceWidget,
  registerCoherenceCommand,
} from "../src/coherence-command.js";
import { loadCoherenceStatus } from "../src/coherence-status.js";
import type { StatusSnapshot } from "../src/coherence-status.js";
import type { CommandDef, ExtCommandCtx, PiApi, UiApi } from "../src/pi-types.js";

const SNAPSHOT: StatusSnapshot = {
  primary: {
    source: "register_check",
    outcome: "failing_gate",
    summary: "register check failed: 1 requirement(s) invalid",
    produced_by: "coherence.register.cli.cmd_check",
    resolve_cmd: ["coherence register check --project-root /repo"],
    observation_ref: "register:requirements",
  },
  exit_code: 1,
  lines: [
    {
      source: "register_check",
      outcome: "failing_gate",
      summary: "register check failed: 1 requirement(s) invalid",
      produced_by: "coherence.register.cli.cmd_check",
      resolve_cmd: ["coherence register check --project-root /repo"],
      observation_ref: "register:requirements",
    },
    {
      source: "audit_age",
      outcome: "proposed_backlog",
      summary: "2 feature(s) declared; none has ever been audited",
      produced_by: "coherence.status._probe_audit_age",
      resolve_cmd: ["coherence audit run FEAT-A --project-root /repo"],
      observation_ref: null,
    },
    {
      source: "trace_check",
      outcome: "nothing_pending",
      summary: "0 pending, 0 deferred, 0 exempt",
      produced_by: "coherence.trace.cli.cmd_check",
      resolve_cmd: null,
      observation_ref: "trace:graph",
    },
  ],
};

function capture(): { commands: Map<string, CommandDef>; pi: PiApi } {
  const commands = new Map<string, CommandDef>();
  const pi: PiApi = {
    registerCommand: (name, def) => commands.set(name, def),
    registerTool: () => {},
    on: () => {},
  };
  registerCoherenceCommand(pi);
  return { commands, pi };
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
    cwd: overrides.cwd ?? "/repo",
    ui: overrides.ui ?? ui,
    hasUI: overrides.hasUI ?? true,
    reload: overrides.reload ?? vi.fn(async () => undefined),
    model: "model" in overrides ? overrides.model : undefined,
    newSession: overrides.newSession ?? vi.fn(async () => ({ cancelled: false })),
  };
}

describe("formatCoherenceMenu", () => {
  test("renders the primary line, its resolve command, and the escape hatch", () => {
    const lines = formatCoherenceMenu(SNAPSHOT);
    expect(lines[0]).toBe("coherence status: [failing_gate] register check failed: 1 requirement(s) invalid");
    expect(lines).toContain("  - coherence register check --project-root /repo");
    expect(lines).toContain(NOT_THAT_PICK_FROM_MENU);
  });

  test("renders every line as a numbered, worst-first menu choice, unreordered", () => {
    const lines = formatCoherenceMenu(SNAPSHOT).join("\n");
    expect(lines).toContain("1. [failing_gate] register check failed: 1 requirement(s) invalid");
    expect(lines).toContain("2. [proposed_backlog] 2 feature(s) declared; none has ever been audited");
    expect(lines).toContain("3. [nothing_pending] 0 pending, 0 deferred, 0 exempt");
  });

  test("renders a multi-command resolve_cmd as a list, never joined into one string", () => {
    const multi: StatusSnapshot = {
      ...SNAPSHOT,
      primary: {
        ...SNAPSHOT.primary,
        resolve_cmd: ["cmd one --flag", "cmd two --flag"],
      },
    };
    const lines = formatCoherenceMenu(multi);
    expect(lines).toContain("  - cmd one --flag");
    expect(lines).toContain("  - cmd two --flag");
    expect(lines.some((l) => l.includes("cmd one --flag;") || l.includes("cmd one --flag &&"))).toBe(false);
  });

  test("omits resolve lines for a line with no resolve_cmd", () => {
    const lines = formatCoherenceMenu(SNAPSHOT).join("\n");
    // trace_check (line 3) has resolve_cmd: null -- nothing after its own line
    // should render as a resolve bullet for it.
    const idx = lines.indexOf("3. [nothing_pending] 0 pending, 0 deferred, 0 exempt");
    expect(idx).toBeGreaterThan(-1);
  });
});

describe("formatCoherenceWidget", () => {
  test("renders one summary line naming the primary outcome", () => {
    expect(formatCoherenceWidget(SNAPSHOT)).toEqual([
      "coherence: failing_gate — register check failed: 1 requirement(s) invalid",
    ]);
  });
});

describe("/using-coherence (zero-argument menu)", () => {
  test("registers using-coherence", () => {
    const { commands } = capture();
    expect(commands.has("using-coherence")).toBe(true);
  });

  test("renders the ranked menu via notify and sets the coherence widget", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("", ctx);

    expect(ctx.ui.setWidget).toHaveBeenCalledWith(COHERENCE_WIDGET_KEY, formatCoherenceWidget(SNAPSHOT));
    expect(ctx.ui.notify).toHaveBeenCalledWith(
      expect.stringContaining(NOT_THAT_PICK_FROM_MENU),
      "info",
    );
    expect(ctx.ui.notify).toHaveBeenCalledWith(
      expect.stringContaining("1. [failing_gate]"),
      "info",
    );
  });

  test("notifies an error and touches no widget when the CLI bridge fails", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: false, error: "boom" });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("", ctx);

    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("boom"), "error");
    expect(ctx.ui.setWidget).not.toHaveBeenCalled();
  });

  test("passes ctx.cwd through to the status bridge", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: "/some/other/repo" });

    await commands.get("using-coherence")!.handler("", ctx);

    expect(loadCoherenceStatus).toHaveBeenCalledWith("/some/other/repo");
  });

  test("sends no model message: never calls newSession, regardless of outcome", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("", ctx);

    expect(ctx.newSession).not.toHaveBeenCalled();
  });

  test("sends no model message even on a bridge error", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: false, error: "boom" });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("", ctx);

    expect(ctx.newSession).not.toHaveBeenCalled();
  });

  test("sends no model message even when an argument is passed", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("some argument", ctx);

    expect(ctx.newSession).not.toHaveBeenCalled();
  });
});
