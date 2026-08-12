import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { reviewGuidePath, readReviewGuide, grillReviewWarning } from "../src/review-guide.js";

let dir: string;
beforeEach(() => { dir = mkdtempSync(join(tmpdir(), "rg-")); });
afterEach(() => { rmSync(dir, { recursive: true, force: true }); });

test("reviewGuidePath builds the transcript path", () => {
  expect(reviewGuidePath("/repo", "s1")).toBe(join("/repo", "sessions", ".factory-transcripts", "s1", "review-guide.json"));
});

test("readReviewGuide parses a valid guide", () => {
  const p = join(dir, "g.json");
  writeFileSync(p, JSON.stringify({ confidence: "high", verify: [{ item: "x", file: "a.ts", line: 3 }] }), "utf-8");
  const g = readReviewGuide(p)!;
  expect(g.confidence).toBe("high");
  expect(g.verify![0]).toEqual({ item: "x", file: "a.ts", line: 3 });
});

test("readReviewGuide returns null on missing file or garbage", () => {
  expect(readReviewGuide(join(dir, "nope.json"))).toBeNull();
  writeFileSync(join(dir, "bad.json"), "not json", "utf-8");
  expect(readReviewGuide(join(dir, "bad.json"))).toBeNull();
});

describe("grillReviewWarning", () => {
  test("returns a warning for a not-agreed guide", () => {
    const w = grillReviewWarning({ grill: { verdict: "not-agreed" } });
    expect(w).toContain("not-agreed");
    expect(w).toContain("extra scrutiny");
  });

  test("includes the grill summary when present", () => {
    const w = grillReviewWarning({ grill: { verdict: "not-agreed", summary: "missed the diff range" } });
    expect(w).toContain("Grill summary: missed the diff range");
  });

  test("returns empty for a guide without a grill field", () => {
    expect(grillReviewWarning({ confidence: "high" })).toBe("");
  });

  test("returns empty for agreed and skipped verdicts", () => {
    expect(grillReviewWarning({ grill: { verdict: "agreed" } })).toBe("");
    expect(grillReviewWarning({ grill: { verdict: "skipped" } })).toBe("");
  });

  test("returns empty for null and undefined", () => {
    expect(grillReviewWarning(null)).toBe("");
    expect(grillReviewWarning(undefined)).toBe("");
  });
});
