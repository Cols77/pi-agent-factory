import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { reviewDecisionPath, writeReviewDecision } from "../src/review-protocol.ts";

describe("reviewDecisionPath", () => {
  test("joins cwd, sessions, .factory-transcripts, sessionId, review-decision.json", () => {
    expect(reviewDecisionPath("/repo", "s1")).toBe(
      join("/repo", "sessions", ".factory-transcripts", "s1", "review-decision.json"),
    );
  });
});

describe("writeReviewDecision", () => {
  test("writes the decision as JSON at the given path, creating parent dirs", () => {
    const dir = mkdtempSync(join(tmpdir(), "review-decision-"));
    const path = join(dir, "nested", "review-decision.json");

    writeReviewDecision(path, { decision: "approve", comments: {} });

    const written = JSON.parse(readFileSync(path, "utf-8"));
    expect(written).toEqual({ decision: "approve", comments: {} });
  });

  test("writes reject decisions with comments", () => {
    const dir = mkdtempSync(join(tmpdir(), "review-decision-"));
    const path = join(dir, "review-decision.json");

    writeReviewDecision(path, { decision: "reject", comments: { "src/a.ts": "fix this" } });

    const written = JSON.parse(readFileSync(path, "utf-8"));
    expect(written).toEqual({ decision: "reject", comments: { "src/a.ts": "fix this" } });
  });

  test("does not leave a .tmp file behind", () => {
    const dir = mkdtempSync(join(tmpdir(), "review-decision-"));
    const path = join(dir, "review-decision.json");

    writeReviewDecision(path, { decision: "approve", comments: {} });

    expect(() => readFileSync(`${path}.tmp`, "utf-8")).toThrow();
  });
});
