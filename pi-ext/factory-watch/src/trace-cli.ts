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
  // Requirements accepted in substance whose binding is undecided. Reported on
  // its own line: they are out of the "SR validated" denominator, not deferred.
  proposed: number;
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

export interface TraceCandidate {
  id: string;
  title: string;
  summary: string;
  shared_terms: string[];
  score: number;
}

export interface TracePendingGap {
  node_id: string;
  kind: string;
  detail: string;
}

export interface TraceProposal {
  gap: TraceGap;
  node_title: string;
  node_excerpt: string;
  pending_total: number;
  candidates: TraceCandidate[];
  // The whole pending set, so a hardcoded kind order never decides what the
  // agent may consider. Visibility is not commit granularity.
  pending: TracePendingGap[];
}

export interface TraceRunResult {
  ok: boolean;
  status: number;
  stdout: string;
  stderr: string;
}

export interface TraceCheckResult {
  ok: boolean;
  pending: number;
  deferred: number;
  exempt: number;
  report: string;
}

export function runTrace(cwd: string, sub: string[]): TraceRunResult {
  const cmd = buildTraceCommand(sub);
  const result = spawnSync(cmd.bin, cmd.args, {
    cwd,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) {
    return {
      ok: false,
      status: -1,
      stdout: "",
      stderr: String(result.error.message ?? result.error),
    };
  }
  const status = result.status ?? -1;
  return { ok: status === 0, status, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

export function loadNextGap(
  cwd: string,
  nodeId?: string,
): { ok: true; proposal: TraceProposal | null } | { ok: false; error: string } {
  const sub = nodeId ? ["next", "--json", "--node-id", nodeId] : ["next", "--json"];
  const result = runTrace(cwd, sub);
  if (!result.ok) {
    return { ok: false, error: result.stderr || result.stdout || `exited ${result.status}` };
  }
  try {
    const parsed = JSON.parse(result.stdout) as { gap: unknown };
    if (parsed.gap === null) return { ok: true, proposal: null };
    return { ok: true, proposal: parsed as unknown as TraceProposal };
  } catch (err) {
    return { ok: false, error: `could not parse factory trace next: ${String(err)}` };
  }
}

const COUNTS_RE = /(\d+) pending, (\d+) deferred, (\d+) exempt/;

export function runTraceCheck(cwd: string): TraceCheckResult {
  const result = runTrace(cwd, ["check"]);
  const report = result.stdout || result.stderr;
  const match = COUNTS_RE.exec(report);
  return {
    // The exit code is authoritative; the parsed counts are for display only, so
    // a formatting change can never turn a failing gate into a passing one.
    ok: result.status === 0,
    pending: match ? Number(match[1]) : 0,
    deferred: match ? Number(match[2]) : 0,
    exempt: match ? Number(match[3]) : 0,
    report,
  };
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
