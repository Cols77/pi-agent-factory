import { Type } from "typebox";
import type { PiApi } from "./pi-types.js";
import {
  loadTaskEvidence,
  runPreflight,
  runReconcile,
} from "./evidence-client.js";
import { loadTraceGraph } from "./trace-cli.js";
import {
  loadSystemBriefing,
  loadSystemGuide,
  loadSystemMatrix,
  loadSystemReverse,
  loadSystemScopes,
  loadSystemStory,
  loadSystemTimeline,
} from "./system-cli.js";
import { buildSystemContext, unknownSource } from "./system-context.js";

interface ToolCtx { cwd: string }

interface Dependencies {
  graph: typeof loadTraceGraph;
  taskEvidence: typeof loadTaskEvidence;
  preflight: typeof runPreflight;
  reconcile: typeof runReconcile;
  scopes: typeof loadSystemScopes;
  briefing: typeof loadSystemBriefing;
  matrix: typeof loadSystemMatrix;
  timeline: typeof loadSystemTimeline;
  guide: typeof loadSystemGuide;
  story: typeof loadSystemStory;
  reverse: typeof loadSystemReverse;
}

const defaultDependencies: Dependencies = {
  graph: loadTraceGraph,
  taskEvidence: loadTaskEvidence,
  preflight: runPreflight,
  reconcile: runReconcile,
  scopes: loadSystemScopes,
  briefing: loadSystemBriefing,
  matrix: loadSystemMatrix,
  timeline: loadSystemTimeline,
  guide: loadSystemGuide,
  story: loadSystemStory,
  reverse: loadSystemReverse,
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
      return result(buildSystemContext(ctx.cwd, params.id, deps).context);
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
      return result(value.ok ? value.value : unknownSource("evidence", value.error));
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
      if (!graphResult.ok) return result(unknownSource("trace", graphResult.error));
      const node = graphResult.graph.nodes.find((item) => item.id === params.id);
      if (node === undefined) return result(unknownSource("trace", `node not found: ${params.id}`));
      const status = graphResult.graph.validation[params.id];
      return result({
        node,
        validation: status ?? unknownSource("validation", `no validation entry for ${params.id}`),
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
      return result(value.ok ? value.value : unknownSource("reconciliation", value.error));
    },
  };

  const systemScopes = {
    name: "system_scopes",
    label: "System navigator: scopes",
    description:
      "Return every declared scope (bundle or SR) the system navigator can open, plus any " +
      "declared bundle files that failed to load. An empty scope list is a legitimate repo " +
      "state (no bundles or requirements directory yet), not an error -- do not treat it as one.",
    parameters: Type.Object({}),
    async execute(
      _callId: string,
      _params: Record<string, never>,
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const value = deps.scopes(ctx.cwd);
      return result(value.ok ? value.value : unknownSource("system", value.error));
    },
  };

  const systemBriefing = {
    name: "system_briefing",
    label: "System navigator: briefing",
    description:
      "Return the Python-computed one-page briefing (recorded/derived/synthesized/missing " +
      "claims, each carrying citations and a freshness state) for a declared scope. This tool " +
      "renders Python's answer; it never re-derives freshness, ordering, or provenance.",
    parameters: Type.Object({
      scope: Type.String({ description: "Scope ref, e.g. bundle:evidence-lifecycle or sr:SR-001" }),
    }),
    async execute(
      _callId: string,
      params: { scope: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const value = deps.briefing(ctx.cwd, params.scope);
      return result(value.ok ? value.value : unknownSource("system", value.error));
    },
  };

  const systemMatrix = {
    name: "system_matrix",
    label: "System navigator: validation matrix",
    description:
      "Return the Python-computed validation matrix (one row per SR relevant to the scope) " +
      "for a declared scope. `status` is the recorded validation outcome only; staleness and " +
      "absence live on each row's `freshness`, never guessed here.",
    parameters: Type.Object({
      scope: Type.String({ description: "Scope ref, e.g. bundle:evidence-lifecycle or sr:SR-001" }),
    }),
    async execute(
      _callId: string,
      params: { scope: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const value = deps.matrix(ctx.cwd, params.scope);
      return result(value.ok ? value.value : unknownSource("system", value.error));
    },
  };

  const systemTimeline = {
    name: "system_timeline",
    label: "System navigator: decision timeline",
    description:
      "Return the Python-computed decision timeline for a declared scope, already ordered by " +
      "recorded timestamp or recorded sequence number. `degraded`/`degraded_reasons` reflect " +
      "recorded gaps (e.g. no actor recorded); this tool never reorders or fills them in.",
    parameters: Type.Object({
      scope: Type.String({ description: "Scope ref, e.g. bundle:evidence-lifecycle or sr:SR-001" }),
    }),
    async execute(
      _callId: string,
      params: { scope: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const value = deps.timeline(ctx.cwd, params.scope);
      return result(value.ok ? value.value : unknownSource("system", value.error));
    },
  };

  const systemGuide = {
    name: "system_guide",
    label: "System navigator: grounded guide",
    description:
      "Return the Python-computed grounded prose guide for a declared scope. Each section is " +
      "either synthesized prose with verbatim quoted spans (only when every supporting " +
      "dependency is fresh) or recorded bullets otherwise -- this tool renders whichever kind " +
      "Python already chose; it never synthesizes, reorders, or re-derives freshness itself.",
    parameters: Type.Object({
      scope: Type.String({ description: "Scope ref, e.g. bundle:evidence-lifecycle or sr:SR-001" }),
    }),
    async execute(
      _callId: string,
      params: { scope: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const value = deps.guide(ctx.cwd, params.scope);
      return result(value.ok ? value.value : unknownSource("system", value.error));
    },
  };

  const systemStory = {
    name: "system_story",
    label: "System navigator: task implementation story",
    description:
      "Return the Python-computed implementation story for a task: scope (increment B, forward " +
      "half of the V-cycle) -- runs sourced from a durable evidence manifest or, when no manifest " +
      "exists for a run, a thinner session record. A session-sourced run's `implementation` is " +
      "always the literal claim kind 'missing'; this tool never fills that in or treats a session " +
      "record as equivalent to a manifest.",
    parameters: Type.Object({
      scope: Type.String({ description: "Scope ref, e.g. task:T-001" }),
    }),
    async execute(
      _callId: string,
      params: { scope: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const value = deps.story(ctx.cwd, params.scope);
      return result(value.ok ? value.value : unknownSource("system", value.error));
    },
  };

  const systemReverse = {
    name: "system_reverse",
    label: "System navigator: reverse navigation",
    description:
      "Return the Python-computed reverse walk for a file: scope (increment B, reverse half of " +
      "the V-cycle): file -> run -> task -> requirements. Each path's `stops_at` names the first " +
      "hop that did not resolve ('task' or 'satisfies'), or is null when the chain completes; " +
      "this tool never guesses past an unresolved hop.",
    parameters: Type.Object({
      scope: Type.String({ description: "Scope ref, e.g. file:src/a.py" }),
    }),
    async execute(
      _callId: string,
      params: { scope: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ToolCtx,
    ) {
      const value = deps.reverse(ctx.cwd, params.scope);
      return result(value.ok ? value.value : unknownSource("system", value.error));
    },
  };

  return [
    systemContext,
    implementationHistory,
    validationStatus,
    evidenceHealth,
    systemScopes,
    systemBriefing,
    systemMatrix,
    systemTimeline,
    systemGuide,
    systemStory,
    systemReverse,
  ];
}

export function registerSystemContextTools(pi: Pick<PiApi, "registerTool">): void {
  for (const tool of buildSystemContextTools()) pi.registerTool(tool);
}
