import type { Component } from "@earendil-works/pi-tui";
import { computeReviewFiles } from "./review-diff.ts";
import type { FileStat } from "./review-diff.ts";
import { ReviewOverlay } from "./review-overlay.ts";
import type { TuiLike } from "./review-overlay.ts";

// Browse-mode wrapper around ReviewOverlay -- this task (E1) only lets the
// user navigate the human-review diff from a standalone terminal window; no
// decision is sent anywhere (E2, deciding from the dashboard, is deferred to
// a future increment per task-9-brief.md).
//
// ReviewOverlay itself isn't a full pi-tui Component -- it has no
// invalidate() (its only other caller, runReviewLoop in review-overlay.ts,
// drives it through the host's `ui.custom()` bridge via an `as unknown as`
// cast rather than tui.addChild()/tui.setFocus()). This adapter supplies the
// missing invalidate() no-op and delegates render()/handleInput() straight
// through, so it can be mounted directly with the real pi-tui TUI the same
// way mission-control-dashboard.ts mounts its own top-level component. The
// onAction callback passed to
// ReviewOverlay is intentionally a no-op: comment/edit/approve/reject all
// route through onAction, and browse mode ignores all of them rather than
// wiring any of them to a decision channel.
export class ReviewBrowser implements Component {
  private readonly overlay: ReviewOverlay;

  constructor(files: FileStat[], tui: TuiLike, cwd: string, startCommit: string) {
    this.overlay = new ReviewOverlay(files, new Map(), tui, cwd, startCommit, () => {});
  }

  // No cached render state of its own -- delegates entirely to the wrapped
  // ReviewOverlay. Required (non-optional) by pi-tui's Component interface
  // so this can be passed to tui.addChild()/tui.setFocus().
  invalidate(): void {}

  handleInput(data: string): void {
    this.overlay.handleInput(data);
  }

  render(width: number): string[] {
    return this.overlay.render(width);
  }
}

export interface ReviewArgs {
  cwd: string;
  startCommit: string;
}

// indexOf returns -1 when a flag is missing; -1 + 1 = 0 would then read
// process.argv[0] (the node executable's own path -- a real, defined
// string), silently defeating the undefined check below. Treat -1
// explicitly as "not found" instead. Mirrors mission-control-dashboard.ts.
export function buildReviewArgs(argv: string[]): ReviewArgs | undefined {
  const cwdArgIndex = argv.indexOf("--cwd");
  const cwd = cwdArgIndex === -1 ? undefined : argv[cwdArgIndex + 1];
  const startCommitArgIndex = argv.indexOf("--start-commit");
  const startCommit = startCommitArgIndex === -1 ? undefined : argv[startCommitArgIndex + 1];
  if (cwd === undefined || startCommit === undefined) {
    return undefined;
  }
  return { cwd, startCommit };
}

// Standalone entry point -- no `pi --extension`, no LLM. Computes the
// human-review diff once and drives a real pi-tui TUI/ProcessTerminal so the
// user can browse it in a separate terminal window (spawned by the
// dashboard, Task 10). See mission-control-dashboard.ts's main() for the
// same TUI mounting sequence and the reasoning behind each call
// (TUI.start() vs terminal.start(), tui.setFocus() being required for input
// to reach the component, etc).
async function main(): Promise<void> {
  const { ProcessTerminal, TUI } = await import("@earendil-works/pi-tui");
  const args = buildReviewArgs(process.argv);
  if (args === undefined) {
    console.error("usage: node mission-control-review.js --cwd <repo-root> --start-commit <sha>");
    process.exit(1);
  }
  const { cwd, startCommit } = args;

  const terminal = new ProcessTerminal();
  const tui = new TUI(terminal);
  const files = computeReviewFiles(cwd, startCommit);
  const browser = new ReviewBrowser(files, { terminal: { rows: terminal.rows } }, cwd, startCommit);
  tui.addChild(browser);
  tui.setFocus(browser);
  tui.start();
}

if (process.argv[1]?.endsWith("mission-control-review.js") || process.argv[1]?.endsWith("mission-control-review.ts")) {
  void main();
}
