import { runJsonCli } from "./cli-runner.js";
import type { CliResult } from "./cli-runner.js";

// Mirrors `coherence.status.StatusLine`/`StatusSnapshot` (Increment 5 Task 1,
// src/coherence/status.py) exactly -- this file renders, it never
// interprets. `outcome` is worst-first precedence-ranked by the Python side
// (interrupted_run > probe_error > failing_gate > stale_audit >
// proposed_backlog > nothing_pending); `lines` arrives already sorted worst
// first and `primary` is the single worst-ranked line. `resolve_cmd`, when
// present, is an array of fully-substituted, ready-to-run shell command
// strings -- callers must render it as a list (or pick one entry) and must
// never join it into one semicolon/&&-concatenated string.
export interface StatusLine {
  source: string;
  outcome: string;
  summary: string;
  produced_by: string;
  resolve_cmd: string[] | null;
  observation_ref: string | null;
}

export interface StatusSnapshot {
  lines: StatusLine[];
  primary: StatusLine;
  exit_code: number;
}

// Mirrors trace-cli.ts's buildTraceCommand / system-cli.ts's
// buildSystemCommand -- the established way this extension reaches a Python
// CLI. Uses the modern `coherence` module directly (not a `factory.*` shim).
export function buildCoherenceStatusCommand(): { bin: string; args: string[] } {
  return { bin: "uv", args: ["run", "python", "-m", "coherence", "status", "--json"] };
}

export function loadCoherenceStatus(cwd: string): CliResult<StatusSnapshot> {
  const cmd = buildCoherenceStatusCommand();
  return runJsonCli<StatusSnapshot>(cwd, cmd.bin, cmd.args);
}
