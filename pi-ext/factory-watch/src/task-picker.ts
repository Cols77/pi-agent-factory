export interface TaskSummary {
  id: string;
  title: string;
  status: string;
  // True when the task's Create:/Test: deliverables already exist on disk
  // (the orchestrator's `list --json` computes this): its work is already done,
  // so it shouldn't be offered for execution.
  already_done?: boolean;
}

export function formatTaskOption(task: TaskSummary): string {
  return `${task.id}  ${task.title}`;
}

export function parseTaskIdFromOption(option: string): string {
  const [id] = option.split(/\s+/);
  return id!;
}
