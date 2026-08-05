import { spawnSync } from "node:child_process";

export type TraceNodeKind = "br" | "sr" | "spec" | "plan" | "task";
export type TraceEdgeKind = "source_plan" | "satisfies" | "upstream" | "spec_ref";
export type TraceDisposition = "pending" | "exempt" | "deferred";
export type TraceValidationState = "passed" | "failed" | "error" | "never_validated";

export interface TraceNode {
  id: string;
  kind: TraceNodeKind;
  title: string;
  path: string;
  exempt: boolean;
  deferred: string | null;
}

export interface TraceEdge {
  src: string;
  dst: string;
  kind: TraceEdgeKind;
}

export interface TraceGap {
  node_id: string;
  kind: string;
  detail: string;
  disposition: TraceDisposition;
}

export interface TraceValidation {
  id: string;
  state: TraceValidationState;
  stale: boolean;
  metric: string | null;
  value: number | null;
  assert_expr: string | null;
  trials: number | null;
  declared_trials: number | null;
  artifacts: string[];
  error: string | null;
}

export interface TraceHealthClass {
  name: string;
  satisfied: number;
  expected: number;
  exempt: number;
}

export interface TraceHealth {
  percent: number;
  satisfied: number;
  expected: number;
  dangling: number;
  deferred: number;
  classes: TraceHealthClass[];
}

export interface TraceGraph {
  nodes: TraceNode[];
  edges: TraceEdge[];
  gaps: TraceGap[];
  validation: Record<string, TraceValidation>;
  health: TraceHealth;
}

export type TraceResult<T> = { ok: true; graph: T } | { ok: false; error: string };

// Mirrors process-control.ts:13 -- the established way this extension reaches
// the Python side.
export function buildTraceCommand(sub: string[]): { bin: string; args: string[] } {
  return { bin: "uv", args: ["run", "python", "-m", "factory.trace", ...sub] };
}

export function loadTraceGraph(cwd: string): TraceResult<TraceGraph> {
  const cmd = buildTraceCommand(["graph", "--json"]);
  const result = spawnSync(cmd.bin, cmd.args, {
    cwd,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) {
    return { ok: false, error: String(result.error.message ?? result.error) };
  }
  if (result.status !== 0) {
    return {
      ok: false,
      error: `factory trace exited ${result.status}: ${(result.stderr ?? "").trim()}`,
    };
  }
  try {
    return { ok: true, graph: JSON.parse(result.stdout) as TraceGraph };
  } catch (err) {
    return { ok: false, error: `could not parse factory trace output: ${String(err)}` };
  }
}
