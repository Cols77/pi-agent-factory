import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export interface ReviewDecisionPayload {
  decision: "approve" | "reject";
  comments: Record<string, string>;
}

export function reviewDecisionPath(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "review-decision.json");
}

export function writeReviewDecision(path: string, decision: ReviewDecisionPayload): void {
  mkdirSync(dirname(path), { recursive: true });
  const tmpPath = `${path}.tmp`;
  writeFileSync(tmpPath, JSON.stringify(decision), "utf-8");
  renameSync(tmpPath, path);
}
