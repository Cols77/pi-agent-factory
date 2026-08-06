import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parsePolishStateFile, type PolishCommand, type PolishStateFile } from "./polish-model.js";
// Reuse the one atomic-rename-with-Windows-retry primitive rather than copying
// it -- two divergent copies of that workaround is exactly how it rots.
import { atomicWriteWithRetry } from "./review-protocol.js";

// These filenames are the cross-process contract. They must match the constants
// in src/factory/polish/cli.py (STATE_FILE / COMMANDS_DIR).
export function polishStatePath(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "polish-state.json");
}

export function polishCommandsDir(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "polish-commands");
}

export function readPolishState(path: string): PolishStateFile | null {
  try {
    return parsePolishStateFile(readFileSync(path, "utf-8"));
  } catch {
    return null; // absent or unreadable; caller keeps the last good state
  }
}

let _seq = 0;

/**
 * Drop a uniquely-named command file for the Python side to consume.
 *
 * Never overwrites a pending command: each call writes a new file, and the
 * bridge deletes each one after applying it. The timestamp+counter name keeps
 * the sorted order the bridge relies on to apply commands in issue order.
 */
export function writePolishCommand(commandsDir: string, cmd: PolishCommand): void {
  const name = `${String(Date.now()).padStart(14, "0")}-${String(_seq++).padStart(4, "0")}.json`;
  atomicWriteWithRetry(join(commandsDir, name), JSON.stringify(cmd));
}
