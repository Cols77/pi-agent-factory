import { mkdirSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { ReviewDecisionPayload } from "./review-model.js";

export type { ReviewDecisionPayload };

// Synchronous sleep without pulling in a timer dependency. The gate polls
// review-decision.json, so a transient lock is possible; a short backoff
// lets the atomic rename succeed.
function syncSleep(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

export function reviewDecisionPath(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "review-decision.json");
}

/**
 * Write `text` to `path` via temp-file + atomic rename, retrying the rename.
 *
 * On Windows, renameSync can fail with ERROR_ACCESS_DENIED (EPERM / WinError 5)
 * when the destination is held open by another process without delete-share --
 * the same class of fragility as FileStatusReporter's os.replace on the status
 * file. A reader polling the file makes a transient lock likely; a few retries
 * let it succeed. Shared by every cross-process file bridge in this extension.
 */
export function atomicWriteWithRetry(path: string, text: string): void {
  mkdirSync(dirname(path), { recursive: true });
  const tmpPath = `${path}.tmp`;
  writeFileSync(tmpPath, text, "utf-8");
  let lastErr: unknown;
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      renameSync(tmpPath, path);
      return;
    } catch (err) {
      lastErr = err;
      syncSleep(50);
    }
  }
  try {
    unlinkSync(tmpPath);
  } catch {
    // best-effort cleanup; ignore
  }
  throw lastErr;
}

export function writeReviewDecision(path: string, decision: ReviewDecisionPayload): void {
  atomicWriteWithRetry(path, JSON.stringify(decision));
}
