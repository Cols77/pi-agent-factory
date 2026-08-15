// Code-context injection for normal pi sessions.
//
// The durable tree-sitter code index (built by /factory-init) is normally only
// consumed inside the factory pipeline (Dev/Review prompts, grill seed). This
// module wires a second consumer: `before_agent_start` injects a bounded,
// token-budgeted slice of the project's index into an ordinary pi session, so
// opening pi in a factory-init'd project gives the agent real code knowledge
// without running /factory.
//
// All freshness/ordering/caps live in Python (factory.codeindex --slice) so the
// TS side stays a thin consumer and can never drift from the index's own rules.

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Path to the index marker (JSON) that factory.codeindex writes on build. */
export function indexMarkerPath(root: string): string {
  return join(root, ".factory", "code-index", "latest.json");
}

/** Whether this project has any durable code index at all. */
export function hasCodeIndex(root: string): boolean {
  try {
    readFileSync(indexMarkerPath(root), "utf-8");
    return true;
  } catch {
    return false;
  }
}

/**
 * Render a bounded slice of the project's code index through the Python CLI.
 * Returns "" when there is no index / no python / any failure. The CLI hard
 * caps the output (default 24k chars; render_index_slice enforces the cap).
 */
export function renderIndexSlice(root: string, capChars = 24000): string {
  const args = ["-m", "factory.codeindex", "--root", root, "--slice", String(capChars)];
  const candidates: Array<[string, string[]]> = [
    ["uv", ["run", "python", ...args]],
    ["python", args],
  ];
  for (const [bin, binArgs] of candidates) {
    try {
      const r = spawnSync(bin, binArgs, { encoding: "utf-8", timeout: 60000 });
      if (r.status === 0 && r.stdout) {
        const out = r.stdout.trim();
        if (out) return out;
      }
    } catch {
      // try next candidate
    }
  }
  return "";
}

/**
 * Decide whether to inject for this session: once per (root, sessionId). Kept
 * pure except for the collected-session memory so the handler stays testable.
 * Returns true when this session has not been injected yet.
 */
export function shouldInject(
  collected: Set<string>,
  root: string,
  sessionId: string | undefined,
): boolean {
  if (!root || !sessionId) return false; // no way to gate or no project
  const key = `${root}::${sessionId}`;
  if (collected.has(key)) return false;
  collected.add(key);
  return true;
}