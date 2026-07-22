import { readFileSync } from "node:fs";
import type { Component } from "@earendil-works/pi-tui";
import { formatMissionControlRows, parseStatus } from "./status-format.js";
import type { StatusRecord } from "./status-format.js";

const STAGE_ORDER = ["context-gather", "dev", "validation", "review", "human-review"];
const POLL_INTERVAL_MS = 500;

export class MissionControlDashboard implements Component {
  private selectedIndex = 0;

  constructor(
    private record: StatusRecord | null,
    private readonly onSelectTranscript: (node: string, sessionId: string) => void,
  ) {}

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
  const statusPathArgIndex = process.argv.indexOf("--status");
  const rawStatusPath = process.argv[statusPathArgIndex + 1];
  if (rawStatusPath === undefined) {
    console.error("usage: node mission-control-dashboard.js --status <path> --cwd <repo-root>");
    process.exit(1);
  }
  // Re-bind to a variable whose *declared* type is `string` (not `string |
  // undefined`) -- TypeScript's control-flow narrowing from the guard above
  // doesn't survive being read inside the nested `readRecord`/setInterval
  // closures below, since those run at some later, unrelated time.
  const statusPath: string = rawStatusPath;

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
    // Wire to terminal-window.ts's spawnTerminalWindow + mission-control-transcript.ts
    // in Task 13, once index.ts's spawn call sites are established.
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
