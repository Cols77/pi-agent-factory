import { wrapTextWithAnsi, truncateToWidth } from "@earendil-works/pi-tui";
import type { Component } from "@earendil-works/pi-tui";
import {
  formatMissionControlRows,
  devEscalated,
  nodeActivity,
  isSubstantiveSnippet,
  iconForState,
  producerLabel,
  resumeCommand,
  obligationResolveCommands,
} from "./status-format.ts";
import type { StatusRecord, RunStatus, RunStatusesPayload } from "./status-format.ts";
import { stageOrder, isAgentNode } from "./node-registry.js";

// Minimal structural subset of pi's real Theme (fg/bold) this dashboard uses.
// Pi passes the real Theme into the ctx.ui.custom() factory; it is structurally
// assignable here (method params are checked bivariantly). Tests construct the
// dashboard without a theme and get PLAIN_THEME, so rendered output stays
// un-ANSI'd and their plain-substring assertions keep working.
export interface DashboardTheme {
  fg(color: string, text: string): string;
  bold(text: string): string;
}

const PLAIN_THEME: DashboardTheme = { fg: (_color, text) => text, bold: (text) => text };

// Map a node_state to a semantic theme color name.
function colorForState(state: string): string {
  switch (state) {
    case "pass":
      return "success";
    case "fail":
    case "reject":
    case "error":
      return "error";
    case "escalate":
    case "blocked":
    case "changes-requested":
      return "warning";
    case "running":
      return "accent";
    case "pending":
      return "dim";
    default:
      return "text";
  }
}

export type MissionControlAction =
  | { type: "inspect"; sessionId: string | null }
  | { type: "gate-log" }
  | { type: "review" }
  | { type: "pair-dev"; sessionId: string }
  | { type: "quit" };

export class MissionControlDashboard implements Component {
  private selectedIndex = 0;
  private record: StatusRecord | null;
  private readonly onAction: (action: MissionControlAction) => void;
  private readonly theme: DashboardTheme;

  constructor(
    record: StatusRecord | null,
    onAction: (action: MissionControlAction) => void,
    theme: DashboardTheme = PLAIN_THEME,
  ) {
    this.record = record;
    this.onAction = onAction;
    this.theme = theme;
  }

  updateRecord(record: StatusRecord | null): void {
    this.record = record;
  }

  invalidate(): void {}

  private handleEnter(): void {
    if (this.record === null) return;
    const row = formatMissionControlRows(this.record, stageOrder())[this.selectedIndex]!;
    const escalated = devEscalated(this.record);
    if (row.node === "dev" && escalated !== null) {
      this.onAction({ type: "pair-dev", sessionId: escalated.sessionId });
    } else if (isAgentNode(row.node)) {
      this.onAction({ type: "inspect", sessionId: row.sessionId });
    } else if (row.node === "validation") {
      this.onAction({ type: "gate-log" });
    } else if (row.node === "human-review") {
      this.onAction({ type: "review" });
    }
  }

  handleInput(data: string): void {
    const rows = formatMissionControlRows(this.record, stageOrder());
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
    const t = this.theme;
    const taskId = this.record?.task_id ?? "(no task)";
    const lines: string[] = [];
    lines.push(t.bold("Factory Mission Control") + t.fg("dim", ` · ${taskId}`), "");

    const hrBlocked = (this.record?.pipeline ?? []).some(
      (e) => e.node === "human-review" && e.node_state === "blocked",
    );
    if (hrBlocked) {
      for (const w of wrapTextWithAnsi("⚠ HUMAN REVIEW NEEDED — select human-review and press Enter", width)) {
        lines.push(t.fg("warning", w));
      }
      lines.push("");
    }
    if (devEscalated(this.record)) {
      for (const w of wrapTextWithAnsi(
        "⚠ DEV STUCK — select developer and press Enter to pair, then re-run the task",
        width,
      )) {
        lines.push(t.fg("warning", w));
      }
      lines.push("");
    }

    const INDENT = "    ";
    const bodyWidth = Math.max(1, width - INDENT.length);
    formatMissionControlRows(this.record, stageOrder()).forEach((row, i) => {
      const selected = i === this.selectedIndex;
      const marker = selected ? "> " : "  ";
      const stateColor = colorForState(row.state);
      const icon = t.fg(stateColor, iconForState(row.state));
      const labelCell = row.label.padEnd(16);
      const label = selected ? t.bold(labelCell) : t.fg("text", labelCell);
      // Header: marker · status icon · agent name · state (icon+state colored
      // by state; the selected row's name is bold).
      lines.push(truncateToWidth(`${marker}${icon} ${label} ${t.fg(stateColor, row.state)}`, width));

      // Dynamic activity: what the stage is doing now / finished and handed
      // off. Always shown -- it is the primary "what's happening" line.
      const activity = nodeActivity(row);
      if (activity) {
        for (const w of wrapTextWithAnsi(`↳ ${activity}`, bodyWidth)) lines.push(INDENT + t.fg("muted", w));
      }
      // Live output preview for a running node -- only when the streamed
      // snippet is substantive (Pi often streams a lone ":" during tool calls,
      // which is noise; isSubstantiveSnippet filters it out).
      if (row.state === "running" && isSubstantiveSnippet(row.snippet)) {
        const last = row.snippet!.split("\n").map((s) => s.trim()).filter(Boolean).pop() ?? "";
        if (last) lines.push(truncateToWidth(INDENT + t.fg("dim", `… ${last}`), width));
      }
      // The concrete output a finished stage produced, when it adds detail
      // beyond the activity line above.
      if (row.summary && !activity.includes(row.summary)) {
        for (const w of wrapTextWithAnsi(row.summary, bodyWidth)) lines.push(INDENT + t.fg("dim", w));
      }
    });

    lines.push("", t.fg("dim", "↑/↓ move · Enter open · q close"));
    return lines;
  }
}

// ---------------------------------------------------------------------------
// Run status dashboard (Increment 7) — renders the unified `serialize_run_statuses`
// payload (`{"runs": [...]}`). Each row is a RUN source, not a pipeline stage,
// discriminated by `producer` (factory | audit | measurement | simulation |
// experiment). The renderer:
//   * labels each run by its producer (source-specific rows);
//   * renders a resume control ONLY when `resume_cmd` is a non-empty string —
//     never "undefined", an empty command, or a stale previous value;
//   * renders the obligation plus each resolve-command array item as its own
//     command item (never joined into a shell string, never executed);
//   * keeps `blocking_obligation_resolve_cmd` (the obligation's resolve tuple)
//     distinct from `resume_cmd` (the native-run resume) -- either may be
//     present without the other.
// ---------------------------------------------------------------------------
export type MissionControlRunAction =
  | { type: "resume"; run: RunStatus }
  | { type: "quit" };

export class RunStatusDashboard implements Component {
  private selectedIndex = 0;
  private payload: RunStatusesPayload | null;
  private readonly onAction: (action: MissionControlRunAction) => void;
  private readonly theme: DashboardTheme;

  constructor(
    payload: RunStatusesPayload | null,
    onAction: (action: MissionControlRunAction) => void,
    theme: DashboardTheme = PLAIN_THEME,
  ) {
    this.payload = payload;
    this.onAction = onAction;
    this.theme = theme;
  }

  update(payload: RunStatusesPayload | null): void {
    this.payload = payload;
  }

  invalidate(): void {}

  private handleEnter(): void {
    const runs = this.payload?.runs ?? [];
    const run = runs[this.selectedIndex];
    if (run === undefined) return;
    if (resumeCommand(run) !== null) {
      this.onAction({ type: "resume", run });
    }
  }

  handleInput(data: string): void {
    const count = this.payload?.runs.length ?? 0;
    if (data === "\x1b[B" || data === "j") {
      this.selectedIndex = Math.min(this.selectedIndex + 1, Math.max(0, count - 1));
    } else if (data === "\x1b[A" || data === "k") {
      this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
    } else if (data === "\r" || data === "\n") {
      this.handleEnter();
    } else if (data === "q" || data === "\x03") {
      this.onAction({ type: "quit" });
    }
  }

  render(width: number): string[] {
    const t = this.theme;
    const lines: string[] = [];
    lines.push(t.bold("Mission Control") + t.fg("dim", " · runs"), "");
    if (this.payload === null || this.payload.runs.length === 0) {
      lines.push(t.fg("dim", "no runs yet"));
      return lines;
    }

    const INDENT = "    ";
    const bodyWidth = Math.max(1, width - INDENT.length);
    this.payload.runs.forEach((run, i) => {
      const selected = i === this.selectedIndex;
      const marker = selected ? "> " : "  ";
      const stateColor = colorForState(run.state);
      const icon = t.fg(stateColor, iconForState(run.state));
      const labelCell = producerLabel(run.producer).padEnd(14);
      const label = selected ? t.bold(labelCell) : t.fg("text", labelCell);
      lines.push(
        truncateToWidth(`${marker}${icon} [${label} ${t.fg(stateColor, run.state)}] ${run.run_id}`, width),
      );

      // Obligation + its resolve commands (each array item a separate command
      // item; rendered independently of the resume control below).
      if (run.blocking_obligation) {
        for (const w of wrapTextWithAnsi(`obligation: ${run.blocking_obligation}`, bodyWidth)) {
          lines.push(INDENT + t.fg("warning", w));
        }
        for (const cmd of obligationResolveCommands(run)) {
          for (const w of wrapTextWithAnsi(`resolve: ${cmd}`, bodyWidth)) {
            lines.push(INDENT + t.fg("muted", `↳ ${w}`));
          }
        }
      }

      // Resume control ONLY when a real resume command is present. When
      // `resume_cmd` is null, we render nothing here -- no label, no control,
      // and never a stale/empty/"undefined" value.
      const resume = resumeCommand(run);
      if (resume !== null) {
        for (const w of wrapTextWithAnsi(`resume: ${resume}`, bodyWidth)) {
          lines.push(INDENT + t.fg("accent", w));
        }
      }

      if (run.rerun_allowed) lines.push(INDENT + t.fg("dim", "rerun allowed"));
    });

    lines.push("", t.fg("dim", "↑/↓ move · Enter resume · q close"));
    return lines;
  }
}
