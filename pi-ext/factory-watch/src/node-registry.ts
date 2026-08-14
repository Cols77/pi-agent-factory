// Single source of truth for the pipeline node graph, consumed by both the
// mission-control dashboard and the transition watcher. The on-disk JSON
// (pi-ext/factory-watch/node-registry.json) is the authoritative copy so the
// same contract can later be read by the Python orchestrator (status.py) to
// drop its own node literals. A missing/corrupt file degrades to a built-in
// fallback that still renders every known node, so the extension never crashes
// on a bad registry.
//
// This addresses the original brittle-wiring bug: the node graph used to be
// duplicated as literals in status-format.ts (NODE_LABELS, STAGE_ORDER),
// mission-control-dashboard.ts (STAGE_ORDER, AGENT_NODES) and index.ts (widget
// detection). Adding a node meant editing ~8 spots across two languages; any
// miss silently dropped a surface (the grill never rendered). Here "add a node"
// is one line in node-registry.json.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export interface NodeReg {
  id: string;
  label: string;
  kind: "agent" | "gate" | "other";
  interactive: boolean;
}

export interface NodeRegistry {
  schema: number;
  order: string[];
  nodes: NodeReg[];
}

const REGISTRY_PATH = join(dirname(fileURLToPath(import.meta.url)), "..", "node-registry.json");

// eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
function fallbackRegistry(): NodeRegistry {
  return {
    schema: 1,
    order: [
      "context-gather",
      "grill",
      "dev",
      "validation",
      "review",
      "human-review",
      "session-review",
    ],
    nodes: [
      { id: "context-gather", label: "context-gatherer", kind: "agent", interactive: false },
      { id: "grill", label: "grill", kind: "gate", interactive: true },
      { id: "dev", label: "developer", kind: "agent", interactive: false },
      { id: "validation", label: "validation", kind: "gate", interactive: false },
      { id: "review", label: "reviewer", kind: "agent", interactive: false },
      { id: "human-review", label: "human-review", kind: "gate", interactive: true },
      { id: "session-review", label: "session-reviewer", kind: "agent", interactive: false },
    ],
  };
}

let cache: NodeRegistry | null = null;

export function loadNodeRegistry(): NodeRegistry {
  if (cache) return cache;
  try {
    const parsed = JSON.parse(readFileSync(REGISTRY_PATH, "utf-8")) as NodeRegistry;
    if (parsed && Array.isArray(parsed.order) && Array.isArray(parsed.nodes) && parsed.nodes.length > 0) {
      cache = parsed;
      return cache;
    }
  } catch {
    // malformed/missing -> fall through to fallback
  }
  cache = fallbackRegistry();
  return cache;
}

export function stageOrder(): string[] {
  return loadNodeRegistry().order;
}

export function labelForNode(id: string): string {
  const node = loadNodeRegistry().nodes.find((n) => n.id === id);
  return node ? node.label : id;
}

export function isAgentNode(id: string): boolean {
  const node = loadNodeRegistry().nodes.find((n) => n.id === id);
  return node ? node.kind === "agent" : false;
}

export function isInteractiveNode(id: string): boolean {
  const node = loadNodeRegistry().nodes.find((n) => n.id === id);
  return node ? node.interactive === true : false;
}
