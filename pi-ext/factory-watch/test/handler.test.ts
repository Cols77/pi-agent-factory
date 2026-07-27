import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { EventEmitter } from "node:events";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import factoryWatch from "../src/index.js";
import { spawnTerminalWindow } from "../src/terminal-window.js";
import { computeImplementingFiles, computeReviewFiles } from "../src/review-diff.js";
import { runReviewLoop } from "../src/review-overlay.js";
import { reviewDecisionPath, writeReviewDecision } from "../src/review-protocol.js";
import type { PipelineEntry, StatusRecord } from "../src/status-format.js";
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
vi.mock("../src/review-diff.js", () => ({
  computeReviewFiles: vi.fn(),
  computeImplementingFiles: vi.fn(),
}));
vi.mock("../src/review-overlay.js", () => ({
  runReviewLoop: vi.fn(),
}));
vi.mock("../src/review-protocol.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/review-protocol.js")>();
  return { ...actual, writeReviewDecision: vi.fn() };
});

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
    // computeReviewFiles/runReviewLoop/writeReviewDecision are only ever
    // exercised by the human-review status-polling tests below -- reset
    // them every test the same way spawnSync is reset, so a mockReturnValue
    // or resolved mock from one test can't leak into another's assertions.
    vi.mocked(computeReviewFiles).mockReset();
    vi.mocked(runReviewLoop).mockReset();
    vi.mocked(writeReviewDecision).mockReset();
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

  test("/factory-run (interactive) spawns the orchestrator with stdin closed and stdout/stderr to the run log", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
    } as ReturnType<typeof spawnSync>);
    const child = new EventEmitter() as EventEmitter & { unref: () => void };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);
    const { commands } = capture();
    const ctx = fakeCtx();

    const handlerPromise = commands.get("factory-run")!.handler("T-001", ctx);
    await Promise.resolve();
    child.emit("exit");
    await handlerPromise;

    // stdin MUST stay "ignore": the file-based human-review handshake depends
    // on the orchestrator having no inherited stdin pipe. stdout/stderr are
    // redirected to the run log (a file descriptor, i.e. a number) so a run
    // that dies mid-pipeline leaves a trace instead of vanishing silently.
    const stdio = vi.mocked(spawn).mock.calls[0]![2]!.stdio as [unknown, unknown, unknown];
    expect(stdio[0]).toBe("ignore");
    expect(typeof stdio[1]).toBe("number");
    expect(typeof stdio[2]).toBe("number");
  });

  test("/factory-run (interactive) detects a blocked human-review via the status file and writes the decision to a file, not the child's stdin", async () => {
    // No child.stdin exists at all in the new stdio-closed world (stdio is
    // fully "ignore") -- the only way a decision can reach the orchestrator
    // is via writeReviewDecision(reviewDecisionPath(...), decision), which
    // this test asserts on directly instead of a child.stdin.write spy.
    vi.useFakeTimers();
    try {
      vi.mocked(spawnSync).mockReturnValue({
        status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
      } as ReturnType<typeof spawnSync>);
      const child = new EventEmitter() as EventEmitter & { unref: () => void };
      child.unref = () => {};
      vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

      // Real tmp status file under ctx.cwd, matching this file's existing
      // "/plan notifies when a required skill isn't vendored" convention of
      // pointing ctx.cwd at a real mkdtempSync() dir rather than mocking fs.
      const cwd = mkdtempSync(join(tmpdir(), "factory-watch-review-poll-"));
      mkdirSync(join(cwd, "sessions"), { recursive: true });
      const blockedEntry: PipelineEntry = {
        node: "human-review",
        node_state: "blocked",
        attempt: 0,
        max_attempts: 0,
        snippet: "",
        outcome: null,
        handoff: null,
        updated_at: new Date().toISOString(),
        start_commit: "abc123",
      };
      const record: StatusRecord = {
        session_id: "sess-1",
        task_id: "T-001",
        current_node: "human-review",
        current_state: "blocked",
        pipeline: [blockedEntry],
        started_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      writeFileSync(join(cwd, "sessions", ".factory-status.json"), JSON.stringify(record), "utf-8");

      const files = [{ path: "a.ts", status: "M" as const, added: 1, removed: 0 }];
      vi.mocked(computeReviewFiles).mockReturnValue(files);
      const decision = { decision: "approve" as const, comments: {} };
      vi.mocked(runReviewLoop).mockResolvedValue(decision);

      const { commands } = capture();
      const ctx = fakeCtx({ cwd });

      const handlerPromise = commands.get("factory-run")!.handler("T-001", ctx);
      await Promise.resolve();

      // One poll tick (POLL_INTERVAL_MS = 1000 in src/index.ts) is enough to
      // read the status file and detect the blocked human-review entry.
      vi.advanceTimersByTime(1000);
      // runReviewLoop's resolution and the writeReviewDecision it triggers
      // happen in a .then() microtask, not synchronously inside the poll
      // tick -- flush the microtask queue before asserting.
      await Promise.resolve();
      await Promise.resolve();

      expect(vi.mocked(runReviewLoop)).toHaveBeenCalledWith(ctx.ui, cwd, "T-001", "abc123", files);
      expect(vi.mocked(writeReviewDecision)).toHaveBeenCalledWith(
        reviewDecisionPath(cwd, "sess-1"),
        decision,
      );

      child.emit("exit");
      await handlerPromise;
    } finally {
      vi.useRealTimers();
    }
  });

  test("/factory-run already-done human-review uses the implementing diff + banner", async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(spawnSync).mockReturnValue({
        status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
      } as ReturnType<typeof spawnSync>);
      const child = new EventEmitter() as EventEmitter & { unref: () => void };
      child.unref = () => {};
      vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

      const cwd = mkdtempSync(join(tmpdir(), "factory-watch-already-done-"));
      mkdirSync(join(cwd, "sessions"), { recursive: true });
      const blockedEntry: PipelineEntry = {
        node: "human-review", node_state: "blocked", attempt: 0, max_attempts: 0,
        snippet: "", outcome: null, handoff: null, updated_at: new Date().toISOString(),
        start_commit: "abc123", already_done: true, deliverables: ["src/x.py"],
      };
      const record: StatusRecord = {
        session_id: "sess-1", task_id: "T-001", current_node: "human-review", current_state: "blocked",
        pipeline: [blockedEntry], started_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      };
      writeFileSync(join(cwd, "sessions", ".factory-status.json"), JSON.stringify(record), "utf-8");

      const implFiles = [{ path: "src/x.py", status: "A" as const, added: 5, removed: 0 }];
      vi.mocked(computeImplementingFiles).mockReturnValue(implFiles);
      vi.mocked(runReviewLoop).mockResolvedValue({ decision: "approve", comments: {} });

      const { commands } = capture();
      const ctx = fakeCtx({ cwd });

      const handlerPromise = commands.get("factory-run")!.handler("T-001", ctx);
      await Promise.resolve();
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();

      expect(vi.mocked(computeImplementingFiles)).toHaveBeenCalledWith(cwd, ["src/x.py"]);
      expect(vi.mocked(computeReviewFiles)).not.toHaveBeenCalled();
      expect(vi.mocked(runReviewLoop)).toHaveBeenCalledWith(
        ctx.ui, cwd, "T-001", "abc123", implFiles,
        expect.objectContaining({ implementing: true }),
      );

      child.emit("exit");
      await handlerPromise;
    } finally {
      vi.useRealTimers();
    }
  });

  test("/factory-run (interactive) does not launch a second review loop for the same task while one is already in flight", async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(spawnSync).mockReturnValue({
        status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
      } as ReturnType<typeof spawnSync>);
      const child = new EventEmitter() as EventEmitter & { unref: () => void };
      child.unref = () => {};
      vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

      const cwd = mkdtempSync(join(tmpdir(), "factory-watch-review-dedupe-"));
      mkdirSync(join(cwd, "sessions"), { recursive: true });
      const blockedEntry: PipelineEntry = {
        node: "human-review",
        node_state: "blocked",
        attempt: 0,
        max_attempts: 0,
        snippet: "",
        outcome: null,
        handoff: null,
        updated_at: new Date().toISOString(),
        start_commit: "abc123",
      };
      const record: StatusRecord = {
        session_id: "sess-1",
        task_id: "T-001",
        current_node: "human-review",
        current_state: "blocked",
        pipeline: [blockedEntry],
        started_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      writeFileSync(join(cwd, "sessions", ".factory-status.json"), JSON.stringify(record), "utf-8");

      vi.mocked(computeReviewFiles).mockReturnValue([]);
      vi.mocked(runReviewLoop).mockResolvedValue({ decision: "approve", comments: {} });

      const { commands } = capture();
      const ctx = fakeCtx({ cwd });

      const handlerPromise = commands.get("factory-run")!.handler("T-001", ctx);
      await Promise.resolve();

      // Two ticks that both see the same still-blocked task_id in the
      // status file must not start a second review loop for it.
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();

      expect(vi.mocked(runReviewLoop)).toHaveBeenCalledTimes(1);

      child.emit("exit");
      await handlerPromise;
    } finally {
      vi.useRealTimers();
    }
  });

  test("/factory-run (interactive) re-launches the review loop for a SECOND blocked round on the same task_id, after the first round left the blocked state", async () => {
    // Regression test for the reviewInFlightForTask guard never resetting:
    // the orchestrator loops the same task.id back through dev-retry after a
    // reject and can block on a second human-review round for that same
    // task later. Without resetting the guard when the entry leaves
    // "blocked", the second round's still-equal task_id would be silently
    // suppressed forever and runReviewLoop would only ever be called once.
    vi.useFakeTimers();
    try {
      vi.mocked(spawnSync).mockReturnValue({
        status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
      } as ReturnType<typeof spawnSync>);
      const child = new EventEmitter() as EventEmitter & { unref: () => void };
      child.unref = () => {};
      vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

      const cwd = mkdtempSync(join(tmpdir(), "factory-watch-review-second-round-"));
      mkdirSync(join(cwd, "sessions"), { recursive: true });
      const statusPath = join(cwd, "sessions", ".factory-status.json");

      const blockedEntry: PipelineEntry = {
        node: "human-review",
        node_state: "blocked",
        attempt: 0,
        max_attempts: 0,
        snippet: "",
        outcome: null,
        handoff: null,
        updated_at: new Date().toISOString(),
        start_commit: "abc123",
      };
      const firstRoundRecord: StatusRecord = {
        session_id: "sess-1",
        task_id: "T-001",
        current_node: "human-review",
        current_state: "blocked",
        pipeline: [blockedEntry],
        started_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      writeFileSync(statusPath, JSON.stringify(firstRoundRecord), "utf-8");

      vi.mocked(computeReviewFiles).mockReturnValue([]);
      vi.mocked(runReviewLoop).mockResolvedValue({ decision: "reject", comments: {} });

      const { commands } = capture();
      const ctx = fakeCtx({ cwd });

      const handlerPromise = commands.get("factory-run")!.handler("T-001", ctx);
      await Promise.resolve();

      // First blocked round is detected -- runReviewLoop launches once.
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
      expect(vi.mocked(runReviewLoop)).toHaveBeenCalledTimes(1);

      // The orchestrator resolves the review (reject) and loops the same
      // task back through a dev retry -- the status file now shows the
      // human-review node no longer blocked.
      const devRetryRecord: StatusRecord = {
        ...firstRoundRecord,
        current_node: "dev",
        current_state: "running",
        pipeline: [{ ...blockedEntry, node_state: "running" }],
        updated_at: new Date().toISOString(),
      };
      writeFileSync(statusPath, JSON.stringify(devRetryRecord), "utf-8");
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
      // Still only the one call from the first round -- leaving "blocked"
      // must not itself trigger a new review loop.
      expect(vi.mocked(runReviewLoop)).toHaveBeenCalledTimes(1);

      // Dev retry finishes and the SAME task_id blocks on a second
      // human-review round.
      const secondRoundRecord: StatusRecord = {
        ...firstRoundRecord,
        pipeline: [{ ...blockedEntry, start_commit: "def456", updated_at: new Date().toISOString() }],
        updated_at: new Date().toISOString(),
      };
      writeFileSync(statusPath, JSON.stringify(secondRoundRecord), "utf-8");
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();

      expect(vi.mocked(runReviewLoop)).toHaveBeenCalledTimes(2);
      expect(vi.mocked(runReviewLoop)).toHaveBeenNthCalledWith(2, ctx.ui, cwd, "T-001", "def456", []);

      child.emit("exit");
      await handlerPromise;
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
