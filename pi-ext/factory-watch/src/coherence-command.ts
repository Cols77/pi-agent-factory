// /using-coherence -- a pure, deterministic rendering of `coherence status
// --json` (Increment 5 Task 3), plus, when an argument is given, a
// deterministic phrase-to-intent classification of it (Increment 5 Task 4,
// spec plan
// docs/superpowers/plans/2026-08-20-coherence-increment-5-status-focus-dispatcher.md).
//
// This command sends no model message: it never calls ctx.newSession or any
// session-sending API. Everything it prints is a mechanical transcription of
// the StatusSnapshot Python already computed and ranked worst-first, plus
// (argument-present path) the RouteMatch `coherence route --json`
// (src/coherence/router.py) already computed via pure phrase matching --
// this file never reimplements that phrase table, and never calls a model
// API to classify the argument itself. A classification is never printed
// alone: the same ranked menu and escape hatch as the zero-argument path
// always render underneath it, and a `null` route (no match, a tie, or a
// below-threshold score) falls through to exactly the zero-argument
// rendering.
import { loadCoherenceRoute } from "./coherence-router.js";
import type { RouteMatch } from "./coherence-router.js";
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

// The argument-present classification line: names the routed intent and its
// score, plus the scope ref `route_text` pulled out of the free text, when
// one was found. Never the only output -- callers always render this above
// `formatCoherenceMenu`'s escape hatch and ranked menu, never in its place.
export function formatRouteClassification(route: RouteMatch): string[] {
  const scopeSuffix = route.scope_ref !== null ? ` scope=${route.scope_ref}` : "";
  return [`route: ${route.intent} (score=${route.score})${scopeSuffix}`];
}

export function registerCoherenceCommand(pi: PiApi): void {
  pi.registerCommand("using-coherence", {
    description:
      "Show the current coherence status as a ranked, actionable menu (worst-first; deterministic, no model call). " +
      "With an argument, also classifies it into a routed intent via a deterministic phrase table (no model call) -- " +
      "the menu and escape hatch always render underneath the classification.",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const trimmed = args.trim();
      // Argument-present path: classify via the deterministic router bridge
      // (a subprocess call to `coherence route --json`, never a model call
      // and never a reimplementation of route_text's phrase table here). A
      // bridge failure or a `null` route (no match, a tie, or a
      // below-threshold score) both fall through to the same zero-argument
      // rendering below -- never a distinct error path that could hide the
      // menu.
      let route: RouteMatch | null = null;
      if (trimmed.length > 0) {
        const routeResult = loadCoherenceRoute(ctx.cwd, trimmed);
        if (routeResult.ok) {
          route = routeResult.value.route;
        }
      }

      const result = loadCoherenceStatus(ctx.cwd);
      if (!result.ok) {
        ctx.ui.notify(`/using-coherence: ${result.error}`, "error");
        return;
      }
      const snapshot = result.value;
      // Guard against a shape-drifted payload (reviewer-B F2): if `primary`
      // is absent, error-notify rather than throwing mid-render and hiding the menu.
      if (!snapshot.primary?.outcome) {
        ctx.ui.notify("/using-coherence: status payload was missing a primary line", "error");
        return;
      }
      ctx.ui.setWidget(COHERENCE_WIDGET_KEY, formatCoherenceWidget(snapshot));

      const menuLines = formatCoherenceMenu(snapshot);
      // Loose `!= null` (not strict `!== null`): a shape-drift payload that
      // yields `route === undefined` must not be treated as a real route and
      // throw in formatRouteClassification — fall through to the plain menu.
      const lines = route != null ? [...formatRouteClassification(route), "", ...menuLines] : menuLines;
      ctx.ui.notify(lines.join("\n"), "info");
    },
  });
}
