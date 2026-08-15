// Pi loads this via: pi --extension pi-ext/factory-watch/src/index.ts
// (project-local auto-discovery via .pi/extensions/ also works once installed there)

import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { isPidAlive, parseLock } from "./lock-status.js";
import {
  buildListCommand,
  buildListJsonCommand,
  buildRunCommand,
  buildSystemNavigatorUrl,
  buildWindowsKillArgs,
} from "./process-control.js";
import type { Command } from "./process-control.js";
import type { ExtCommandCtx, PiApi } from "./pi-types.js";
import { formatStatusLines, parseStatus, devEscalated } from "./status-format.js";
import type { StatusRecord } from "./status-format.js";
import { homedir } from "node:os";
import { getMarkdownTheme, loadSkills, stripFrontmatter } from "@earendil-works/pi-coding-agent";
import {
  buildGrillSeedPrompt,
  buildPlanSeedPrompt,
  buildSkillBlock,
  buildTraceFixSeedPrompt,
  buildVisualExplainSeedPrompt,
} from "./skill-prompt.js";
import { registerTraceTools } from "./trace-tools.js";
import { registerSystemContextTools } from "./system-context-tools.js";
import { registerSessionReviewSuggestTools } from "./session-review-suggest.js";
import { registerFactoryInit } from "./factory-init-command.js";
import { registerSessionMemory } from "./session-memory-command.js";
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
import { atomicWriteWithRetry, reviewDecisionPath, writeReviewDecision } from "./review-protocol.js";
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
  buildBrowserUrl,
  openInBrowser,
  parseReviewPlansArgs,
  readSurfacePref,
  writeSurfacePref,
} from "./review-surface.js";
import { ensureDocsServer, stopDocsServer } from "./docs-server.js";
import { loadCurrentRun } from "./evidence-client.js";
import type { Surface } from "./review-surface.js";
import { spawnTerminalWindow } from "./terminal-window.js";
import { MissionControlDashboard } from "./mission-control-dashboard.js";
import type { MissionControlAction } from "./mission-control-dashboard.js";
import { parseSessionTranscript } from "./session-transcript.js";
import { SessionTranscriptView } from "./session-transcript-view.js";
import { resolveSessionPath } from "./session-path.js";
import { freshSessionJsonl, grillResultPath, grillSessionPath, readFreshExplainerSummary, } from "./grill.js";
import { loadNodeRegistry } from "./node-registry.js";
import { diffBlocked, snapshotStates } from "./pipeline-diff.js";
import { readContextPacket, renderPacketSlice } from "./context-packet.js";

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

function browserFocusUrl(cwd: string, baseUrl: string): string {
  const current = loadCurrentRun(cwd);
  if (!current.ok || current.value.checkpoint === null) {
    return baseUrl;
  }
  const checkpoint = current.value.checkpoint as Record<string, unknown>;
  const taskId = typeof checkpoint.task_id === "string" ? checkpoint.task_id : undefined;
  const runId = typeof checkpoint.run_id === "string" ? checkpoint.run_id : undefined;
  return buildBrowserUrl(baseUrl, { taskId, runId });
}

// Shared by /review-plans (docs browsing) and /factory-watch (run watching):
// open the existing docs server (singleton, confined to ctx.cwd), focused on
// the current checkpoint run-state. Throws on failure (e.g. a singleton root
// mismatch, or the browser launcher throwing) so each caller can fall back
// to its own terminal surface. Non-blocking by design: open the tab and
// return, so the session stays usable while the docs stay open beside it.
// `/system` (the navigator) does not use this: it has no checkpoint to
// focus on and no terminal fallback (see the `system` command below).
async function openDocsServerFocused(ctx: ExtCommandCtx, label: string): Promise<void> {
  const server = await ensureDocsServer(ctx.cwd);
  const focusedUrl = browserFocusUrl(ctx.cwd, server.url);
  ctx.ui.notify(`${label} open at ${focusedUrl} (/system --stop to close)`, "info");
  openInBrowser(focusedUrl);
}

function readFileIfExists(path: string): string | null {
  try {
    return readFileSync(path, "utf-8");
  } catch {
    return null;
  }
}

// Grill de-dup for the current process: once a grill has been offered (or its
// verdict written) for a given run, never re-raise the same select for it.
// Keyed by session id so a later run (new session) can still be offered its
// own grill. This is the in-process half of "avoid nagging"; the on-disk half
// is checking that grill-result.json already exists for the run.
const offeredGrillFor = new Set<string>();

// Read the task file that `taskId` refers to, resolving the authoritative
// frontmatter `id` rather than guessing at a filename convention (mirrors
// review-server.ts's readTaskContext). Returns the full raw task markdown so
// the seed carries body, DoD, `satisfies:` targets and touched code paths.
function readTaskText(cwd: string, taskId: string): string | null {
  let names: string[];
  try {
    names = readdirSync(join(cwd, "tasks"));
  } catch {
    return null;
  }
  for (const name of names) {
    if (!name.endsWith(".md") || !name.startsWith("T-")) continue;
    const raw = readFileIfExists(join(cwd, "tasks", name));
    if (raw === null) continue;
    const task = parseTaskFrontmatter(raw);
    if (task === null || task.id !== taskId) continue;
    return raw;
  }
  return null;
}

// Resolve the grill-understanding skill via findSkillFile. Missing skill is NOT
// a hard error (design ruling): notify and fall back to the inline protocol
// instructions buildGrillSeedPrompt already carries.
function buildGrillSkillBlocks(ctx: ExtCommandCtx): string[] {
  const filePath = findSkillFile(ctx.cwd, "grill-understanding");
  if (filePath === null) {
    ctx.ui.notify(
      "grill-understanding skill not found (looked in " +
        `${ctx.cwd}/.pi/skills and ${factorySkillsDir()}) -- using inline protocol instructions`,
      "warning",
    );
    return [];
  }
  const body = stripFrontmatter(readFileSync(filePath, "utf-8")).trim();
  return [buildSkillBlock({ name: "grill-understanding", location: filePath, body })];
}

function writeGrillSkipped(path: string): void {
  const payload = {
    decision: "skipped",
    summary: null,
    explainers: 0,
    updated_at: new Date().toISOString(),
  };
  atomicWriteWithRetry(path, JSON.stringify(payload));
}

// Build the grill seed and open the standalone grill window (a fresh pi session
// seeded with the prompt), mirroring the existing spawnTerminalWindow sites.
function openGrillWindow(ctx: ExtCommandCtx, rec: StatusRecord): void {
  const taskText = readTaskText(ctx.cwd, rec.task_id);
  const skillBlocks = buildGrillSkillBlocks(ctx);
  const freshSummary = readFreshExplainerSummary(ctx.cwd);
  const resultPath = grillResultPath(ctx.cwd, rec.session_id);
  // Feed the gatherer's content-bearing packet to the grill when one exists, so
  // the grill agent arrives already knowing the task + code instead of reading
  // the codebase from zero. Degrades to task-text-only when unavailable.
  const packet = readContextPacket(ctx.cwd, rec.session_id);
  const packetSlice = packet ? renderPacketSlice(packet) : null;
  const seed = buildGrillSeedPrompt(
    taskText ?? `(task file for ${rec.task_id} not found)`,
    skillBlocks,
    freshSummary,
    resultPath,
    packetSlice,
  );
  const sessionPath = grillSessionPath(ctx.cwd, rec.session_id);
  mkdirSync(dirname(sessionPath), { recursive: true });
  writeFileSync(sessionPath, freshSessionJsonl(seed, ctx.cwd), "utf-8");
  ctx.ui.notify("grill window opened", "info");
  spawnTerminalWindow("pi", ["--session", sessionPath], { cwd: ctx.cwd });
}

// Detect grill:blocked on the run's pipeline entry and, if it has not already
// been handled, raise the ["Grill now", "Skip"] select. Returns true when a
// grill was offered/handled so callers can distinguish "not our turn" from
// "settled". Never nags: an existing grill-result.json or a prior offer for
// this run short-circuits before the select is raised.
async function maybeOfferGrill(
  ctx: ExtCommandCtx,
  readRecord: () => StatusRecord | null,
): Promise<boolean> {
  const rec = readRecord();
  const grill = rec?.pipeline.find((e) => e.node === "grill");
  if (!rec || !grill || grill.node_state !== "blocked") return false;
  if (readFileIfExists(grillResultPath(ctx.cwd, rec.session_id)) !== null) return false;
  if (offeredGrillFor.has(rec.session_id)) return false;

  const choice = await ctx.ui.select("Grill your understanding of this task?", [
    "Grill now",
    "Skip",
  ]);
  // Record regardless of choice (or even a cancelled select) so a re-entry or
  // a later poll tick cannot re-nag this run.
  offeredGrillFor.add(rec.session_id);
  if (choice === "Grill now") {
    openGrillWindow(ctx, rec);
  } else if (choice === "Skip") {
    writeGrillSkipped(grillResultPath(ctx.cwd, rec.session_id));
    ctx.ui.notify("grill skipped", "info");
  }
  return true;
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

  // Transition watcher: pushes blocking conditions to an ALREADY-OPEN mission
  // control instead of waiting for a re-open of /factory-watch. The old design
  // called maybeOfferGrill exactly once before the loop, so a grill that
  // appeared after open (the normal case, since the run is detached/async) was
  // silently missed. We run the check synchronously at open (so a run that is
  // already blocked on the grill is offered immediately, prev=[]) AND on an
  // interval (so a grill that blocks while mission control is open is pushed).
  // diffBlocked self-guards (a node already blocked in prev is not re-reported)
  // and maybeOfferGrill self-guards again via offeredGrillFor / the on-disk
  // grill-result.json, so the watcher can never nag.
  const lastSeen = new Map<string, ReturnType<typeof snapshotStates>>();
  const checkTransitions = async (): Promise<void> => {
    try {
      const rec = readRecord();
      if (!rec) return;
      const prev = lastSeen.get(rec.session_id) ?? [];
      lastSeen.set(rec.session_id, snapshotStates(rec));
      const transitions = diffBlocked(prev, snapshotStates(rec), loadNodeRegistry());
      for (const t of transitions) {
        if (t.node === "grill") {
          await maybeOfferGrill(ctx, readRecord);
        }
      }
    } catch {
      // a transient status-file read/protocol error must not crash the loop
    }
  };
  await checkTransitions();
  const grillWatcher = setInterval(() => {
    void checkTransitions();
  }, POLL_INTERVAL_MS);
  // (The old one-shot pre-loop `await maybeOfferGrill(...)` is gone: the grill is
  // now offered by the transition watcher above the moment grill:blocked appears,
  // even if mission control is already open. The grill is strongly-advised but
  // never a hard block: both choices resolve, and a missing/abandoned grill
  // simply waits on the gate timeout.)

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
        clearInterval(grillWatcher);
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
              const srv = await startReviewServer(pageData, { cwd: ctx.cwd });
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
  registerSystemContextTools(pi);
  registerSessionReviewSuggestTools(pi);
  // The deterministic project bootstrap: /factory-init, /factory-doctor, and the
  // subagent tool with its prompt metadata.
  registerFactoryInit(pi);
  // The volatile session-continuity layer: /remember, session_shutdown prune,
  // and before_agent_start rollup injection.
  registerSessionMemory(pi);

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
        const grillBlocked = (record?.pipeline ?? []).some((e) => e.node === "grill" && e.node_state === "blocked");
        if (hrBlocked) lines.push("⚠ human review needed — /factory-watch");
        if (grillBlocked) lines.push("⚠ grill needed — /factory-watch");
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
    description: "Open mission control for the current factory run (--browser to watch in the docs server)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      // Mission control is a TUI surface by default. A browser path exists,
      // but it is opt-in per-command: either an explicit --browser flag or
      // this command's OWN "watch" preference. It deliberately does NOT read
      // the "docs" key any more -- choosing Browser once for /review-plans
      // used to silently reroute mission control into the browser, which
      // contradicted this command's own description.
      //
      // The volatile status file is NOT consulted for the browser path: the
      // checkpoint survives a reboot that clears
      // sessions/.factory-status.json, so browser watching keeps working
      // after a reboot. Terminal mode keeps its status-file gate.
      const watchArgs = parseReviewPlansArgs(args);
      const wantsBrowser =
        watchArgs.surface === "browser" ||
        (watchArgs.surface === null && readSurfacePref(ctx.cwd, "watch") === "browser");
      if (wantsBrowser) {
        try {
          await openDocsServerFocused(ctx, "factory run");
          return;
        } catch (err) {
          ctx.ui.notify(`browser docs failed (${String(err)}); falling back to terminal`, "warning");
        }
      }

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

  const docsCommand = {
    description: "Browse system specs, plans, requirements, tasks, and evidence (--browser | --terminal | --stop)",
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
          // usable while the docs stay open beside it. Spec section 4. Shared with
          // /factory-watch so both commands open the same focused docs server.
          await openDocsServerFocused(ctx, "system evidence");
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
  };
  pi.registerCommand("review-plans", docsCommand);

  // The `system` command is repointed (user ruling, 2026-08-08; design
  // section 6.4): it now opens the docs browser directly on the `/system`
  // route -- the navigator -- instead of aliasing the generic docs-browser
  // command above. `/system` is still opt-in (this is an explicit command
  // invocation, not the default browser landing page, and `ensureDocsServer`
  // still serves "/" as the ordinary docs shell). Unlike /review-plans,
  // there is no terminal-view equivalent for the navigator to fall back to,
  // so this never prompts for a surface and never falls back to
  // ScrollableMarkdown -- a browser-launch failure is reported and left
  // there.
  const systemCommand = {
    description: "Open the system navigator (/system) directly in the browser (--stop to close)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const parsedArgs = parseReviewPlansArgs(args);

      if (parsedArgs.stop) {
        ctx.ui.notify(
          stopDocsServer() ? "docs server stopped" : "no docs server running",
          "info",
        );
        return;
      }

      try {
        const server = await ensureDocsServer(ctx.cwd);
        const url = buildSystemNavigatorUrl(server.url);
        ctx.ui.notify(`system navigator open at ${url} (/system --stop to close)`, "info");
        openInBrowser(url);
      } catch (err) {
        ctx.ui.notify(`system navigator failed to open: ${String(err)}`, "error");
      }
    },
  };
  pi.registerCommand("system", systemCommand);

  // /goal: thin agent-UX shim over the deterministic `factory.goals` core.
  // Arg passthrough to the Python CLI; the core owns all state/parsing. Rich
  // wiring and eng_* agent tools land in Inc 4; this only surfaces the core.
  pi.registerCommand("goal", {
    description:
      "Create and evaluate engineering goals via factory.goals (list|show|create|set-state|evaluate|history)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const parts = args.trim().split(/\s+/).filter(Boolean);
      if (parts.length === 0) {
        ctx.ui.notify("usage: /goal <list|show|create|set-state|evaluate|history> ...", "error");
        return;
      }
      const sub = parts[0];
      const result = spawnSync(
        "uv",
        ["run", "python", "-m", "factory.goals", ...parts, "--repo", ctx.cwd, "--json"],
        { cwd: ctx.cwd, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 },
      );
      const stderr = (result.stderr ?? "").trim();
      if (result.status !== 0) {
        ctx.ui.notify(`/goal ${sub}: ${stderr || "command failed"}`, "error");
        return;
      }
      const stdout = (result.stdout ?? "").trim();
      ctx.ui.notify(`/goal ${sub}: ${stdout.slice(0, 240)}`, "info");
    },
  });

  // /visual-explain: explain parts of the system with a diagram-design SVG +
  // markdown note. Same pattern as /trace-fix: resolve the vendored skill
  // (project .pi/skills first, then the factory's own copy), seed a fresh
  // session with the full skill content plus the workflow instructions, and
  // let the agent do the design + export + note writing. newSession() makes
  // ctx stale, so nothing may touch ctx after this call (see /clear).
  pi.registerCommand("visual-explain", {
    description:
      "Explain parts of the system: diagram-design SVG + markdown note (docs/visual-explain/)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const filePath = findSkillFile(ctx.cwd, "diagram-design");
      if (filePath === null) {
        ctx.ui.notify(
          `/visual-explain: diagram-design skill not found (looked in ${ctx.cwd}/.pi/skills and ${factorySkillsDir()})`,
          "error",
        );
        return;
      }
      const body = stripFrontmatter(readFileSync(filePath, "utf-8")).trim();
      const skillBlocks = [
        buildSkillBlock({ name: "diagram-design", location: filePath, body }),
      ];
      const focus =
        args.trim() === ""
          ? "no specific focus — inspect the repo and choose the most instructive parts"
          : args.trim();
      const seed = buildVisualExplainSeedPrompt(focus, skillBlocks);
      await ctx.newSession({
        withSession: async (session: ReplacedSessionCtx) => {
          await session.sendUserMessage(seed, { deliverAs: "followUp" });
        },
      });
    },
  });
}
