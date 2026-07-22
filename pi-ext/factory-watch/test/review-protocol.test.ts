import { describe, expect, test, vi } from "vitest";
import { parseReviewPendingLine, writeReviewDecision } from "../src/review-protocol.js";

describe("parseReviewPendingLine", () => {
  test("parses a valid review_pending line", () => {
    const line = JSON.stringify({ type: "review_pending", task_id: "T-001", start_commit: "abc123" });
    expect(parseReviewPendingLine(line)).toEqual({
      type: "review_pending", task_id: "T-001", start_commit: "abc123",
    });
  });

  test("returns null for unrelated JSON", () => {
    expect(parseReviewPendingLine(JSON.stringify({ type: "something_else" }))).toBeNull();
  });

  test("returns null for non-JSON stdout noise", () => {
    expect(parseReviewPendingLine("not json at all")).toBeNull();
  });

  test("returns null for an empty line", () => {
    expect(parseReviewPendingLine("")).toBeNull();
  });
});

describe("writeReviewDecision", () => {
  test("writes exactly one JSON line to the given stream", () => {
    const write = vi.fn();
    const stdin = { write } as unknown as NodeJS.WritableStream;

    writeReviewDecision(stdin, { decision: "reject", comments: { "src/x.py": "fix" } });

    expect(write).toHaveBeenCalledWith(
      JSON.stringify({ decision: "reject", comments: { "src/x.py": "fix" } }) + "\n",
    );
  });
});
