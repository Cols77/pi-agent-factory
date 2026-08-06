import { spawnSync } from "node:child_process";

export type CliResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: string; status: number };

export interface BlobRef {
  sha256: string;
  size: number;
  media_type: string;
  local?: boolean;
  publication?: "local" | "queued" | "published" | "failed";
  uri?: string | null;
}

export interface EvidenceReview {
  reviewed_at?: string;
  decision?: string;
  annotations?: Array<{
    file?: string;
    line?: number | null;
    severity?: string | null;
    body?: string;
  }>;
  reviewed_files?: string[];
  patch?: BlobRef;
  guide?: BlobRef;
  diff_error?: string | null;
}

export interface FreshnessIssue {
  code: string;
  severity: "integrity" | "blocking" | "warning";
  subject: string;
  dependency: string;
  detail: string;
  repair: string | null;
}

export interface ReconcileItem {
  kind: string;
  subject: string;
  detail: string;
  repairable: boolean;
  source: string;
}

export interface RecoveryAssessment {
  state: "resumable" | "inspect-only" | "conflict" | "complete";
  reasons: string[];
  actions: string[];
}

export interface RunState {
  checkpoint: Record<string, unknown> | null;
  assessment: RecoveryAssessment | null;
}

export interface EvidenceRun {
  schema_version: number;
  run_id: string;
  task_id: string;
  started_at: string;
  ended_at: string;
  start_commit: string;
  result_commit: string;
  outcome: "completed" | "rejected" | "escalated";
  implementation: { changed_files: string[]; patch: BlobRef };
  validation: Array<Record<string, unknown>>;
  reviews: EvidenceReview[];
  decisions: Array<Record<string, unknown>>;
  publication: { state: "local" | "queued" | "published" | "failed"; errors: string[] };
}

function runJson<T>(
  cwd: string,
  module: string,
  args: string[],
  acceptedStatuses: number[] = [0],
): CliResult<T> {
  const result = spawnSync(
    "uv",
    ["run", "python", "-m", module, ...args, "--repo", cwd, "--json"],
    { cwd, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 },
  );
  if (result.error) {
    return { ok: false, status: -1, error: result.error.message };
  }
  const status = result.status ?? -1;
  if (!acceptedStatuses.includes(status)) {
    return {
      ok: false,
      status,
      error: (result.stderr || result.stdout || `factory evidence exited ${status}`).trim(),
    };
  }
  try {
    return { ok: true, value: JSON.parse(result.stdout) as T };
  } catch (err) {
    return { ok: false, status, error: `could not parse ${module} output: ${String(err)}` };
  }
}

export function loadTaskEvidence(cwd: string, taskId: string): CliResult<{ runs: EvidenceRun[] }> {
  return runJson(cwd, "factory.evidence", ["task", taskId]);
}

export function loadRunEvidence(cwd: string, runId: string): CliResult<EvidenceRun> {
  return runJson(cwd, "factory.evidence", ["run", runId]);
}

export function listEvidence(cwd: string): CliResult<{ runs: EvidenceRun[] }> {
  return runJson(cwd, "factory.evidence", ["list"]);
}

export function runPreflight(
  cwd: string,
  taskId: string,
): CliResult<{ ok: boolean; issues: FreshnessIssue[] }> {
  return runJson(cwd, "factory.preflight", ["--task", taskId], [0, 2, 3]);
}

export function runReconcile(
  cwd: string,
  taskId?: string,
): CliResult<{ items: ReconcileItem[] }> {
  const args = ["reconcile"];
  if (taskId) args.push("--task", taskId);
  return runJson(cwd, "factory.evidence", args, [0, 1]);
}

export function loadCurrentRun(cwd: string): CliResult<RunState> {
  return runJson(cwd, "factory.orchestrator", ["run-state", "current"]);
}

export function requestRunAction(
  cwd: string,
  runId: string,
  action: "resume" | "abandon",
  reason?: string,
): CliResult<RunState> {
  const args = ["run-state", action, runId];
  if (reason !== undefined) args.push("--reason", reason);
  return runJson(cwd, "factory.orchestrator", args);
}
