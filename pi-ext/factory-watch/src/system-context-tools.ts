import { Type } from "typebox";
import type { PiApi } from "./pi-types.js";
import {
  loadTaskEvidence,
  runPreflight,
  runReconcile,
} from "./evidence-client.js";
import { loadTraceGraph } from "./trace-cli.js";

interface ToolCtx { cwd: string }

interface Dependencies {
  graph: typeof loadTraceGraph;
  taskEvidence: typeof loadTaskEvidence;
  preflight: typeof runPreflight;
  reconcile: typeof runReconcile;
}

const defaultDependencies: Dependencies = {
  graph: loadTraceGraph,
  taskEvidence: loadTaskEvidence,
  preflight: runPreflight,
  reconcile: runReconcile,
};

const MAX_OUTPUT_BYTES = 50 * 1024;

function result(value: unknown) {
  const full = JSON.stringify(value, null, 2);
  const bytes = Buffer.from(full, "utf-8");
  const text = bytes.length <= MAX_OUTPUT_BYTES
    ? full
    : `${bytes.subarray(0, MAX_OUTPUT_BYTES).toString("utf-8")}\n[truncated; use a narrower id]`;
  return { content: [{ type: "text" as const, text }], details: value };
}

function unknown(source: string, error: string): Record<string, unknown> {
  return {
    status: "unknown",
    source,
    error,
    instruction: "Missing evidence is unknown. Do not infer or manufacture it.",
  };
}

export function buildSystemContextTools(deps: Dependencies = defaultDependencies) {
  const systemContext = {
    name: "system_context",
    label: "System context",
    description:
      "Return the exact declared trace node, one-hop neighbours, freshness findings, and durable " +
      "task evidence references for an id. Missing data is unknown; never infer links or history.",
    parameters: Type.Object({
      id: Type.String({ description: "Declared task, requirement, plan, or spec id" }),
    }),
    async execute(
      _callId: string,
      params: { id: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const graphResult = deps.graph(ctx.cwd);
      if (!graphResult.ok) return result(unknown("trace", graphResult.error));
      const node = graphResult.graph.nodes.find((item) => item.id === params.id);
      if (node === undefined) return result(unknown("trace", `node not found: ${params.id}`));
      const edges = graphResult.graph.edges.filter(
        (edge) => edge.src === params.id || edge.dst === params.id,
      );
      const neighbourIds = new Set(
        edges.flatMap((edge) => [edge.src, edge.dst]).filter((id) => id !== params.id),
      );
      const neighbours = graphResult.graph.nodes.filter((item) => neighbourIds.has(item.id));
      const taskEvidence = node.kind === "task"
        ? deps.taskEvidence(ctx.cwd, params.id)
        : null;
      const freshness = node.kind === "task" ? deps.preflight(ctx.cwd, params.id) : null;
      return result({
        node,
        edges,
        neighbours,
        freshness: freshness === null
          ? { status: "not-applicable", reason: "freshness is task-scoped" }
          : freshness.ok ? freshness.value : unknown("preflight", freshness.error),
        evidence: taskEvidence === null
          ? { status: "not-applicable", reason: "implementation evidence is task-scoped" }
          : taskEvidence.ok
            ? { runs: taskEvidence.value.runs.map((run) => ({
                run_id: run.run_id,
                outcome: run.outcome,
                start_commit: run.start_commit,
                result_commit: run.result_commit,
              })) }
            : unknown("evidence", taskEvidence.error),
        provenance: "recorded and deterministically derived project data only",
      });
    },
  };

  const implementationHistory = {
    name: "implementation_history",
    label: "Implementation history",
    description:
      "Return durable run manifests for a task. An empty result means no recorded evidence, not " +
      "that implementation never happened; do not infer provenance from nearby commits.",
    parameters: Type.Object({ task_id: Type.String() }),
    async execute(
      _callId: string,
      params: { task_id: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const value = deps.taskEvidence(ctx.cwd, params.task_id);
      return result(value.ok ? value.value : unknown("evidence", value.error));
    },
  };

  const validationStatus = {
    name: "validation_status",
    label: "Validation status",
    description:
      "Return the declared requirement node and its exact validation status. Missing status is " +
      "unknown and must not be described as passed or failed.",
    parameters: Type.Object({ id: Type.String({ description: "Requirement id, e.g. SR-001" }) }),
    async execute(
      _callId: string,
      params: { id: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const graphResult = deps.graph(ctx.cwd);
      if (!graphResult.ok) return result(unknown("trace", graphResult.error));
      const node = graphResult.graph.nodes.find((item) => item.id === params.id);
      if (node === undefined) return result(unknown("trace", `node not found: ${params.id}`));
      const status = graphResult.graph.validation[params.id];
      return result({
        node,
        validation: status ?? unknown("validation", `no validation entry for ${params.id}`),
      });
    },
  };

  const evidenceHealth = {
    name: "evidence_health",
    label: "Evidence health",
    description:
      "Return Python-owned reconciliation findings. Missing or unattributed data stays unknown; " +
      "this read-only tool never repairs or invents task attribution.",
    parameters: Type.Object({ task_id: Type.Optional(Type.String()) }),
    async execute(
      _callId: string,
      params: { task_id?: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const value = deps.reconcile(ctx.cwd, params.task_id);
      return result(value.ok ? value.value : unknown("reconciliation", value.error));
    },
  };

  return [systemContext, implementationHistory, validationStatus, evidenceHealth];
}

export function registerSystemContextTools(pi: Pick<PiApi, "registerTool">): void {
  for (const tool of buildSystemContextTools()) pi.registerTool(tool);
}
