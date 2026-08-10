import type { TraceEdgeKind, TraceGraph, TraceNode, TraceNodeKind } from "./trace-cli.js";

export interface ReviewChainNode {
  id: string;
  kind: TraceNodeKind;
  title: string;
  path: string;
  // How many FURTHER edges of the same kind left the same source. A task may
  // declare several `satisfies` and a plan may reference several specs, but the
  // chain shows one line per hop. Without this count the reviewer would be
  // shown a partial chain with no sign anything was omitted -- the exact
  // failure this pane exists to prevent. 0 in the ordinary single-edge case.
  alternatives: number;
}

export interface IntentChain {
  chain: ReviewChainNode[];
  stopsAt: string | null;
}

// The order hops are reported as missing. Fixed rather than derived from the
// display order, so `stopsAt` names a cause and not merely the topmost blank
// row: an absent `upstream` is only interesting once `satisfies` resolved.
const HOP_PRECEDENCE = ["satisfies", "upstream", "source_plan", "spec_ref"] as const;

interface Hop {
  node: TraceNode | undefined;
  alternatives: number;
}

function toChainNode(node: TraceNode, alternatives: number): ReviewChainNode {
  return { id: node.id, kind: node.kind, title: node.title, path: node.path, alternatives };
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

  const NONE: Hop = { node: undefined, alternatives: 0 };

  // Collect every candidate rather than taking the first: the count of the ones
  // not shown is what the chain reports as "+N more".
  const hop = (src: string, kind: TraceEdgeKind): Hop => {
    const edges = graph.edges.filter((each) => each.src === src && each.kind === kind);
    const first = edges[0];
    return {
      node: first === undefined ? undefined : byId.get(first.dst),
      alternatives: Math.max(0, edges.length - 1),
    };
  };

  const sr = hop(taskId, "satisfies");
  const br = sr.node === undefined ? NONE : hop(sr.node.id, "upstream");
  const plan = hop(taskId, "source_plan");
  const spec = plan.node === undefined ? NONE : hop(plan.node.id, "spec_ref");

  const resolved: Record<(typeof HOP_PRECEDENCE)[number], Hop> = {
    satisfies: sr, upstream: br, source_plan: plan, spec_ref: spec,
  };
  const stopsAt = HOP_PRECEDENCE.find((hopName) => resolved[hopName].node === undefined) ?? null;

  // The task itself was not reached through an edge, so it has no alternatives.
  const chain = [br, sr, spec, plan, { node: task, alternatives: 0 }]
    .filter((each): each is { node: TraceNode; alternatives: number } => each.node !== undefined)
    .map((each) => toChainNode(each.node, each.alternatives));
  return { chain, stopsAt };
}
