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

interface ToolCtx {
  cwd: string;
  model?: { provider: string; id: string };
}

function taskResult(text: string): { content: { type: "text"; text: string }[]; details: null } {
  return { content: [{ type: "text", text }], details: null };
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

/**
 * Delegates a bounded sub-task to a dedicated child pi process. Returns the
 * child's structured output (message_end) or a hard error string. Never
 * spawns when at the recursion bound.
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

  const proc = spawnSync(invocation.cmd[0]!, invocation.cmd.slice(1), {
    cwd: root, // project root: same AGENTS.md / bootstrap as the parent
    env: invocation.env,
    encoding: "utf-8",
    timeout: 600_000,
  });
  let stdout = proc.stdout ?? "";
  if (proc.status !== 0) {
    return taskResult(
      `subagent failed (exit ${proc.status ?? "?"}): ${(proc.stderr || "").slice(0, 2000) || "(no stderr)"}`,
    );
  }
  const output = (proc.stdout ?? "").trim();
  return taskResult(`subagent output:\n${(output || "(empty output)").slice(0, 4000)}`);
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
