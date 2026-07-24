import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Component } from "@earendil-works/pi-tui";
import { wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { formatMissionControlRows, parseStatus } from "./status-format.ts";
import type { StatusRecord } from "./status-format.ts";
import { resolveSessionPath } from "./session-path.ts";
import { spawnTerminalWindow } from "./terminal-window.ts";

const STAGE_ORDER = ["context-gather", "dev", "validation", "review", "human-review"];
const POLL_INTERVAL_MS = 500;

// Pipeline nodes whose `sessionId` (Task 7) is a real pi agent session --
// Enter on one of these opens the live session in a new `pi --session`
// window rather than tailing a log or opening the review browser.
// "session-review" isn't in STAGE_ORDER today, but is included per the
// brief for forward compatibility with a future stage of that name.
const AGENT_NODES = new Set(["context-gather", "dev", "review", "session-review"]);

const SESSION_NOT_READY_MESSAGE = "session not ready";

export class MissionControlDashboard implements Component {
  private selectedIndex = 0;
  private record: StatusRecord | null;
  private readonly cwd: string;
  // Transient inline feedback surfaced in render() (e.g. "session not
  // ready") when an Enter dispatch can't spawn anything yet. Cleared the
  // next time a dispatch succeeds.
  private statusMessage: string | null = null;

  constructor(record: StatusRecord | null, cwd: string) {
    this.record = record;
    this.cwd = cwd;
  }

  updateRecord(record: StatusRecord | null): void {
    this.record = record;
  }

  // No cached render state to drop -- render() always recomputes from
  // `this.record`, so there is nothing to invalidate. Required by pi-tui's
  // Component interface so this can be passed to tui.addChild().
  invalidate(): void {}

  private openAgentSession(sessionId: string | null): void {
    const path = sessionId === null ? null : resolveSessionPath(sessionId);
    if (path === null) {
      this.statusMessage = SESSION_NOT_READY_MESSAGE;
      return;
    }
    this.statusMessage = null;
    spawnTerminalWindow("pi", ["--session", path], { cwd: this.cwd });
  }

  // The gate log lives under the top-level factory run id (record.session_id
  // -- the same directory write_role_transcript/the orchestrator use for
  // .factory-transcripts/<id>/), NOT the row's own pi sessionId.
  private tailGateLog(factoryRunId: string): void {
    const logPath = join(this.cwd, "sessions", ".factory-transcripts", factoryRunId, "sim-gate.log");
    this.statusMessage = null;
    if (process.platform === "win32") {
      spawnTerminalWindow(
        "powershell",
        ["-NoExit", "-Command", `Get-Content '${logPath}' -Wait -Tail 40`],
        { cwd: this.cwd },
      );
    } else {
      spawnTerminalWindow("tail", ["-f", logPath], { cwd: this.cwd });
    }
  }

  private openReviewBrowser(startCommit: string | null): void {
    if (startCommit === null) {
      this.statusMessage = SESSION_NOT_READY_MESSAGE;
      return;
    }
    this.statusMessage = null;
    // Note: this.record is guaranteed to be non-null here because handleEnter()
    // checks this.record !== null before calling any dispatch method.
    const taskId = this.record!.task_id;
    const sessionId = this.record!.session_id;
    spawnTerminalWindow(
      "node",
      [
        join(this.cwd, "pi-ext", "factory-watch", "src", "mission-control-review.ts"),
        "--cwd",
        this.cwd,
        "--start-commit",
        startCommit,
        "--task-id",
        taskId,
        "--session-id",
        sessionId,
      ],
      { cwd: this.cwd },
    );
  }

  private handleEnter(): void {
    if (this.record === null) {
      return;
    }
    const rows = formatMissionControlRows(this.record, STAGE_ORDER);
    const row = rows[this.selectedIndex]!;
    if (AGENT_NODES.has(row.node)) {
      this.openAgentSession(row.sessionId);
    } else if (row.node === "validation") {
      this.tailGateLog(this.record.session_id);
    } else if (row.node === "human-review") {
      this.openReviewBrowser(row.startCommit);
    }
  }

  handleInput(data: string): void {
    const rows = formatMissionControlRows(this.record, STAGE_ORDER);
    if (data === "\x1b[B" || data === "j") {
      this.selectedIndex = Math.min(this.selectedIndex + 1, rows.length - 1);
    } else if (data === "\x1b[A" || data === "k") {
      this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
    } else if (data === "\r" || data === "\n") {
      this.handleEnter();
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
      if (row.summary) {
        for (const wrapped of wrapTextWithAnsi(row.summary, Math.max(1, width - 4))) {
          lines.push(`    ${wrapped}`);
        }
      }
    });
    if (this.statusMessage !== null) {
      lines.push("", this.statusMessage);
    }
    lines.push("", "up/down select  Enter open  q close");
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
  const dashboard = new MissionControlDashboard(readRecord(), cwd);
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
