import { Type } from "typebox";
import type { PiApi } from "./pi-types.js";
import {
  loadSystemDiagram,
  loadSystemGoal,
  loadSystemGoalEvaluate,
  loadSystemGoalsList,
  loadSystemPresent,
  loadSystemSimFailure,
  loadSystemSimGoalEvidence,
  loadSystemSimLatest,
  loadSystemSimMetric,
  loadSystemSimRun,
  loadSystemTraversal,
  loadSystemVcycle,
  loadSystemRequirementsContext,
} from "./system-cli.js";
import {
  formatDiagram,
  formatGoal,
  formatGoalEvaluate,
  formatGoalList,
  formatPresent,
  formatSimFailure,
  formatSimGoalEvidence,
  formatSimLatest,
  formatSimMetric,
  formatSimRun,
  formatVcycle,
  formatRequirementsContext,
} from "./eng-context-tool-format.js";

// Structural subset of the ExtensionContext fields these read-only tools read.
interface ToolCtx {
  cwd: string;
}

interface Dependencies {
  vcycle: typeof loadSystemVcycle;
  diagram: typeof loadSystemDiagram;
  simRun: typeof loadSystemSimRun;
  simLatest: typeof loadSystemSimLatest;
  simFailure: typeof loadSystemSimFailure;
  simMetric: typeof loadSystemSimMetric;
  simGoalEvidence: typeof loadSystemSimGoalEvidence;
  goal: typeof loadSystemGoal;
  goalsList: typeof loadSystemGoalsList;
  goalEvaluate: typeof loadSystemGoalEvaluate;
  present: typeof loadSystemPresent;
  traversal: typeof loadSystemTraversal;
  requirementsContext: typeof loadSystemRequirementsContext;
}

const defaultDependencies: Dependencies = {
  vcycle: loadSystemVcycle,
  diagram: loadSystemDiagram,
  simRun: loadSystemSimRun,
  simLatest: loadSystemSimLatest,
  simFailure: loadSystemSimFailure,
  simMetric: loadSystemSimMetric,
  simGoalEvidence: loadSystemSimGoalEvidence,
  goal: loadSystemGoal,
  goalsList: loadSystemGoalsList,
  goalEvaluate: loadSystemGoalEvaluate,
  present: loadSystemPresent,
  traversal: loadSystemTraversal,
  requirementsContext: loadSystemRequirementsContext,
};

const MAX_OUTPUT_BYTES = 50 * 1024;

// AgentToolResult.content is a block array; `details` is required. Same shape
// as the other tool modules (trace-tools.ts / system-context-tools.ts).
function result(text: string, details: unknown = null) {
  const bytes = Buffer.from(text, "utf-8");
  const body =
    bytes.length <= MAX_OUTPUT_BYTES
      ? text
      : `${bytes.subarray(0, MAX_OUTPUT_BYTES).toString("utf-8")}\n[truncated; use a narrower id]`;
  return { content: [{ type: "text" as const, text: body }], details };
}

// Reconstruct the trace chain for a requirement: requirement -> satisfying
// tasks -> design decisions -> changed files (spec §26 step 4 "affected
// design/code"). Reuses `factory.system traversal` (SP-B Task 9) so this
// never re-derives the graph in TS.
function formatTraversalForRequirement(
  cwd: string,
  requirementId: string,
  deps: Dependencies,
): string {
  const scope = `sr:${requirementId}`;
  const res = deps.traversal(cwd, scope);
  if (!res.ok) return `trace_requirement failed: ${res.error}`;
  const lines = [`trace for ${requirementId}:`];
  lines.push(`  requirements: ${res.value.requirement.length ? res.value.requirement.join(", ") : "none"}`);
  lines.push(`  tasks: ${res.value.tasks.length ? res.value.tasks.join(", ") : "none"}`);
  lines.push(`  design: ${res.value.design.length ? res.value.design.join(", ") : "none"}`);
  lines.push(`  files: ${res.value.files.length ? res.value.files.join(", ") : "none"}`);
  return lines.join("\n");
}

// The action tools write goal state and must stay separable from the read-only
// set (Task 3 Step 3): a reviewer can forbid these ids without touching the
// read-only tools' registration.
export const ENG_ACTION_TOOL_IDS = ["eng_evaluate_goal", "eng_present"] as const;

export function buildEngContextTools(deps: Dependencies = defaultDependencies) {
  const engGetVcycle = {
    name: "eng_get_vcycle",
    label: "Engineering context: V-cycle slice",
    description:
      "Return the typed V-cycle slice (definition + verification sides, goals, metrics) " +
      "for one exact feat: or sr: scope, as Python's factory.system vcycle computes it.",
    parameters: Type.Object({
      ref: Type.String({ description: "Scope ref, e.g. feat:FEAT-NAV-017 or sr:SR-001" }),
    }),
    async execute(_id: string, params: { ref: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.vcycle(ctx.cwd, params.ref);
      return result(res.ok ? formatVcycle(res.value) : `eng_get_vcycle failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  const engGetRequirementsContext = {
    name: "eng_get_requirements_context",
    label: "Engineering context: all requirements",
    description: "Return the complete read-only project SR context, including status, source anchors, graph relationships, trace metadata, candidate duplicates/contradictions, and a binding digest.",
    parameters: Type.Object({}),
    async execute(_id: string, _params: Record<string, never>, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.requirementsContext(ctx.cwd);
      return result(res.ok ? formatRequirementsContext(res.value) : `eng_get_requirements_context failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  const engGetDiagram = {
    name: "eng_get_diagram",
    label: "Engineering context: diagram",
    description:
      "Resolve a diag: artifact stub to its canonical committed HTML path, focus, and " +
      "illustrates references. Read-only; the diagram is a committed reviewable artifact (D7).",
    parameters: Type.Object({
      diagram_id: Type.String({ description: "Diagram id, e.g. DIAG-NAV-001" }),
    }),
    async execute(_id: string, params: { diagram_id: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.diagram(ctx.cwd, params.diagram_id);
      return result(res.ok ? formatDiagram(res.value) : `eng_get_diagram failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  const engTraceRequirement = {
    name: "eng_trace_requirement",
    label: "Engineering context: trace requirement",
    description:
      "Return the trace chain for one requirement: requirement -> satisfying tasks -> " +
      "design decisions -> changed files. Exact refs only, no fuzzy fallback.",
    parameters: Type.Object({
      requirement_id: Type.String({ description: "Requirement id, e.g. SR-001" }),
    }),
    async execute(_id: string, params: { requirement_id: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      return result(formatTraversalForRequirement(ctx.cwd, params.requirement_id, deps));
    },
  };

  const engGetLatestSimulation = {
    name: "eng_get_latest_simulation",
    label: "Engineering context: latest simulation",
    description:
      "Return the latest simulation run for a feature (deterministic by run id). None is a " +
      "legitimate state (no run yet), not an error.",
    parameters: Type.Object({
      feature_id: Type.String({ description: "Feature id, e.g. FEAT-NAV-017" }),
    }),
    async execute(_id: string, params: { feature_id: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.simLatest(ctx.cwd, params.feature_id);
      return result(res.ok ? formatSimLatest(res.value) : `eng_get_latest_simulation failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  const engGetLatestFailure = {
    name: "eng_get_latest_failure",
    label: "Engineering context: latest failure",
    description:
      "Return the most recent non-passed simulation run for a feature, or None. Exact and " +
      "deterministic; never a fuzzy match.",
    parameters: Type.Object({
      feature_id: Type.String({ description: "Feature id, e.g. FEAT-NAV-017" }),
    }),
    async execute(_id: string, params: { feature_id: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.simFailure(ctx.cwd, params.feature_id);
      return result(res.ok ? formatSimFailure(res.value) : `eng_get_latest_failure failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  const engGetGoal = {
    name: "eng_get_goal",
    label: "Engineering context: goal",
    description:
      "Return one goal: contract, current state, feature/requirement bindings, target. Loaded " +
      "through the goals registry, never a re-glob.",
    parameters: Type.Object({
      goal_id: Type.String({ description: "Goal id, e.g. GOAL-NAV-003" }),
    }),
    async execute(_id: string, params: { goal_id: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.goal(ctx.cwd, params.goal_id);
      return result(res.ok ? formatGoal(res.value) : `eng_get_goal failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  const engGetGoals = {
    name: "eng_get_goals",
    label: "Engineering context: goals for a scope",
    description:
      "Return the goals bound to a feat:, sr:, or goal: scope. Binding is read from declared " +
      "data, never inferred.",
    parameters: Type.Object({
      scope: Type.String({ description: "Scope ref, e.g. feat:FEAT-NAV-017 or sr:SR-001" }),
    }),
    async execute(_id: string, params: { scope: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.goalsList(ctx.cwd, params.scope);
      return result(res.ok ? formatGoalList(res.value) : `eng_get_goals failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  const engGetGoalEvidence = {
    name: "eng_get_goal_evidence",
    label: "Engineering context: goal evidence",
    description:
      "Return the simulation runs whose manifest lists goal_id (ascending by run id). A goal " +
      "with no runs resolves to an empty list, never a guess.",
    parameters: Type.Object({
      goal_id: Type.String({ description: "Goal id, e.g. GOAL-NAV-003" }),
    }),
    async execute(_id: string, params: { goal_id: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.simGoalEvidence(ctx.cwd, params.goal_id);
      return result(res.ok ? formatSimGoalEvidence(res.value) : `eng_get_goal_evidence failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  const engGetMetricHistory = {
    name: "eng_get_metric_history",
    label: "Engineering context: metric history",
    description:
      "Return the ascending history of one metric across simulation runs (deterministic order).",
    parameters: Type.Object({
      metric_id: Type.String({ description: "Metric id, e.g. reacquisition_rate" }),
    }),
    async execute(_id: string, params: { metric_id: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.simMetric(ctx.cwd, params.metric_id);
      return result(res.ok ? formatSimMetric(res.value) : `eng_get_metric_history failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  const engGetSimulationRun = {
    name: "eng_get_simulation_run",
    label: "Engineering context: simulation run",
    description:
      "Return one simulation run by its run id (spec §20 bundle). A run no bundle declares is " +
      "a resolution failure, never a fuzzy guess.",
    parameters: Type.Object({
      run_id: Type.String({ description: "Run id, e.g. RUN-20260811-1702" }),
    }),
    async execute(_id: string, params: { run_id: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.simRun(ctx.cwd, params.run_id);
      return result(res.ok ? formatSimRun(res.value) : `eng_get_simulation_run failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  // ACTION tool (Task 3 Step 1): the ONLY tool that writes goal state. It runs
  // the Inc 3 auto-eval for one goal and records the resulting state IF the
  // lifecycle (spec §13 can_transition) permits it; an illegal or unmeasurable
  // edge is reported without writing.
  const engEvaluateGoal = {
    name: "eng_evaluate_goal",
    label: "Engineering context: evaluate goal (ACTION)",
    description:
      "ACTION (writes goal state). Run the Inc 3 auto-eval for one goal against its latest " +
      "simulation run and record the resulting transition when the lifecycle (spec §13) " +
      "permits it. An illegal lifecycle edge or a goal with no measurable run is reported " +
      "without writing. This is the only tool that writes goal state; a reviewer can forbid " +
      "it without touching any read-only eng_* tool.",
    parameters: Type.Object({
      goal_id: Type.String({ description: "Goal id, e.g. GOAL-NAV-003" }),
    }),
    async execute(_id: string, params: { goal_id: string }, _sig: AbortSignal | undefined, _u: unknown, ctx: ToolCtx) {
      const res = deps.goalEvaluate(ctx.cwd, params.goal_id);
      return result(res.ok ? formatGoalEvaluate(res.value) : `eng_evaluate_goal failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  // ACTION tool (Task 3 Step 2): request a human-facing presentation of an
  // artifact. The Inc 5 router is not landed yet, so in Inc 4 this validates
  // the args, records the intent, and returns the resolution plan as a
  // declaration — it never dispatches an adapter or fabricates a target
  // (forward/declare only).
  const engPresent = {
    name: "eng_present",
    label: "Engineering context: present artifact (ACTION)",
    description:
      "ACTION (requests human-facing presentation). Resolve the presentation " +
      "intent (artifact, optional focus) through the Inc 5 router to the chosen " +
      "level + adapter + target. It never shells out with unvalidated strings and " +
      "never opens UI itself — the caller/Inc 6 performs the open from the returned " +
      "target. This is an action (not read-only); a reviewer can forbid it with the " +
      "other action.",
    parameters: Type.Object({
      artifact: Type.String({ description: "Artifact to present, e.g. feat:FEAT-NAV-017, sr:SR-001, or a file path" }),
      focus: Type.Optional(Type.String({ description: "Optional focus within the artifact, e.g. a node id or line number" })),
      why_required: Type.Optional(Type.Boolean({ description: "Include compiled obligation explanations" })),
    }),
    async execute(
      _id: string,
      params: { artifact: string; focus?: string; why_required?: boolean },
      _sig: AbortSignal | undefined,
      _u: unknown,
      ctx: ToolCtx,
    ) {
      const res = deps.present(ctx.cwd, params.artifact, params.focus ?? undefined, params.why_required ?? false);
      return result(res.ok ? formatPresent(res.value) : `eng_present failed: ${res.error}`, res.ok ? res.value : null);
    },
  };

  return [
    engGetVcycle,
    engGetRequirementsContext,
    engGetDiagram,
    engTraceRequirement,
    engGetLatestSimulation,
    engGetLatestFailure,
    engGetGoal,
    engGetGoals,
    engGetGoalEvidence,
    engGetMetricHistory,
    engGetSimulationRun,
    engEvaluateGoal,
    engPresent,
  ];
}

export function registerEngContextTools(pi: Pick<PiApi, "registerTool">): void {
  for (const tool of buildEngContextTools()) pi.registerTool(tool);
}
