// Pi loads this via: pi --extension pi-ext/factory-watch/src/index.ts
// (project-local auto-discovery via .pi/extensions/ also works once installed there)

import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { isPidAlive, parseLock } from "./lock-status.js";
import { buildListCommand, buildListJsonCommand, buildRunCommand, buildWindowsKillArgs } from "./process-control.js";
import type { Command } from "./process-control.js";
import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import { formatStatusLines, parseStatus } from "./status-format.js";
import { homedir } from "node:os";
import { getMarkdownTheme, loadSkills, stripFrontmatter } from "@earendil-works/pi-coding-agent";
import { buildPlanSeedPrompt, buildSkillBlock } from "./skill-prompt.js";
import type { ReplacedSessionCtx } from "./pi-types.js";
import { formatTaskOption, parseTaskIdFromOption } from "./task-picker.js";
import type { TaskSummary } from "./task-picker.js";
import { listDocs } from "./doc-lister.js";
import { formatTaskHeader, parseTaskFrontmatter } from "./task-header.js";
import { ScrollableMarkdown } from "./scrollable-markdown.js";
import { registerWriteChunkGuard } from "./write-chunk-guard.js";
import { computeReviewFiles } from "./review-diff.js";
import { parseReviewPendingLine, writeReviewDecision } from "./review-protocol.js";
import { runReviewLoop } from "./review-overlay.js";
import { spawnTerminalWindow } from "./terminal-window.js";

const STATUS_FILE = "sessions/.factory-status.json";
const LOCK_FILE = "sessions/.factory-run.lock";
const LOG_FILE = "sessions/.factory-run.log";
const POLL_INTERVAL_MS = 1000;
const POSIX_GRACEFUL_TIMEOUT_MS = 3000;
const PLAN_SKILL_NAMES = ["brainstorming", "writing-plans"];

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

export default function factoryWatch(pi: PiApi): void {
  registerWriteChunkGuard(pi);

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

  function launchMissionControl(ctx: ExtCommandCtx): void {
    const statusPath = join(ctx.cwd, STATUS_FILE);
    spawnTerminalWindow(
      "node",
      [join(ctx.cwd, "pi-ext", "factory-watch", "src", "mission-control-dashboard.ts"), "--status", statusPath, "--cwd", ctx.cwd],
      { cwd: ctx.cwd },
    );
  }

  async function launchInteractiveReview(ctx: ExtCommandCtx, cmd: Command, label: string): Promise<void> {
    const child = spawn(cmd.bin, cmd.args, { cwd: ctx.cwd, stdio: ["pipe", "pipe", "pipe"] });
    ctx.ui.notify(`factory started (${label}, human review on)`, "info");

    // child.stdout "data" chunks are not guaranteed to align with line
    // boundaries -- a single review_pending JSON line can arrive split
    // across two chunks (or several lines can arrive in one chunk).
    // Buffer across events and only parse complete, newline-terminated
    // lines; keep any trailing partial line for the next chunk.
    let buffer = "";
    child.stdout.on("data", (chunk: Buffer) => {
      buffer += chunk.toString("utf-8");
      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex !== -1) {
        const line = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);
        newlineIndex = buffer.indexOf("\n");

        const message = parseReviewPendingLine(line);
        if (message === null) {
          continue;
        }
        const files = computeReviewFiles(ctx.cwd, message.start_commit);
        void runReviewLoop(ctx.ui, ctx.cwd, message.task_id, message.start_commit, files).then(
          (decision) => writeReviewDecision(child.stdin, decision),
        );
      }
    });

    await new Promise<void>((resolve) => child.on("exit", () => resolve()));
    ctx.ui.notify("factory run finished", "info");
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
      // Fired before launchInteractiveReview, which awaits the run's own
      // exit -- mission control must open while the run is live, not after.
      launchMissionControl(ctx);
      if (auto) {
        launchAndWatch(ctx, cmd, `${ctx.model.provider}/${ctx.model.id}`);
      } else {
        await launchInteractiveReview(ctx, cmd, `${ctx.model.provider}/${ctx.model.id}`);
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
      let taskId = rest;
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
        const todoTasks = tasks.filter((t) => t.status === "todo");
        if (todoTasks.length === 0) {
          ctx.ui.notify("no todo tasks", "info");
          return;
        }
        const selected = await ctx.ui.select("Run which task?", todoTasks.map(formatTaskOption));
        if (selected === undefined) {
          return;
        }
        taskId = parseTaskIdFromOption(selected);
      }

      const cmd = buildRunCommand(ctx.model.provider, ctx.model.id, taskId);
      const label = `${ctx.model.provider}/${ctx.model.id}, task ${taskId}`;
      // Fired before launchInteractiveReview, which awaits the run's own
      // exit -- mission control must open while the run is live, not after.
      launchMissionControl(ctx);
      if (auto) {
        launchAndWatch(ctx, cmd, label);
      } else {
        await launchInteractiveReview(ctx, cmd, label);
      }
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

  pi.registerCommand("review-plans", {
    description: "Browse and view specs, plans, and tasks in a scrollable, rendered view",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const docs = listDocs(ctx.cwd);
      if (docs.length === 0) {
        ctx.ui.notify("no specs, plans, or tasks found", "info");
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
