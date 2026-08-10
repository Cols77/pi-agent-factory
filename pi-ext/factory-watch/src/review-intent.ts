import type { TraceEdgeKind, TraceGraph, TraceNode, TraceNodeKind } from "./trace-cli.js";

export interface ReviewChainNode {
  id: string;
  kind: TraceNodeKind;
  title: string;
  path: string;
}

export interface IntentChain {
  chain: ReviewChainNode[];
  stopsAt: string | null;
}

// The order hops are reported as missing. Fixed rather than derived from the
// display order, so `stopsAt` names a cause and not merely the topmost blank
// row: an absent `upstream` is only interesting once `satisfies` resolved.
const HOP_PRECEDENCE = ["satisfies", "upstream", "source_plan", "spec_ref"] as const;

function toChainNode(node: TraceNode): ReviewChainNode {
  return { id: node.id, kind: node.kind, title: node.title, path: node.path };
}

/** Walk the two branches `factory.trace.model.extract_edges` actually writes:
 *
 *     task --satisfies--> SR --upstream--> BR
 *     task --source_plan--> plan --spec_ref--> spec
 *
 * Returns the resolved hops ordered BR -> SR -> spec -> plan -> task, and the
 * first hop that did not resolve. An edge whose destination has no node is
 * unresolved: the walk never guesses past a hop it could not follow, it stops
 * and says where -- the discipline `factory.system.reverse` states for its own
 * `stops_at`. Pure: no I/O, the graph is already loaded.
 */
export function walkIntentChain(graph: TraceGraph, taskId: string): IntentChain {
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const task = byId.get(taskId);
  if (task === undefined) return { chain: [], stopsAt: "task" };

  const hop = (src: string, kind: TraceEdgeKind): TraceNode | undefined => {
    const edge = graph.edges.find((each) => each.src === src && each.kind === kind);
    return edge === undefined ? undefined : byId.get(edge.dst);
  };

  const sr = hop(taskId, "satisfies");
  const br = sr === undefined ? undefined : hop(sr.id, "upstream");
  const plan = hop(taskId, "source_plan");
  const spec = plan === undefined ? undefined : hop(plan.id, "spec_ref");

  const resolved: Record<(typeof HOP_PRECEDENCE)[number], TraceNode | undefined> = {
    satisfies: sr, upstream: br, source_plan: plan, spec_ref: spec,
  };
  const stopsAt = HOP_PRECEDENCE.find((hopName) => resolved[hopName] === undefined) ?? null;

  const chain = [br, sr, spec, plan, task]
    .filter((node): node is TraceNode => node !== undefined)
    .map(toChainNode);
  return { chain, stopsAt };
}
