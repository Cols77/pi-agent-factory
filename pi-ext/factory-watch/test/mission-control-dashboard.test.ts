import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { MissionControlDashboard } from "../src/mission-control-dashboard.js";
import { resolveSessionPath } from "../src/session-path.js";
import { spawnTerminalWindow } from "../src/terminal-window.js";
import type { PipelineEntry, StatusRecord } from "../src/status-format.js";

vi.mock("../src/terminal-window.js", () => ({
  spawnTerminalWindow: vi.fn(),
}));

vi.mock("../src/session-path.js", () => ({
  resolveSessionPath: vi.fn(),
}));

const RECORD: StatusRecord = {
  session_id: "s1", task_id: "T-029", current_node: "dev", current_state: "running",
  pipeline: [
    { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: "-> dev: 3 files, coherence=yes", updated_at: "2026-07-22T00:00:00Z" },
    { node: "dev", node_state: "running", attempt: 2, max_attempts: 3, snippet: "", outcome: null, handoff: null, updated_at: "2026-07-22T00:00:01Z", session_id: "dev-session-abc" },
  ],
  started_at: "2026-07-22T00:00:00Z", updated_at: "2026-07-22T00:00:01Z",
};

// STAGE_ORDER (mission-control-dashboard.ts) is
// ["context-gather", "dev", "validation", "review", "human-review"] --
// formatMissionControlRows always emits one row per stage regardless of
// whether the record's pipeline has an entry for it, so row indices below
// are stable across every test in this file.
function withPipelineEntry(entry: Partial<PipelineEntry> & { node: string }): StatusRecord {
  const base: PipelineEntry = {
    node: entry.node, node_state: "pending", attempt: 0, max_attempts: 0,
    snippet: "", outcome: null, handoff: null, updated_at: "2026-07-22T00:00:02Z",
  };
  return { ...RECORD, pipeline: [...RECORD.pipeline, { ...base, ...entry }] };
}

function moveDown(dashboard: MissionControlDashboard, times: number): void {
  for (let i = 0; i < times; i++) {
    dashboard.handleInput("\x1b[B");
  }
}

beforeEach(() => {
  vi.mocked(spawnTerminalWindow).mockClear();
  vi.mocked(resolveSessionPath).mockReset();
});

describe("MissionControlDashboard", () => {
  test("renders one row per pipeline stage with the task header", () => {
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    const lines = dashboard.render(80).join("\n");
    expect(lines).toContain("T-029");
    expect(lines).toContain("context-gatherer");
    expect(lines).toContain("dev");
    expect(lines).toContain("validation");
    expect(lines).toContain("review");
    expect(lines).toContain("human-review");
  });

  test("Down/Up move the selected row", () => {
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    dashboard.handleInput("\x1b[B");
    expect(dashboard.render(80).find((l) => l.startsWith("> "))).toContain("developer");
    dashboard.handleInput("\x1b[A");
    expect(dashboard.render(80).find((l) => l.startsWith("> "))).toContain("context-gatherer");
  });

  test("updateRecord replaces the displayed data without losing selection", () => {
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    dashboard.handleInput("\x1b[B"); // select "dev"
    const updated: StatusRecord = {
      ...RECORD,
      pipeline: [...RECORD.pipeline, {
        node: "validation", node_state: "pass", attempt: 1, max_attempts: 1,
        snippet: "", outcome: null, handoff: "-> review: sim tests green", updated_at: "2026-07-22T00:00:02Z",
      }],
    };
    dashboard.updateRecord(updated);
    expect(dashboard.render(80).join("\n")).toContain("-> review: sim tests green");
  });

  test("q invokes the onQuit callback so the standalone window can close", () => {
    const onQuit = vi.fn();
    const dashboard = new MissionControlDashboard(RECORD, "/repo", onQuit);
    dashboard.handleInput("q");
    expect(onQuit).toHaveBeenCalledTimes(1);
  });

  test("Ctrl-C also invokes onQuit", () => {
    const onQuit = vi.fn();
    const dashboard = new MissionControlDashboard(RECORD, "/repo", onQuit);
    dashboard.handleInput("\x03");
    expect(onQuit).toHaveBeenCalledTimes(1);
  });

  test("q without an onQuit callback is a no-op (doesn't throw)", () => {
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    expect(() => dashboard.handleInput("q")).not.toThrow();
  });

  test("render() prints a row's summary (width-wrapped) under its handoff line", () => {
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
    const dashboard = new MissionControlDashboard(record, "/repo");
    const lines = dashboard.render(40);
    expect(lines.join("\n")).toContain("Reviewed three files");
    // width-wrapped: no rendered line should blow past the given width.
    for (const line of lines) {
      expect(line.length).toBeLessThanOrEqual(40);
    }
  });
});

describe("Enter dispatch: agent rows (context-gather/dev/review/session-review)", () => {
  test("Enter on a dev row with a resolvable sessionId opens `pi --session <resolved path>`", () => {
    vi.mocked(resolveSessionPath).mockReturnValue(
      join("/home", "user", ".pi", "agent", "sessions", "proj", "x_dev-session-abc.jsonl"),
    );
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    moveDown(dashboard, 1); // "dev" row (index 1)
    dashboard.handleInput("\r");

    expect(resolveSessionPath).toHaveBeenCalledWith("dev-session-abc");
    expect(spawnTerminalWindow).toHaveBeenCalledWith(
      "pi",
      ["--session", join("/home", "user", ".pi", "agent", "sessions", "proj", "x_dev-session-abc.jsonl")],
      { cwd: "/repo" },
    );
  });

  test("Enter on an agent row whose session isn't resolvable yet shows an inline message instead of spawning", () => {
    vi.mocked(resolveSessionPath).mockReturnValue(null);
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    moveDown(dashboard, 1); // "dev" row, has a sessionId but resolveSessionPath fails
    dashboard.handleInput("\r");

    expect(spawnTerminalWindow).not.toHaveBeenCalled();
    expect(dashboard.render(80).join("\n")).toContain("session not ready");
  });

  test("Enter on an agent row with no sessionId at all shows the inline message without crashing", () => {
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    dashboard.handleInput("\r"); // "context-gather" row (index 0) has no session_id in RECORD
    expect(spawnTerminalWindow).not.toHaveBeenCalled();
    expect(resolveSessionPath).not.toHaveBeenCalled();
    expect(dashboard.render(80).join("\n")).toContain("session not ready");
  });
});

describe("Enter dispatch: validation (tail the gate log)", () => {
  const originalPlatform = process.platform;

  afterEach(() => {
    Object.defineProperty(process, "platform", { value: originalPlatform });
  });

  test("win32 tails the gate log via `Get-Content -Wait`", () => {
    Object.defineProperty(process, "platform", { value: "win32" });
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    moveDown(dashboard, 2); // "validation" row (index 2)
    dashboard.handleInput("\r");

    const expectedLog = join("/repo", "sessions", ".factory-transcripts", "s1", "sim-gate.log");
    expect(spawnTerminalWindow).toHaveBeenCalledWith(
      "powershell",
      ["-NoExit", "-Command", `Get-Content '${expectedLog}' -Wait -Tail 40`],
      { cwd: "/repo" },
    );
  });

  test("non-win32 tails the gate log via `tail -f`", () => {
    Object.defineProperty(process, "platform", { value: "linux" });
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    moveDown(dashboard, 2); // "validation" row (index 2)
    dashboard.handleInput("\r");

    const expectedLog = join("/repo", "sessions", ".factory-transcripts", "s1", "sim-gate.log");
    expect(spawnTerminalWindow).toHaveBeenCalledWith("tail", ["-f", expectedLog], { cwd: "/repo" });
  });

  test("the gate log path is built from the top-level record.session_id, not a row's pi sessionId", () => {
    Object.defineProperty(process, "platform", { value: "linux" });
    // The "dev" row carries its own pi sessionId ("dev-session-abc"); the
    // validation tail must ignore that and use the top-level factory run id
    // ("s1") instead, since that's the directory write_role_transcript/the
    // orchestrator actually write sim-gate.log under.
    const dashboard = new MissionControlDashboard(RECORD, "/repo");
    moveDown(dashboard, 2);
    dashboard.handleInput("\r");

    const expectedLog = join("/repo", "sessions", ".factory-transcripts", "s1", "sim-gate.log");
    expect(spawnTerminalWindow).toHaveBeenCalledWith("tail", ["-f", expectedLog], { cwd: "/repo" });
  });
});

describe("Enter dispatch: human-review (open the review browser)", () => {
  test("Enter on human-review with a startCommit spawns mission-control-review.ts", () => {
    const record = withPipelineEntry({ node: "human-review", node_state: "blocked", start_commit: "abc123" });
    const dashboard = new MissionControlDashboard(record, "/repo");
    moveDown(dashboard, 4); // "human-review" row (index 4)
    dashboard.handleInput("\r");

    expect(spawnTerminalWindow).toHaveBeenCalledWith(
      "node",
      [
        join("/repo", "pi-ext", "factory-watch", "src", "mission-control-review.ts"),
        "--cwd",
        "/repo",
        "--start-commit",
        "abc123",
        "--task-id",
        "T-029",
        "--session-id",
        "s1",
      ],
      { cwd: "/repo" },
    );
  });

  test("Enter on human-review without a startCommit shows the inline message instead of spawning", () => {
    const record = withPipelineEntry({ node: "human-review", node_state: "pending" });
    const dashboard = new MissionControlDashboard(record, "/repo");
    moveDown(dashboard, 4);
    dashboard.handleInput("\r");

    expect(spawnTerminalWindow).not.toHaveBeenCalled();
  });

  test("Enter on human-review passes --task-id and --session-id to mission-control-review.ts", () => {
    const record = withPipelineEntry({ node: "human-review", node_state: "blocked", start_commit: "abc123" });
    const dashboard = new MissionControlDashboard(record, "/repo");
    moveDown(dashboard, 4); // "human-review" row (index 4)
    dashboard.handleInput("\r");

    expect(spawnTerminalWindow).toHaveBeenCalledWith(
      "node",
      expect.arrayContaining(["--task-id", "T-029", "--session-id", "s1"]),
      { cwd: "/repo" },
    );
  });
});
