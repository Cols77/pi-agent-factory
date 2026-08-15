import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { EventEmitter } from "node:events";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import factoryWatch from "../src/index.js";
import { spawnTerminalWindow } from "../src/terminal-window.js";
import { openInBrowser, readSurfacePref, writeSurfacePref } from "../src/review-surface.js";
import { computeImplementingFiles, computeReviewFiles } from "../src/review-diff.js";
import { runReviewLoop } from "../src/review-overlay.js";
import { readReviewGuide } from "../src/review-guide.js";
import { reviewDecisionPath, writeReviewDecision } from "../src/review-protocol.js";
import { resolveSessionPath } from "../src/session-path.js";
import { grillResultPath } from "../src/grill.js";
import { stopDocsServer } from "../src/docs-server.js";
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
vi.mock("../src/review-surface.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/review-surface.js")>();
  return { ...actual, openInBrowser: vi.fn() };
});
vi.mock("../src/review-diff.js", () => ({
  computeReviewFiles: vi.fn(),
  computeImplementingFiles: vi.fn(),
}));
vi.mock("../src/review-overlay.js", () => ({
  runReviewLoop: vi.fn(),
}));
vi.mock("../src/review-guide.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/review-guide.js")>();
  return { ...actual, readReviewGuide: vi.fn() };
});
vi.mock("../src/review-protocol.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/review-protocol.js")>();
  return { ...actual, writeReviewDecision: vi.fn() };
});
vi.mock("../src/session-path.js", () => ({
  resolveSessionPath: vi.fn(),
}));

function capture(): { commands: Map<string, CommandDef>; pi: PiApi } {
  const commands = new Map<string, CommandDef>();
  const pi: PiApi = {
    registerCommand: (name, def) => commands.set(name, def),
    registerTool: () => {},
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
    hasUI: overrides.hasUI ?? true,
    reload: overrides.reload ?? vi.fn(async () => undefined),
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
    // without this, an earlier test's pop-out ("o" in the transcript view)
    // could leak into later /factory-run assertions.
    vi.mocked(spawnTerminalWindow).mockReset();
    vi.mocked(openInBrowser).mockReset();
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
    vi.mocked(computeImplementingFiles).mockReset();
    vi.mocked(runReviewLoop).mockReset();
    vi.mocked(readReviewGuide).mockReset();
    vi.mocked(writeReviewDecision).mockReset();
    vi.mocked(resolveSessionPath).mockReset();
  });

  afterEach(() => {
    stopDocsServer();
  });

  test("registers factory, factory-stop, factory-tasks, factory-run, factory-watch, and plan", () => {
    const { commands } = capture();
    expect(commands.has("factory")).toBe(true);
    expect(commands.has("factory-stop")).toBe(true);
    expect(commands.has("factory-tasks")).toBe(true);
    expect(commands.has("factory-run")).toBe(true);
    expect(commands.has("factory-watch")).toBe(true);
    expect(commands.has("plan")).toBe(true);
    expect(commands.has("review-plans")).toBe(true);
    expect(commands.has("system")).toBe(true);
  });

  test("system is repointed: it is a distinct command from review-plans, not an alias (design SS6.4, user ruling 2026-08-08)", () => {
    const { commands } = capture();
    expect(commands.get("system")).not.toBe(commands.get("review-plans"));
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

  test("/factory-stop removes the lock file after killing (RC2)", async () => {
    // A live lock (this test process's own pid, which isPidAlive sees as alive)
    // must be deleted so a hung/killed run can't strand a stale lock.
    const cwd = mkdtempSync(join(tmpdir(), "factory-stop-lock-"));
    mkdirSync(join(cwd, "sessions"), { recursive: true });
    const lockPath = join(cwd, "sessions", ".factory-run.lock");
    writeFileSync(lockPath, JSON.stringify({ pid: process.pid, started_at: "t" }), "utf-8");

    const { commands } = capture();
    const ctx = fakeCtx({ cwd });
    await commands.get("factory-stop")!.handler("", ctx);

    expect(existsSync(lockPath)).toBe(false);
    expect(ctx.ui.notify).toHaveBeenCalledWith("factory stopped", "info");
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
    // The mission control action loop opens via ctx.ui.custom -- resolve it
    // with "quit" immediately so the handler (which no longer awaits the
    // child's exit event at all) returns right away.
    vi.mocked(ctx.ui.custom).mockResolvedValueOnce({ type: "quit" });

    await commands.get("factory-run")!.handler("T-001", ctx);

    // stdin MUST stay "ignore": the file-based human-review handshake depends
    // on the orchestrator having no inherited stdin pipe. stdout/stderr are
    // redirected to the run log (a file descriptor, i.e. a number) so a run
    // that dies mid-pipeline leaves a trace instead of vanishing silently.
    const stdio = vi.mocked(spawn).mock.calls[0]![2]!.stdio as [unknown, unknown, unknown];
    expect(stdio[0]).toBe("ignore");
    expect(typeof stdio[1]).toBe("number");
    expect(typeof stdio[2]).toBe("number");
  });

  test("/factory-run opens the dashboard overlay and dispatches quit without spawning a window", async () => {
    // ui.custom resolves { type: "quit" } on the first dashboard open.
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
    } as ReturnType<typeof spawnSync>);
    const child = new EventEmitter() as EventEmitter & { unref: () => void };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

    const { commands } = capture();
    const ctx = fakeCtx();
    vi.mocked(ctx.ui.custom).mockResolvedValueOnce({ type: "quit" });

    await commands.get("factory-run")!.handler("T-001", ctx);

    expect(spawnTerminalWindow).not.toHaveBeenCalled(); // no dashboard window
    expect(ctx.ui.custom).toHaveBeenCalled(); // in-session overlay used
  });

  test("/factory-run dispatches an inspect action to the transcript overlay then reopens", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
    } as ReturnType<typeof spawnSync>);
    const child = new EventEmitter() as EventEmitter & { unref: () => void };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

    const { commands } = capture();
    const ctx = fakeCtx();
    vi.mocked(ctx.ui.custom)
      .mockResolvedValueOnce({ type: "inspect", sessionId: "dev-abc" }) // dashboard
      .mockResolvedValueOnce(undefined) // transcript view closes
      .mockResolvedValueOnce({ type: "quit" }); // dashboard again
    vi.mocked(resolveSessionPath).mockReturnValue("/home/x_dev-abc.jsonl");

    await commands.get("factory-run")!.handler("T-001", ctx);

    expect(resolveSessionPath).toHaveBeenCalledWith("dev-abc");
    // custom called at least 3x: dashboard, transcript, dashboard
    expect(vi.mocked(ctx.ui.custom).mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  test("/factory-run dispatches a gate-log action to the ScrollableMarkdown overlay", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
    } as ReturnType<typeof spawnSync>);
    const child = new EventEmitter() as EventEmitter & { unref: () => void };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

    const { commands } = capture();
    const ctx = fakeCtx();
    vi.mocked(ctx.ui.custom)
      .mockResolvedValueOnce({ type: "gate-log" }) // dashboard
      .mockResolvedValueOnce(undefined) // gate log viewer closes
      .mockResolvedValueOnce({ type: "quit" }); // dashboard again

    await commands.get("factory-run")!.handler("T-001", ctx);

    expect(vi.mocked(ctx.ui.custom).mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  test("/factory-run interactive: the review action reads the blocked human-review entry and runs the review loop", async () => {
    // No child.stdin exists at all in the stdio-closed world (stdio is fully
    // "ignore") -- the only way a decision reaches the orchestrator is via
    // writeReviewDecision(reviewDecisionPath(...), decision), asserted below.
    // Review is Enter-driven now: the action loop only runs the review when
    // ctx.ui.custom resolves a { type: "review" } action (dispatched by
    // MissionControlDashboard's Enter handler on the human-review row), not
    // via a background poll.
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
    } as ReturnType<typeof spawnSync>);
    const child = new EventEmitter() as EventEmitter & { unref: () => void };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

    // Real tmp status file under ctx.cwd, matching this file's existing
    // "/plan notifies when a required skill isn't vendored" convention of
    // pointing ctx.cwd at a real mkdtempSync() dir rather than mocking fs.
    const cwd = mkdtempSync(join(tmpdir(), "factory-watch-review-action-"));
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
    const decision = { decision: "approve" as const, annotations: [], reviewedFiles: [] };
    vi.mocked(runReviewLoop).mockResolvedValue(decision);

    const { commands } = capture();
    const ctx = fakeCtx({ cwd });
    vi.mocked(ctx.ui.custom)
      .mockResolvedValueOnce({ type: "review" }) // dashboard: Enter on human-review
      .mockResolvedValueOnce({ type: "quit" }); // dashboard again after review

    await commands.get("factory-run")!.handler("T-001", ctx);

    expect(vi.mocked(runReviewLoop)).toHaveBeenCalledWith(ctx.ui, cwd, "T-001", "abc123", files, {});
    expect(vi.mocked(writeReviewDecision)).toHaveBeenCalledWith(
      reviewDecisionPath(cwd, "sess-1"),
      decision,
    );
  });

  test("/factory-run interactive: the review action passes the review guide into the review loop", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0, stdout: JSON.stringify([{ id: "T-001", title: "t", status: "todo" }]), stderr: "",
    } as ReturnType<typeof spawnSync>);
    const child = new EventEmitter() as EventEmitter & { unref: () => void };
    child.unref = () => {};
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);

    const cwd = mkdtempSync(join(tmpdir(), "factory-watch-review-guide-"));
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
    const guide = { confidence: "high", verify: [{ item: "x" }] };
    vi.mocked(readReviewGuide).mockReturnValue(guide);
    const decision = { decision: "approve" as const, annotations: [], reviewedFiles: [] };
    vi.mocked(runReviewLoop).mockResolvedValue(decision);

    const { commands } = capture();
    const ctx = fakeCtx({ cwd });
    vi.mocked(ctx.ui.custom)
      .mockResolvedValueOnce({ type: "review" }) // dashboard: Enter on human-review
      .mockResolvedValueOnce({ type: "quit" }); // dashboard again after review

    await commands.get("factory-run")!.handler("T-001", ctx);

    expect(vi.mocked(runReviewLoop)).toHaveBeenCalledWith(
      ctx.ui, cwd, "T-001", "abc123", files,
      expect.objectContaining({ guide }),
    );
  });

  test("/factory-run interactive: the review action on an already-done human-review uses the implementing diff + banner", async () => {
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
    vi.mocked(runReviewLoop).mockResolvedValue({ decision: "approve", annotations: [], reviewedFiles: [] });

    const { commands } = capture();
    const ctx = fakeCtx({ cwd });
    vi.mocked(ctx.ui.custom)
      .mockResolvedValueOnce({ type: "review" })
      .mockResolvedValueOnce({ type: "quit" });

    await commands.get("factory-run")!.handler("T-001", ctx);

    expect(vi.mocked(computeImplementingFiles)).toHaveBeenCalledWith(cwd, ["src/x.py"]);
    expect(vi.mocked(computeReviewFiles)).not.toHaveBeenCalled();
    expect(vi.mocked(runReviewLoop)).toHaveBeenCalledWith(
      ctx.ui, cwd, "T-001", "abc123", implFiles,
      expect.objectContaining({ implementing: true }),
    );
  });

  test("/factory-watch notifies when there is no factory run to watch", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only" });
    await commands.get("factory-watch")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no factory run to watch"), "info");
    expect(ctx.ui.custom).not.toHaveBeenCalled();
  });

  test("/factory-watch ignores the docs surface preference", async () => {
    // Regression: factory-watch used to read the "docs" key, so choosing
    // Browser once for /review-plans silently rerouted mission control into
    // the browser. Surfaces are per-command, not one global mode.
    const dir = mkdtempSync(join(tmpdir(), "watch-pref-"));
    writeSurfacePref(dir, "browser", "docs");
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: dir });
    await commands.get("factory-watch")!.handler("", ctx);
    // Assert the browser branch was never ENTERED, not merely that we ended
    // up on the terminal path: openDocsServerFocused throws in this
    // environment, so a notify-only assertion passes even against the old
    // code that did take the browser branch and failed out of it.
    expect(openInBrowser).not.toHaveBeenCalled();
    expect(ctx.ui.notify).not.toHaveBeenCalledWith(
      expect.stringContaining("browser docs failed"),
      "warning",
    );
  });

  test("/factory-watch honours its own watch surface preference", async () => {
    const dir = mkdtempSync(join(tmpdir(), "watch-pref-"));
    writeSurfacePref(dir, "browser", "watch");
    expect(readSurfacePref(dir, "watch")).toBe("browser");
    expect(readSurfacePref(dir, "docs")).toBe("terminal");
  });

  test("/system --stop reports when no docs server is running", async () => {
    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("system")!.handler("--stop", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no docs server running"), "info");
  });

  test("/system opens directly on the /system route, with no surface picker (design SS6.4, repointed)", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: REPO_ROOT });

    await commands.get("system")!.handler("", ctx);

    // Unlike /review-plans, /system never asks "Open docs in Browser/Terminal".
    expect(ctx.ui.select).not.toHaveBeenCalled();
    expect(openInBrowser).toHaveBeenCalledTimes(1);
    const [url] = vi.mocked(openInBrowser).mock.calls[0]!;
    expect(new URL(url).pathname).toBe("/system");
    // No checkpoint-focus query params -- a bundle/SR scope has no
    // checkpoint to focus on; the navigator opens on its own scope picker.
    expect(new URL(url).search).toBe("");
  });

  test("/system reports an error and does not fall back to a terminal view when the browser fails to open", async () => {
    vi.mocked(openInBrowser).mockImplementationOnce(() => {
      throw new Error("open failed");
    });
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: REPO_ROOT });

    await commands.get("system")!.handler("", ctx);

    expect(ctx.ui.notify).toHaveBeenCalledWith(
      expect.stringContaining("system navigator failed to open"),
      "error",
    );
    // No ScrollableMarkdown/terminal fallback exists for the navigator.
    expect(ctx.ui.select).not.toHaveBeenCalled();
    expect(ctx.ui.custom).not.toHaveBeenCalled();
  });

  test("/factory-watch browser preference opens checkpoint-focused docs without volatile status", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "factory-watch-browser-"));
    writeSurfacePref(cwd, "browser", "watch");
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify({
        checkpoint: { task_id: "T 042/?", run_id: "run#7" },
        assessment: { state: "resumable", reasons: [], actions: [] },
      }),
      stderr: "",
    } as ReturnType<typeof spawnSync>);
    const { commands } = capture();
    const ctx = fakeCtx({ cwd });

    await commands.get("factory-watch")!.handler("", ctx);

    expect(openInBrowser).toHaveBeenCalledTimes(1);
    const [url] = vi.mocked(openInBrowser).mock.calls[0]!;
    expect(url).toContain("task=T+042%2F%3F");
    expect(url).toContain("run=run%237");
    expect(ctx.ui.custom).not.toHaveBeenCalled();
  });

  test("/factory-watch browser preference opens an unfocused page when no run is active", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "factory-watch-no-run-"));
    writeSurfacePref(cwd, "browser", "watch");
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify({ checkpoint: null, assessment: null }),
      stderr: "",
    } as ReturnType<typeof spawnSync>);
    const { commands } = capture();
    const ctx = fakeCtx({ cwd });

    await commands.get("factory-watch")!.handler("", ctx);

    const [url] = vi.mocked(openInBrowser).mock.calls[0]!;
    expect(url).not.toContain("task=");
    expect(url).not.toContain("run=");
  });

  test("/factory-watch browser launch failure falls back to terminal mission control", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "factory-watch-fallback-"));
    writeSurfacePref(cwd, "browser", "watch");
    const record: StatusRecord = {
      session_id: "sess-1", task_id: "T-001", current_node: "dev", current_state: "running",
      pipeline: [], started_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    };
    writeFileSync(join(cwd, "sessions", ".factory-status.json"), JSON.stringify(record), "utf-8");
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify({ checkpoint: null, assessment: null }),
      stderr: "",
    } as ReturnType<typeof spawnSync>);
    vi.mocked(openInBrowser).mockImplementationOnce(() => { throw new Error("open failed"); });
    const { commands } = capture();
    const ctx = fakeCtx({ cwd });
    vi.mocked(ctx.ui.custom).mockResolvedValueOnce({ type: "quit" });

    await commands.get("factory-watch")!.handler("", ctx);

    expect(ctx.ui.notify).toHaveBeenCalledWith(
      expect.stringContaining("falling back to terminal"), "warning",
    );
    expect(ctx.ui.custom).toHaveBeenCalled();
  });

  test("/factory-watch browser mode rejects reuse across repository roots", async () => {
    const first = mkdtempSync(join(tmpdir(), "factory-watch-root-a-"));
    const second = mkdtempSync(join(tmpdir(), "factory-watch-root-b-"));
    writeSurfacePref(first, "browser", "watch");
    writeSurfacePref(second, "browser", "watch");
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify({ checkpoint: null, assessment: null }),
      stderr: "",
    } as ReturnType<typeof spawnSync>);
    const { commands } = capture();
    await commands.get("factory-watch")!.handler("", fakeCtx({ cwd: first }));
    const secondCtx = fakeCtx({ cwd: second });

    await commands.get("factory-watch")!.handler("", secondCtx);

    expect(secondCtx.ui.notify).toHaveBeenCalledWith(
      expect.stringContaining("falling back to terminal"), "warning",
    );
    expect(secondCtx.ui.notify).toHaveBeenCalledWith("no factory run to watch", "info");
  });

  test("/factory-watch re-enters the mission control loop against the current status file, without spawning the orchestrator", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "factory-watch-command-"));
    mkdirSync(join(cwd, "sessions"), { recursive: true });
    const record: StatusRecord = {
      session_id: "sess-1", task_id: "T-001", current_node: "dev", current_state: "running",
      pipeline: [], started_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    };
    writeFileSync(join(cwd, "sessions", ".factory-status.json"), JSON.stringify(record), "utf-8");

    const { commands } = capture();
    const ctx = fakeCtx({ cwd });
    vi.mocked(ctx.ui.custom).mockResolvedValueOnce({ type: "quit" });

    await commands.get("factory-watch")!.handler("", ctx);

    expect(ctx.ui.custom).toHaveBeenCalled();
    expect(spawn).not.toHaveBeenCalled();
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

    expect(ctx.ui.notify).toHaveBeenCalledWith("no todo tasks", "info");
    expect(ctx.ui.select).not.toHaveBeenCalled();
  });

  test("/factory-run hides already-done todo tasks from the picker", async () => {
    vi.mocked(spawnSync).mockReturnValue({
      status: 0,
      stdout: JSON.stringify([
        { id: "T-001", title: "First", status: "todo", already_done: true },
        { id: "T-002", title: "Second", status: "todo", already_done: false },
      ]),
      stderr: "",
    } as ReturnType<typeof spawnSync>);
    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(),
      select: vi.fn().mockResolvedValue(undefined),
      confirm: vi.fn(async () => true), editor: vi.fn(async () => undefined), custom: vi.fn(),
    };
    const { commands } = capture();
    await commands.get("factory-run")!.handler("", fakeCtx({ ui }));

    // T-001 (already_done) shown with annotation; both tasks offered.
    expect(ui.select).toHaveBeenCalledWith("Run which task?", [
      "T-001  First  — deliverables present (will route to review)",
      "T-002  Second",
    ]);
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

  test("/factory-run with no id lists todo tasks, picks one, and routes through launchAndWatch like /factory --auto", async () => {
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

  test("/review-plans notifies when no docs are found, without opening a viewer", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only" });
    // --terminal skips the surface prompt so this still exercises the empty-list
    // branch rather than short-circuiting on an unanswered "Open docs in" select.
    await commands.get("review-plans")!.handler("--terminal", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(
      expect.stringContaining("no specs, plans, requirements, or tasks"),
      "info",
    );
  });

  test("/review-plans --stop reports when no docs server is running", async () => {
    const { commands } = capture();
    const ctx = fakeCtx();
    await commands.get("review-plans")!.handler("--stop", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(
      expect.stringContaining("no docs server running"),
      "info",
    );
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
    // --terminal so the single select() below is the DOCUMENT picker. Without it
    // the surface prompt would be the one cancelled, and this test would still
    // pass while no longer testing what it names.
    await commands.get("review-plans")!.handler("--terminal", ctx);
    expect(select).toHaveBeenCalledTimes(1);
    expect(custom).not.toHaveBeenCalled();
  });

  test("/clear starts a fresh empty session (like Claude Code's /clear)", async () => {
    const { commands } = capture();
    expect(commands.has("clear")).toBe(true);
    const ctx = fakeCtx();
    await commands.get("clear")!.handler("", ctx);
    // Wipes context by replacing the live session with a fresh one, no seed
    // message (no withSession callback) -- the empty-conversation UX matching
    // Claude Code's /clear.
    expect(ctx.newSession).toHaveBeenCalledTimes(1);
    expect(vi.mocked(ctx.newSession).mock.calls[0]![0]).toBeUndefined();
  });

  // --- grill:blocked detection + interactive grill window (Task 4b) ---

  function writeGrillBlockedStatus(cwd: string, sessionId: string, taskId = "T-001"): void {
    mkdirSync(join(cwd, "sessions"), { recursive: true });
    const grillEntry: PipelineEntry = {
      node: "grill",
      node_state: "blocked",
      attempt: 1,
      max_attempts: 1,
      snippet: "",
      outcome: null,
      handoff: "grill your understanding before implementation (advised)",
      updated_at: new Date().toISOString(),
    };
    const record: StatusRecord = {
      session_id: sessionId,
      task_id: taskId,
      current_node: "grill",
      current_state: "blocked",
      pipeline: [grillEntry],
      started_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    writeFileSync(join(cwd, "sessions", ".factory-status.json"), JSON.stringify(record), "utf-8");
  }

  function writeTask(cwd: string, taskId = "T-001", body = "- Create: src/foo.ts"): void {
    mkdirSync(join(cwd, "tasks"), { recursive: true });
    const content = [
      "---",
      "id: " + taskId,
      'title: "Task title"',
      "status: todo",
      "dod:",
      "- 'A definition of done item'",
      "---",
      "",
      body,
    ].join("\n");
    writeFileSync(join(cwd, "tasks", `${taskId}-task.md`), content, "utf-8");
  }

  function writeVendoredGrillSkill(cwd: string): void {
    const skillDir = join(cwd, ".pi", "skills", "grill-understanding");
    mkdirSync(skillDir, { recursive: true });
    writeFileSync(join(skillDir, "SKILL.md"), "GRILL_SKILL_BODY_MARKER", "utf-8");
  }

  test("at grill:blocked, entering mission control offers the [Grill now, Skip] select", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "grill-offer-"));
    writeGrillBlockedStatus(cwd, "grill-offer-sess");
    const { commands } = capture();
    const ctx = fakeCtx({ cwd });
    vi.mocked(ctx.ui.custom).mockResolvedValueOnce({ type: "quit" });

    await commands.get("factory-watch")!.handler("", ctx);

    expect(ctx.ui.select).toHaveBeenCalledWith(
      "Grill your understanding of this task?",
      ["Grill now", "Skip"],
    );
    // No choice made -> neither a result file nor a spawned window yet.
    expect(spawnTerminalWindow).not.toHaveBeenCalled();
    expect(existsSync(grillResultPath(cwd, "grill-offer-sess"))).toBe(false);
  });

  test("[Skip] writes a skipped grill-result.json at the transcript path and does not spawn a window", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "grill-skip-"));
    writeGrillBlockedStatus(cwd, "grill-skip-sess");
    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(),
      select: vi.fn().mockResolvedValue("Skip"),
      confirm: vi.fn(async () => true), editor: vi.fn(async () => undefined), custom: vi.fn(),
    };
    const { commands } = capture();
    const ctx = fakeCtx({ cwd, ui });
    vi.mocked(ctx.ui.custom).mockResolvedValueOnce({ type: "quit" });

    await commands.get("factory-watch")!.handler("", ctx);

    const written = JSON.parse(readFileSync(grillResultPath(cwd, "grill-skip-sess"), "utf-8"));
    expect(written.decision).toBe("skipped");
    expect(written.summary).toBeNull();
    expect(written.explainers).toBe(0);
    expect(typeof written.updated_at).toBe("string");
    expect(spawnTerminalWindow).not.toHaveBeenCalled();
  });

  test("[Grill now] builds the seed from the task, writes a fresh session file, and spawns a tunnel window", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "grill-now-"));
    writeGrillBlockedStatus(cwd, "grill-now-sess");
    writeTask(cwd, "T-001", "- Create: src/foo.ts\n- Touch: src/bar.ts");
    writeVendoredGrillSkill(cwd);
    // Persist a context packet for the run so the seed carries gathered context.
    const pktDir = join(cwd, "sessions", ".factory-transcripts", "grill-now-sess");
    mkdirSync(pktDir, { recursive: true });
    writeFileSync(
      join(pktDir, "context-packet.json"),
      JSON.stringify({
        task_id: "T-001",
        primary_files: ["src/foo.ts"],
        reference_files: [],
        files: {
          "src/foo.ts": { primary: true, kind: "content", content: "PACKET_PRIMARY_MARKER\n", signatures: [] },
        },
        missing: [],
        truncated: false,
      }),
      "utf-8",
    );
    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(),
      select: vi.fn().mockResolvedValue("Grill now"),
      confirm: vi.fn(async () => true), editor: vi.fn(async () => undefined), custom: vi.fn(),
    };
    const { commands } = capture();
    const ctx = fakeCtx({ cwd, ui });
    vi.mocked(ctx.ui.custom).mockResolvedValueOnce({ type: "quit" });

    await commands.get("factory-watch")!.handler("", ctx);

    const transcriptDir = join(cwd, "sessions", ".factory-transcripts", "grill-now-sess");
    const sessionFiles = readdirSync(transcriptDir).filter((f) => f.startsWith("grill-") && f.endsWith(".jsonl"));
    expect(sessionFiles.length).toBe(1);
    const sessionText = readFileSync(join(transcriptDir, sessionFiles[0]!), "utf-8");
    // seed carries the task scope (body / touched code paths), the skill block, and the gathered packet
    expect(sessionText).toContain("src/foo.ts");
    expect(sessionText).toContain("GRILL_SKILL_BODY_MARKER");
    expect(sessionText).toContain("PACKET_PRIMARY_MARKER");
    expect(spawnTerminalWindow).toHaveBeenCalledWith(
      "pi",
      ["--session", join(transcriptDir, sessionFiles[0]!)],
      { cwd },
    );
  });

  test("existing grill-result.json for the run prevents re-offering (no nag, no duplicate window)", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "grill-nag-"));
    writeGrillBlockedStatus(cwd, "grill-nag-sess");
    mkdirSync(join(cwd, "sessions", ".factory-transcripts", "grill-nag-sess"), { recursive: true });
    writeFileSync(
      grillResultPath(cwd, "grill-nag-sess"),
      JSON.stringify({ decision: "agreed", summary: null, explainers: 0, updated_at: new Date().toISOString() }),
      "utf-8",
    );
    const ui: UiApi = {
      notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(),
      select: vi.fn().mockResolvedValue("Grill now"), // must NOT be consulted
      confirm: vi.fn(async () => true), editor: vi.fn(async () => undefined), custom: vi.fn(),
    };
    const { commands } = capture();
    const ctx = fakeCtx({ cwd, ui });
    vi.mocked(ctx.ui.custom).mockResolvedValueOnce({ type: "quit" });

    await commands.get("factory-watch")!.handler("", ctx);

    expect(ctx.ui.select).not.toHaveBeenCalled();
    expect(spawnTerminalWindow).not.toHaveBeenCalled();
  });

  test("an offer already made for the run is not re-raised on re-entry (in-process no-nag)", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "grill-dup-"));
    writeGrillBlockedStatus(cwd, "grill-dup-sess");
    const { commands } = capture();
    const firstCtx = fakeCtx({ cwd });
    vi.mocked(firstCtx.ui.custom).mockResolvedValueOnce({ type: "quit" });
    await commands.get("factory-watch")!.handler("", firstCtx);
    expect(firstCtx.ui.select).toHaveBeenCalledWith(expect.anything(), ["Grill now", "Skip"]);

    // Re-enter mission control for the same run: the select must NOT be offered again.
    const secondCtx = fakeCtx({ cwd });
    vi.mocked(secondCtx.ui.custom).mockResolvedValueOnce({ type: "quit" });
    await commands.get("factory-watch")!.handler("", secondCtx);
    expect(secondCtx.ui.select).not.toHaveBeenCalled();
    expect(spawnTerminalWindow).not.toHaveBeenCalled();
  });
});
