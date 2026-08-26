import { runJsonCli } from "./cli-runner.js";
import type { CliResult } from "./cli-runner.js";

// Mirrors `coherence.router.RouteMatch` (Increment 5 Task 4, src/coherence
// /router.py) exactly -- this file bridges, it never reimplements the
// phrase-to-intent table. `route` is `null` whenever `route_text` found no
// unique intent at or above threshold (tie, no match, or below-threshold
// score); a non-null route always names one of the eight `Intent` values.
export interface RouteMatch {
  intent: string;
  scope_ref: string | null;
  score: number;
}

export interface RouteResult {
  route: RouteMatch | null;
}

// Mirrors coherence-status.ts's buildCoherenceStatusCommand -- the
// established way this extension reaches a Python CLI (a subprocess call,
// never an embedded reimplementation of `route_text` in TypeScript).
export function buildCoherenceRouteCommand(text: string): { bin: string; args: string[] } {
  // `--` separator so a free-text argument that begins with `-` (e.g.
  // `/using-coherence --help ...`) is still treated as the positional `text`
  // by argparse instead of being swallowed as an unknown option (exit 2, no
  // JSON). The flags precede the separator; nothing after `--` is option-like.
  return { bin: "uv", args: ["run", "python", "-m", "coherence", "route", "--json", "--", text] };
}

export function loadCoherenceRoute(cwd: string, text: string): CliResult<RouteResult> {
  const cmd = buildCoherenceRouteCommand(text);
  return runJsonCli<RouteResult>(cwd, cmd.bin, cmd.args);
}
