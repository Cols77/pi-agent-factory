import { describe, expect, test, vi } from "vitest";

vi.mock("../src/coherence-status.js", () => ({
  loadCoherenceStatus: vi.fn(),
}));

vi.mock("../src/coherence-router.js", () => ({
  loadCoherenceRoute: vi.fn(),
}));

import {
  COHERENCE_WIDGET_KEY,
  NOT_THAT_PICK_FROM_MENU,
  formatCoherenceMenu,
  formatCoherenceWidget,
  formatRouteClassification,
  registerCoherenceCommand,
} from "../src/coherence-command.js";
import { loadCoherenceStatus } from "../src/coherence-status.js";
import type { StatusSnapshot } from "../src/coherence-status.js";
import { loadCoherenceRoute } from "../src/coherence-router.js";
import type { RouteMatch } from "../src/coherence-router.js";
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

// Review finding: `coherence-command.ts` trusts that `snapshot.lines` already
// arrives worst-first sorted (status.py's snapshot_from_lines now guarantees
// this) -- it does no sorting of its own. The SNAPSHOT fixture above was
// hand-assembled already in worst-first order, which never exercised that
// trust: it would have passed identically even if coherence-command.ts had
// silently re-sorted or reordered on its own. This fixture instead mirrors
// the real five-probe shape (`_PROBES`' declared order in status.py:
// trace_check, register_check, run_checkpoint, audit_age, membership_gate)
// with its worst outcome deliberately produced by the THIRD-declared probe
// (run_checkpoint), exactly as the Python-side regression test does -- so a
// menu/widget that happened to just echo declaration order (trace_check
// first) rather than genuinely worst-first order would fail this.
const REALISTIC_SNAPSHOT: StatusSnapshot = {
  primary: {
    source: "run_checkpoint",
    outcome: "interrupted_run",
    summary: "run run-1 (T-001) is interrupted at dev",
    produced_by: "factory.orchestrator.run_cli.load_current_checkpoint",
    resolve_cmd: ["python -m factory.orchestrator run-state inspect run-1 --repo /repo"],
    observation_ref: "run:run-1",
  },
  exit_code: 1,
  lines: [
    {
      source: "run_checkpoint",
      outcome: "interrupted_run",
      summary: "run run-1 (T-001) is interrupted at dev",
      produced_by: "factory.orchestrator.run_cli.load_current_checkpoint",
      resolve_cmd: ["python -m factory.orchestrator run-state inspect run-1 --repo /repo"],
      observation_ref: "run:run-1",
    },
    {
      source: "audit_age",
      outcome: "proposed_backlog",
      summary: "1 feature(s) declared; none has ever been audited",
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
    {
      source: "register_check",
      outcome: "nothing_pending",
      summary: "0 invalid requirement(s)",
      produced_by: "coherence.register.cli.cmd_check",
      resolve_cmd: null,
      observation_ref: "register:requirements",
    },
    {
      source: "membership_gate",
      outcome: "nothing_pending",
      summary: "bundle coverage: 3/3 artifacts",
      produced_by: "coherence.navigate.cli.cmd_coverage",
      resolve_cmd: null,
      observation_ref: "bundle:coverage",
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

  test("menu choice 1 is whichever probe is worst, even when that probe is not first-declared (REALISTIC_SNAPSHOT: run_checkpoint, 3rd of 5 real probes)", () => {
    const lines = formatCoherenceMenu(REALISTIC_SNAPSHOT);
    expect(lines[0]).toBe("coherence status: [interrupted_run] run run-1 (T-001) is interrupted at dev");
    const joined = lines.join("\n");
    expect(joined).toContain("1. [interrupted_run] run run-1 (T-001) is interrupted at dev");
    expect(joined).toContain("2. [proposed_backlog] 1 feature(s) declared; none has ever been audited");
    // The three clean lines fill 3-5, in the same order status.py's stable
    // sort would preserve (trace_check, register_check, membership_gate --
    // _PROBES' own declared order among themselves).
    expect(joined).toContain("3. [nothing_pending] 0 pending, 0 deferred, 0 exempt");
    expect(joined).toContain("4. [nothing_pending] 0 invalid requirement(s)");
    expect(joined).toContain("5. [nothing_pending] bundle coverage: 3/3 artifacts");
  });
});

describe("formatCoherenceWidget", () => {
  test("renders one summary line naming the primary outcome", () => {
    expect(formatCoherenceWidget(SNAPSHOT)).toEqual([
      "coherence: failing_gate — register check failed: 1 requirement(s) invalid",
    ]);
  });

  test("names the worst probe's outcome even when it is not first-declared", () => {
    expect(formatCoherenceWidget(REALISTIC_SNAPSHOT)).toEqual([
      "coherence: interrupted_run — run run-1 (T-001) is interrupted at dev",
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

  test("widget and menu both surface the worst probe even when it is not first-declared (REALISTIC_SNAPSHOT)", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: REALISTIC_SNAPSHOT });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("", ctx);

    expect(ctx.ui.setWidget).toHaveBeenCalledWith(
      COHERENCE_WIDGET_KEY,
      formatCoherenceWidget(REALISTIC_SNAPSHOT),
    );
    expect(ctx.ui.notify).toHaveBeenCalledWith(
      expect.stringContaining("1. [interrupted_run]"),
      "info",
    );
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
    vi.mocked(loadCoherenceRoute).mockReturnValue({ ok: true, value: { route: null } });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("some argument", ctx);

    expect(ctx.newSession).not.toHaveBeenCalled();
  });
});

describe("/using-coherence (argument-present routing)", () => {
  const MATCHED_ROUTE: RouteMatch = { intent: "BUILD", scope_ref: null, score: 4 };
  const MATCHED_WITH_SCOPE: RouteMatch = { intent: "VERIFY_CLAIM", scope_ref: "sr:SR-001", score: 3 };

  test("a classified route prints the classification, the escape hatch, and the ranked menu underneath it", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    vi.mocked(loadCoherenceRoute).mockReturnValue({ ok: true, value: { route: MATCHED_ROUTE } });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("let's build this", ctx);

    expect(ctx.ui.setWidget).toHaveBeenCalledWith(COHERENCE_WIDGET_KEY, formatCoherenceWidget(SNAPSHOT));
    const notified = vi.mocked(ctx.ui.notify).mock.calls[0]?.[0] as string;
    expect(notified).toContain("BUILD");
    expect(notified).toContain(NOT_THAT_PICK_FROM_MENU);
    expect(notified).toContain("1. [failing_gate]");
  });

  test("the classification never appears alone -- the menu always renders underneath it", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    vi.mocked(loadCoherenceRoute).mockReturnValue({ ok: true, value: { route: MATCHED_ROUTE } });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("let's build this", ctx);

    const notified = vi.mocked(ctx.ui.notify).mock.calls[0]?.[0] as string;
    expect(notified).toEqual(
      [...formatRouteClassification(MATCHED_ROUTE), "", ...formatCoherenceMenu(SNAPSHOT)].join("\n"),
    );
  });

  test("a route with a scope_ref renders it in the classification", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    vi.mocked(loadCoherenceRoute).mockReturnValue({ ok: true, value: { route: MATCHED_WITH_SCOPE } });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("verify sr:SR-001", ctx);

    const notified = vi.mocked(ctx.ui.notify).mock.calls[0]?.[0] as string;
    expect(notified).toContain("sr:SR-001");
  });

  test("a null route (no match/tie/below-threshold) falls through to exactly the zero-argument menu", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    vi.mocked(loadCoherenceRoute).mockReturnValue({ ok: true, value: { route: null } });
    const { commands } = capture();
    const ctxArg = fakeCtx();
    const ctxNoArg = fakeCtx();

    await commands.get("using-coherence")!.handler("the weather is nice today", ctxArg);
    await commands.get("using-coherence")!.handler("", ctxNoArg);

    const notifiedWithArg = vi.mocked(ctxArg.ui.notify).mock.calls[0]?.[0];
    const notifiedNoArg = vi.mocked(ctxNoArg.ui.notify).mock.calls[0]?.[0];
    expect(notifiedWithArg).toEqual(notifiedNoArg);
  });

  test("a router-bridge failure falls through to the zero-argument menu rather than erroring", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    vi.mocked(loadCoherenceRoute).mockReturnValue({ ok: false, error: "router boom" });
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("let's build this", ctx);

    expect(ctx.ui.notify).toHaveBeenCalledWith(
      expect.stringContaining("1. [failing_gate]"),
      "info",
    );
    expect(ctx.ui.notify).not.toHaveBeenCalledWith(expect.stringContaining("router boom"), "error");
  });

  test("passes the trimmed argument text to the router bridge, with ctx.cwd", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    vi.mocked(loadCoherenceRoute).mockReturnValue({ ok: true, value: { route: null } });
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: "/some/other/repo" });

    await commands.get("using-coherence")!.handler("  let's build this  ", ctx);

    expect(loadCoherenceRoute).toHaveBeenCalledWith("/some/other/repo", "let's build this");
  });

  test("does not call the router bridge at all when the argument is only whitespace", async () => {
    vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
    vi.mocked(loadCoherenceRoute).mockClear();
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("using-coherence")!.handler("   ", ctx);

    expect(loadCoherenceRoute).not.toHaveBeenCalled();
  });

  test("sends no model message on the classified path", async () => {
      vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
      vi.mocked(loadCoherenceRoute).mockReturnValue({ ok: true, value: { route: MATCHED_ROUTE } });
      const { commands } = capture();
      const ctx = fakeCtx();

      await commands.get("using-coherence")!.handler("let's build this", ctx);

      expect(ctx.newSession).not.toHaveBeenCalled();
    });

    test("a shape-drifted status payload missing `primary` errors out the handler cleanly instead of throwing (F2)", async () => {
      // Force the loaders to hand back a payload that parses as JSON but lacks
      // the `primary` field the render path depends on. Pre-fix this threw inside
      // formatCoherenceWidget and swallowed the menu entirely; post-fix it must
      // produce a clean error notify.
      vi.mocked(loadCoherenceStatus).mockReturnValue({
        ok: true,
        value: { lines: [], exit_code: 1 } as unknown as StatusSnapshot,
      });
      const { commands } = capture();
      const ctx = fakeCtx();

      await commands.get("using-coherence")!.handler("", ctx);

      expect(ctx.ui.notify).toHaveBeenCalledWith(
        expect.stringContaining("missing a primary line"),
        "error",
      );
      expect(ctx.ui.setWidget).not.toHaveBeenCalled();
    });

    test("a route payload of `{route: undefined}` shape falls through to the menu, not a throw (F2)", async () => {
      vi.mocked(loadCoherenceStatus).mockReturnValue({ ok: true, value: SNAPSHOT });
      // Simulate shape-drift: the bridge parsed an object whose `route` is
      // `undefined` (not `null`). Strict `!== null` treated this as a real route
      // and threw in formatRouteClassification; the loose guard must fall back to
      // the plain menu.
      vi.mocked(loadCoherenceRoute).mockReturnValue({
        ok: true,
        value: { route: undefined as unknown as RouteMatch },
      });
      const { commands } = capture();
      const ctxArg = fakeCtx();
      const ctxNoArg = fakeCtx();

      await commands.get("using-coherence")!.handler("some text", ctxArg);
      await commands.get("using-coherence")!.handler("", ctxNoArg);

      expect(ctxArg.ui.notify).toHaveBeenCalled();
      const notifiedWithArg = vi.mocked(ctxArg.ui.notify).mock.calls[0]?.[0] as string;
      expect(notifiedWithArg).toContain(NOT_THAT_PICK_FROM_MENU); // menu rendered, no throw
    });
  });
