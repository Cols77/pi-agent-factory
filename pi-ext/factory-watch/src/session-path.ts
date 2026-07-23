import { readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export function resolveSessionPath(
  sessionId: string,
  sessionsRoot: string = join(homedir(), ".pi", "agent", "sessions"),
): string | null {
  let projectDirs: string[];
  try {
    projectDirs = readdirSync(sessionsRoot, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => d.name);
  } catch {
    return null;
  }
  const suffix = `_${sessionId}.jsonl`;
  for (const dir of projectDirs) {
    let files: string[];
    try {
      files = readdirSync(join(sessionsRoot, dir));
    } catch {
      continue;
    }
    const match = files.find((f) => f.endsWith(suffix));
    if (match) {
      return join(sessionsRoot, dir, match);
    }
  }
  return null;
}
