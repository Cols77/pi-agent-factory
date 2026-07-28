import { secondsAgo } from "./status-format.js";

export interface LastRun {
  node: string | null;
  state: string | null;
  outcome: string | null;
  handoff: string | null;
  updated_at: string | null;
}

export interface TaskSummary {
  id: string;
  title: string;
  status: string;
  // True when the task's Create:/Test: deliverables already exist on disk
  // (orchestrator's `list --json` computes this). Used only to ANNOTATE a task
  // with no run history as likely-done -- never to hide it.
  already_done?: boolean;
  // The task's last factory run stop-point, or null if it never ran.
  last_run?: LastRun | null;
}

export function humanizeAge(seconds: number): string {
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function formatTaskOption(task: TaskSummary, now: Date = new Date()): string {
  const base = `${task.id}  ${task.title}`;
  const lr = task.last_run;
  if (lr && lr.node && lr.state) {
    const age = lr.updated_at ? ` (${humanizeAge(secondsAgo(lr.updated_at, now))})` : "";
    const reason = lr.handoff ? `: ${lr.handoff}` : "";
    return `${base}  — ⚠ stopped: ${lr.node} ${lr.state}${age}${reason}`;
  }
  if (task.already_done) {
    return `${base}  — deliverables present (will route to review)`;
  }
  return base;
}

export function parseTaskIdFromOption(option: string): string {
  const [id] = option.split(/\s+/);
  return id!;
}
