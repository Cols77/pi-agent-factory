import { spawnSync } from "node:child_process";
import { Type } from "typebox";
import type { PiApi } from "./pi-types.js";

// SR-034/SR-049 governed-execution host tools.
//
// These four tools are a transport, not a lifecycle. Each one validates its
// identifiers, hands `ctx.cwd` and a fixed argv to the Python-owned
// `coherence execution` command surface, and returns that command's output
// UNCHANGED. No tool here decides pass/fail, interprets a gate, writes a flaky
// record, keeps host-local run state, or fabricates a human decision.
//
// `resolve-human` is deliberately NOT a tool: resolving a durable `needs_input`
// request is a human decision, invoked by the Codex skill / Claude Code command
// or an explicit Pi UI action, never an automatic tool transition.

// Structural subset of the ExtensionContext fields these tools read, kept local
// so the tools stay unit-testable without constructing a real context.
interface ToolCtx {
  cwd: string;
}

/** The one seam that reaches Python; injected so the tools are unit-testable. */
export interface ExecutionRunner {
  run(argv: string[], cwd: string): string;
}

/** The closed worker-result vocabulary the Python CLI accepts. */
export const WORKER_RESULTS = ["pass", "fail", "error"] as const;

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

// Mirrors trace-cli.ts / process-control.ts: the established way this extension
// reaches the Python side.
export function buildExecutionCommand(argv: string[]): { bin: string; args: string[] } {
  return { bin: "uv", args: ["run", "coherence", ...argv] };
}

function runCoherenceExecution(argv: string[], cwd: string): string {
  const cmd = buildExecutionCommand(argv);
  const spawned = spawnSync(cmd.bin, cmd.args, {
    cwd,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (spawned.error) {
    return `coherence execution failed: ${String(spawned.error.message ?? spawned.error)}`;
  }
  // The CLI prints its blocked/escalated payload on stdout too (exit 1), so the
  // payload is forwarded whatever the exit code was; only an empty stdout (a
  // usage error, exit 2) falls back to the command's own stderr text.
  const stdout = spawned.stdout ?? "";
  if (stdout.trim() !== "") return stdout;
  const stderr = (spawned.stderr ?? "").trim();
  return `coherence execution failed: ${stderr || `exited ${spawned.status ?? -1}`}`;
}

const defaultRunner: ExecutionRunner = { run: runCoherenceExecution };

// AgentToolResult.content is a block array, not a string, and `details` is
// required -- pi's getTextOutput calls result.content.filter(), so returning a
// bare string crashes the interactive renderer.
function result(text: string): { content: { type: "text"; text: string }[]; details: null } {
  return { content: [{ type: "text", text }], details: null };
}

function unsafe(field: string, value: string): string {
  return (
    `${field} ${JSON.stringify(value)} is not a safe identifier ` +
    "(expected [A-Za-z0-9][A-Za-z0-9._-]*); nothing was run."
  );
}

/** Validate every identifier before Python is reached; return the first refusal. */
function refuse(fields: Record<string, string>): string | null {
  for (const [field, value] of Object.entries(fields)) {
    if (typeof value !== "string" || !SAFE_ID.test(value)) return unsafe(field, value);
  }
  return null;
}

export function buildExecutionTools(deps: ExecutionRunner = defaultRunner) {
  const legalActions = {
    name: "execution_legal_actions",
    label: "Execution: legal actions",
    description:
      "Return the read-only governed-execution projection for one run/task: the current stage " +
      "state, the closed list of legal next actions, current hashes, the pending human-decision " +
      "request when there is one, and the visibility-only denied_write_count. It never mutates " +
      "state and is the ONLY transition projection a host may act on.",
    promptSnippet: "ask Python which governed-execution actions are legal for a run/task",
    promptGuidelines: [
      "Call execution_legal_actions before any other execution tool; act only on an action it returned.",
      "Never infer the state or the next action: starts_automatically is always false and means stop.",
    ],
    parameters: Type.Object({
      run_id: Type.String({ description: "Run id, e.g. run-013" }),
      task_id: Type.String({ description: "Task id, e.g. T-013" }),
    }),
    async execute(
      _id: string,
      params: { run_id: string; task_id: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const refusal = refuse({ run_id: params.run_id, task_id: params.task_id });
      if (refusal) return result(refusal);
      return result(
        deps.run(
          ["execution", "legal-actions", "--run-id", params.run_id, "--task-id", params.task_id, "--json"],
          ctx.cwd,
        ),
      );
    },
  };

  const dispatchTask = {
    name: "execution_dispatch_task",
    label: "Execution: dispatch task",
    description:
      "Dispatch one task through the Python-owned governed execution driver and return its " +
      "structured result verbatim. The driver owns every stage, gate and retry; this tool only " +
      "forwards. Query execution_legal_actions first and dispatch only when it says so.",
    promptSnippet: "dispatch one governed task through the Python driver and forward its result",
    promptGuidelines: [
      "Use execution_dispatch_task only when execution_legal_actions returned dispatch-task.",
      "Forward the returned JSON unchanged, including any blocking reason; never retry it yourself.",
    ],
    parameters: Type.Object({
      run_id: Type.String({ description: "Run id, e.g. run-013" }),
      task_id: Type.String({ description: "Task id, e.g. T-013" }),
    }),
    async execute(
      _id: string,
      params: { run_id: string; task_id: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const refusal = refuse({ run_id: params.run_id, task_id: params.task_id });
      if (refusal) return result(refusal);
      return result(
        deps.run(
          ["execution", "dispatch-task", params.task_id, "--run-id", params.run_id, "--json"],
          ctx.cwd,
        ),
      );
    },
  };

  const reportWorkerResult = {
    name: "execution_report_worker_result",
    label: "Execution: report worker result",
    description:
      "Append ONE validated worker observation (pass | fail | error, with a detail and an " +
      "optional denied-write count) to the run's evidence. It is an observation, never a " +
      "verdict: it cannot complete a task, change a gate, or resolve a human decision.",
    promptSnippet: "record one worker lane observation as run evidence",
    promptGuidelines: [
      "Use execution_report_worker_result to record what a lane observed; it never marks work done.",
      "The result vocabulary is exactly pass, fail or error.",
    ],
    parameters: Type.Object({
      run_id: Type.String({ description: "Run id, e.g. run-013" }),
      task_id: Type.String({ description: "Task id, e.g. T-013" }),
      lane: Type.String({ description: "Worker lane, e.g. dev or review-spec" }),
      result: Type.String({ description: "One of pass, fail, error" }),
      detail: Type.String({ description: "What the lane observed — recorded verbatim" }),
      denied_writes: Type.Optional(
        Type.Integer({ description: "Denied out-of-worktree writes (visibility only)" }),
      ),
    }),
    async execute(
      _id: string,
      params: {
        run_id: string;
        task_id: string;
        lane: string;
        result: string;
        detail: string;
        denied_writes?: number;
      },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const refusal = refuse({
        run_id: params.run_id,
        task_id: params.task_id,
        lane: params.lane,
      });
      if (refusal) return result(refusal);
      if (!(WORKER_RESULTS as readonly string[]).includes(params.result)) {
        return result(
          `execution_report_worker_result needs result to be one of ${WORKER_RESULTS.join(", ")}; ` +
            "nothing was recorded.",
        );
      }
      if (typeof params.detail !== "string" || params.detail.trim() === "") {
        return result("execution_report_worker_result needs a non-empty detail; nothing was recorded.");
      }
      const denied = params.denied_writes;
      if (denied !== undefined && (!Number.isInteger(denied) || denied < 0)) {
        return result(
          "execution_report_worker_result needs denied_writes to be a non-negative integer; " +
            "nothing was recorded.",
        );
      }
      const argv = [
        "execution",
        "report-worker-result",
        "--run-id",
        params.run_id,
        "--task-id",
        params.task_id,
        "--lane",
        params.lane,
        "--result",
        params.result,
        "--detail",
        params.detail,
      ];
      if (denied !== undefined) argv.push("--denied-writes", String(denied));
      argv.push("--json");
      return result(deps.run(argv, ctx.cwd));
    },
  };

  const streamProgress = {
    name: "execution_stream_progress",
    label: "Execution: stream progress",
    description:
      "Return the canonical run journal's events in sequence order, exactly as Python emits " +
      "them. Read-only: it interprets nothing and decides nothing.",
    promptSnippet: "read one governed run's journal events in sequence order",
    promptGuidelines: [
      "Use execution_stream_progress to show what actually happened; never summarise it as a verdict.",
    ],
    parameters: Type.Object({
      run_id: Type.String({ description: "Run id, e.g. run-013" }),
    }),
    async execute(
      _id: string,
      params: { run_id: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const refusal = refuse({ run_id: params.run_id });
      if (refusal) return result(refusal);
      return result(
        deps.run(["execution", "stream-progress", params.run_id, "--json"], ctx.cwd),
      );
    },
  };

  return [legalActions, dispatchTask, reportWorkerResult, streamProgress];
}

/** The registered tool names, derived from the builder itself. */
export const EXECUTION_TOOL_NAMES = buildExecutionTools().map((tool) => tool.name);

// Typed as PiApi's real registerTool, NOT `{ registerTool(tool: unknown) }` --
// see trace-tools.ts for why the `unknown` version is unsafe.
export function registerExecutionTools(pi: Pick<PiApi, "registerTool">): void {
  for (const tool of buildExecutionTools()) pi.registerTool(tool);
}
