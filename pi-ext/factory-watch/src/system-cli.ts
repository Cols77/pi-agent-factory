import { runJsonCli } from "./cli-runner.js";
import type { CliResult } from "./cli-runner.js";

// Types below mirror src/factory/schemas/system_response.schema.json (and the
// sibling system_bundle/system_matrix_row/system_timeline_event schemas)
// exactly -- this file renders, it never interprets. If a field here doesn't
// match the schema, the schema is the one that's right.

export type SystemScopeKind = "bundle" | "sr";

export interface SystemScopeRef {
  kind: SystemScopeKind;
  ref: string;
}

export type CitationKind =
  | "manifest"
  | "task"
  | "requirement"
  | "validation"
  | "review"
  | "decision"
  | "trace"
  | "bundle";

export interface SystemCitation {
  kind: CitationKind;
  path: string;
  sha256: string | null;
  anchor: string | null;
}

export interface SystemSpan {
  text: string;
  citation_index: number;
}

export type FreshnessState = "fresh" | "stale" | "degraded" | "n/a";

export interface FreshnessDependency {
  name: string;
  expected: string | null;
  actual: string | null;
}

export interface SystemFreshness {
  state: FreshnessState;
  reason: string | null;
  dependencies: FreshnessDependency[];
}

export type ClaimClass = "recorded" | "derived" | "synthesized" | "missing";

export interface SystemClaim {
  kind: ClaimClass;
  text: string;
  citations: SystemCitation[];
  spans: SystemSpan[];
  freshness: SystemFreshness;
}

export interface SystemBrief {
  scope: SystemScopeRef;
  claims: SystemClaim[];
  degraded?: boolean;
  degraded_reasons?: string[];
}

export interface MatrixSubjectRef {
  kind: "sr";
  ref: string;
}

export type MatrixStatus = "passed" | "failed" | "error" | "blocked" | "never-run" | "unknown";

export interface ValidationMatrixRow {
  subject: MatrixSubjectRef;
  status: MatrixStatus;
  evidence: string[];
  freshness: SystemFreshness;
  summary: string;
}

export interface SystemMatrix {
  scope: SystemScopeRef;
  rows: ValidationMatrixRow[];
}

export interface TimelineSubjectRef {
  kind: "task" | "sr" | "run" | "manifest";
  ref: string;
}

export type TimelineActor =
  | "human"
  | "dev"
  | "review"
  | "validation"
  | "orchestrator"
  | "unknown"
  | "not-recorded";

export type TimelineAction =
  | "approved"
  | "rejected"
  | "validated"
  | "repaired"
  | "published"
  | "stopped"
  | "not-recorded";

export interface DecisionTimelineEvent {
  at: string | null;
  sequence: number | null;
  actor: TimelineActor;
  action: TimelineAction;
  subject: TimelineSubjectRef;
  citation: SystemCitation;
  freshness: SystemFreshness;
}

export interface SystemTimeline {
  scope: SystemScopeRef;
  events: DecisionTimelineEvent[];
  degraded: boolean;
  degraded_reasons: string[];
}

export interface BundleLoadError {
  path: string;
  bundle_id: string;
  error: string;
}

export interface SystemScopeList {
  scopes: SystemScopeRef[];
  errors: BundleLoadError[];
}

// Matches `SystemGuide` (design SS5.3): a scope plus an ordered list of
// claim sections. Each section is a full `SystemClaim` -- either
// synthesized prose with verified verbatim spans, or recorded bullets
// (design SS4.4's collapse predicate). This file never decides which; it
// only renders whichever `kind` Python already chose.
export interface SystemGuide {
  scope: SystemScopeRef;
  sections: SystemClaim[];
}

// Mirrors trace-cli.ts:75's buildTraceCommand exactly -- there is no
// `factory` console script in this repo (design SS5.1, SS2 item 12); every
// subpackage is invoked as `uv run python -m factory.<x>`.
export function buildSystemCommand(sub: string[]): { bin: string; args: string[] } {
  return { bin: "uv", args: ["run", "python", "-m", "factory.system", ...sub] };
}

export function loadSystemScopes(cwd: string): CliResult<SystemScopeList> {
  const cmd = buildSystemCommand(["scope", "--json"]);
  return runJsonCli<SystemScopeList>(cwd, cmd.bin, cmd.args);
}

export function loadSystemBriefing(cwd: string, scope: string): CliResult<SystemBrief> {
  const cmd = buildSystemCommand(["brief", "--scope", scope, "--json"]);
  return runJsonCli<SystemBrief>(cwd, cmd.bin, cmd.args);
}

export function loadSystemMatrix(cwd: string, scope: string): CliResult<SystemMatrix> {
  const cmd = buildSystemCommand(["matrix", "--scope", scope, "--json"]);
  return runJsonCli<SystemMatrix>(cwd, cmd.bin, cmd.args);
}

export function loadSystemTimeline(cwd: string, scope: string): CliResult<SystemTimeline> {
  const cmd = buildSystemCommand(["timeline", "--scope", scope, "--json"]);
  return runJsonCli<SystemTimeline>(cwd, cmd.bin, cmd.args);
}

export function loadSystemGuide(cwd: string, scope: string): CliResult<SystemGuide> {
  const cmd = buildSystemCommand(["guide", "--scope", scope, "--json"]);
  return runJsonCli<SystemGuide>(cwd, cmd.bin, cmd.args);
}
