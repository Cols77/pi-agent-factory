import { describe, expect, test } from "vitest";
import { formatStatusLines, parseStatus, secondsAgo, formatMissionControlRows } from "../src/status-format.js";
import type { StatusRecord, PipelineEntry } from "../src/status-format.js";

const NOW = new Date("2026-07-20T10:16:52Z");

// Legacy format record (no pipeline)
const LEGACY_RECORD: StatusRecord = {
  session_id: "2026-07-20T10-15-00Z",
  task_id: "T-001",
  current_node: "dev",
  current_state: "running",
  pipeline: [],
  started_at: "2026-07-20T10:15:00Z",
  updated_at: "2026-07-20T10:16:42Z",
  // legacy compat fields
  node: "dev",
  node_state: "running",
  attempt: 2,
  max_attempts: 3,
  snippet: "implementing goto()",
  outcome: null,
};

const PIPELINE_RECORD: StatusRecord = {
  session_id: "2026-07-20T10-15-00Z",
  task_id: "T-029",
  current_node: "dev",
  current_state: "running",
  pipeline: [
    {
      node: "context-gather",
      node_state: "pass",
      attempt: 1,
      max_attempts: 2,
      snippet: "",
      outcome: null,
      handoff: "→ dev: 3 files, coherence=yes",
      updated_at: "2026-07-20T10:15:30Z",
    },
    {
      node: "dev",
      node_state: "running",
      attempt: 1,
      max_attempts: 3,
      snippet: "writing test for Pose",
      outcome: null,
      handoff: null,
      updated_at: "2026-07-20T10:16:42Z",
    },
  ],
  started_at: "2026-07-20T10:15:00Z",
  updated_at: "2026-07-20T10:16:42Z",
};

describe("parseStatus", () => {
  test("parses a valid pipeline record", () => {
    expect(parseStatus(JSON.stringify(PIPELINE_RECORD))).toEqual(PIPELINE_RECORD);
  });
  test("parses a legacy record", () => {
    expect(parseStatus(JSON.stringify(LEGACY_RECORD))).toEqual(LEGACY_RECORD);
  });
  test("returns null for malformed JSON", () => {
    expect(parseStatus("not json")).toBeNull();
  });
  test("returns null for a JSON value that isn't a status object", () => {
    expect(parseStatus("42")).toBeNull();
    expect(parseStatus("null")).toBeNull();
    expect(parseStatus('{"foo": "bar"}')).toBeNull();
  });
});

describe("secondsAgo", () => {
  test("computes elapsed seconds", () => {
    expect(secondsAgo("2026-07-20T10:16:42Z", NOW)).toBe(10);
  });
  test("never returns negative (clock skew safety)", () => {
    const before = new Date("2026-07-20T10:16:40Z");
    expect(secondsAgo("2026-07-20T10:16:42Z", before)).toBe(0);
  });
});

describe("formatStatusLines", () => {
  test("shows a waiting message when there's no record yet", () => {
    expect(formatStatusLines(null, NOW)).toEqual(["factory: waiting for status..."]);
  });

  test("renders pipeline with icons and handoff", () => {
    const lines = formatStatusLines(PIPELINE_RECORD, NOW);
    expect(lines[0]).toContain("T-029");
    // context-gatherer pass with handoff
    expect(lines.some((l) => l.includes("context-gatherer") && l.includes("pass"))).toBe(true);
    expect(lines.some((l) => l.includes("→ dev: 3 files"))).toBe(true);
    // developer running with attempt info
    expect(lines.some((l) => l.includes("developer") && l.includes("running"))).toBe(true);
    expect(lines.some((l) => l.includes("1/3"))).toBe(true);
  });

  test("shows snippet for running nodes", () => {
    const lines = formatStatusLines(PIPELINE_RECORD, NOW);
    expect(lines.some((l) => l.includes("writing test for Pose"))).toBe(true);
  });

  test("falls back to legacy format when pipeline is empty", () => {
    const lines = formatStatusLines(LEGACY_RECORD, NOW);
    expect(lines[0]).toContain("T-001");
    expect(lines.some((l) => l.includes("2/3"))).toBe(true);
    expect(lines.some((l) => l.includes("implementing goto()"))).toBe(true);
  });

  test("includes outcome when set", () => {
    const record: StatusRecord = {
      ...PIPELINE_RECORD,
      pipeline: [
        { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 2, snippet: "", outcome: null, handoff: "→ dev", updated_at: "2026-07-20T10:15:30Z" },
        { node: "dev", node_state: "pass", attempt: 1, max_attempts: 3, snippet: "", outcome: null, handoff: "→ validation", updated_at: "2026-07-20T10:16:00Z" },
        { node: "review", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: "completed", handoff: "✓ task complete", updated_at: "2026-07-20T10:16:30Z" },
      ],
    };
    const lines = formatStatusLines(record, NOW);
    expect(lines.some((l) => l.includes("outcome: completed"))).toBe(true);
  });

  test("formatStatusLines renders the blocked icon, not the default fallback", () => {
    const record: StatusRecord = {
      session_id: "s1",
      task_id: "T-001",
      current_node: "human-review",
      current_state: "blocked",
      pipeline: [
        {
          node: "human-review",
          node_state: "blocked",
          attempt: 1,
          max_attempts: 1,
          snippet: "",
          outcome: null,
          handoff: "waiting for you to review the diff",
          updated_at: "2026-07-22T00:00:00Z",
        },
      ],
      started_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    };
    const lines = formatStatusLines(record);
    expect(lines[1]).toBe("⊘ human-review: blocked  (1/1)");
  });
});

const STAGE_ORDER = ["context-gather", "dev", "validation", "review", "human-review"];

describe("formatMissionControlRows", () => {
  test("shows every stage in fixed order, pending for stages not yet reached", () => {
    const record: StatusRecord = {
      session_id: "s1",
      task_id: "T-001",
      current_node: "dev",
      current_state: "running",
      pipeline: [
        {
          node: "context-gather",
          node_state: "pass",
          attempt: 1,
          max_attempts: 1,
          snippet: "",
          outcome: null,
          handoff: "-> dev: 3 files",
          updated_at: "2026-07-22T00:00:00Z",
        },
        {
          node: "dev",
          node_state: "running",
          attempt: 1,
          max_attempts: 3,
          snippet: "",
          outcome: null,
          handoff: null,
          updated_at: "2026-07-22T00:00:01Z",
        },
      ],
      started_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:01Z",
    };
    const rows = formatMissionControlRows(record, STAGE_ORDER);
    expect(rows).toEqual([
      { node: "context-gather", label: "context-gatherer", state: "pass", handoff: "-> dev: 3 files", sessionId: null, summary: null, startCommit: null, snippet: "" },
      { node: "dev", label: "developer", state: "running", handoff: null, sessionId: null, summary: null, startCommit: null, snippet: "" },
      { node: "validation", label: "validation", state: "pending", handoff: null, sessionId: null, summary: null, startCommit: null, snippet: null },
      { node: "review", label: "reviewer", state: "pending", handoff: null, sessionId: null, summary: null, startCommit: null, snippet: null },
      { node: "human-review", label: "human-review", state: "pending", handoff: null, sessionId: null, summary: null, startCommit: null, snippet: null },
    ]);
  });

  test("returns all-pending rows when record is null", () => {
    const rows = formatMissionControlRows(null, STAGE_ORDER);
    expect(rows.every((r) => r.state === "pending")).toBe(true);
    expect(rows).toHaveLength(5);
  });

  test("copies session_id and summary from the dev entry, start_commit from the human-review entry", () => {
    const record: StatusRecord = {
      session_id: "s1",
      task_id: "T-001",
      current_node: "human-review",
      current_state: "blocked",
      pipeline: [
        {
          node: "dev",
          node_state: "pass",
          attempt: 1,
          max_attempts: 3,
          snippet: "",
          outcome: null,
          handoff: "-> validation",
          updated_at: "2026-07-22T00:00:01Z",
          session_id: "2026-07-20T10-15-00Z",
          summary: "implemented goto()",
        },
        {
          node: "human-review",
          node_state: "blocked",
          attempt: 1,
          max_attempts: 1,
          snippet: "",
          outcome: null,
          handoff: "waiting for you to review the diff",
          updated_at: "2026-07-22T00:00:02Z",
          start_commit: "abc1234",
        },
      ],
      started_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:02Z",
    };
    const rows = formatMissionControlRows(record, STAGE_ORDER);
    const devRow = rows.find((r) => r.node === "dev");
    const humanReviewRow = rows.find((r) => r.node === "human-review");
    const contextRow = rows.find((r) => r.node === "context-gather");

    expect(devRow).toMatchObject({
      sessionId: "2026-07-20T10-15-00Z",
      summary: "implemented goto()",
      startCommit: null,
    });
    expect(humanReviewRow).toMatchObject({
      sessionId: null,
      summary: null,
      startCommit: "abc1234",
    });
    // Stage untouched by this record should have all three fields null.
    expect(contextRow).toMatchObject({
      sessionId: null,
      summary: null,
      startCommit: null,
    });
  });

  test("carries the snippet from a running entry", () => {
    const record: StatusRecord = {
      session_id: "s1", task_id: "T-1", current_node: "dev", current_state: "running",
      pipeline: [
        { node: "dev", node_state: "running", attempt: 1, max_attempts: 3, snippet: "grepping for advance_waypoint", outcome: null, handoff: null, updated_at: "t" },
      ],
      started_at: "t", updated_at: "t",
    };
    const rows = formatMissionControlRows(record, ["dev"]);
    expect(rows[0]!.snippet).toBe("grepping for advance_waypoint");
  });
});

test("parseStatus surfaces already_done and deliverables on a pipeline entry", () => {
  const raw = JSON.stringify({
    session_id: "s1", task_id: "T-1", current_node: "human-review", current_state: "blocked",
    started_at: "t", updated_at: "t",
    pipeline: [{
      node: "human-review", node_state: "blocked", attempt: 1, max_attempts: 1,
      snippet: "", outcome: null, handoff: null, updated_at: "t",
      already_done: true, deliverables: ["src/x.py"],
    }],
  });
  const rec = parseStatus(raw)!;
  expect(rec.pipeline[0]!.already_done).toBe(true);
  expect(rec.pipeline[0]!.deliverables).toEqual(["src/x.py"]);
});
