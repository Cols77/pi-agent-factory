import { describe, expect, test, vi } from "vitest";
import { MissionControlDashboard } from "../src/mission-control-dashboard.js";
import type { PipelineEntry, StatusRecord } from "../src/status-format.js";

const RECORD: StatusRecord = {
  session_id: "s1", task_id: "T-029", current_node: "dev", current_state: "running",
  pipeline: [
    { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: "-> dev", updated_at: "t" },
    { node: "dev", node_state: "running", attempt: 2, max_attempts: 3, snippet: "", outcome: null, handoff: null, updated_at: "t", session_id: "dev-abc" },
  ],
  started_at: "t", updated_at: "t",
};

function withEntry(entry: Partial<PipelineEntry> & { node: string }): StatusRecord {
  const base: PipelineEntry = { node: entry.node, node_state: "pending", attempt: 0, max_attempts: 0, snippet: "", outcome: null, handoff: null, updated_at: "t" };
  return { ...RECORD, pipeline: [...RECORD.pipeline, { ...base, ...entry }] };
}

function down(d: MissionControlDashboard, n: number) {
  for (let i = 0; i < n; i++) {
    d.handleInput("\x1b[B");
  }
}

test("Enter on an agent row resolves inspect with its sessionId", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(RECORD, onAction);
  down(d, 2); // dev row (order: context-gather, grill, dev, ...)
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "inspect", sessionId: "dev-abc" });
});

test("Enter on validation resolves gate-log", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(RECORD, onAction);
  down(d, 3); // validation row
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "gate-log" });
});

test("Enter on human-review resolves review", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(withEntry({ node: "human-review", node_state: "blocked", start_commit: "abc" }), onAction);
  down(d, 5); // human-review row
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "review" });
});

test("Enter on the session-review row resolves inspect with its sessionId", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(withEntry({ node: "session-review", node_state: "pass", session_id: "sr-xyz" }), onAction);
  down(d, 6); // session-review is the last stage row (after human-review)
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "inspect", sessionId: "sr-xyz" });
});

test("q and Ctrl-C resolve quit", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(RECORD, onAction);
  d.handleInput("q");
  d.handleInput("\x03");
  expect(onAction).toHaveBeenNthCalledWith(1, { type: "quit" });
  expect(onAction).toHaveBeenNthCalledWith(2, { type: "quit" });
});

test("renders one row per stage with the task header", () => {
  const d = new MissionControlDashboard(RECORD, () => {});
  const lines = d.render(80).join("\n");
  expect(lines).toContain("T-029");
  expect(lines).toContain("context-gatherer");
  expect(lines).toContain("grill");
  expect(lines).toContain("human-review");
  expect(lines).toContain("session-reviewer");
});

test("a blocked grill renders as a selectable row (not dropped from the pane)", () => {
  const d = new MissionControlDashboard(withEntry({ node: "grill", node_state: "blocked" }), () => {});
  const lines = d.render(80).join("\n");
  expect(lines).toContain("grill");
  expect(lines).toContain("blocked");
});

test("shows a HUMAN REVIEW NEEDED alert when human-review is blocked", () => {
  const d = new MissionControlDashboard(withEntry({ node: "human-review", node_state: "blocked", start_commit: "abc" }), () => {});
  expect(d.render(80).join("\n")).toContain("HUMAN REVIEW NEEDED");
});

test("no alert when human-review is not blocked", () => {
  const d = new MissionControlDashboard(RECORD, () => {});
  expect(d.render(80).join("\n")).not.toContain("HUMAN REVIEW NEEDED");
});

test("Down/Up move the selected row", () => {
  const d = new MissionControlDashboard(RECORD, () => {});
  d.handleInput("\x1b[B");
  d.handleInput("\x1b[B");
  expect(d.render(80).find((l) => l.startsWith("> "))).toContain("developer");
  d.handleInput("\x1b[A");
  d.handleInput("\x1b[A");
  expect(d.render(80).find((l) => l.startsWith("> "))).toContain("context-gatherer");
});

test("updateRecord replaces the displayed data without losing selection", () => {
  const d = new MissionControlDashboard(RECORD, () => {});
  d.handleInput("\x1b[B"); // select "dev"
  const updated: StatusRecord = {
    ...RECORD,
    pipeline: [...RECORD.pipeline, {
      node: "validation", node_state: "pass", attempt: 1, max_attempts: 1,
      snippet: "", outcome: null, handoff: "-> review: sim tests green", updated_at: "t",
    }],
  };
  d.updateRecord(updated);
  expect(d.render(80).join("\n")).toContain("-> review: sim tests green");
});

test("renders the live snippet under a running row", () => {
  const record = { ...RECORD, pipeline: [
    { node: "dev", node_state: "running", attempt: 1, max_attempts: 3, snippet: "grepping for advance_waypoint", outcome: null, handoff: null, updated_at: "t" },
  ] } as typeof RECORD;
  const lines = new MissionControlDashboard(record, () => {}).render(80).join("\n");
  expect(lines).toContain("grepping for advance_waypoint");
});

test("does not render a snippet for a non-running row", () => {
  const record = { ...RECORD, pipeline: [
    { node: "dev", node_state: "pass", attempt: 1, max_attempts: 3, snippet: "should not show", outcome: null, handoff: "→ validation", updated_at: "t" },
  ] } as typeof RECORD;
  const lines = new MissionControlDashboard(record, () => {}).render(80).join("\n");
  expect(lines).not.toContain("should not show");
});

test("render() prints a row's summary (width-wrapped)", () => {
  const record: StatusRecord = {
    ...RECORD,
    pipeline: [
      {
        ...RECORD.pipeline[0]!,
        summary: "Reviewed three files and found no blocking issues in the change.",
      },
      RECORD.pipeline[1]!,
    ],
  };
  const d = new MissionControlDashboard(record, () => {});
  const lines = d.render(40);
  expect(lines.join("\n")).toContain("Reviewed three files");
  // width-wrapped: no rendered line should blow past the given width.
  for (const line of lines) {
    expect(line.length).toBeLessThanOrEqual(40);
  }
});

function escalatedDevRecord(): StatusRecord {
  return {
    session_id: "s1", task_id: "T-029", current_node: "dev", current_state: "escalate",
    pipeline: [
      { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: "-> dev", updated_at: "t" },
      { node: "dev", node_state: "escalate", attempt: 3, max_attempts: 3, snippet: "", outcome: "escalated", handoff: "escalated: unit tests still red", updated_at: "t", session_id: "dev-abc" },
    ],
    started_at: "t", updated_at: "t",
  };
}

test("Enter on an escalated dev row resolves pair-dev with its sessionId", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(escalatedDevRecord(), onAction);
  down(d, 2); // dev row
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "pair-dev", sessionId: "dev-abc" });
});

test("Enter on a running dev row still resolves inspect (not pair-dev)", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(RECORD, onAction);
  down(d, 2); // dev row (RECORD has dev running)
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "inspect", sessionId: "dev-abc" });
});

test("shows a DEV STUCK alert when dev is escalated", () => {
  const d = new MissionControlDashboard(escalatedDevRecord(), () => {});
  expect(d.render(80).join("\n")).toContain("DEV STUCK");
});

test("no DEV STUCK alert when dev is not escalated", () => {
  const d = new MissionControlDashboard(RECORD, () => {});
  expect(d.render(80).join("\n")).not.toContain("DEV STUCK");
});

test("shows each stage's dynamic activity, not a static description", () => {
  const lines = new MissionControlDashboard(escalatedDevRecord(), () => {}).render(80).join("\n");
  // developer escalated -> its real handoff text is surfaced
  expect(lines).toContain("escalated: unit tests still red");
  // a stage that hasn't run shows a dynamic waiting hint, not a job description
  expect(lines).toContain("waiting to start");
});

test("applies theme colors to state/title when a theme is provided", () => {
  const theme = {
    fg: (color: string, text: string) => `<${color}>${text}</${color}>`,
    bold: (text: string) => `*${text}*`,
  };
  const lines = new MissionControlDashboard(escalatedDevRecord(), () => {}, theme)
    .render(80)
    .join("\n");
  expect(lines).toContain("*Factory Mission Control*"); // title is bold
  expect(lines).toContain("<warning>"); // escalated dev state colored warning
  expect(lines).toContain("<muted>"); // activity lines are muted
});

test("a running dev with a junk ':' snippet shows the activity, not the noise", () => {
  const record: StatusRecord = {
    session_id: "s1", task_id: "T-042", current_node: "dev", current_state: "running",
    pipeline: [
      { node: "dev", node_state: "running", attempt: 1, max_attempts: 3, snippet: ":", outcome: null, handoff: null, updated_at: "t", session_id: "dev-abc" },
    ],
    started_at: "t", updated_at: "t",
  };
  const lines = new MissionControlDashboard(record, () => {}).render(80).join("\n");
  expect(lines).toContain("working… (attempt 1/3)"); // real activity shown
  expect(lines).not.toContain("… :"); // the lone-colon fragment is filtered out
});

test("every rendered line respects the given width", () => {
  const lines = new MissionControlDashboard(escalatedDevRecord(), () => {}).render(48);
  for (const line of lines) {
    expect(line.length).toBeLessThanOrEqual(48);
  }
});
