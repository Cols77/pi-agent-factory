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

function runJson<T>(cwd: string, args: string[]): CliResult<T> {
  const result = spawnSync(
    "uv",
    ["run", "python", "-m", "factory.evidence", ...args, "--repo", cwd, "--json"],
    { cwd, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 },
  );
  if (result.error) {
    return { ok: false, status: -1, error: result.error.message };
  }
  const status = result.status ?? -1;
  if (status !== 0) {
    return {
      ok: false,
      status,
      error: (result.stderr || result.stdout || `factory evidence exited ${status}`).trim(),
    };
  }
  try {
    return { ok: true, value: JSON.parse(result.stdout) as T };
  } catch (err) {
    return { ok: false, status, error: `could not parse factory evidence output: ${String(err)}` };
  }
}

export function loadTaskEvidence(cwd: string, taskId: string): CliResult<{ runs: EvidenceRun[] }> {
  return runJson(cwd, ["task", taskId]);
}

export function loadRunEvidence(cwd: string, runId: string): CliResult<EvidenceRun> {
  return runJson(cwd, ["run", runId]);
}

export function listEvidence(cwd: string): CliResult<{ runs: EvidenceRun[] }> {
  return runJson(cwd, ["list"]);
}
