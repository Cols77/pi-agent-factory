// /using-coherence -- a pure, deterministic rendering of `coherence status
// --json` (Increment 5 Task 3, spec plan
// docs/superpowers/plans/2026-08-20-coherence-increment-5-status-focus-dispatcher.md).
//
// This command sends no model message: it never calls ctx.newSession or any
// session-sending API. Everything it prints is a mechanical transcription of
// the StatusSnapshot Python already computed and ranked worst-first --
// picking which line is worst, and any argument-driven intent routing over
// that ranking, is later increments' job (Task 4's deterministic router).
import { loadCoherenceStatus } from "./coherence-status.js";
import type { StatusLine, StatusSnapshot } from "./coherence-status.js";
import type { ExtCommandCtx, PiApi } from "./pi-types.js";

export const COHERENCE_WIDGET_KEY = "coherence";

// The fixed escape-hatch phrase the brief requires: the top suggestion is a
// default, never the only option -- every ranked line remains one keystroke
// away.
export const NOT_THAT_PICK_FROM_MENU = "not that? pick from the menu:";

function formatResolveLines(resolveCmd: string[] | null, indent: string): string[] {
  // resolve_cmd is an ordered array of fully-substituted, ready-to-run
  // commands (Increment 2B contract) -- rendered one per line, NEVER joined
  // into a single ";"/"&&"-concatenated string.
  if (!resolveCmd || resolveCmd.length === 0) return [];
  return resolveCmd.map((cmd) => `${indent}- ${cmd}`);
}

function formatMenuEntry(line: StatusLine, index: number): string[] {
  const entry = [`${index + 1}. [${line.outcome}] ${line.summary}`];
  entry.push(...formatResolveLines(line.resolve_cmd, "   "));
  return entry;
}

// The ranked menu: the primary (worst-ranked) line offered first as the
// default action, then the escape hatch, then every line -- primary
// included -- renumbered as menu choices in the same worst-first order
// Python already computed. Never reorders, dedupes, or drops a line.
export function formatCoherenceMenu(snapshot: StatusSnapshot): string[] {
  const lines: string[] = [];
  lines.push(`coherence status: [${snapshot.primary.outcome}] ${snapshot.primary.summary}`);
  lines.push(...formatResolveLines(snapshot.primary.resolve_cmd, "  "));
  lines.push("");
  lines.push(NOT_THAT_PICK_FROM_MENU);
  for (const [index, line] of snapshot.lines.entries()) {
    lines.push(...formatMenuEntry(line, index));
  }
  return lines;
}

// A short summary for the status-bar widget -- one line, beside the
// existing "factory" widget (index.ts).
export function formatCoherenceWidget(snapshot: StatusSnapshot): string[] {
  return [`coherence: ${snapshot.primary.outcome} — ${snapshot.primary.summary}`];
}

export function registerCoherenceCommand(pi: PiApi): void {
  pi.registerCommand("using-coherence", {
    description:
      "Show the current coherence status as a ranked, actionable menu (worst-first; deterministic, no model call)",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const result = loadCoherenceStatus(ctx.cwd);
      if (!result.ok) {
        ctx.ui.notify(`/using-coherence: ${result.error}`, "error");
        return;
      }
      const snapshot = result.value;
      ctx.ui.setWidget(COHERENCE_WIDGET_KEY, formatCoherenceWidget(snapshot));
      ctx.ui.notify(formatCoherenceMenu(snapshot).join("\n"), "info");
    },
  });
}
