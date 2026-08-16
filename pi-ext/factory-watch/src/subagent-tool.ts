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
// buried at the tail behind session echo and the injected code index. We
// therefore parse the stream (mirroring pi_backend.py's parse_pi_json) and
// return the child's final assistant text. Failure modes are classified so a
// broken spawn, a timeout, an over-budget output buffer, or a non-zero child
// exit are never reported as the same opaque "(no stderr)".

import { Type } from "typebox";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { resolveProjectRoot } from "./factory-init.js";
import { agentExtensionPath } from "./factory-path.js";

// Recursion bound. A subagent that could spawn its own subagents forever is a
// resource leak; the factory's own orchestrator runs a single bounded depth and
// this guard keeps the delta non-recursive unless explicitly raised.
export const MAX_SUBAGENT_DEPTH = 1;
export const RECURSE_GUARD_ENV = "PI_FACTORY_SUBAGENT_DEPTH";

// Total wall-clock budget for a child pi run.
export const SUBAGENT_TIMEOUT_MS = 600_000;

// spawnSync's default maxBuffer is 1 MiB: a child whose event stream exceeds
// that (tool-heavy runs echo every tool result + the injected code index into
// JSONL) is killed with ENOBUFS, leaving status null and stderr empty -- which
// used to surface as the opaque "(no stderr)" failure. Raise it generously;
// the parser only keeps the extracted answer, so memory stays bounded.
export const SUBAGENT_MAX_BUFFER = 128 * 1024 * 1024;

interface ToolCtx {
  cwd: string;
  model?: { provider: string; id: string };
}

function taskResult(text: string): { content: { type: "text"; text: string }[]; details: null } {
  return { content: [{ type: "text", text }], details: null };
}

/**
 * Turn a pure argv command into the shape `spawnSync` needs for this platform.
 *
 * On Windows the npm `pi` bin is a `.cmd`/`.sh` shim that Node's `spawnSync`
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
  writeFileSync(
    packetFile,
    `You are a bounded subagent in project ${input.root}.\n\n` +
      `TASK\n${input.task}\n\n` +
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
 * Reconstruct the child's final answer from its JSONL event stream. Only the
 * LAST assistant message's content is returned (earlier assistant messages are
 * intermediate tool-call turns; their tool_call blocks carry no text anyway).
 * Mirrors pi_backend.parse_pi_json's message_end + text/thinking handling.
 */
export function parseChildJsonl(stdout: string): ChildJsonlAnswer {
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
  for (const rawLine of stdout.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    let event: unknown;
    try {
      event = JSON.parse(line);
    } catch {
      continue; // non-JSON noise is not part of the stream
    }
    if (!event || typeof event !== "object" || Array.isArray(event)) continue;
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
      if (!Array.isArray(content)) continue;
      // Keep the LAST assistant message only: earlier ones are intermediate
      // turns. Reset the accumulators when a new assistant message ends.
      if (answer.assistantMessages > 1) {
        textBlocks = [];
        thinkingBlocks = [];
      }
      for (const block of content) {
        if (!block || typeof block !== "object" || Array.isArray(block)) continue;
        const b = block as Record<string, unknown>;
        if (b.type === "text" && typeof b.text === "string") textBlocks.push(b.text);
        else if (b.type === "thinking" && typeof b.thinking === "string")
          thinkingBlocks.push(b.thinking);
      }
    }
  }
  if (textBlocks.length > 0) {
    answer.text = textBlocks.join("\n");
  } else if (thinkingBlocks.length > 0) {
    answer.text = thinkingBlocks.join("\n");
    answer.thinkingOnly = true;
  }
  return answer;
}

// ---------------------------------------------------------------------------
// Outcome rendering (pure: classify a finished spawn into a parent-facing
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

export function renderSubagentOutcome(proc: SubagentProc): string {
  // Spawn-level failure: child never ran or was killed by the harness. This is
  // where a timeout (ETIMEDOUT) and an over-budget output (ENOBUFS, the old
  // opaque "(no stderr)" failure when a tool-heavy child exceeded 1 MiB of
  // JSONL under spawnSync's default maxBuffer) land.
  if (proc.error) {
    const code = (proc.error as Error & { code?: string }).code;
    const detail =
      code === "ETIMEDOUT"
        ? `child pi did not finish within ${SUBAGENT_TIMEOUT_MS}ms`
        : code === "ENOBUFS"
          ? `child output exceeded ${SUBAGENT_MAX_BUFFER} bytes (tool-heavy runs emit large JSONL event streams)`
          : `${proc.error.message}${code ? ` (code ${code})` : ""}`;
    return `subagent spawn failed: ${detail}`;
  }

  const stdout = proc.stdout ?? "";
  const stderr = (proc.stderr ?? "").trim();

  // Non-zero exit: the child ran but died. stderr is usually empty for a CLI
  // crash; fall back to a JSONL error event, then to the stdout tail so the
  // parent sees the actual reason instead of "(no stderr)".
  if (proc.status !== 0) {
    const parsed = parseChildJsonl(stdout);
    const detail =
      (stderr || parsed.failureEvent) ||
      (stdout.trim() ? `stdout tail: ${stdout.slice(-1500)}` : "(no output)");
    const signal = proc.signal ? `, signal ${proc.signal}` : "";
    return `subagent failed (exit ${proc.status}${signal}): ${detail.slice(0, 2000)}`;
  }

  // Exit 0 with a parseable answer.
  const parsed = parseChildJsonl(stdout);
  if (parsed.text.trim() !== "") {
    const truncated = parsed.text.length > ANSWER_CAP ? `\n(truncated to ${ANSWER_CAP} chars)` : "";
    const provenance = parsed.thinkingOnly
      ? "\n(answer recovered from the model's thinking block -- no plain text block was emitted)"
      : "";
    return `subagent output:\n${parsed.text.slice(0, ANSWER_CAP)}${provenance}${truncated}`;
  }

  // Exit 0, non-empty stream, no assistant text: pi's event shape may not
  // match our parser -- say so explicitly instead of reporting an empty run.
  if (parsed.jsonEvents > 0) {
    return (
      `subagent completed (exit 0) but emitted no assistant text ` +
      `(${parsed.jsonEvents} JSON events, last: ${parsed.lastEventType ?? "?"}) -- ` +
      `possible event-shape mismatch. Raw tail:\n${stdout.slice(-1500)}`
    );
  }

  // Genuinely empty.
  return `subagent output: (empty output)${stderr ? `\nstderr: ${stderr.slice(0, 1000)}` : ""}`;
}

/**
 * Delegates a bounded sub-task to a dedicated child pi process. Returns the
 * child's final answer (extracted from its JSONL event stream) or a
 * classified failure message. Never spawns when at the recursion bound.
 */
export async function executeSubagent(
  task: string,
  ctx: ToolCtx,
  deps: {
    build: typeof buildSubagentInvocation;
    resolveRoot: typeof resolveProjectRoot;
  } = {
    build: buildSubagentInvocation,
    resolveRoot: resolveProjectRoot,
  },
): Promise<{ content: { type: "text"; text: string }[]; details: null }> {
  const { root } = deps.resolveRoot(ctx.cwd);
  const depth = Number(process.env[RECURSE_GUARD_ENV] ?? "0") || 0;
  const invocation = deps.build({
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
  const proc = spawnSync(plan.file, plan.args, {
    cwd: root, // project root: same AGENTS.md / bootstrap as the parent
    env: invocation.env,
    encoding: "utf-8",
    timeout: SUBAGENT_TIMEOUT_MS,
    maxBuffer: SUBAGENT_MAX_BUFFER,
    shell: plan.shell,
  });
  return taskResult(
    renderSubagentOutcome({
      status: proc.status,
      signal: proc.signal,
      error: proc.error ?? null,
      stdout: proc.stdout ?? "",
      stderr: proc.stderr ?? "",
    }),
  );
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
  }),
  async execute(
    _callId: string,
    params: { task: string },
    _signal: AbortSignal | undefined,
    _onUpdate: unknown,
    ctx: ToolCtx,
  ) {
    if (!params.task || params.task.trim() === "") {
      return taskResult("subagent needs a non-empty task packet; nothing was dispatched.");
    }
    return executeSubagent(params.task, ctx);
  },
};
