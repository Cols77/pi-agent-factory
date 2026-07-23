import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Component } from "@earendil-works/pi-tui";
import { formatMissionControlRows, parseStatus } from "./status-format.ts";
import type { StatusRecord } from "./status-format.ts";
import { spawnTerminalWindow } from "./terminal-window.ts";

const STAGE_ORDER = ["context-gather", "dev", "validation", "review", "human-review"];
const POLL_INTERVAL_MS = 500;

// Attempt 1 is a reasonable default -- the dashboard doesn't currently track
// which attempt is "current" for a stage, and the transcript viewer's own
// poll loop will pick up growth if the file doesn't exist yet. Stages with
// no agent transcript (e.g. "validation", "human-review") simply resolve to
// a path that never exists; TranscriptViewer already renders a graceful
// "(not started yet)" placeholder for that case.
export function buildTranscriptPath(cwd: string, sessionId: string, node: string): string {
  return join(cwd, "sessions", ".factory-transcripts", sessionId, `${node}-attempt1.log`);
}

export class MissionControlDashboard implements Component {
  private selectedIndex = 0;
  private record: StatusRecord | null;
  private readonly onSelectTranscript: (node: string, sessionId: string) => void;

  constructor(
    record: StatusRecord | null,
    onSelectTranscript: (node: string, sessionId: string) => void,
  ) {
    this.record = record;
    this.onSelectTranscript = onSelectTranscript;
  }

  updateRecord(record: StatusRecord | null): void {
    this.record = record;
  }

  // No cached render state to drop -- render() always recomputes from
  // `this.record`, so there is nothing to invalidate. Required by pi-tui's
  // Component interface so this can be passed to tui.addChild().
  invalidate(): void {}

  handleInput(data: string): void {
    const rows = formatMissionControlRows(this.record, STAGE_ORDER);
    if (data === "\x1b[B" || data === "j") {
      this.selectedIndex = Math.min(this.selectedIndex + 1, rows.length - 1);
    } else if (data === "\x1b[A" || data === "k") {
      this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
    } else if ((data === "\r" || data === "\n") && this.record !== null) {
      this.onSelectTranscript(rows[this.selectedIndex]!.node, this.record.session_id);
    }
  }

  render(width: number): string[] {
    const taskId = this.record?.task_id ?? "(no task)";
    const lines = [`Factory Mission Control — ${taskId}`, ""];
    const rows = formatMissionControlRows(this.record, STAGE_ORDER);
    rows.forEach((row, i) => {
      const prefix = i === this.selectedIndex ? "> " : "  ";
      lines.push(`${prefix}${row.label.padEnd(16)} ${row.state}`);
      if (row.handoff) {
        lines.push(`    ${row.handoff}`);
      }
    });
    lines.push("", "up/down select  Enter open transcript  q close");
    return lines;
  }
}

// Standalone entry point -- no `pi --extension`, no LLM. Polls a status file
// and drives a real pi-tui TUI/ProcessTerminal.
//
// API verified directly against node_modules/@earendil-works/pi-tui/dist/
// {tui,terminal}.d.ts (and the compiled tui.js) rather than assumed:
//
//   - `TUI.start()` (no args) is the correct call to begin driving the
//     terminal. It internally does
//     `terminal.start((data) => this.handleInput(data), () => this.requestRender())`,
//     hides the cursor, queries cell size, and performs the initial render
//     via `this.requestRender()`. Calling `terminal.start(...)` directly (as
//     an earlier sketch of this entry point did) bypasses all of that --
//     nothing would ever render, because there'd be no initial
//     `requestRender()` call.
//   - `TUI`'s private `handleInput` only forwards input to
//     `this.focusedComponent`, so `tui.setFocus(dashboard)` is required after
//     `addChild` or keypresses would never reach the dashboard.
//   - `TUI.invalidate()` only recursively clears cached render state on
//     children (a no-op for this component, which caches nothing) -- it does
//     NOT itself trigger a re-render. `TUI.requestRender()` is the method
//     that actually schedules a differential re-render, so poll ticks call
//     `requestRender()`, not `invalidate()`.
async function main(): Promise<void> {
  const { ProcessTerminal, TUI } = await import("@earendil-works/pi-tui");
  // indexOf returns -1 when the flag is missing; -1 + 1 = 0 would then read
  // process.argv[0] (the node executable's own path -- a real, defined
  // string), silently defeating the undefined check below. Treat -1
  // explicitly as "not found" instead.
  const statusPathArgIndex = process.argv.indexOf("--status");
  const rawStatusPath = statusPathArgIndex === -1 ? undefined : process.argv[statusPathArgIndex + 1];
  const cwdArgIndex = process.argv.indexOf("--cwd");
  const rawCwd = cwdArgIndex === -1 ? undefined : process.argv[cwdArgIndex + 1];
  if (rawStatusPath === undefined || rawCwd === undefined) {
    console.error("usage: node mission-control-dashboard.js --status <path> --cwd <repo-root>");
    process.exit(1);
  }
  // Re-bind to variables whose *declared* type is `string` (not `string |
  // undefined`) -- TypeScript's control-flow narrowing from the guard above
  // doesn't survive being read inside the nested `readRecord`/setInterval
  // closures below, since those run at some later, unrelated time.
  const statusPath: string = rawStatusPath;
  const cwd: string = rawCwd;

  function readRecord(): StatusRecord | null {
    try {
      return parseStatus(readFileSync(statusPath, "utf-8"));
    } catch {
      return null;
    }
  }

  const terminal = new ProcessTerminal();
  const tui = new TUI(terminal);
  const dashboard = new MissionControlDashboard(readRecord(), (node, sessionId) => {
    const transcriptPath = buildTranscriptPath(cwd, sessionId, node);
    spawnTerminalWindow(
      "node",
      [join(cwd, "pi-ext", "factory-watch", "src", "mission-control-transcript.ts"), "--transcript", transcriptPath],
      { cwd },
    );
  });
  tui.addChild(dashboard);
  tui.setFocus(dashboard);
  tui.start();
  setInterval(() => {
    dashboard.updateRecord(readRecord());
    tui.requestRender();
  }, POLL_INTERVAL_MS);
}

if (process.argv[1]?.endsWith("mission-control-dashboard.js") || process.argv[1]?.endsWith("mission-control-dashboard.ts")) {
  void main();
}
