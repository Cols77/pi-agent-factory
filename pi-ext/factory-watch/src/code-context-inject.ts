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

import { factoryRoot } from "./factory-path.js";
import type { BeforeAgentStartEventResult } from "./pi-types.js";

/** Path to the index marker (JSON) that factory.codeindex writes on build. */
export function indexMarkerPath(root: string): string {
  return join(root, ".factory", "code-index", "latest.json");
}

/** Whether this project has any durable code index at all. */
export function hasCodeIndex(root: string): boolean {
  if (typeof root !== "string" || root === "") return false;
  try {
    readFileSync(indexMarkerPath(root), "utf-8");
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolve which python environment runs the durable code index for a project.
 *
 * The tree-sitter grammars ship as the factory's optional `code-index` extra,
 * and a consumer installs the factory as a dev dependency WITHOUT extras — so
 * the consumer's own venv has no tree-sitter. The factory checkout's own
 * environment (reached via `uv run --project <factoryRoot>`) DOES carry the
 * extra, so it is tried first; then the consumer env; then bare `python` on
 * PATH. The resolver returns candidate argv lists + binary, in preference
 * order, so build/slice callers share one decision and every spawn failure
 * simply falls through to the next candidate (never fatal).
 */
export function factoryIndexCandidates(
  root: string,
  factoryRootDir: string,
  extraArgs: string[],
): Array<[string, string[]]> {
  const args = ["-m", "factory.codeindex", "--root", root, ...extraArgs];
  return [
    ["uv", ["run", "--project", factoryRootDir, "python", ...args]],
    ["uv", ["run", "python", ...args]],
    ["python", args],
  ];
}

/**
 * Render a bounded slice of the project's code index through the Python CLI.
 * Returns "" when there is no index / no python / any failure. The CLI hard
 * caps the output (default 24k chars; render_index_slice enforces the cap).
 */
export function renderIndexSlice(root: string, capChars = 24000): string {
  const candidates = factoryIndexCandidates(root, factoryRoot(), [
    "--slice",
    String(capChars),
  ]);
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

/**
 * Compose the before_agent_start injection result for a project: a bounded
 * slice of its durable code index, delivered once per (root, sessionId). Pure
 * and unit-testable — the pi handler is a thin wrapper around it.
 *
 * Returns {} (no injection) when the project has no index, the session was
 * already injected, or the slice comes back empty. `renderSlice` is injectable
 * so tests never spawn python.
 */
export function composeCodeContextMessage(
  root: string,
  sessionId: string | undefined,
  injectedSessions: Set<string>,
  renderSlice: (root: string) => string = renderIndexSlice,
): BeforeAgentStartEventResult | Record<string, never> {
  if (!hasCodeIndex(root)) return {}; // project has no factory code index
  if (!shouldInject(injectedSessions, root, sessionId)) return {};
  const slice = renderSlice(root);
  if (!slice) return {};
  return {
    message: {
      customType: "factory-code-context",
      content: slice,
      display: false, // don't clatter the TUI; the slice is agent-only
    },
  };
}