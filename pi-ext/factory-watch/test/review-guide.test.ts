import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, expect, test } from "vitest";
import { reviewGuidePath, readReviewGuide } from "../src/review-guide.js";

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
