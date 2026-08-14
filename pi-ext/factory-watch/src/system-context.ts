import { loadTraceGraph } from "./trace-cli.js";
import type { TraceGraph } from "./trace-cli.js";
import { loadTaskEvidence, runPreflight } from "./evidence-client.js";

export interface SystemContextDeps {
  graph: typeof loadTraceGraph;
  taskEvidence: typeof loadTaskEvidence;
  preflight: typeof runPreflight;
}

export interface SystemContextResult {
  context: Record<string, unknown>;
  // The graph the composition already loaded. Returned so a caller that needs
  // the full node/edge set (the review server's chain walk) does not spawn a
  // second `uv run` for data this call already has in hand.
  graph: TraceGraph | null;
}

export function unknownSource(source: string, error: string): Record<string, unknown> {
  return {
    status: "unknown",
    source,
    error,
    instruction: "Missing evidence is unknown. Do not infer or manufacture it.",
  };
}

export function buildSystemContext(
  cwd: string,
  id: string,
  deps: SystemContextDeps,
): SystemContextResult {
  const graphResult = deps.graph(cwd);
  if (!graphResult.ok) {
    return { context: unknownSource("trace", graphResult.error), graph: null };
  }
  const graph = graphResult.graph;
  const node = graph.nodes.find((item) => item.id === id);
  if (node === undefined) {
    return { context: unknownSource("trace", `node not found: ${id}`), graph };
  }
  const edges = graph.edges.filter((edge) => edge.src === id || edge.dst === id);
  const neighbourIds = new Set(
    edges.flatMap((edge) => [edge.src, edge.dst]).filter((each) => each !== id),
  );
  const neighbours = graph.nodes.filter((item) => neighbourIds.has(item.id));
  const taskEvidence = node.kind === "task" ? deps.taskEvidence(cwd, id) : null;
  const freshness = node.kind === "task" ? deps.preflight(cwd, id) : null;
  return {
    graph,
    context: {
      node,
      edges,
      neighbours,
      freshness: freshness === null
        ? { status: "not-applicable", reason: "freshness is task-scoped" }
        : freshness.ok ? freshness.value : unknownSource("preflight", freshness.error),
      evidence: taskEvidence === null
        ? { status: "not-applicable", reason: "implementation evidence is task-scoped" }
        : taskEvidence.ok
          ? { runs: taskEvidence.value.runs.map((run) => ({
              run_id: run.run_id,
              outcome: run.outcome,
              start_commit: run.start_commit,
              result_commit: run.result_commit,
            })) }
          : unknownSource("evidence", taskEvidence.error),
      provenance: "recorded and deterministically derived project data only",
    },
  };
}
