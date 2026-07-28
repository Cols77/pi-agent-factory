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

// Pipeline node display labels
const NODE_LABELS: Record<string, string> = {
  "context-gather": "context-gatherer",
  dev: "developer",
  validation: "validation",
  review: "reviewer",
  "human-review": "human-review",
  "session-review": "session-reviewer",
};

// Icons for node states
const STATE_ICONS: Record<string, string> = {
  running: "●",
  pass: "✓",
  fail: "✗",
  reject: "✗",
  escalate: "↑",
  "changes-requested": "↻",
  blocked: "⊘",
};

export function iconForState(state: string): string {
  return STATE_ICONS[state] || "·";
}

function labelForNode(node: string): string {
  return NODE_LABELS[node] || node;
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
      handoff: entry?.handoff ?? null,
      sessionId: entry?.session_id ?? null,
      summary: entry?.summary ?? null,
      startCommit: entry?.start_commit ?? null,
      snippet: entry?.snippet ?? null,
    };
  });
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
      return "working…";
    case "pass":
      return "done";
    case "escalate":
      return "escalated";
    case "blocked":
      return "waiting for you";
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
