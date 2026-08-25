import { labelForNode } from "./node-registry.js";

export interface PipelineEntry {
  node: string;
  node_state: string;
  attempt: number;
  max_attempts: number;
  snippet: string;
  outcome: string | null;
  handoff: string | null;
  updated_at: string;
  session_id?: string | null;
  summary?: string | null;
  start_commit?: string | null;
  already_done?: boolean;
  deliverables?: string[];
}

export interface StatusRecord {
  session_id: string;
  task_id: string;
  current_node: string;
  current_state: string;
  pipeline: PipelineEntry[];
  started_at: string;
  updated_at: string;
  // Legacy fields (for backward compat if old status file is still around)
  node?: string;
  node_state?: string;
  attempt?: number;
  max_attempts?: number;
  snippet?: string;
  outcome?: string | null;
}

function isStatusRecord(value: unknown): value is StatusRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    "updated_at" in value
  );
}

export function parseStatus(raw: string): StatusRecord | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  return isStatusRecord(data) ? data : null;
}

export function secondsAgo(isoTimestamp: string, now: Date = new Date()): number {
  const then = new Date(isoTimestamp);
  return Math.max(0, Math.round((now.getTime() - then.getTime()) / 1000));
}

// Icons for node states
const STATE_ICONS: Record<string, string> = {
  running: "●",
  pass: "✓",
  passed: "✓",
  fail: "✗",
  failed: "✗",
  reject: "✗",
  escalate: "↑",
  "changes-requested": "↻",
  blocked: "⊘",
  interrupted: "■",
};

export function iconForState(state: string): string {
  return STATE_ICONS[state] || "·";
}

export function formatStatusLines(record: StatusRecord | null, now: Date = new Date()): string[] {
  if (record === null) {
    return ["factory: waiting for status..."];
  }

  // Handle legacy format (no pipeline array)
  if (!record.pipeline || record.pipeline.length === 0) {
    const node = record.current_node || record.node || "(no task)";
    const state = record.current_state || record.node_state || "";
    const attempt = record.attempt ?? 0;
    const maxAttempts = record.max_attempts ?? 0;
    const snippet = record.snippet || "";
    const outcome = record.outcome;
    const lines: string[] = [];
    lines.push(`factory: ${record.task_id || "(no task)"}  [${node} / ${state}]`);
    lines.push(`  attempt ${attempt}/${maxAttempts}  (updated ${secondsAgo(record.updated_at, now)}s ago)`);
    if (snippet) lines.push(`  ${snippet.slice(-120)}`);
    if (outcome) lines.push(`  outcome: ${outcome}`);
    return lines;
  }

  // New pipeline format
  const lines: string[] = [];
  const taskId = record.task_id || "(no task)";
  lines.push(`factory: ${taskId}`);

  for (const entry of record.pipeline) {
    const icon = iconForState(entry.node_state);
    const label = labelForNode(entry.node);
    const state = entry.node_state;
    const isRunning = entry.node_state === "running";

    // Main pipeline line
    let line = `${icon} ${label}: ${state}`;
    if (entry.attempt > 0) {
      line += `  (${entry.attempt}/${entry.max_attempts})`;
    }
    if (isRunning) {
      line += `  ${secondsAgo(entry.updated_at, now)}s ago`;
    }
    lines.push(line);

    // Handoff line — what this node passes to the next
    if (entry.handoff) {
      lines.push(`  ${entry.handoff}`);
    }

    // Snippet line for running nodes (agent output preview)
    if (entry.snippet && isRunning) {
      lines.push(`  “${entry.snippet.slice(-100)}"`);
    }
  }

  // Outcome line
  const lastEntry = record.pipeline[record.pipeline.length - 1];
  if (lastEntry && lastEntry.outcome) {
    lines.push(`  outcome: ${lastEntry.outcome}`);
  }

  return lines;
}

export interface MissionControlRow {
  node: string;
  label: string;
  state: string;
  attempt: number;
  maxAttempts: number;
  handoff: string | null;
  sessionId: string | null;
  summary: string | null;
  startCommit: string | null;
  snippet: string | null;
}

export function formatMissionControlRows(record: StatusRecord | null, stageOrder: string[]): MissionControlRow[] {
  const byNode = new Map((record?.pipeline ?? []).map((entry) => [entry.node, entry]));
  return stageOrder.map((node) => {
    const entry = byNode.get(node);
    return {
      node,
      label: labelForNode(node),
      state: entry?.node_state ?? "pending",
      attempt: entry?.attempt ?? 0,
      maxAttempts: entry?.max_attempts ?? 0,
      handoff: entry?.handoff ?? null,
      sessionId: entry?.session_id ?? null,
      summary: entry?.summary ?? null,
      startCommit: entry?.start_commit ?? null,
      snippet: entry?.snippet ?? null,
    };
  });
}

// A streamed snippet is worth showing only if it carries real content. Pi's
// text-delta capture often yields a lone punctuation fragment (e.g. ":") while
// the agent is busy in tool calls -- that is noise, not activity, and must not
// crowd out the activity line.
export function isSubstantiveSnippet(snippet: string | null): boolean {
  return snippet != null && /[A-Za-z0-9]/.test(snippet) && snippet.trim().length >= 2;
}

// A short, dynamic line describing what a stage is doing right now or what it
// finished and handed off -- NOT a static job description. Prefers the
// orchestrator's own handoff text (e.g. "→ validation: unit tests green",
// "unit tests failed, retry 2/3", "escalated: unit tests still red"), falling
// back to a state-based phrase when no handoff was emitted yet (e.g. a stage
// that hasn't run, or is mid-run before its first handoff).
export function nodeActivity(row: MissionControlRow): string {
  if (row.handoff) return row.handoff;
  switch (row.state) {
    case "pending":
      return "waiting to start";
    case "running":
      return row.attempt > 0 ? `working… (attempt ${row.attempt}/${row.maxAttempts})` : "working…";
    case "pass":
      return "done";
    case "fail":
      return "tests failed";
    case "reject":
      return "rejected";
    case "escalate":
      return "escalated — needs a human";
    case "blocked":
      return "waiting for you";
    case "changes-requested":
      return "changes requested — back to the developer";
    case "already-done":
      return "already complete";
    default:
      return row.state;
  }
}

// Detects the dev-escalation handoff state: the dev node exhausted its
// retries with unit tests still red. Returns the last dev attempt's pi
// session id (preserved on the entry by FileStatusReporter's sticky-field
// logic) so the dashboard can open `pi --session <id>` for the human to pair
// with the agent. Returns null unless the dev node is escalated AND a session
// id was captured.
export function devEscalated(record: StatusRecord | null): { sessionId: string } | null {
  const entry = (record?.pipeline ?? []).find(
    (e) => e.node === "dev" && (e.node_state === "escalate" || e.outcome === "escalated"),
  );
  if (entry && typeof entry.session_id === "string") {
    return { sessionId: entry.session_id };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Increment 7 — unified long-run status protocol (`serialize_run_statuses`).
//
// `coherence.runs.transport.serialize_run_statuses` (the canonical python
// serializer) emits `{"runs": [ ... ]}` in which each row is DISCRIMINATED by
// `producer` (factory | audit | measurement | simulation | experiment) rather
// than being a pipeline stage. These types mirror that payload EXACTLY -- we
// consume the python shape, we never build a second serializer here.
//
// Row contract (all keys always present):
//   producer, run_id, state, observation_ref,
//   artifacts: [{ref, kind, location, content_hash, scope_refs, media_type}],
//   resume_cmd: string | null,            // native-run resume command; null == none
//   updated_at, diagnostics: [{code, summary}], terminal_observation_id,
//   blocking_obligation: string | null,   // winning open obligation id
//   blocking_obligation_resolve_cmd: string[] | null, // obligation's resolve tuple as array
//   rerun_allowed: boolean
// ---------------------------------------------------------------------------

export const RUN_PRODUCERS = ["factory", "audit", "measurement", "simulation", "experiment"] as const;
export type RunProducer = (typeof RUN_PRODUCERS)[number];

export function isRunProducer(value: string): value is RunProducer {
  return (RUN_PRODUCERS as readonly string[]).includes(value);
}

// Every run row carries a source-specific label derived from its producer. The
// label is the producer name itself unless a clearer display name is wanted
// later; discriminating by producer (not by pipeline position) is what matters.
const PRODUCER_LABELS: Record<string, string> = {
  factory: "factory",
  audit: "audit",
  measurement: "measurement",
  simulation: "simulation",
  experiment: "experiment",
};

export function producerLabel(producer: string): string {
  return PRODUCER_LABELS[producer] ?? producer;
}

export interface RunArtifact {
  ref: string;
  kind: string;
  location: string;
  content_hash: string;
  scope_refs: string[];
  media_type: string;
}

export interface RunDiagnostic {
  code: string;
  summary: string;
}

export interface RunStatus {
  producer: string;
  run_id: string;
  state: string;
  observation_ref: string;
  artifacts: RunArtifact[];
  resume_cmd: string | null;
  updated_at: string;
  diagnostics: RunDiagnostic[];
  terminal_observation_id: string | null;
  blocking_obligation: string | null;
  blocking_obligation_resolve_cmd: string[] | null;
  rerun_allowed: boolean;
}

export interface RunStatusesPayload {
  runs: RunStatus[];
}

export function parseRunStatuses(raw: string): RunStatusesPayload | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof data === "object" && data !== null) {
    const runs = (data as { runs?: unknown }).runs;
    if (Array.isArray(runs)) {
      return { runs: runs as RunStatus[] };
    }
  }
  return null;
}

// The native-run resume command is meaningful only when it is a non-empty
// string. Anything else (null, undefined, empty, whitespace) means "no resume
// control" -- the dashboard must render no resume label/control, and must
// never leak an empty string, "undefined", or a stale value from elsewhere.
export function resumeCommand(run: RunStatus): string | null {
  const value = run.resume_cmd;
  if (typeof value === "string" && value.trim().length > 0) return value;
  return null;
}

// The obligation's resolve-command TUPLE arrives as a JSON array. It is
// rendered item-by-item (never shell-joined, never executed) and is
// independent of `resume_cmd`: both may be present together, only the
// obligation may be present, or neither.
export function obligationResolveCommands(run: RunStatus): string[] {
  const commands = run.blocking_obligation_resolve_cmd;
  if (!Array.isArray(commands)) return [];
  return commands.map((c) => (typeof c === "string" ? c : String(c))).filter((c) => c.length > 0);
}

// Producer-aware status lines for the background widget (primary condition
// mirrors formatStatusLines, but each row is anchored by its producer).
export function formatRunStatusLines(payload: RunStatusesPayload | null, now: Date = new Date()): string[] {
  if (payload === null || payload.runs.length === 0) {
    return ["mission control: no runs yet"];
  }
  const lines: string[] = [];
  for (const run of payload.runs) {
    lines.push(`[${producerLabel(run.producer)}] ${run.run_id} · ${run.state}`);
    const resume = resumeCommand(run);
    if (resume !== null) lines.push(`  resume: ${resume}`);
    if (run.blocking_obligation) {
      lines.push(`  obligation: ${run.blocking_obligation}`);
      for (const cmd of obligationResolveCommands(run)) {
        lines.push(`    resolve: ${cmd}`);
      }
    }
    if (run.rerun_allowed) lines.push("  rerun allowed");
  }
  return lines;
}

