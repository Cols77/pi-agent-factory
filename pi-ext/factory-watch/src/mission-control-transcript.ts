import { existsSync, readFileSync, statSync } from "node:fs";
import { Key, matchesKey } from "@earendil-works/pi-tui";
import type { Component } from "@earendil-works/pi-tui";

/** Minimal structural subset of pi-tui's TUI that this component actually needs. */
export interface TuiLike {
  terminal: { rows: number };
}

export class TranscriptViewer implements Component {
  private lines: string[];
  private scrollOffset = 0;
  private followingBottom = false;
  private readonly tui: TuiLike;

  constructor(initialLines: string[], tui: TuiLike) {
    this.lines = initialLines;
    this.tui = tui;
  }

  // No cached render state to drop -- render() always recomputes from
  // `this.lines`, so there is nothing to invalidate. Required by pi-tui's
  // Component interface (non-optional, unlike handleInput) so this can be
  // passed to tui.addChild()/tui.setFocus().
  invalidate(): void {}

  private getViewportHeight(): number {
    return Math.max(1, this.tui.terminal.rows - 2);
  }

  appendLines(newLines: string[]): void {
    const wasAtBottom = this.followingBottom;
    this.lines.push(...newLines);
    if (wasAtBottom) {
      this.scrollOffset = Number.MAX_SAFE_INTEGER;
    }
  }

  handleInput(data: string): void {
    const viewportHeight = this.getViewportHeight();
    if (matchesKey(data, Key.down)) {
      this.scrollOffset += 1;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.up)) {
      this.scrollOffset -= 1;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.pageDown)) {
      this.scrollOffset += viewportHeight;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.pageUp)) {
      this.scrollOffset -= viewportHeight;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.home)) {
      this.scrollOffset = 0;
      this.followingBottom = false;
    } else if (matchesKey(data, Key.end)) {
      this.scrollOffset = Number.MAX_SAFE_INTEGER;
      this.followingBottom = true;
    }
  }

  render(width: number): string[] {
    if (this.lines.length === 0) {
      return ["(not started yet)"];
    }
    const viewportHeight = this.getViewportHeight();
    const maxOffset = Math.max(0, this.lines.length - viewportHeight);
    this.scrollOffset = Math.min(Math.max(0, this.scrollOffset), maxOffset);
    if (this.scrollOffset >= maxOffset) {
      this.followingBottom = true;
    }
    const visible = this.lines.slice(this.scrollOffset, this.scrollOffset + viewportHeight);
    const lastShown = Math.min(this.scrollOffset + viewportHeight, this.lines.length);
    const footer = `-- line ${this.scrollOffset + 1}-${lastShown} of ${this.lines.length} (arrows/PgUp/PgDn/Home/End, q close) --`;
    return [...visible, footer];
  }
}

// Standalone entry point -- no `pi --extension`, no LLM. Polls a transcript
// log file for growth and drives a real pi-tui TUI/ProcessTerminal.
//
// API verified directly against node_modules/@earendil-works/pi-tui/dist/
// {tui,terminal}.d.ts (and the compiled tui.js), mirroring the same
// corrections already made in mission-control-dashboard.ts's main():
//
//   - `TUI.start()` (no args) is the correct call to begin driving the
//     terminal -- it internally does
//     `terminal.start((data) => this.handleInput(data), () => this.requestRender())`
//     and performs the initial render via `requestRender()`. Calling
//     `terminal.start(...)` directly bypasses all of that -- nothing would
//     ever render.
//   - `TUI`'s private `handleInput` only forwards input to
//     `this.focusedComponent`, so `tui.setFocus(viewer)` is required after
//     `addChild` or keypresses would never reach the viewer.
//   - `TUI.invalidate()` only recursively clears cached render state on
//     children -- it does NOT itself trigger a re-render. `requestRender()`
//     is the method that actually schedules a differential re-render, so
//     poll ticks call `requestRender()`, not `invalidate()`.
async function main(): Promise<void> {
  const { ProcessTerminal, TUI } = await import("@earendil-works/pi-tui");
  // indexOf returns -1 when the flag is missing; -1 + 1 = 0 would then read
  // process.argv[0] (the node executable's own path -- a real, defined
  // string), silently defeating the undefined check below. Treat -1
  // explicitly as "not found" instead.
  const pathArgIndex = process.argv.indexOf("--transcript");
  const rawTranscriptPath = pathArgIndex === -1 ? undefined : process.argv[pathArgIndex + 1];
  if (rawTranscriptPath === undefined) {
    console.error("usage: node mission-control-transcript.js --transcript <path>");
    process.exit(1);
  }
  // Re-bind to a variable whose *declared* type is `string` (not
  // `string | undefined`) -- TypeScript's control-flow narrowing from the
  // guard above doesn't survive being read inside the nested
  // readLines/setInterval closures below, since those run at some later,
  // unrelated time.
  const transcriptPath: string = rawTranscriptPath;

  function readLines(): string[] {
    if (!existsSync(transcriptPath)) {
      return [];
    }
    return readFileSync(transcriptPath, "utf-8").split("\n");
  }

  const terminal = new ProcessTerminal();
  const tui = new TUI(terminal);
  const viewer = new TranscriptViewer(readLines(), { terminal: { rows: terminal.rows } });
  tui.addChild(viewer);
  tui.setFocus(viewer);
  tui.start();

  let lastSize = existsSync(transcriptPath) ? statSync(transcriptPath).size : 0;
  setInterval(() => {
    if (!existsSync(transcriptPath)) {
      return;
    }
    const size = statSync(transcriptPath).size;
    if (size > lastSize) {
      // Rough approximation mixing byte-size deltas with line-count slicing
      // -- see the brief's note (task-12-brief.md) for the known rough
      // edge here (a partial last line growing across polls could be
      // double-counted). Left as-is per the brief: flag if visibly wrong
      // in manual testing, don't over-engineer a fix into the initial
      // implementation.
      const allLines = readLines();
      viewer.appendLines(allLines.slice(-Math.max(1, allLines.length - lastSize)));
      lastSize = size;
      tui.requestRender();
    }
  }, 500);
}

if (process.argv[1]?.endsWith("mission-control-transcript.js") || process.argv[1]?.endsWith("mission-control-transcript.ts")) {
  void main();
}
