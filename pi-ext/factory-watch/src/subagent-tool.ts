// The factory's subagent tool.
//
// This registers a single in-session tool the parent agent can call to hand a
// bounded, self-contained piece of work to a dedicated child pi process
// running in the same project root. It is the parent-session sibling of the
// orchestrator's pi_backend.py subagent launcher, but intentionally lives as a
// registered tool so the parent model learns ABOUT it from the tool
// registration itself (promptSnippet + promptGuidelines), not from AGENTS.md.
//
// The prompt-side contract (what it does, when to delegate, how results come
// back, recursion prevention) is spelled out in the promptGuidelines below --
// that metadata IS the delivered knowledge for the parent agent, per section 1
// of the bootstrap design.
//
// Result handling: the child runs `pi --mode json`, which emits a line-
// delimited event stream (session, message_start/message_end, tool execution,
// ...). Rawly forwarding that stream is useless to the parent -- the answer is
// buried at the tail behind session echo and the injected code index -- and
// buffering it in memory is a disaster for big runs: a tool-heavy child can
// emit hundreds of MB of JSONL, which used to blow past spawnSync's 1 MiB
// default maxBuffer and surface as the opaque "(no stderr)" ENOBUFS failure.
// We therefore stream the child's stdout line-by-line (never retaining more
// than the parsed final answer + a small diagnostics tail), enforce idle and
// total timeouts ourselves like pi_backend.py's _drain_lines, and return the
// child's final assistant text. Failure modes are classified so a broken
// spawn, a timeout, or a non-zero child exit are never reported as the same
// opaque "(no stderr)".

import { Type } from "typebox";
import { mkdtempSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { resolveProjectRoot } from "./factory-init.js";
import { agentExtensionPath } from "./factory-path.js";

// Recursion bound. A subagent that could spawn its own subagents forever is a
// resource leak; the factory's own orchestrator runs a single bounded depth and
// this guard keeps the delta non-recursive unless explicitly raised.
export const MAX_SUBAGENT_DEPTH = 1;
export const RECURSE_GUARD_ENV = "PI_FACTORY_SUBAGENT_DEPTH";

// Label + task summary surfaced with the subagent result so the parent (and
// anyone reading the transcript) can see at a glance which child did what and
// on which prompt -- without opening the child's session. The label is a short
// role-ish noun ("researcher", "dev", "reviewer", "docs", "worker") derived from
// the task text or given explicitly; the summary is a single-line truncation of
// the task packet.
export const SUBAGENT_TASK_SUMMARY_MAX = 240;

// Timeout budgets for a child pi run, mirroring pi_backend.py's defaults:
// idle = max silence between consecutive output lines (a true stall), total =
// whole-run budget. Both are enforced by killing the child, like the Python
// launcher's _drain_lines + proc.kill().
export const SUBAGENT_IDLE_TIMEOUT_MS = 300_000; // 5 min

// Liveness-aware idle (pulls the same contract pi-subagents / pi-background-tasks
// use): the idle budget is a wall-clock silence window AND a strike count. A
// child that is mid-generation or mid-file-write must not be killed simply
// because it produced no stdout line for one window -- a single slow model turn
// or a long generate-then-write burst is legitimately silent (reference
// rationale: pi-background-tasks FUSION_CHILD_IDLE_TIMEOUT_MS is 35 min for
// this reason). We keep a short idle window but withstand a small number of
// consecutive breach windows and, when liveness dirs are configured, treat any
// file write under them as a heartbeat that resets the live counter.
export const SUBAGENT_IDLE_GRACE_BREACHES = 2;
export const SUBAGENT_LIVENESS_DEPTH = 4; // depth of the file-heartbeat probe
// 20 min total -- mirrors pi_backend.py's FACTORY_AGENT_TOTAL_TIMEOUT_S=1200.
// Kept larger than idle×grace (2×5 min = 10 min of permitted silence) so a
// genuine stall is caught by the idle bound (reachable) rather than always
// running up to the total runaway ceiling, and so a long plan-authoring burst
// is not cut off mid-deliverable.
export const SUBAGENT_TIMEOUT_MS = 1_200_000; // 20 min total

// DEFENSIVE ONLY: spawnSync/spawn-level ENOBUFS cannot occur for us anymore
// because stdout is streamed (see spawnStreamedChild); the classification
// branch stays for rare OS-level kill paths.
export const SUBAGENT_MAX_BUFFER = 128 * 1024 * 1024;

// Retained-memory bounds while streaming: the accumulated answer text and one
// stray event line are capped; the rest of the event stream is parsed and
// discarded line-by-line regardless of its total size.
export const MAX_ANSWER_CHARS = 1_000_000;
export const MAX_EVENT_LINE_CHARS = 10 * 1024 * 1024;

export interface ToolCtx {
  cwd: string;
  model?: { provider: string; id: string };
}

function taskResult(text: string): { content: { type: "text"; text: string }[]; details: null } {
  return { content: [{ type: "text", text }], details: null };
}

/**
 * Turn a pure argv command into the shape `spawn` needs for this platform.
 *
 * On Windows the npm `pi` bin is a `.cmd`/`.sh` shim that Node's `spawn`
 * cannot launch directly (`pi` -> ENOENT, `pi.cmd` -> EINVAL); it must run
 * through a shell. A bare `shell: true` is not enough on its own either:
 * Node does not quote the argument list for the shell, so any argument
 * containing whitespace (e.g. a temp packet or extension path under a
 * directory with a space) would be split into several arguments. We therefore
 * pre-quote every element that contains whitespace or a double quote, using
 * cmd.exe's escape rule (a double quote is doubled).
 *
 * On POSIX the `pi` shebang script can be exec'd directly, so we keep the
 * original argv split form with no shell.
 *
 * Platform is an injected parameter so the branching is unit-testable on any
 * host without actually spawning.
 */
export function planSubagentSpawn(
  cmd: string[],
  platform: NodeJS.Platform = process.platform,
): { file: string; args: string[]; shell: boolean } {
  if (platform === "win32") {
    const quoted = cmd.map((part) =>
      /[\s"]/.test(part) ? `"${part.replace(/"/g, '""')}"` : part,
    );
    return { file: quoted.join(" "), args: [], shell: true };
  }
  return { file: cmd[0]!, args: cmd.slice(1), shell: false };
}

/**
 * Construct the child pi invocation for a delegated sub-task. Pure and
 * unit-testable: it only builds the command array + env; callers decide whether
 * to spawn (a real model is required, so tests only exercise the builder).
 *
 * Contract enforced here (mirrors pi_backend.py):
 *  - working directory is the resolved PROJECT ROOT, so the child receives the
 *    same root AGENTS.md;
 *  - NO `--no-context-files` / `-nc`, so native context files load in the child;
 *  - the task packet is passed via a temp @file (concise, not the transcript);
 *  - the child runs in --mode json so structured output returns to the parent;
 *  - recursion is prevented: if the parent is already at/beyond MAX_SUBAGENT_DEPTH
 *    the builder returns null rather than constructing a deeper spawn.
 */
export function buildSubagentInvocation(input: {
  root: string;
  task: string;
  provider?: string;
  model?: string;
  currentDepth?: number;
  /** Pre-rendered "available factory tools" line, injected by the glue layer. */
  toolsSummary?: string;
}): {
  cmd: string[];
  env: Record<string, string>;
  packetFile: string | null;
} | null {
  const depth = input.currentDepth ?? 0;
  if (depth >= MAX_SUBAGENT_DEPTH) return null;

  // Write the concise task packet to a temp @file (not the parent transcript).
  const packetDir = mkdtempSync(join(tmpdir(), "pi-subagent-"));
  const packetFile = join(packetDir, "packet.md");
  const toolsBlock = input.toolsSummary
    ? `\n\nAVAILABLE FACTORY TOOLS\n${input.toolsSummary}\n`
    : `\nRoot AGENTS.md (loaded with context files) lists the factory tools available to you. `;
  writeFileSync(
    packetFile,
    `You are a bounded subagent in project ${input.root}.\n\n` +
      `TASK\n${input.task}\n` +
      toolsBlock +
      "Return a concise, structured answer. Do NOT spawn a subagent; do not modify project-level config. ",
    "utf-8",
  );

  const piBin = process.env.PI_SUBAGENT_BIN ?? "pi";
  const cmd: string[] = [
    piBin,
    "-p",
    `@${packetFile}`,
    "--mode",
    "json",
    "--extension",
    agentExtensionPath(),
  ];
  // Working directory is the resolved PROJECT ROOT (so root AGENTS.md loads);
  // no --no-context-files / -nc is ever added.
  if (input.provider) cmd.push("--provider", input.provider);
  if (input.model) cmd.push("--model", input.model);

  return {
    cmd,
    env: { ...process.env, [RECURSE_GUARD_ENV]: String(depth + 1) },
    packetFile,
  };
}

// ---------------------------------------------------------------------------
// JSONL event-stream parsing (mirrors pi_backend.py's parse_pi_json).
// ---------------------------------------------------------------------------

const ERROR_EVENT_TYPES = new Set(["error", "agent_error", "provider_error"]);

function isAssistantMessage(value: unknown): value is { content: unknown } {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const m = value as Record<string, unknown>;
  return m.role === "assistant";
}

function errorTextOf(event: Record<string, unknown>): string | null {
  for (const key of ["error", "message", "detail"]) {
    const value = event[key];
    if (typeof value === "string" && value.trim() !== "") return value.trim();
    if (value && typeof value === "object") {
      const rendered = Object.values(value as Record<string, unknown>)
        .filter((v): v is string => typeof v === "string")
        .join(" ");
      if (rendered.trim() !== "") return rendered.trim();
    }
  }
  return null;
}

/** Parsed view of a child's `pi --mode json` event stream. */
export interface ChildJsonlAnswer {
  /** Final assistant text: text content blocks, or thinking blocks when no
   *  text block was ever emitted (some providers answer inside thinking). */
  text: string;
  /** True when `text` came from thinking blocks (no plain text block seen). */
  thinkingOnly: boolean;
  /** Number of assistant message_end events seen. */
  assistantMessages: number;
  /** Total number of JSON events parsed (non-JSON lines are skipped). */
  jsonEvents: number;
  /** `type` of the last event parsed, if any. */
  lastEventType: string | null;
  /** Session id from the `session` event, if present. */
  sessionId: string | null;
  /** Text of the first error-ish event (type error/agent_error/provider_error). */
  failureEvent: string | null;
}

/**
 * Incremental collector over a child's JSONL event stream. Feed it one line at
 * a time (as they arrive on stdout) and read `answer()` at the end; it never
 * retains the stream itself, so memory stays bounded however many MB the child
 * emits. Only the LAST assistant message's content is kept (earlier assistant
 * messages are intermediate tool-call turns; their tool_call blocks carry no
 * text anyway). Mirrors pi_backend.parse_pi_json's message_end + text/thinking
 * handling.
 */
export interface JsonlCollector {
  pushLine(line: string): void;
  answer(): ChildJsonlAnswer;
}

export function createJsonlCollector(): JsonlCollector {
  const answer: ChildJsonlAnswer = {
    text: "",
    thinkingOnly: false,
    assistantMessages: 0,
    jsonEvents: 0,
    lastEventType: null,
    sessionId: null,
    failureEvent: null,
  };
  let textBlocks: string[] = [];
  let thinkingBlocks: string[] = [];
  let accumulated = 0;
  let capped = false;

  const capAppend = (blocks: string[], block: string) => {
    if (capped) return;
    if (accumulated + block.length > MAX_ANSWER_CHARS) {
      capped = true; // drop further content rather than blow memory
      return;
    }
    accumulated += block.length;
    blocks.push(block);
  };

  const classify = (line: string) => {
    if (!line.trim()) return;
    let event: unknown;
    try {
      event = JSON.parse(line);
    } catch {
      return; // non-JSON noise is not part of the stream
    }
    if (!event || typeof event !== "object" || Array.isArray(event)) return;
    const e = event as Record<string, unknown>;
    answer.jsonEvents += 1;
    if (typeof e.type === "string") answer.lastEventType = e.type;
    if (e.type === "session" && typeof e.id === "string") answer.sessionId = e.id;
    if (
      typeof e.type === "string" &&
      ERROR_EVENT_TYPES.has(e.type) &&
      answer.failureEvent === null
    ) {
      answer.failureEvent = errorTextOf(e);
    }
    if (e.type === "message_end" && isAssistantMessage(e.message)) {
      answer.assistantMessages += 1;
      const content = (e.message as { content: unknown }).content;
      if (!Array.isArray(content)) return;
      // Keep the LAST assistant message only: earlier ones are intermediate
      // turns. Reset the accumulators when a new assistant message ends.
      if (answer.assistantMessages > 1) {
        textBlocks = [];
        thinkingBlocks = [];
      }
      for (const block of content) {
        if (!block || typeof block !== "object" || Array.isArray(block)) continue;
        const b = block as Record<string, unknown>;
        if (b.type === "text" && typeof b.text === "string") capAppend(textBlocks, b.text);
        else if (b.type === "thinking" && typeof b.thinking === "string")
          capAppend(thinkingBlocks, b.thinking);
      }
    }
  };

  return {
    pushLine(line: string) {
      // Pathological single event line: never hold it (or JSON.parse it) in
      // memory; the counters stay honest, the content is simply not kept.
      if (line.length > MAX_EVENT_LINE_CHARS) return;
      classify(line);
    },
    answer() {
      if (textBlocks.length > 0) {
        answer.text = textBlocks.join("\n");
      } else if (thinkingBlocks.length > 0) {
        answer.text = thinkingBlocks.join("\n");
        answer.thinkingOnly = true;
      }
      return answer;
    },
  };
}

/** One-shot parse of a full captured stream (tests; streaming uses the collector). */
export function parseChildJsonl(stdout: string): ChildJsonlAnswer {
  const collector = createJsonlCollector();
  for (const line of stdout.split(/\r?\n/)) collector.pushLine(line);
  return collector.answer();
}

// ---------------------------------------------------------------------------
// Streaming spawn: bounded memory no matter how large the event stream.
// ---------------------------------------------------------------------------

export type StreamKillReason = "idle" | "total" | null;

export interface StreamedChildRun {
  status: number | null;
  signal: NodeJS.Signals | null;
  /** Spawn-level failure (e.g. ENOENT when `pi` is not on PATH). */
  error: Error | null;
  answer: ChildJsonlAnswer;
  /** Last ~2 KB of stdout, for diagnostics only. */
  stdoutTail: string;
  /** Last ~1.5 KB of stderr. */
  stderrTail: string;
  killedFor: StreamKillReason;
}

// ---------------------------------------------------------------------------
// Liveness-aware idle keeper (pure, injectable for tests)
// ---------------------------------------------------------------------------
//
// Distinguishes "quiet because thinking hard / writing" from "stalled". A live
// keeper starts with a breach count of zero; any progress you report (an output
// line, or a file-heartbeat from the liveness probe) resets it. Each full idle
// window with no progress increments it, and only after graceBreaches windows
// does the caller kill. This lets a productive-but-quiet child finish (T-029)
// while a genuinely stalled one still hits the hammer.

export type IdleDisposition = "keep-running" | "kill";

export interface IdleKeeperOptions {
  /** Wall-clock idle window (ms) = one breach. */
  idleMs: number;
  /** Consecutive silent windows permitted before a kill. */
  graceBreaches?: number;
  /**
   * Optional file-write liveness probe. Called at each window boundary; return
   * true when the child's deliverables are still being written (resets breach).
   */
  probe?: (sinceMs: number) => boolean;
  /** Injectable clock (tests). Defaults to Date.now(). */
  now?: () => number;
}

export interface IdleKeeper {
  /** Reset the breach count + record liveness (call on any child output). */
  noteLive(): void;
  /**
   * A full idle window elapsed. Resets the breach when the probe reports
   * file-progress; otherwise increments breaches and says whether to kill.
   */
  onElapsed(): IdleDisposition;
  /** Current breach count (observable for tests). */
  breaches(): number;
}

export function createIdleKeeper(opts: IdleKeeperOptions): IdleKeeper {
  const grace = opts.graceBreaches ?? SUBAGENT_IDLE_GRACE_BREACHES;
  let breaches = 0;
  let since = (opts.now ?? Date.now)();
  const nowMs = (): number => (opts.now ?? Date.now)();
  const noteLive = () => {
    breaches = 0;
    since = nowMs();
  };
  const onElapsed = (): IdleDisposition => {
    const t = nowMs();
    if (opts.probe && opts.probe(since)) {
      // File-heartbeat: the child is still writing deliverables.
      breaches = 0;
      since = t;
      return "keep-running";
    }
    breaches += 1;
    // Kill once MORE than `grace` silent windows have elapsed (grace windows are
    // permitted; the breach count is the incident count, so it must exceed grace).
    if (breaches > Math.max(1, grace)) return "kill";
    return "keep-running"; // one more silent window is allowed
  };
  return { noteLive, onElapsed, breaches: () => breaches };
}

// Best-effort file-write heartbeat: true when any file under any of `dirs` has a
// modification time newer than `sinceMs`. Early-returns as soon as one is found
// so an actively-writing child is cheap to detect; depth-bounded to stay cheap.
export function probeFileHeartbeat(
  dirs: string[],
  sinceMs: number,
  maxDepth = SUBAGENT_LIVENESS_DEPTH,
): boolean {
  if (!dirs || dirs.length === 0) return false;
  return dirs.some((dir) => probeDir(dir, sinceMs, maxDepth));
}

function probeDir(dir: string, sinceMs: number, depth: number): boolean {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return false; // missing/unreadable dir -> no signal
  }
  for (const name of entries) {
    if (name.startsWith(".")) continue;
    const p = join(dir, name);
    try {
      const st = statSync(p);
      if (st.mtimeMs > sinceMs) return true;
      if (st.isDirectory() && depth > 0 && probeDir(p, sinceMs, depth - 1)) return true;
    } catch {
      /* transient stat race -> try next */
    }
  }
  return false;
}

export interface StreamSpawnOptions {
  cwd: string;
  env: NodeJS.ProcessEnv;
  shell: boolean;
  totalTimeoutMs?: number;
  idleTimeoutMs?: number;
  /** Liveness-aware idle: consecutive silent windows before a kill (default 4). */
  idleGraceBreaches?: number;
  /**
   * Optional directories to probe for file-write heartbeats; any write newer
   * than the last probe keeps a silent child alive (never trips idle on a long
   * plan-authoring burst).
   */
  livenessDirs?: string[];
  tailChars?: number;
  stderrCapChars?: number;
}

/**
 * Spawn a child and stream its stdout line-by-line, retaining only the parsed
 * answer and a small diagnostics tail -- the stream's total size never lands
 * in memory (a 134 MB event stream behaves exactly like a 134 KB one). Idle
 * (silence between lines) and total (whole-run) budgets are enforced by
 * killing the child, mirroring pi_backend.py's _drain_lines + proc.kill().
 */
export function spawnStreamedChild(
  file: string,
  args: string[],
  opts: StreamSpawnOptions,
): Promise<StreamedChildRun> {
  const totalMs = opts.totalTimeoutMs ?? SUBAGENT_TIMEOUT_MS;
  const idleMs = opts.idleTimeoutMs ?? SUBAGENT_IDLE_TIMEOUT_MS;
  const tailChars = opts.tailChars ?? 2000;
  const stderrCap = opts.stderrCapChars ?? 1500;

  return new Promise((resolve) => {
    // stdin 'ignore' (like pi_backend's DEVNULL): the child's readPipedStdin()
    // gets EOF instead of blocking on an inherited long-lived pipe.
    const child = spawn(file, args, {
      cwd: opts.cwd,
      env: opts.env,
      shell: opts.shell,
      stdio: ["ignore", "pipe", "pipe"],
    });
    child.stdout?.setEncoding("utf-8");
    child.stderr?.setEncoding("utf-8");

    const collector = createJsonlCollector();
    let outBuf = "";
    let stdoutTail = "";
    let stderrTail = "";
    let spawnError: Error | null = null;
    let killedFor: StreamKillReason = null;
    let status: number | null = null;
    let signal: NodeJS.Signals | null = null;
    let settled = false;
    let idleTimer: NodeJS.Timeout | null = null;
    let totalTimer: NodeJS.Timeout | null = null;

    // Liveness-aware idle: each silent window is a probation increment, cleared
    // by any child output or (when livenessDirs are configured) any file write
    // under them. Only the grace-breach budget yields an idle kill; the total
    // budget stays the hard runaway ceiling.
    const idle = createIdleKeeper({
      idleMs,
      graceBreaches: opts.idleGraceBreaches,
      probe: opts.livenessDirs?.length
        ? (since) => probeFileHeartbeat(opts.livenessDirs!, since)
        : undefined,
    });

    const killChild = () => {
      try {
        child.kill();
      } catch {
        /* already gone */
      }
    };

    const armIdle = () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        if (settled) return;
        if (idle.onElapsed() === "kill") {
          killedFor = "idle";
          killChild();
        } else {
          armIdle();
        }
      }, idleMs);
    };

    const reportLive = () => {
      idle.noteLive();
      armIdle();
    };

    const finish = () => {
      if (settled) return;
      settled = true;
      if (idleTimer) clearTimeout(idleTimer);
      if (totalTimer) clearTimeout(totalTimer);
      resolve({
        status,
        signal,
        error: spawnError,
        answer: collector.answer(),
        stdoutTail,
        stderrTail,
        killedFor,
      });
    };

    totalTimer = setTimeout(() => {
      if (!settled) {
        killedFor = "total";
        killChild();
      }
    }, totalMs);
    armIdle();

    child.on("error", (err) => {
      // Spawn never happened (ENOENT, EINVAL, ...). 'close' may not fire.
      spawnError = err;
      finish();
    });
    child.stdout?.on("data", (chunk: string) => {
      reportLive();
      outBuf += chunk;
      // A pathological single line must not grow the buffer unboundedly.
      if (outBuf.length > MAX_EVENT_LINE_CHARS) outBuf = outBuf.slice(-MAX_EVENT_LINE_CHARS);
      let idx: number;
      while ((idx = outBuf.indexOf("\n")) >= 0) {
        const line = outBuf.slice(0, idx).replace(/\r$/, "");
        outBuf = outBuf.slice(idx + 1);
        collector.pushLine(line);
        stdoutTail = (stdoutTail + line + "\n").slice(-tailChars);
      }
    });
    child.stderr?.on("data", (chunk: string) => {
      reportLive();
      stderrTail = (stderrTail + chunk).slice(-stderrCap);
    });
    child.on("close", (code, sig) => {
      status = code;
      signal = sig ?? null;
      finish();
    });
  });
}

// ---------------------------------------------------------------------------
// Outcome rendering (pure: classify a finished child run into a parent-facing
// message). Mirrors pi_backend.py's diagnostics: timeouts, process exits, and
// event-shape mismatches are each reported distinctly instead of collapsing
// into "(no stderr)".
// ---------------------------------------------------------------------------

export interface SubagentProc {
  status: number | null;
  signal: NodeJS.Signals | null;
  error: Error | null;
  stdout: string;
  stderr: string;
}

const ANSWER_CAP = 8000;

export interface ChildOutcome {
  status: number | null;
  signal: NodeJS.Signals | null;
  error: Error | null;
  answer: ChildJsonlAnswer;
  stdoutTail: string;
  stderrTail: string;
  killedFor: StreamKillReason;
}

export function renderChildOutcome(o: ChildOutcome): string {
  // Spawn-level failure: the child never ran or the harness killed it. This is
  // also where a defensive ENOBUFS classification lives (streaming makes it
  // practically unreachable).
  if (o.error) {
    const code = (o.error as Error & { code?: string }).code;
    const detail =
      code === "ETIMEDOUT"
        ? `child pi did not finish within ${SUBAGENT_TIMEOUT_MS}ms`
        : code === "ENOBUFS"
          ? `child output exceeded the retention budget (event stream is streamed; this should not happen)`
          : `${o.error.message}${code ? ` (code ${code})` : ""}`;
    return `subagent spawn failed: ${detail}`;
  }

  // Killed by our own timeouts.
  if (o.killedFor === "idle") {
    return `subagent killed: child produced no output for ${SUBAGENT_IDLE_TIMEOUT_MS}ms (idle timeout, mirroring pi_backend.py) and was terminated. Treating the run as failed.`;
  }
  if (o.killedFor === "total") {
    return `subagent killed: child did not finish within ${SUBAGENT_TIMEOUT_MS}ms (total timeout, mirroring pi_backend.py) and was terminated. Treating the run as failed.`;
  }

  // Non-zero exit: the child ran but died. stderr is usually empty for a CLI
  // crash; fall back to a JSONL error event, then to the stdout tail so the
  // parent sees the actual reason instead of "(no stderr)".
  if (o.status !== 0) {
    const detail =
      (o.stderrTail || o.answer.failureEvent) ||
      (o.stdoutTail ? `stdout tail: ${o.stdoutTail}` : "(no output)");
    const signal = o.signal ? `, signal ${o.signal}` : "";
    return `subagent failed (exit ${o.status}${signal}): ${detail.slice(0, 2000)}`;
  }

  // Exit 0 with a parseable answer.
  if (o.answer.text.trim() !== "") {
    const truncated = o.answer.text.length > ANSWER_CAP ? `\n(truncated to ${ANSWER_CAP} chars)` : "";
    const provenance = o.answer.thinkingOnly
      ? "\n(answer recovered from the model's thinking block -- no plain text block was emitted)"
      : "";
    return `subagent output:\n${o.answer.text.slice(0, ANSWER_CAP)}${provenance}${truncated}`;
  }

  // Exit 0, non-empty stream, no assistant text: pi's event shape may not
  // match our parser -- say so explicitly instead of reporting an empty run.
  if (o.answer.jsonEvents > 0) {
    return (
      `subagent completed (exit 0) but emitted no assistant text ` +
      `(${o.answer.jsonEvents} JSON events, last: ${o.answer.lastEventType ?? "?"}) -- ` +
      `possible event-shape mismatch. Raw tail:\n${o.stdoutTail}`
    );
  }

  // Genuinely empty.
  return `subagent output: (empty output)${o.stderrTail ? `\nstderr: ${o.stderrTail.slice(0, 1000)}` : ""}`;
}

/** Sync wrapper over a captured full stream + spawn result (used by tests). */
export function renderSubagentOutcome(proc: SubagentProc): string {
  return renderChildOutcome({
    status: proc.status,
    signal: proc.signal,
    error: proc.error,
    answer: parseChildJsonl(proc.stdout),
    stdoutTail: proc.stdout.slice(-1500),
    stderrTail: proc.stderr.trim(),
    killedFor: null,
  });
}

// ---------------------------------------------------------------------------
// Subagent label + task summary (so a result names which child did what).
// A short, role-ish noun keeps the transcript legible without forcing the
// caller to hand over a label every time.
// ---------------------------------------------------------------------------

const SUBAGENT_LABEL_RULES: [RegExp, string][] = [
  [/\b(doc|documentation|design doc|changelog|readme)\b/i, "docs"],
  [/\b(research|read|summari[sz]e|investigat|spike)\b/i, "researcher"],
  [/\b(implement|build|write|code|dev|fix|port|refactor|add)\b/i, "dev"],
  [/\b(review|audit|inspect|verify)\b/i, "reviewer"],
  [/\b(test|unit test|vitest|pytest)\b/i, "tester"],
];

/**
 * Pick a short role label for a subagent task. An explicit `fallback` (from
 * the caller) wins; otherwise the first keyword rule that matches the task
 * text decides (e.g. "implement..." -> "dev", "review..." -> "reviewer").
 * Pure and deterministic so it can be unit-tested.
 */
export function deriveSubagentLabel(task: string, fallback: string | null = null): string {
  const trimmed = task.trim();
  if (fallback && fallback.trim() !== "") return fallback.trim();
  if (trimmed === "") return "worker";
  for (const [pattern, label] of SUBAGENT_LABEL_RULES) {
    if (pattern.test(trimmed)) return label;
  }
  return "worker";
}

/**
 * Collapse a task packet into one legible line, truncated to a bounded width
 * so a transcript line does not balloon. Pure and deterministic.
 */
export function summarizeSubagentTask(task: string, maxChars: number = SUBAGENT_TASK_SUMMARY_MAX): string {
  const flat = task.replace(/\s+/g, " ").trim();
  if (maxChars <= 0) return "";
  if (flat.length <= maxChars) return flat;
  return `${flat.slice(0, Math.max(0, maxChars - 1))}…`;
}

/**
 * Delegates a bounded sub-task to a dedicated child pi process. Returns the
 * child's final answer (streamed + extracted from its JSONL event stream) or
 * a classified failure message. Never spawns when at the recursion bound.
 */
export async function executeSubagent(
  task: string,
  ctx: ToolCtx,
  deps: Partial<{
    build: typeof buildSubagentInvocation;
    resolveRoot: typeof resolveProjectRoot;
    /** Optional short role label, e.g. "researcher" / "dev" (default: derived). */
    label?: string | null;
  }> = {},
): Promise<{ content: { type: "text"; text: string }[]; details: null }> {
  // Partial deps objects (as passed by wrapping call sites) merge over the
  // defaults, so a caller that overrides only `build` still gets a wired
  // `resolveRoot` instead of `undefined` (previously: deps.resolveRoot is
  // not a function).
  const resolvedDeps = {
    build: deps.build ?? buildSubagentInvocation,
    resolveRoot: deps.resolveRoot ?? resolveProjectRoot,
    label: deps.label ?? null,
  };
  const { root } = resolvedDeps.resolveRoot(ctx.cwd);
  const depth = Number(process.env[RECURSE_GUARD_ENV] ?? "0") || 0;
  const invocation = resolvedDeps.build({
    root,
    task,
    provider: ctx.model?.provider,
    model: ctx.model?.id,
    currentDepth: depth,
  });
  if (invocation === null) {
    return taskResult(
      "subagent refused: recursion bound reached. A subagent may not spawn a " +
        `deeper subagent (max depth ${MAX_SUBAGENT_DEPTH}). Do it inline or hand back to the parent.`,
    );
  }

  const plan = planSubagentSpawn(invocation.cmd);
  const run = await spawnStreamedChild(plan.file, plan.args, {
    cwd: root, // project root: same AGENTS.md / bootstrap as the parent
    env: invocation.env,
    shell: plan.shell,
    // Liveness-aware idle: a long plan-authoring run writes these dirs while
    // staying silent on stdout, so watch them as a written-heartbeat. Any file
    // write under docs/plans/tasks/requirements resets the idle breach and the
    // child is never killed mid-deliverable (T-029). Missing dirs are ignored.
    livenessDirs: [
      join(root, "docs"),
      join(root, "plans"),
      join(root, "tasks"),
      join(root, "requirements"),
      join(root, ".pi"),
    ],
  });
  const label = deriveSubagentLabel(task, resolvedDeps.label);
  const summary = summarizeSubagentTask(task);
  const body = renderChildOutcome(run);
  return taskResult(`subagent[${label}] — ${summary}\n\n${body}`);
}

export const subagentTool = {
  name: "subagent",
  label: "Subagent",
  description:
    "Delegate a bounded, self-contained piece of work to a dedicated child pi session in the same " +
    "project root. The child starts with the root AGENTS.md loaded (never --no-context-files), " +
    "gets a concise task packet, and returns structured output to the parent.",
  promptSnippet: "delegate a bounded sub-task to a focused child pi session and collect its structured result",
  promptGuidelines: [
    "Use subagent when a piece of work is well-bounded and can run independently, so the parent keeps focus and cheaper headroom.",
    "Independent sub-tasks may be dispatched in parallel when the model orchestrates multiple subagent calls in one turn.",
    "The subagent's result returns to the parent as the tool result; the parent stays authoritative and does final integration.",
    "Do NOT use subagent for work the parent can finish in a few steps, work that must share the parent's working memory, or tiny commits.",
    "A subagent cannot spawn a deeper subagent: recursion is bounded at max depth, so a child that 'needs a subagent' must finish inline or hand back to the parent.",
    "The child runs in the resolved project root with context files enabled, so it sees the same AGENTS.md bootstrap the parent does.",
  ],
  parameters: Type.Object({
    task: Type.String({
      description: "The concise, self-contained task packet for the child. Include success criteria and the exact deliverable.",
    }),
    name: Type.Optional(Type.String({
      description: "Optional short role label shown with the result, e.g. 'researcher' or 'dev'. Defaults to a label derived from the task text.",
    })),
  }),
  async execute(
    _callId: string,
    params: { task: string; name?: string },
    _signal: AbortSignal | undefined,
    _onUpdate: unknown,
    ctx: ToolCtx,
  ) {
    if (!params.task || params.task.trim() === "") {
      return taskResult("subagent needs a non-empty task packet; nothing was dispatched.");
    }
    return executeSubagent(params.task, ctx, {
      label: params.name ?? null,
    });
  },
};
