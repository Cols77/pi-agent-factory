import { readdirSync } from "node:fs";
import { join } from "node:path";

// The grill lives in the same per-session transcript directory as the review
// decision and review guide, so the Python gate and this extension agree on
// exactly one location per run.
export function grillResultPath(cwd: string, sessionId: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, "grill-result.json");
}

// A fresh, self-contained pi session file for the standalone grill window.
// Timestamped so an abandoned file can never collide with a later retry for a
// different task in the same transcript dir.
export function grillSessionPath(cwd: string, sessionId: string, now: Date = new Date()): string {
  const stamp = now.toISOString().replace(/[:.]/g, "-");
  return join(cwd, "sessions", ".factory-transcripts", sessionId, `grill-${stamp}.jsonl`);
}

const NONE_SUMMARY =
  "No visual explainers present yet -- generate one via visual-explainer/diagram-design.";

/**
 * Summary of the visual explainers present under docs/visual-explain/ (the
 * grill session verifies each one's dependency fingerprint is current before
 * reusing it; otherwise it falls back to generating a new one). Pure and local
 * by design (extension-side only): it just lists the *.md files, it does not
 * run any Python subprocess.
 */
export function readFreshExplainerSummary(cwd: string): string {
  let names: string[];
  try {
    names = readdirSync(join(cwd, "docs", "visual-explain"))
      .filter((n) => n.endsWith(".md"))
      .sort();
  } catch {
    return NONE_SUMMARY;
  }
  if (names.length === 0) {
    return NONE_SUMMARY;
  }
  const bases = names.map((n) => n.replace(/\.md$/, "")).join(", ");
  return `Visual explainers present in docs/visual-explain/: ${bases}. Reuse one whose dependency fingerprint matches the current code; otherwise generate a new explainer via visual-explainer/diagram-design.`;
}

/**
 * Render a self-contained fresh pi session (JSONL) that opens straight into the
 * grill: a session header followed by a single user message carrying the seed.
 * The header + message schema mirrors what pi itself writes for a v3 session
 * (see session-manager.ts), so `pi --session <file>` loads it as a normal
 * session and triggers a model turn off the seed.
 */
export function freshSessionJsonl(
  seed: string,
  cwd: string,
  now: Date = new Date(),
  newId: () => string = () =>
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`,
): string {
  const iso = now.toISOString();
  const header = { type: "session", version: 3, id: newId(), timestamp: iso, cwd };
  const message = {
    type: "message",
    id: newId(),
    parentId: null,
    timestamp: iso,
    message: { role: "user", content: [{ type: "text", text: seed }] },
  };
  return `${JSON.stringify(header)}\n${JSON.stringify(message)}\n`;
}
