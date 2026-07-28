import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface VerifyItem { item: string; file?: string; line?: number; why?: string }
export interface GateResult { gate: string; ok?: boolean; summary?: string }
export interface ReviewGuide {
  confidence?: string;
  verify?: VerifyItem[];
  validation?: GateResult[];
  addressed?: string[];
}

export function reviewGuidePath(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "review-guide.json");
}

export function readReviewGuide(path: string): ReviewGuide | null {
  try {
    return JSON.parse(readFileSync(path, "utf-8")) as ReviewGuide;
  } catch {
    return null; // missing or unparseable -> no guide, plain diff
  }
}
