// Pi loads this via: pi --extension pi-ext/factory-watch/src/index.ts
// (project-local auto-discovery via .pi/extensions/ also works once installed there)

import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, readFileSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { isPidAlive, parseLock } from "./lock-status.js";
import { buildListCommand, buildListJsonCommand, buildRunCommand, buildWindowsKillArgs } from "./process-control.js";
import type { Command } from "./process-control.js";
import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import { formatStatusLines, parseStatus, devEscalated } from "./status-format.js";
import { homedir } from "node:os";
import { getMarkdownTheme, loadSkills, stripFrontmatter } from "@earendil-works/pi-coding-agent";
import { buildPlanSeedPrompt, buildSkillBlock, buildTraceFixSeedPrompt } from "./skill-prompt.js";
import { registerTraceTools } from "./trace-tools.js";
import { factorySkillsDir, findSkillFile } from "./factory-skills.js";
import { runTraceCheck } from "./trace-cli.js";
import type { ReplacedSessionCtx } from "./pi-types.js";
import { formatTaskOption, parseTaskIdFromOption } from "./task-picker.js";
import type { TaskSummary } from "./task-picker.js";
import { listDocs } from "./doc-lister.js";
import { formatTaskHeader, parseTaskFrontmatter } from "./task-header.js";
import { ScrollableMarkdown } from "./scrollable-markdown.js";
import { registerWriteChunkGuard } from "./write-chunk-guard.js";
import { computeImplementingFiles, computeReviewFiles } from "./review-diff.js";
import { reviewDecisionPath, writeReviewDecision } from "./review-protocol.js";
import { PolishOverlay } from "./polish-overlay.js";
import type { PolishAction } from "./polish-overlay.js";
import type { PolishStateFile } from "./polish-model.js";
import {
  polishCommandsDir,
  polishStatePath,
  readPolishState,
  writePolishCommand,
} from "./polish-protocol.js";
import { readReviewGuide, reviewGuidePath } from "./review-guide.js";
import { runReviewLoop } from "./review-overlay.js";
import { buildDecision } from "./review-model.js";
import type { ReviewDecisionPayload } from "./review-model.js";
import { buildReviewPageData, startReviewServer } from "./review-server.js";
import {
  openInBrowser,
  parseReviewPlansArgs,
  readSurfacePref,
  writeSurfacePref,
} from "./review-surface.js";
import { ensureDocsServer, stopDocsServer } from "./docs-server.js";
import type { Surface } from "./review-surface.js";
import { spawnTerminalWindow } from "./terminal-window.js";
import { MissionControlDashboard } from "./mission-control-dashboard.js";
import type { MissionControlAction } from "./mission-control-dashboard.js";
import { parseSessionTranscript } from "./session-transcript.js";
import { SessionTranscriptView } from "./session-transcript-view.js";
import { resolveSessionPath } from "./session-path.js";

const STATUS_FILE = "sessions/.factory-status.json";
const LOCK_FILE = "sessions/.factory-run.lock";
const LOG_FILE = "sessions/.factory-run.log";
const POLL_INTERVAL_MS = 1000;
const POSIX_GRACEFUL_TIMEOUT_MS = 3000;
const PLAN_SKILL_NAMES = ["brainstorming", "writing-plans"];
const TRACE_FIX_SKILL_NAMES = ["trace-fix"];

function parseAutoFlag(args: string): { auto: boolean; rest: string } {
  const auto = /(^|\s)--auto(\s|$)/.test(args);
  const rest = args.replace("--auto", "").trim();
  return { auto, rest };
}

function readFileIfExists(path: string): string | null {
  try {
    return readFileSync(path, "utf-8");
  } catch {
    return null;
  }
}

// The in-session mission control action loop. Opens the dashboard overlay,
// dispatches on whatever action it resolves with, and reopens until "quit".
// Review is Enter-driven only -- this loop's own poll (inside the dashboard
// overlay factory below) only refreshes the displayed record; it never
// auto-launches the review overlay itself.
async function runMissionControl(ctx: ExtCommandCtx): Promise<void> {
  const statusPath = join(ctx.cwd, STATUS_FILE);
  const readRecord = () => {
    const raw = readFileIfExists(statusPath);
    return raw === null ? null : parseStatus(raw);
  };

  loop: for (;;) {
    const action = await ctx.ui.custom<MissionControlAction>((tui, theme, _keybindings, done) => {
      const dash = new MissionControlDashboard(readRecord(), (a) => {
        clearInterval(poll);
        done(a);
      }, theme);
      // Live update only -- review is Enter-driven, never auto-opened.
      const poll = setInterval(() => {
        dash.updateRecord(readRecord());
        tui.requestRender();
      }, POLL_INTERVAL_MS);
      return dash;
    });

    switch (action.type) {
      case "quit":
        break loop;
      case "inspect": {
        const path = action.sessionId === null ? null : resolveSessionPath(action.sessionId);
        if (path === null) {
          ctx.ui.notify("session not ready", "info");
          break;
        }
        const text = parseSessionTranscript(readFileIfExists(path) ?? "");
        const lines = text.split("\n");
        await ctx.ui.custom<void>(
          (tui, _theme, _keybindings, done) =>
            new SessionTranscriptView(lines, tui, () => done(undefined), () => {
              spawnTerminalWindow("pi", ["--session", path], { cwd: ctx.cwd });
            }),
          { overlay: true, overlayOptions: { width: "90%", maxHeight: "90%", anchor: "center" } },
        );
        break;
      }
      case "gate-log": {
        const rec = readRecord();
        const logPath = join(ctx.cwd, "sessions", ".factory-transcripts", rec?.session_id ?? "", "sim-gate.log");
        const text = readFileIfExists(logPath) ?? "(no gate log yet)";
        await ctx.ui.custom<void>(
          (tui, _theme, _keybindings, done) => new ScrollableMarkdown(text, getMarkdownTheme(), tui, () => done(undefined)),
          { overlay: true, overlayOptions: { width: "90%", maxHeight: "90%", anchor: "center" } },
        );
        break;
      }
      case "review": {
        const rec = readRecord();
        const hr = rec?.pipeline.find((e) => e.node === "human-review");
        if (rec && hr && hr.node_state === "blocked" && typeof hr.start_commit === "string") {
          const alreadyDone = hr.already_done === true;
          const guide = readReviewGuide(reviewGuidePath(ctx.cwd, rec.session_id)) ?? undefined;
          const files = alreadyDone
            ? computeImplementingFiles(ctx.cwd, hr.deliverables ?? [])
            : computeReviewFiles(ctx.cwd, hr.start_commit);
          const opts = alreadyDone
            ? {
                implementing: true,
                banner: "This task appears already complete -- approve to mark it done, reject to re-run it.",
                guide,
              }
            : { guide };

          const remembered = readSurfacePref(ctx.cwd);
          const pick = await ctx.ui.select(
            "Open review in",
            remembered === "browser" ? ["Browser", "Terminal"] : ["Terminal", "Browser"],
          );
          const surface: Surface = pick === "Browser" ? "browser" : "terminal";
          writeSurfacePref(ctx.cwd, surface);

          let decision: ReviewDecisionPayload | null = null;
          if (surface === "browser") {
            try {
              const pageData = buildReviewPageData(ctx.cwd, hr.start_commit, files, {
                taskId: rec.task_id,
                implementing: opts.implementing,
                banner: opts.banner,
                guide: opts.guide ?? null,
              });
              const srv = await startReviewServer(pageData);
              ctx.ui.notify(`review open in your browser: ${srv.url}`, "info");
              openInBrowser(srv.url);
              decision = await srv.decision; // resolves on submit; null if the server is closed without a post
            } catch (err) {
              ctx.ui.notify(`browser review failed (${String(err)}); falling back to terminal`, "warning");
            }
          }
          if (decision === null) {
            // terminal surface, or browser closed without submitting / failed to start: fall back to the TUI
            const result = await runReviewLoop(ctx.ui, ctx.cwd, rec.task_id, hr.start_commit, files, opts);
            decision = buildDecision(result.decision, result.annotations, result.reviewedFiles);
          }
          writeReviewDecision(reviewDecisionPath(ctx.cwd, rec.session_id), decision);
        }
        break;
      }
      case "pair-dev": {
        const path = resolveSessionPath(action.sessionId);
        if (path === null) {
          ctx.ui.notify("dev session not ready", "info");
          break;
        }
        spawnTerminalWindow("pi", ["--session", path], { cwd: ctx.cwd });
        ctx.ui.notify(
          "paired dev session opened — get unit tests green, then re-run the task to continue",
          "info",
        );
        break;
      }
    }
  }
}

const POLISH_POLL_MS = 200;

export function parsePolishTarget(args: string): { playground: string; usecase: string } | null {
  const m = /^(\S+):(\S+)$/.exec(args.trim());
  return m ? { playground: m[1]!, usecase: m[2]! } : null;
}

/** Read the bridge state file, returning it only when the publisher's seq advanced. */
export function pollPolishState(statePath: string, lastSeq: number): PolishStateFile | null {
  const parsed = readPolishState(statePath);
  if (parsed && parsed.seq > lastSeq) return parsed;
  return null;
}

// Spawn the deterministic Python orchestrator behind a file bridge, then drive
// the control panel against it: direct keys (accept/discard/tick) write command
// files from inside the overlay; free-text actions close the panel so ui.editor
// can run, then reopen it.
async function runPolishSession(
  ctx: ExtCommandCtx,
  target: { playground: string; usecase: string },
): Promise<void> {
  const sessionId = `polish-${Date.now()}`;
  const statePath = polishStatePath(ctx.cwd, sessionId);
  const cmdsDir = polishCommandsDir(ctx.cwd, sessionId);

  // The serve loop starts the app (front+back), opens the browser, publishes
  // polish-state.json, and consumes polish-commands/*.json.
  const child = spawn(
    "python",
    [
      "-m",
      "factory.polish",
      "serve",
      "--project-root",
      ctx.cwd,
      "--playground",
      target.playground,
      "--usecase",
      target.usecase,
      "--session",
      sessionId,
    ],
    { cwd: ctx.cwd, stdio: "ignore" },
  );

  let lastSeq = 0;
  try {
    loop: for (;;) {
      const action = await ctx.ui.custom<PolishAction>((tui, _theme, _keybindings, done) => {
        let poll: ReturnType<typeof setInterval> | undefined;
        const overlay = new PolishOverlay(
          tui,
          (cmd) => writePolishCommand(cmdsDir, cmd),
          (a) => {
            if (poll) clearInterval(poll);
            done(a);
          },
        );
        const first = pollPolishState(statePath, lastSeq);
        if (first) {
          lastSeq = first.seq;
          overlay.update(first.state);
        }
        poll = setInterval(() => {
          // Same staleness guard as the other poll loops here: ctx.ui can throw
          // after a session replacement/reload. Stop polling rather than taking
          // the host process down on the next tick.
          try {
            const s = pollPolishState(statePath, lastSeq);
            if (s) {
              lastSeq = s.seq;
              overlay.update(s.state);
              tui.requestRender();
            }
          } catch {
            if (poll) clearInterval(poll);
          }
        }, POLISH_POLL_MS);
        return overlay;
      });

      switch (action.type) {
        case "quit":
          break loop;
        case "feedback": {
          const text = await ctx.ui.editor(`Feedback - ${target.usecase}`, "");
          if (text) writePolishCommand(cmdsDir, { kind: "feedback", args: { text } });
          break;
        }
        case "edit": {
          const text = await ctx.ui.editor("Edit finding description", action.description);
          if (text) {
            writePolishCommand(cmdsDir, {
              kind: "edit",
              args: { gid: action.gid, changes: { description: text } },
            });
          }
          break;
        }
        case "comment": {
          const text = await ctx.ui.editor("What's wrong with this change?", "");
          if (text) {
            writePolishCommand(cmdsDir, { kind: "comment", args: { gid: action.gid, text } });
          }
          break;
        }
      }
    }
  } finally {
    // SIGTERM -> the serve loop's handler stops the loop and tears down both
    // dev-servers and the fix worker.
    child.kill();
  }
}

export default function factoryWatch(pi: PiApi): void {
  registerWriteChunkGuard(pi);
  // The deterministic half of /trace-fix: the model reasons, these tools do the
  // enumerating, validating and writing.
  registerTraceTools(pi);

  let pollHandle: ReturnType<typeof setInterval> | undefined;

  function stopPolling(): void {
    if (pollHandle !== undefined) {
      clearInterval(pollHandle);
      pollHandle = undefined;
    }
  }

  function isAlreadyRunning(ctx: ExtCommandCtx, lockPath: string): boolean {
    const existingLockRaw = readFileIfExists(lockPath);
    if (existingLockRaw === null) {
      return false;
    }
    const existingLock = parseLock(existingLockRaw);
    if (existingLock !== null && isPidAlive(existingLock.pid)) {
      ctx.ui.notify(
        `factory already running (pid ${existingLock.pid}) -- use /factory-stop first`,
        "warning",
      );
      return true;
    }
    return false;
  }

  function launchAndWatch(ctx: ExtCommandCtx, cmd: Command, label: string): void {
    const statusPath = join(ctx.cwd, STATUS_FILE);
    const lockPath = join(ctx.cwd, LOCK_FILE);
    mkdirSync(join(ctx.cwd, "sessions"), { recursive: true });
    const logFd = openSync(join(ctx.cwd, LOG_FILE), "a");
    const child = spawn(cmd.bin, cmd.args, {
      cwd: ctx.cwd,
      detached: true,
      stdio: ["ignore", logFd, logFd],
    });
    child.unref();

    stopPolling();
    pollHandle = setInterval(() => {
      // ctx captured by this closure can outlive its session (e.g. a
      // single `-p` turn ending, or ctx.newSession()/fork()/reload() in an
      // interactive one) -- touching ctx.ui after that throws. Stop
      // polling instead of taking the whole host process down with an
      // uncaught exception on the next tick.
      try {
        const raw = readFileIfExists(statusPath);
        const record = raw === null ? null : parseStatus(raw);
        ctx.ui.setWidget("factory", formatStatusLines(record));

        const stillLocked = readFileIfExists(lockPath) !== null;
        if (!stillLocked) {
          stopPolling();
          ctx.ui.notify("factory run finished", "info");
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);

    ctx.ui.notify(`factory started (${label})`, "info");
  }

  function startBackgroundWidgetPoll(ctx: ExtCommandCtx): void {
    const statusPath = join(ctx.cwd, STATUS_FILE);
    const lockPath = join(ctx.cwd, LOCK_FILE);
    stopPolling();
    pollHandle = setInterval(() => {
      // Same staleness guard as launchAndWatch's poll loop -- ctx.ui can
      // throw after a session replacement/reload; stop polling rather than
      // crashing the whole host process on the next tick.
      try {
        const raw = readFileIfExists(statusPath);
        const record = raw === null ? null : parseStatus(raw);
        const lines = formatStatusLines(record);
        const hrBlocked = (record?.pipeline ?? []).some((e) => e.node === "human-review" && e.node_state === "blocked");
        if (hrBlocked) lines.push("⚠ human review needed — /factory-watch");
        if (devEscalated(record)) lines.push("⚠ dev stuck — /factory-watch to pair");
        ctx.ui.setWidget("factory", lines);
        if (readFileIfExists(lockPath) === null) {
          stopPolling();
          ctx.ui.notify("factory run finished", "info");
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }

  // Spawns the orchestrator detached with stdout/stderr sent to the run log
  // (so a run that dies mid-pipeline leaves a trace instead of vanishing
  // silently), starts the background widget poll, and returns immediately --
  // the caller is expected to follow up with `await runMissionControl(ctx)`.
  function spawnInteractive(ctx: ExtCommandCtx, cmd: Command, label: string): void {
    mkdirSync(join(ctx.cwd, "sessions"), { recursive: true });
    const logFd = openSync(join(ctx.cwd, LOG_FILE), "a");
    const child = spawn(cmd.bin, cmd.args, { cwd: ctx.cwd, detached: true, stdio: ["ignore", logFd, logFd] });
    child.unref();
    ctx.ui.notify(`factory started (${label}, human review on)`, "info");
    startBackgroundWidgetPoll(ctx);
  }

  pi.registerCommand("factory", {
    description: "Run the next todo factory task, watching progress live",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      if (isAlreadyRunning(ctx, lockPath)) {
        return;
      }

      if (ctx.model === undefined) {
        ctx.ui.notify("no model selected in this session -- can't launch factory", "error");
        return;
      }

      const { auto } = parseAutoFlag(args);
      const cmd = buildRunCommand(ctx.model.provider, ctx.model.id);
      const label = `${ctx.model.provider}/${ctx.model.id}`;
      if (auto) {
        launchAndWatch(ctx, cmd, label);
      } else {
        spawnInteractive(ctx, cmd, label);
        await runMissionControl(ctx);
      }
    },
  });

  pi.registerCommand("factory-stop", {
    description: "Stop the currently running factory task",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      const raw = readFileIfExists(lockPath);
      if (raw === null) {
        ctx.ui.notify("factory is not running", "info");
        return;
      }
      const lock = parseLock(raw);
      if (lock === null || !isPidAlive(lock.pid)) {
        ctx.ui.notify("factory lock is stale (process already gone)", "info");
        return;
      }

      if (process.platform === "win32") {
        spawnSync("taskkill", buildWindowsKillArgs(lock.pid));
      } else {
        try {
          process.kill(-lock.pid, "SIGTERM");
        } catch {
          // process group may already be gone; the liveness check below handles it
        }
        await new Promise((resolve) => setTimeout(resolve, POSIX_GRACEFUL_TIMEOUT_MS));
        if (isPidAlive(lock.pid)) {
          try {
            process.kill(-lock.pid, "SIGKILL");
          } catch {
            // already gone
          }
        }
      }

      // Remove the lock so a hung/killed run can't leave a stale lock that
      // blocks every future run with "already running" (RC2). acquire_lock
      // also self-heals a dead-pid lock, but deleting it here makes recovery
      // immediate and unambiguous.
      try {
        unlinkSync(lockPath);
      } catch {
        // already gone
      }

      stopPolling();
      ctx.ui.setWidget("factory", undefined);
      ctx.ui.notify("factory stopped", "info");
    },
  });

  pi.registerCommand("factory-tasks", {
    description: "List factory tasks grouped by status",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const cmd = buildListCommand();
      const result = spawnSync(cmd.bin, cmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
      if (result.status !== 0) {
        ctx.ui.notify(`factory-tasks failed: ${result.stderr || "unknown error"}`, "error");
        return;
      }
      const lines = result.stdout.split(/\r?\n/).filter((line) => line.length > 0);
      ctx.ui.setWidget("factory-tasks", lines);
    },
  });

  pi.registerCommand("factory-run", {
    description: "Run the factory on one specific task, watching progress live",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const lockPath = join(ctx.cwd, LOCK_FILE);
      if (isAlreadyRunning(ctx, lockPath)) {
        return;
      }
      if (ctx.model === undefined) {
        ctx.ui.notify("no model selected in this session -- can't launch factory", "error");
        return;
      }

      const { auto, rest } = parseAutoFlag(args);
      // --force resumes a task that isn't `todo` (e.g. after manual work), so
      // the orchestrator doesn't dead-end with TaskNotTodoError (RC3).
      const force = /(^|\s)--force(\s|$)/.test(rest);
      let taskId = rest.replace("--force", "").trim();
      if (taskId === "") {
        const cmd = buildListJsonCommand();
        const result = spawnSync(cmd.bin, cmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
        if (result.status !== 0) {
          ctx.ui.notify(`factory-run failed to list tasks: ${result.stderr || "unknown error"}`, "error");
          return;
        }
        let tasks: TaskSummary[];
        try {
          tasks = JSON.parse(result.stdout) as TaskSummary[];
        } catch {
          ctx.ui.notify("factory-run failed to parse task list", "error");
          return;
        }
        // Show every todo task. A task is hidden only when its ledger status is
        // "done" -- never because its files exist on disk (that would swallow a
        // started-but-unfinished task). Run-state is surfaced via formatTaskOption.
        const todoTasks = tasks.filter((t) => t.status === "todo");
        if (todoTasks.length === 0) {
          ctx.ui.notify("no todo tasks", "info");
          return;
        }
        const selected = await ctx.ui.select("Run which task?", todoTasks.map((t) => formatTaskOption(t)));
        if (selected === undefined) {
          return;
        }
        taskId = parseTaskIdFromOption(selected);
      }

      const cmd = buildRunCommand(ctx.model.provider, ctx.model.id, taskId, force);
      const label = `${ctx.model.provider}/${ctx.model.id}, task ${taskId}${force ? " (force)" : ""}`;
      if (auto) {
        launchAndWatch(ctx, cmd, label);
      } else {
        spawnInteractive(ctx, cmd, label);
        await runMissionControl(ctx);
      }
    },
  });

  pi.registerCommand("factory-watch", {
    description: "Open mission control for the current factory run",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const statusPath = join(ctx.cwd, STATUS_FILE);
      if (readFileIfExists(statusPath) === null) {
        ctx.ui.notify("no factory run to watch", "info");
        return;
      }
      await runMissionControl(ctx);
    },
  });

  pi.registerCommand("clear", {
    description: "Clear the conversation and start fresh (like Claude Code's /clear)",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      // Replace the live session with a fresh, empty one -- the
      // wipe-context-and-keep-working UX of Claude Code's /clear. Call it and
      // return immediately: per Pi's contract, `ctx` (and `pi`) go stale after
      // newSession() and throw if touched again, so no post-call ctx.ui use.
      await ctx.newSession();
    },
  });

  pi.registerCommand("plan", {
    description: "Start an interactive planning session (brainstorming -> writing-plans)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const topic = args.trim();
      if (topic === "") {
        ctx.ui.notify("usage: /plan <topic>", "error");
        return;
      }

      const { skills } = loadSkills({
        cwd: ctx.cwd,
        agentDir: join(homedir(), ".pi", "agent"),
        skillPaths: [],
        includeDefaults: true,
      });

      const skillBlocks: string[] = [];
      for (const name of PLAN_SKILL_NAMES) {
        const skill = skills.find((s) => s.name === name);
        if (skill === undefined) {
          ctx.ui.notify(`/plan: skill not found: ${name}`, "error");
          return;
        }
        const content = readFileSync(skill.filePath, "utf-8");
        const body = stripFrontmatter(content).trim();
        skillBlocks.push(buildSkillBlock({ name: skill.name, location: skill.filePath, body }));
      }

      const seedText = buildPlanSeedPrompt(topic, skillBlocks);
      await ctx.newSession({
        withSession: async (session: ReplacedSessionCtx) => {
          await session.sendUserMessage(seedText, { deliverAs: "followUp" });
        },
      });
    },
  });

  pi.registerCommand("polish", {
    description: "Run a factory polish session (deterministic orchestrator + control panel)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const target = parsePolishTarget(args);
      if (!target) {
        ctx.ui.notify("usage: /polish <playground>:<usecase>", "error");
        return;
      }
      await runPolishSession(ctx, target);
    },
  });

  pi.registerCommand("trace-fix", {
    description: "Work through traceability gaps with the trace tools",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const check = runTraceCheck(ctx.cwd);
      if (check.ok) {
        ctx.ui.notify(
          `trace-fix: nothing pending (${check.deferred} deferred, ${check.exempt} exempt)`,
          "info",
        );
        return;
      }

      // Resolved via findSkillFile, not loadSkills: commands run with ctx.cwd set
      // to whatever repo the human is in, and a target project may vendor no
      // skills at all -- cool_physical_ai_project's .pi/ is empty. The factory's
      // own copy travels with this extension, so /trace-fix works anywhere.
      const skillBlocks: string[] = [];
      for (const name of TRACE_FIX_SKILL_NAMES) {
        const filePath = findSkillFile(ctx.cwd, name);
        if (filePath === null) {
          ctx.ui.notify(
            `/trace-fix: skill not found: ${name} (looked in ${ctx.cwd}/.pi/skills and ${factorySkillsDir()})`,
            "error",
          );
          return;
        }
        const body = stripFrontmatter(readFileSync(filePath, "utf-8")).trim();
        skillBlocks.push(buildSkillBlock({ name, location: filePath, body }));
      }

      const seed = buildTraceFixSeedPrompt(skillBlocks, check.report);
      // newSession() replaces the session and makes ctx stale (see /clear at
      // the handler above), so nothing may touch ctx after this call.
      await ctx.newSession({
        withSession: async (session: ReplacedSessionCtx) => {
          await session.sendUserMessage(seed, { deliverAs: "followUp" });
        },
      });
    },
  });

  pi.registerCommand("review-plans", {
    description: "Browse specs, plans, requirements and tasks (--browser | --terminal | --stop)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const parsedArgs = parseReviewPlansArgs(args);

      if (parsedArgs.stop) {
        ctx.ui.notify(
          stopDocsServer() ? "docs server stopped" : "no docs server running",
          "info",
        );
        return;
      }

      let surface = parsedArgs.surface;
      if (surface === null) {
        const remembered = readSurfacePref(ctx.cwd, "docs");
        const pick = await ctx.ui.select(
          "Open docs in",
          remembered === "browser" ? ["Browser", "Terminal"] : ["Terminal", "Browser"],
        );
        if (pick === undefined) return;
        surface = pick === "Browser" ? "browser" : "terminal";
        writeSurfacePref(ctx.cwd, surface, "docs");
      }

      if (surface === "browser") {
        try {
          // Non-blocking by design: open the tab and return, so the session stays
          // usable while the docs stay open beside it. Spec section 4.
          const server = await ensureDocsServer(ctx.cwd);
          ctx.ui.notify(`docs open at ${server.url} (/review-plans --stop to close)`, "info");
          openInBrowser(server.url);
          return;
        } catch (err) {
          ctx.ui.notify(
            `browser docs failed (${String(err)}); falling back to terminal`,
            "warning",
          );
        }
      }

      const docs = listDocs(ctx.cwd);
      if (docs.length === 0) {
        ctx.ui.notify("no specs, plans, requirements, or tasks found", "info");
        return;
      }

      const selectedLabel = await ctx.ui.select(
        "Review which document?",
        docs.map((d) => d.label),
      );
      if (selectedLabel === undefined) {
        return;
      }
      const doc = docs.find((d) => d.label === selectedLabel);
      if (doc === undefined) {
        ctx.ui.notify("review-plans: selected document not found", "error");
        return;
      }

      let raw: string;
      try {
        raw = readFileSync(doc.path, "utf-8");
      } catch (err) {
        ctx.ui.notify(`review-plans: failed to read ${doc.path}: ${String(err)}`, "error");
        return;
      }

      let displayText = raw;
      if (doc.type === "task") {
        const parsed = parseTaskFrontmatter(raw);
        displayText = parsed ? `${formatTaskHeader(parsed)}\n\n${parsed.body}` : raw;
      }

      const markdownTheme = getMarkdownTheme();
      await ctx.ui.custom<void>((tui, _theme, _keybindings, done) => {
        return new ScrollableMarkdown(displayText, markdownTheme, tui, () => done(undefined));
      }, { overlay: true, overlayOptions: { width: "90%", maxHeight: "90%", anchor: "center" } });
    },
  });
}
