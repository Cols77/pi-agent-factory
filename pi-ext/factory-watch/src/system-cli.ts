import { runJsonCli, runJsonCliAsync } from "./cli-runner.js";
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

// The presentation router lives in its own package (Inc 5, spec §22-§24), so
// ``eng_present`` invokes ``factory.presentation`` rather than ``factory.system``.
export function buildPresentationCommand(sub: string[]): { bin: string; args: string[] } {
  return { bin: "uv", args: ["run", "python", "-m", "factory.presentation", ...sub] };
}

// Mirrors `factory.system brief --json` ... this file renders, it never
// interprets -- see the top of this file.

// SP-B performance (2026-08-13, extended): one combined scope-navigation
// payload. `factory.system dossier --scope <ref> --json` computes
// brief/matrix/timeline strictly (a failure fails the dossier, exactly as a
// failing individual endpoint fails a scope load today) and guide/vcycle/
// validation best-effort (null + error text, degrading only their own tab).
// `brief` is typed as `unknown`: for a `feat:` scope it is the trace-backed
// dossier (query_feature_context), not a SystemBrief -- the browser picks the
// renderer by scope kind, exactly as it does for `/api/system/brief` today.
export interface SystemDossier {
  scope: { kind: string; ref: string };
  brief: unknown;
  matrix: SystemMatrix;
  timeline: SystemTimeline;
  guide: SystemGuide | null;
  guide_error: string | null;
  vcycle: SystemVcycle | null;
  vcycle_error: string | null;
  validation: SystemValidation | null;
  validation_error: string | null;
}

export function loadSystemDossier(cwd: string, scope: string): CliResult<SystemDossier> {
  const cmd = buildSystemCommand(["dossier", "--scope", scope, "--json"]);
  return runJsonCli<SystemDossier>(cwd, cmd.bin, cmd.args);
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

// Mirrors `factory.system health --json` (the composed landing projection).
// This file renders it, never recomputes it -- health, coverage, ordering and
// readiness all come from Python exactly as `query_health` composed them.
export interface SystemHealthClass {
  name: string;
  satisfied: number;
  expected: number;
  exempt: number;
}

export interface SystemHealthBundle {
  id: string;
  label: string;
  readiness: string;
  readiness_counts: Record<string, number>;
  members: number;
}

export interface SystemHealth {
  health: {
    classes: SystemHealthClass[];
    satisfied: number;
    expected: number;
    percent: number;
    dangling: number;
    deferred: number;
    proposed: number;
  };
  coverage: {
    total: number;
    bundled: number;
    unbundled: number;
    kinds: Array<{ kind: string; total: number; bundled: number; unbundled: number }>;
  };
  bundles: SystemHealthBundle[];
  unbundled: Record<string, string[]>;
  ordering_available: boolean;
  sr_listed: boolean;
  degraded: string[];
}

export function loadSystemHealth(cwd: string): CliResult<SystemHealth> {
  const cmd = buildSystemCommand(["health", "--json"]);
  return runJsonCli<SystemHealth>(cwd, cmd.bin, cmd.args);
}

export function loadSystemHealthAsync(cwd: string): Promise<CliResult<SystemHealth>> {
  const cmd = buildSystemCommand(["health", "--json"]);
  return runJsonCliAsync<SystemHealth>(cwd, cmd.bin, cmd.args);
}

// SP-B Task 9 -- working traversal. Mirrors `factory.system.traversal --json`
// (requirement -> satisfying tasks -> design decisions -> changed files).
export interface SystemTraversal {
  requirement: string[];
  tasks: string[];
  design: string[];
  files: string[];
}

export function loadSystemTraversal(cwd: string, scope: string): CliResult<SystemTraversal> {
  const cmd = buildSystemCommand(["traversal", "--json", "--scope", scope]);
  return runJsonCli<SystemTraversal>(cwd, cmd.bin, cmd.args);
}

export function loadSystemTraversalAsync(cwd: string, scope: string): Promise<CliResult<SystemTraversal>> {
  const cmd = buildSystemCommand(["traversal", "--json", "--scope", scope]);
  return runJsonCliAsync<SystemTraversal>(cwd, cmd.bin, cmd.args);
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
  dod: string[];
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

export interface StoryPlanSection {
  plan_path: string;
  heading: string;
  body: string;
}

export interface SystemStory {
  scope: StoryScopeRef;
  task: StoryTask;
  runs: StoryRun[];
  requirements: string[];
  // The `### Task N:` section of the task's source plan -- the steps the
  // implementer worked from. Null when the task declares no source_plan, the
  // plan is unreadable, or no section matches.
  plan_section: StoryPlanSection | null;
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

// Mirrors `factory.system labels --json`. Titles and descriptions are read
// from recorded fields in Python; this file renders them and never derives a
// description, a title, or a ref.
export interface SystemLabelEntry {
  ref: string;
  id: string;
  kind: string;
  title: string;
  description: string | null;
  description_source: string | null;
  deferral_reason: string | null;
  status: string | null;
  relations: Record<string, string[]>;
  path: string;
  scope_href: string | null;
}

export interface SystemLabels {
  labels: Record<string, SystemLabelEntry>;
  aliases: Record<string, string>;
  degraded: string[];
}

export function loadSystemLabelsAsync(cwd: string): Promise<CliResult<SystemLabels>> {
  const cmd = buildSystemCommand(["labels", "--json"]);
  return runJsonCliAsync<SystemLabels>(cwd, cmd.bin, cmd.args);
}

// ---------------------------------------------------------------------------
// Increment 4 -- Engineering Context agent surface (D1: pi-ext tools).
//
// These loaders mirror `factory.system` subcommands that back the deterministic
// `eng_*` agent tools. As everywhere in this file: this layer renders JSON the
// Python side already computed, it never re-derives freshness, ordering, or
// provenance. The eng_* tools call one of these and format the payload.
// ---------------------------------------------------------------------------

export interface SystemVcycleNode {
  id: string;
  kind: string;
}

export interface SystemVcycleSide {
  label: string;
  nodes: SystemVcycleNode[];
}

export interface SystemVcycle {
  scope: { kind: "feat" | "sr"; ref: string };
  vcycle: {
    anchor: string;
    definition: SystemVcycleSide[];
    verification: SystemVcycleSide[];
    goals: SystemVcycleNode[];
    metrics: SystemVcycleNode[];
  };
}

export function loadSystemVcycle(cwd: string, scope: string): CliResult<SystemVcycle> {
  const cmd = buildSystemCommand(["vcycle", "--scope", scope, "--json"]);
  return runJsonCli<SystemVcycle>(cwd, cmd.bin, cmd.args);
}

export interface SystemValidation {
  scope: { kind: string; ref: string };
  validation: {
    id: string;
    raw_state: string;
    stale: boolean;
    error: string | null;
    goal_state: string | null;
    goals: { id: string; state: string }[];
    runs: string[];
    metrics: string[];
  };
}

export function loadSystemValidation(cwd: string, scope: string): CliResult<SystemValidation> {
  const cmd = buildSystemCommand(["validation", "--scope", scope, "--json"]);
  return runJsonCli<SystemValidation>(cwd, cmd.bin, cmd.args);
}

export interface SystemDiagram {
  id: string;
  title: string;
  diagram_path: string | null;
  errors: string[];
}

export function loadSystemDiagram(cwd: string, diagramId: string): CliResult<SystemDiagram> {
  const cmd = buildSystemCommand(["diagram", diagramId, "--json"]);
  return runJsonCli<SystemDiagram>(cwd, cmd.bin, cmd.args);
}

export interface SimRun {
  run: string;
  experiment: string;
  feature: string;
  requirements: string[];
  goals: string[];
  commit: string | null;
  result: string | null;
  scope_errors: string[];
  metrics?: Record<string, number>;
  recording?: string | null;
  recorded_ts?: string | null;
}

export interface SimLatest {
  run: string;
  experiment: string;
  feature: string;
  requirements: string[];
  goals: string[];
  commit: string | null;
  result: string | null;
  scope_errors: string[];
}

export interface SimMetricEntry {
  run: string;
  commit: string | null;
  value: number;
  ts: string | null;
}

export interface SimGoalEvidence {
  goal: string;
  runs: SimRun[];
}

export function loadSystemSimRun(cwd: string, runId: string): CliResult<SimRun> {
  const cmd = buildSystemCommand(["sim", "run", runId, "--json"]);
  return runJsonCli<SimRun>(cwd, cmd.bin, cmd.args);
}

export function loadSystemSimLatest(cwd: string, feature: string): CliResult<SimLatest> {
  const cmd = buildSystemCommand(["sim", "latest", "--feature", feature, "--json"]);
  return runJsonCli<SimLatest>(cwd, cmd.bin, cmd.args);
}

export function loadSystemSimFailure(cwd: string, feature: string): CliResult<SimLatest> {
  const cmd = buildSystemCommand(["sim", "failure", "--feature", feature, "--json"]);
  return runJsonCli<SimLatest>(cwd, cmd.bin, cmd.args);
}

export function loadSystemSimMetric(cwd: string, metricId: string): CliResult<SimMetricEntry[]> {
  const cmd = buildSystemCommand(["sim", "metric", "--metric", metricId, "--json"]);
  return runJsonCli<SimMetricEntry[]>(cwd, cmd.bin, cmd.args);
}

export function loadSystemSimGoalEvidence(cwd: string, goalId: string): CliResult<SimGoalEvidence> {
  const cmd = buildSystemCommand(["sim", "goal-evidence", "--goal", goalId, "--json"]);
  return runJsonCli<SimGoalEvidence>(cwd, cmd.bin, cmd.args);
}

export interface SystemGoal {
  id: string;
  title: string;
  state: string;
  version: number;
  feature: string[];
  requirements: string[];
  metric: Record<string, unknown> | null;
  target: string;
  evidence: unknown[];
  history: unknown[];
  scope_errors: string[];
}

export interface SystemGoalsList {
  scope: string;
  goals: Array<{
    id: string;
    title: string;
    state: string;
    feature: string[];
    requirements: string[];
    metric: Record<string, unknown> | null;
    target: string;
    evidence: unknown[];
    history: unknown[];
  }>;
}

export function loadSystemGoal(cwd: string, goalId: string): CliResult<SystemGoal> {
  const cmd = buildSystemCommand(["goal", "show", goalId, "--json"]);
  return runJsonCli<SystemGoal>(cwd, cmd.bin, cmd.args);
}

export interface GoalEvaluate {
  evaluated: boolean;
  goal_id: string;
  state?: string;
  transition: { from: string; to: string; legal: boolean } | null;
  derived?: {
    state: string;
    passed: boolean;
    value: number;
    target: number | null;
    operator: string | null;
    run: string | null;
    commit: string | null;
    blocked_reason: string | null;
  };
  note?: string;
}

export function loadSystemGoalEvaluate(cwd: string, goalId: string): CliResult<GoalEvaluate> {
  const cmd = buildSystemCommand(["goal", "evaluate", goalId, "--json"]);
  return runJsonCli<GoalEvaluate>(cwd, cmd.bin, cmd.args);
}

export interface PresentResult {
  artifact: string;
  focus: string | null;
  level: string;
  intent: { artifact: string; focus: string | null };
  resolution: string;
  adapter: string | null;
  target: string | null;
  note: string;
}

export function loadSystemPresent(cwd: string, artifact: string, focus?: string): CliResult<PresentResult> {
  const args = focus ? ["present", artifact, "--focus", focus, "--json"] : ["present", artifact, "--json"];
  const cmd = buildPresentationCommand(args);
  return runJsonCli<PresentResult>(cwd, cmd.bin, cmd.args);
}

export function loadSystemGoalsList(cwd: string, scope: string): CliResult<SystemGoalsList> {
  const cmd = buildSystemCommand(["goal", "list", "--scope", scope, "--json"]);
  return runJsonCli<SystemGoalsList>(cwd, cmd.bin, cmd.args);
}

