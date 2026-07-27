import { wrapTextWithAnsi } from "@earendil-works/pi-tui";
import type { Component } from "@earendil-works/pi-tui";
import { formatMissionControlRows } from "./status-format.ts";
import type { StatusRecord } from "./status-format.ts";

const STAGE_ORDER = ["context-gather", "dev", "validation", "review", "human-review", "session-review"];
const AGENT_NODES = new Set(["context-gather", "dev", "review", "session-review"]);

export type MissionControlAction =
  | { type: "inspect"; sessionId: string | null }
  | { type: "gate-log" }
  | { type: "review" }
  | { type: "quit" };

export class MissionControlDashboard implements Component {
  private selectedIndex = 0;
  private record: StatusRecord | null;
  private readonly onAction: (action: MissionControlAction) => void;

  constructor(record: StatusRecord | null, onAction: (action: MissionControlAction) => void) {
    this.record = record;
    this.onAction = onAction;
  }

  updateRecord(record: StatusRecord | null): void {
    this.record = record;
  }

  invalidate(): void {}

  private handleEnter(): void {
    if (this.record === null) return;
    const row = formatMissionControlRows(this.record, STAGE_ORDER)[this.selectedIndex]!;
    if (AGENT_NODES.has(row.node)) {
      this.onAction({ type: "inspect", sessionId: row.sessionId });
    } else if (row.node === "validation") {
      this.onAction({ type: "gate-log" });
    } else if (row.node === "human-review") {
      this.onAction({ type: "review" });
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
    } else if (data === "q" || data === "\x03") {
      this.onAction({ type: "quit" });
    }
  }

  render(width: number): string[] {
    const taskId = this.record?.task_id ?? "(no task)";
    const lines = [`Factory Mission Control — ${taskId}`, ""];
    const hrBlocked = (this.record?.pipeline ?? []).some(
      (e) => e.node === "human-review" && e.node_state === "blocked",
    );
    if (hrBlocked) lines.push("⚠ HUMAN REVIEW NEEDED — select human-review and press Enter", "");
    formatMissionControlRows(this.record, STAGE_ORDER).forEach((row, i) => {
      const prefix = i === this.selectedIndex ? "> " : "  ";
      lines.push(`${prefix}${row.label.padEnd(16)} ${row.state}`);
      if (row.handoff) lines.push(`    ${row.handoff}`);
      if (row.summary) {
        for (const wrapped of wrapTextWithAnsi(row.summary, Math.max(1, width - 4))) lines.push(`    ${wrapped}`);
      }
    });
    lines.push("", "up/down select  Enter open  q close");
    return lines;
  }
}
