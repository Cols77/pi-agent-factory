import { join } from "node:path";
import { describe, expect, test, vi } from "vitest";
import { buildTranscriptPath, MissionControlDashboard } from "../src/mission-control-dashboard.js";
import { spawnTerminalWindow } from "../src/terminal-window.js";
import type { StatusRecord } from "../src/status-format.js";

vi.mock("../src/terminal-window.js", () => ({
  spawnTerminalWindow: vi.fn(),
}));

const RECORD: StatusRecord = {
  session_id: "s1", task_id: "T-029", current_node: "dev", current_state: "running",
  pipeline: [
    { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: "-> dev: 3 files, coherence=yes", updated_at: "2026-07-22T00:00:00Z" },
    { node: "dev", node_state: "running", attempt: 2, max_attempts: 3, snippet: "", outcome: null, handoff: null, updated_at: "2026-07-22T00:00:01Z" },
  ],
  started_at: "2026-07-22T00:00:00Z", updated_at: "2026-07-22T00:00:01Z",
};

describe("MissionControlDashboard", () => {
  test("renders one row per pipeline stage with the task header", () => {
    const dashboard = new MissionControlDashboard(RECORD, () => {});
    const lines = dashboard.render(80).join("\n");
    expect(lines).toContain("T-029");
    expect(lines).toContain("context-gatherer");
    expect(lines).toContain("dev");
    expect(lines).toContain("validation");
    expect(lines).toContain("review");
    expect(lines).toContain("human-review");
  });

  test("Down/Up move the selected row", () => {
    const dashboard = new MissionControlDashboard(RECORD, () => {});
    dashboard.handleInput("\x1b[B");
    dashboard.handleInput("\r");
    const onSelect = vi.fn();
    const dashboard2 = new MissionControlDashboard(RECORD, onSelect);
    dashboard2.handleInput("\x1b[B"); // move to "dev" row (index 1)
    dashboard2.handleInput("\r");
    expect(onSelect).toHaveBeenCalledWith("dev", "s1");
  });

  test("updateRecord replaces the displayed data without losing selection", () => {
    const dashboard = new MissionControlDashboard(RECORD, () => {});
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
});

describe("buildTranscriptPath", () => {
  test("builds the same layout write_role_transcript/orchestrator use: <cwd>/sessions/.factory-transcripts/<sessionId>/<node>-attempt1.log", () => {
    expect(buildTranscriptPath("/repo", "s1", "dev")).toBe(
      join("/repo", "sessions", ".factory-transcripts", "s1", "dev-attempt1.log"),
    );
  });
});

describe("mission control dashboard's transcript drill-down (Enter key)", () => {
  // main() itself is a standalone script entry point (guarded by an argv
  // check, dynamically imports pi-tui, and polls forever) and isn't
  // reasonably unit-testable directly. This test instead wires a
  // MissionControlDashboard's onSelectTranscript callback the same way
  // main() does -- via buildTranscriptPath + spawnTerminalWindow -- and
  // confirms pressing Enter drives that wiring end-to-end with a mocked
  // spawnTerminalWindow.
  test("Enter on a row spawns the transcript viewer with the computed transcript path", () => {
    const cwd = "/repo";
    const dashboard = new MissionControlDashboard(RECORD, (node, sessionId) => {
      const transcriptPath = buildTranscriptPath(cwd, sessionId, node);
      spawnTerminalWindow(
        "node",
        [join(cwd, "pi-ext", "factory-watch", "src", "mission-control-transcript.ts"), "--transcript", transcriptPath],
        { cwd },
      );
    });

    dashboard.handleInput("\r"); // selectedIndex starts at 0 -> "context-gather" row

    expect(vi.mocked(spawnTerminalWindow)).toHaveBeenCalledWith(
      "node",
      [
        join(cwd, "pi-ext", "factory-watch", "src", "mission-control-transcript.ts"),
        "--transcript",
        join(cwd, "sessions", ".factory-transcripts", "s1", "context-gather-attempt1.log"),
      ],
      { cwd },
    );
  });
});
