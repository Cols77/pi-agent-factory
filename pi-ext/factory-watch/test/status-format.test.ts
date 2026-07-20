import { describe, expect, test } from "vitest";
import { formatStatusLines, parseStatus, secondsAgo } from "../src/status-format.js";
import type { StatusRecord } from "../src/status-format.js";

const RECORD: StatusRecord = {
  session_id: "2026-07-20T10-15-00Z",
  task_id: "T-001",
  node: "dev",
  node_state: "running",
  attempt: 2,
  max_attempts: 3,
  snippet: "implementing goto()",
  outcome: null,
  started_at: "2026-07-20T10:15:00Z",
  updated_at: "2026-07-20T10:16:42Z",
};

describe("parseStatus", () => {
  test("parses a valid record", () => {
    expect(parseStatus(JSON.stringify(RECORD))).toEqual(RECORD);
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
    const now = new Date("2026-07-20T10:16:52Z");
    expect(secondsAgo("2026-07-20T10:16:42Z", now)).toBe(10);
  });
  test("never returns negative (clock skew safety)", () => {
    const now = new Date("2026-07-20T10:16:40Z"); // before updated_at
    expect(secondsAgo("2026-07-20T10:16:42Z", now)).toBe(0);
  });
});

describe("formatStatusLines", () => {
  const now = new Date("2026-07-20T10:16:52Z");

  test("shows a waiting message when there's no record yet", () => {
    expect(formatStatusLines(null, now)).toEqual(["factory: waiting for status..."]);
  });

  test("includes task, node, state, attempt, and time-since-update", () => {
    const lines = formatStatusLines(RECORD, now);
    expect(lines[0]).toContain("T-001");
    expect(lines[0]).toContain("dev");
    expect(lines[0]).toContain("running");
    expect(lines.some((l) => l.includes("2/3"))).toBe(true);
    expect(lines.some((l) => l.includes("10s ago"))).toBe(true);
  });

  test("includes the snippet when present", () => {
    const lines = formatStatusLines(RECORD, now);
    expect(lines.some((l) => l.includes("implementing goto()"))).toBe(true);
  });

  test("includes outcome when set, omits it when null", () => {
    const withOutcome = formatStatusLines({ ...RECORD, outcome: "completed" }, now);
    expect(withOutcome.some((l) => l.includes("outcome: completed"))).toBe(true);

    const withoutOutcome = formatStatusLines(RECORD, now);
    expect(withoutOutcome.some((l) => l.includes("outcome:"))).toBe(false);
  });
});
