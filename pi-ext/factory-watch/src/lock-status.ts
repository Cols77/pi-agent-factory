export interface LockRecord {
  pid: number;
  started_at: string;
}

function isLockRecord(value: unknown): value is LockRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    "pid" in value &&
    typeof (value as { pid: unknown }).pid === "number" &&
    "started_at" in value
  );
}

export function parseLock(raw: string): LockRecord | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  return isLockRecord(data) ? data : null;
}

export function isPidAlive(pid: number): boolean {
  // process.kill with signal 0 is a Node-documented existence check: it
  // sends no actual signal and works this way on both POSIX and Windows
  // (unlike Python's os.kill, which doesn't support signal 0 on Windows --
  // see src/factory/orchestrator/lock.py's tasklist-based workaround there).
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}
