import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { EventEmitter } from "node:events";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import factoryWatch from "../src/index.js";
import { spawnTerminalWindow } from "../src/terminal-window.js";
import type { CommandDef, ExtCommandCtx, PiApi, ReplacedSessionCtx, UiApi } from "../src/pi-types.js";

// This test file lives at <repo-root>/pi-ext/factory-watch/test/, so three
// levels up from here is always the real repo root -- regardless of what
// directory `npm test`/vitest itself was invoked from. This matters because
// npm always runs package scripts with process.cwd() set to the package
// directory (pi-ext/factory-watch), *not* the repo root, so `process.cwd()`
// on its own does not reach this repo's real vendored `.pi/skills/`.
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

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
vi.mock("../src/terminal-window.js", () => ({
  spawnTerminalWindow: vi.fn(),
}));

function capture(): { commands: Map<string, CommandDef>; pi: PiApi } {
  const commands = new Map<string, CommandDef>();
  const pi: PiApi = {
    registerCommand: (name, def) => commands.set(name, def),
    on: () => {},
  };
  factoryWatch(pi);
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
    cwd: overrides.cwd ?? process.cwd(),
    ui: overrides.ui ?? ui,
    model:
      "model" in overrides ? overrides.model : { provider: "openrouter", id: "anthropic/claude-opus-4" },
    newSession: overrides.newSession ?? vi.fn(async () => ({ cancelled: false })),
  };
}

describe("factory-watch commands", () => {
  beforeEach(() => {
    vi.mocked(spawnSync).mockReset();
    // spawnTerminalWindow's mock has no baked-in default implementation (it's
    // a bare vi.fn() from the vi.mock factory above), so a full mockReset()
    // between tests is as safe as spawnSync's and matches its convention --
    // without this, an earlier test's call to launchMissionControl leaks into
    // later /factory-run assertions and they'd pass even if /factory-run
    // stopped calling it entirely.
    vi.mocked(spawnTerminalWindow).mockReset();
    // spawn, unlike spawnSync/spawnTerminalWindow, has a real default
    // implementation baked into the vi.mock factory above (it returns a
    // fresh EventEmitter child per call) that several tests below rely on
    // without ever setting their own mockReturnValue. mockReset() would wipe
    // that default implementation entirely (spawn() would then return
    // undefined), breaking those tests -- so only clear call history here,
    // not the implementation.
    vi.mocked(spawn).mockClear();
  });

  test("registers factory, factory-stop, factory-tasks, factory-run, and plan", () => {
    const { commands } = capture();
    expect(commands.has("factory")).toBe(true);
    expect(commands.has("factory-stop")).toBe(true);
    expect(commands.has("factory-tasks")).toBe(true);
    expect(commands.has("factory-run")).toBe(true);
    expect(commands.has("plan")).toBe(true);
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
    // This guard lives in launchAndWatch's poll loop, which only the --auto
    // path uses now that a bare /factory opens the foreground review path.
    vi.useFakeTimers();
    try {
      const { commands } = capture();
      const setWidget = vi.fn(() => {
        throw new Error("This extension ctx is stale after session replacement or reload.");
      });
      const ui: UiApi = {
        notify: vi.fn(),
        setStatus: vi.fn(),
        setWidget,
        select: vi.fn(),
        confirm: vi.fn(async () => true),
        editor: vi.fn(async () => undefined),
        custom: vi.fn(),
      };
      const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only", ui });

      await commands.get("factory")!.handler("--auto", ctx);

      expect(() => vi.advanceTimersByTime(5_000)).not.toThrow();
      expect(setWidget).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  test("/factory --auto still uses the detached launchAndWatch path", async () => {
    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("factory")!.handler("--auto", ctx);
    expect(spawn).toHaveBeenCalled();
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("factory started"), "info");
  });

  test("/factory without --auto spawns non-detached and opens the review overlay on review_pending", async () => {
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter; stdin: { write: ReturnType<typeof vi.fn> }; unref: () => void;
    };
    child.stdout = new EventEmitter();
    child.stdin = { write: vi.fn() };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);
    // computeReviewFiles shells out to `git diff --numstat`/`--name-status`
    // via spawnSync -- give it an empty-but-parseable result (this test
    // only cares that the overlay opens and a decision is written back).
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: "",
      stderr: "",
    } as ReturnType<typeof spawnSync>);

    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(), select: vi.fn(),
      confirm: vi.fn(async () => true), editor: vi.fn(),
      custom: vi.fn(async () => ({ type: "approve" })) as unknown as UiApi["custom"],
    };
    const { commands } = capture();
    const ctx = fakeCtx({ ui });

    const handlerDone = commands.get("factory")!.handler("", ctx);
    child.stdout.emit(
      "data",
      Buffer.from(JSON.stringify({ type: "review_pending", task_id: "T-001", start_commit: "abc123" }) + "\n"),
    );
    child.emit("exit", 0);
    await handlerDone;

    expect(ui.custom).toHaveBeenCalled();
    expect(child.stdin.write).toHaveBeenCalledWith(
      JSON.stringify({ decision: "approve", comments: {} }) + "\n",
    );
  });

  test("/factory without --auto reassembles a review_pending line split across two stdout chunks", async () => {
    // A single `data` event is not guaranteed to align with line boundaries --
    // this reproduces a review_pending JSON line arriving in two pieces (no
    // trailing newline on the first chunk) and confirms the handler still
    // parses it as one line instead of dropping it or crashing on partial JSON.
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter; stdin: { write: ReturnType<typeof vi.fn> }; unref: () => void;
    };
    child.stdout = new EventEmitter();
    child.stdin = { write: vi.fn() };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: "",
      stderr: "",
    } as ReturnType<typeof spawnSync>);

    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(), select: vi.fn(),
      confirm: vi.fn(async () => true), editor: vi.fn(),
      custom: vi.fn(async () => ({ type: "approve" })) as unknown as UiApi["custom"],
    };
    const { commands } = capture();
    const ctx = fakeCtx({ ui });

    const fullLine = JSON.stringify({ type: "review_pending", task_id: "T-002", start_commit: "def456" }) + "\n";
    const splitPoint = Math.floor(fullLine.length / 2);

    const handlerDone = commands.get("factory")!.handler("", ctx);
    // First chunk: no newline yet -- must not fire early or throw on partial JSON.
    child.stdout.emit("data", Buffer.from(fullLine.slice(0, splitPoint)));
    expect(ui.custom).not.toHaveBeenCalled();
    // Second chunk completes the line.
    child.stdout.emit("data", Buffer.from(fullLine.slice(splitPoint)));
    child.emit("exit", 0);
    await handlerDone;

    expect(ui.custom).toHaveBeenCalledTimes(1);
    expect(child.stdin.write).toHaveBeenCalledWith(
      JSON.stringify({ decision: "approve", comments: {} }) + "\n",
    );
  });

  test("/factory without --auto handles two review_pending lines delivered in a single chunk", async () => {
    // The converse boundary case: multiple newline-terminated lines arriving
    // together in one `data` event must each be parsed and handled once,
    // not merged or dropped.
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter; stdin: { write: ReturnType<typeof vi.fn> }; unref: () => void;
    };
    child.stdout = new EventEmitter();
    child.stdin = { write: vi.fn() };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: "",
      stderr: "",
    } as ReturnType<typeof spawnSync>);

    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(), select: vi.fn(),
      confirm: vi.fn(async () => true), editor: vi.fn(),
      custom: vi.fn(async () => ({ type: "approve" })) as unknown as UiApi["custom"],
    };
    const { commands } = capture();
    const ctx = fakeCtx({ ui });

    const line1 = JSON.stringify({ type: "review_pending", task_id: "T-003", start_commit: "aaa111" }) + "\n";
    const line2 = JSON.stringify({ type: "review_pending", task_id: "T-004", start_commit: "bbb222" }) + "\n";

    const handlerDone = commands.get("factory")!.handler("", ctx);
    child.stdout.emit("data", Buffer.from(line1 + line2));
    child.emit("exit", 0);
    await handlerDone;

    expect(ui.custom).toHaveBeenCalledTimes(2);
    expect(child.stdin.write).toHaveBeenCalledTimes(2);
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

  test("/plan rejects an empty topic without starting a session", async () => {
    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("plan")!.handler("   ", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("usage: /plan"), "error");
    expect(ctx.newSession).not.toHaveBeenCalled();
  });

  test("/plan notifies when a required skill isn't vendored in this repo", async () => {
    const { commands } = capture();
    const emptyDir = mkdtempSync(join(tmpdir(), "factory-watch-plan-test-"));
    const ctx = fakeCtx({ cwd: emptyDir });
    await commands.get("plan")!.handler("some topic", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("skill not found"), "error");
    expect(ctx.newSession).not.toHaveBeenCalled();
  });

  test("/plan seeds a fresh session with the topic once skills are found", async () => {
    const { commands } = capture();
    // This repo's real .pi/skills/ has brainstorming + writing-plans vendored
    // (Task 3), so pointing ctx.cwd at the real repo root (REPO_ROOT, not
    // process.cwd() -- see note above) exercises the real
    // loadSkills()+readFileSync() path end to end.
    const ctx = fakeCtx({ cwd: REPO_ROOT });
    await commands.get("plan")!.handler("add battery-aware RTB", ctx);
    expect(ctx.newSession).toHaveBeenCalledTimes(1);
    const call = vi.mocked(ctx.newSession).mock.calls[0]![0];
    const session: ReplacedSessionCtx = { sendUserMessage: vi.fn() };
    await call!.withSession!(session);
    expect(session.sendUserMessage).toHaveBeenCalledWith(
      expect.stringContaining("add battery-aware RTB"),
      { deliverAs: "followUp" },
    );
  });

  test("/factory-run notifies when no todo tasks exist, without spawning", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify([{ id: "T-001", title: "done one", status: "done" }]),
      stderr: "",
    } as ReturnType<typeof spawnSync>);

    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("factory-run")!.handler("", ctx);

    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no todo tasks"), "info");
    expect(ctx.ui.select).not.toHaveBeenCalled();
  });

  test("/factory-run shows a picker over todo tasks and does nothing if cancelled", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify([
        { id: "T-001", title: "First", status: "todo" },
        { id: "T-002", title: "Second", status: "todo" },
      ]),
      stderr: "",
    } as ReturnType<typeof spawnSync>);

    const ui: UiApi = {
      notify: vi.fn(),
      setStatus: vi.fn(),
      setWidget: vi.fn(),
      select: vi.fn().mockResolvedValue(undefined),
      confirm: vi.fn(async () => true),
      editor: vi.fn(async () => undefined),
      custom: vi.fn(),
    };
    const { commands } = capture();
    const ctx = fakeCtx({ ui });
    await commands.get("factory-run")!.handler("", ctx);

    expect(ui.select).toHaveBeenCalledWith("Run which task?", ["T-001  First", "T-002  Second"]);
  });

  test("/factory-run with no id lists todo tasks, picks one, and routes through launchAndWatch/launchInteractiveReview like /factory", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify([{ id: "T-001", title: "First", status: "todo" }]),
      stderr: "",
    } as ReturnType<typeof spawnSync>);
    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(),
      select: vi.fn().mockResolvedValue("T-001  First"),
      confirm: vi.fn(async () => true), editor: vi.fn(), custom: vi.fn(),
    };
    const { commands } = capture();
    const ctx = fakeCtx({ ui });

    await commands.get("factory-run")!.handler("--auto", ctx);

    // --auto -> launchAndWatch -> detached spawn, matching /factory's own --auto test
    expect(spawn).toHaveBeenCalled();
  });

  test("/factory-run spawns a mission control terminal window alongside the run", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
    } as ReturnType<typeof spawnSync>);
    const { commands } = capture();
    const ctx = fakeCtx();

    await commands.get("factory-run")!.handler("--auto T-001", ctx);

    expect(vi.mocked(spawnTerminalWindow)).toHaveBeenCalled();
  });

  test("/factory-run opens mission control immediately, not after the run finishes (interactive mode)", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
    } as ReturnType<typeof spawnSync>);
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter; stdin: { write: ReturnType<typeof vi.fn> }; unref: () => void;
    };
    child.stdout = new EventEmitter();
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);
    const { commands } = capture();
    const ctx = fakeCtx();

    // No --auto: this goes through launchInteractiveReview, which awaits the
    // child's "exit" event before returning. Don't await the handler yet --
    // the whole point of this test is to check spawnTerminalWindow was
    // already called BEFORE the run completes, not merely by the time the
    // handler promise eventually resolves.
    const handlerPromise = commands.get("factory-run")!.handler("T-001", ctx);

    // Let the synchronous/microtask work up to the awaited exit-listener run.
    await Promise.resolve();
    await Promise.resolve();

    expect(vi.mocked(spawnTerminalWindow)).toHaveBeenCalled();

    // Let the handler's awaited promise resolve so the test cleans up.
    child.emit("exit");
    await handlerPromise;
  });

  test("/review-plans notifies when no docs are found, without opening a viewer", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only" });
    await commands.get("review-plans")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no specs, plans, or tasks"), "info");
  });

  test("/review-plans does nothing further when the picker is cancelled", async () => {
    const select = vi.fn().mockResolvedValue(undefined);
    const custom = vi.fn();
    const ui: UiApi = {
      notify: vi.fn(),
      setStatus: vi.fn(),
      setWidget: vi.fn(),
      select,
      confirm: vi.fn(async () => true),
      editor: vi.fn(async () => undefined),
      custom,
    };
    const { commands } = capture();
    // This repo's real root has real specs/plans/tasks (Task 2's listDocs will find some),
    // so the picker is genuinely shown here rather than short-circuited by the empty-list path.
    // Deliberately REPO_ROOT, not process.cwd() -- see the note atop this file: npm always runs
    // package scripts with process.cwd() set to the package directory (pi-ext/factory-watch),
    // which has no docs/tasks dirs of its own and would hit the empty-list branch instead.
    const ctx = fakeCtx({ cwd: REPO_ROOT, ui });
    await commands.get("review-plans")!.handler("", ctx);
    expect(select).toHaveBeenCalledTimes(1);
    expect(custom).not.toHaveBeenCalled();
  });
});
