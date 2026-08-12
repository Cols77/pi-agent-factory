import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface VerifyItem { item: string; file?: string; line?: number; why?: string }
export interface GateResult { gate: string; ok?: boolean; summary?: string }
export interface ReviewGuide {
  confidence?: string;
  verify?: VerifyItem[];
  validation?: GateResult[];
  addressed?: string[];
  grill?: { verdict: "agreed" | "not-agreed" | "skipped"; summary?: string | null };
}

// Returns a short, clear Markdown warning when the pre-implementation grill
// came back not-agreed (the author did not demonstrate understanding). Empty
// for every other case so callers can append it to a banner unconditionally.
export function grillReviewWarning(guide: ReviewGuide | null | undefined): string {
  if (!guide || guide.grill?.verdict !== "not-agreed") return "";
  const base =
    "⚠ You did not demonstrate understanding in the pre-implementation grill (not-agreed). Reviews should get extra scrutiny.";
  if (guide.grill.summary) return `${base}\n\nGrill summary: ${guide.grill.summary}`;
  return base;
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
