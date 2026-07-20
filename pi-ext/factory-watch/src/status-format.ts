export interface StatusRecord {
  session_id: string;
  task_id: string;
  node: string;
  node_state: string;
  attempt: number;
  max_attempts: number;
  snippet: string;
  outcome: string | null;
  started_at: string;
  updated_at: string;
}

function isStatusRecord(value: unknown): value is StatusRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    "node" in value &&
    "node_state" in value &&
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

export function formatStatusLines(record: StatusRecord | null, now: Date = new Date()): string[] {
  if (record === null) {
    return ["factory: waiting for status..."];
  }
  const lines: string[] = [];
  lines.push(`factory: ${record.task_id || "(no task)"}  [${record.node} / ${record.node_state}]`);
  lines.push(
    `  attempt ${record.attempt}/${record.max_attempts}  (updated ${secondsAgo(record.updated_at, now)}s ago)`,
  );
  if (record.snippet) {
    lines.push(`  ${record.snippet.slice(-120)}`);
  }
  if (record.outcome) {
    lines.push(`  outcome: ${record.outcome}`);
  }
  return lines;
}
