export interface TaskSummary {
  id: string;
  title: string;
  status: string;
}

export function formatTaskOption(task: TaskSummary): string {
  return `${task.id}  ${task.title}`;
}

export function parseTaskIdFromOption(option: string): string {
  const [id] = option.split(/\s+/);
  return id!;
}
