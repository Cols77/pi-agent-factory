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
  | "bundle"
  | "session";

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

// Mirrors system_claim.schema.json's optional `implementation_summary`
// (Task 5, design SS4.3): attached only to a bundle `task:` member claim --
// run count, latest outcome, changed-file count, and latest validation
// verdict, computed entirely in Python. `changed_file_count` is `null`
// (never `0`) whenever nothing was recorded, so "no runs yet" is never
// confused with "changed nothing" -- the rendering side must preserve that
// distinction, not flatten it.
export interface SystemClaimImplementationSummary {
  runs: number;
  latest_outcome: string | null;
  changed_file_count: number | null;
  latest_validation: string | null;
}

export interface SystemClaim {
  kind: ClaimClass;
  text: string;
  citations: SystemCitation[];
  spans: SystemSpan[];
  freshness: SystemFreshness;
  implementation_summary?: SystemClaimImplementationSummary;
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

// The rest of this file mirrors `factory.system.story.query_story` /
// `factory.system.reverse.query_reverse` (increment B, V-cycle) exactly --
// same discipline as every type above: this file renders, it never
// interprets.

export interface StoryScopeRef {
  kind: "task";
  ref: string;
}

export interface StoryTask {
  id: string;
  title: string;
  status: string;
}

// A claim (kind/text/citations/spans/freshness) plus `changed_files`:
// present (a list, possibly empty) only when recorded by a real evidence
// manifest; `null` for a session-only run, which never captures changed
// files.
export interface StoryImplementation extends SystemClaim {
  changed_files: string[] | null;
}

// One recorded run of a task's story, sourced either from a durable
// evidence manifest (`source: "manifest"`) or, when no manifest exists for
// that run, from a session record (`source: "session"`, `implementation`
// always missing/n-a). `start_commit`/`result_commit` are `null` for a
// session-sourced run -- a session record never captures a commit range.
export interface StoryRun {
  run_id: string;
  source: "manifest" | "session";
  outcome: string;
  started_at: string | null;
  ended_at: string | null;
  start_commit: string | null;
  result_commit: string | null;
  implementation: StoryImplementation;
  citation: SystemCitation;
}

export interface SystemStory {
  scope: StoryScopeRef;
  task: StoryTask;
  runs: StoryRun[];
  requirements: string[];
  degraded: boolean;
  degraded_reasons: string[];
}

export interface ReverseScopeRef {
  kind: "file";
  ref: string;
}

// The evidence manifest run that recorded the walked file in its
// `implementation.changed_files`. Always sourced from a durable evidence
// manifest -- session records carry no changed files and cannot
// participate in a file-anchored walk, so unlike `StoryRun` there is no
// `source` field here.
export interface ReverseRun {
  run_id: string;
  outcome: string;
  started_at: string | null;
  ended_at: string | null;
  start_commit: string | null;
  result_commit: string | null;
  implementation: StoryImplementation;
  citation: SystemCitation;
}

// The resolved task record a path's `task` hop points at, or `null` when
// the matched run's `task_id` does not resolve in the ledger
// (`stops_at: "task"`).
export type ReverseTask = StoryTask | null;

// One walked path from the file back to a requirement: run -> task ->
// satisfies. `stops_at` names the first hop that did not resolve
// (`"task"` or `"satisfies"`), or `null` when the chain completes.
export interface ReversePath {
  file: string;
  run: ReverseRun;
  task: ReverseTask;
  requirements: string[];
  stops_at: "task" | "satisfies" | null;
}

export interface SystemReverse {
  scope: ReverseScopeRef;
  paths: ReversePath[];
  degraded: boolean;
  degraded_reasons: string[];
}

export function loadSystemStory(cwd: string, scope: string): CliResult<SystemStory> {
  const cmd = buildSystemCommand(["story", "--scope", scope, "--json"]);
  return runJsonCli<SystemStory>(cwd, cmd.bin, cmd.args);
}

export function loadSystemReverse(cwd: string, scope: string): CliResult<SystemReverse> {
  const cmd = buildSystemCommand(["reverse", "--scope", scope, "--json"]);
  return runJsonCli<SystemReverse>(cwd, cmd.bin, cmd.args);
}
