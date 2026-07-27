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

function iconForState(state: string): string {
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
    };
  });
}
