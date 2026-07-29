import { describe, expect, test } from "vitest";
import { annotationsForFile, buildDecision, anchorForRow, mapDiffRows } from "../src/review-model.js";
import type { Annotation } from "../src/review-model.js";

const ANNS: Annotation[] = [
  { file: "a.py", line: 10, side: "new", body: "fix", severity: "must-fix" },
  { file: "a.py", body: "file note" },
  { file: "b.py", line: 3, side: "old", body: "old side" },
];

describe("review-model", () => {
  test("buildDecision packages decision, annotations, reviewedFiles", () => {
    const d = buildDecision("reject", ANNS, ["a.py"]);
    expect(d.decision).toBe("reject");
    expect(d.annotations).toHaveLength(3);
    expect(d.reviewedFiles).toEqual(["a.py"]);
  });

  test("annotationsForFile filters by path", () => {
    expect(annotationsForFile(ANNS, "a.py")).toHaveLength(2);
    expect(annotationsForFile(ANNS, "b.py")).toHaveLength(1);
    expect(annotationsForFile(ANNS, "z.py")).toHaveLength(0);
  });
});

const RAW = [
  "diff --git a/x.py b/x.py",
  "index 111..222 100644",
  "--- a/x.py",
  "+++ b/x.py",
  "@@ -10,3 +10,4 @@ def f():",
  " context1",   // old 10 / new 10  -> anchor new 10
  "-removed",    // old 11           -> anchor old 11
  "+added1",     // new 11           -> anchor new 11
  "+added2",     // new 12           -> anchor new 12
  " context2",   // old 12 / new 13  -> anchor new 13
];

describe("mapDiffRows", () => {
  test("assigns line numbers per side across a hunk", () => {
    const meta = mapDiffRows(RAW);
    expect(meta).toHaveLength(RAW.length);
    expect(meta[4].kind).toBe("hunk");
    expect(anchorForRow(meta, 5)).toEqual({ line: 10, side: "new" });   // context1
    expect(anchorForRow(meta, 6)).toEqual({ line: 11, side: "old" });   // removed
    expect(anchorForRow(meta, 7)).toEqual({ line: 11, side: "new" });   // added1
    expect(anchorForRow(meta, 8)).toEqual({ line: 12, side: "new" });   // added2
    expect(anchorForRow(meta, 9)).toEqual({ line: 13, side: "new" });   // context2
  });

  test("hunk/meta rows and out-of-range anchor to file-level {}", () => {
    const meta = mapDiffRows(RAW);
    expect(anchorForRow(meta, 0)).toEqual({});   // diff header
    expect(anchorForRow(meta, 4)).toEqual({});   // hunk header
    expect(anchorForRow(meta, 999)).toEqual({}); // out of range
  });
});
