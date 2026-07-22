import { describe, expect, test } from "vitest";
import { formatStatusLines, parseStatus, secondsAgo } from "../src/status-format.js";
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
});
