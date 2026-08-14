// Transition detection for the mission-control watcher (pure, unit-testable).
//
// The mission-control loop is pull-based: it refreshes a displayed record but
// never acts on a *change*. Blocking conditions (grill, human-review) therefore
// never got *pushed* to an already-open mission control — the grill was only
// offered at open time (a one-shot call before the loop), so a grill that
// appeared after open was silently missed and required /factory-watch. This
// module turns the status poll into a transition signal the watcher can act on.

import type { StatusRecord } from "./status-format.js";
import type { NodeRegistry } from "./node-registry.js";
import { isInteractiveNode } from "./node-registry.js";

export interface NodeState {
  node: string;
  state: string;
}

/** Flatten a record's pipeline into [node, state] pairs (order preserved). */
export function snapshotStates(record: StatusRecord | null): NodeState[] {
  return (record?.pipeline ?? []).map((e) => ({ node: e.node, state: e.node_state }));
}

/**
 * Return the interactive nodes that newly entered `blocked` between `prev` and
 * `next`. Nag-free: a node already blocked in `prev` is not re-reported (the
 * caller guards re-offering with `offeredGrillFor`/result-file on top, but the
 * diff itself is self-guarding). Ignores nodes not present in `next` and
 * non-interactive nodes.
 */
export function diffBlocked(prev: NodeState[], next: NodeState[], registry: NodeRegistry): NodeState[] {
  const prevMap = new Map(prev.map((s) => [s.node, s.state]));
  const nextMap = new Map(next.map((s) => [s.node, s.state]));
  const out: NodeState[] = [];
  for (const id of registry.order) {
    if (!isInteractiveNode(id)) continue;
    const nextState = nextMap.get(id);
    if (nextState === "blocked" && prevMap.get(id) !== "blocked") {
      out.push({ node: id, state: nextState });
    }
  }
  return out;
}
