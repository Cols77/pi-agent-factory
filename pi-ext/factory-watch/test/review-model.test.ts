import { describe, expect, test } from "vitest";
import { annotationsForFile, buildDecision, anchorForRow, findAnnotation, mapDiffRows } from "../src/review-model.js";
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

  test("findAnnotation matches on the exact file/line/side anchor", () => {
    expect(findAnnotation(ANNS, "a.py", 10, "new")).toBe(ANNS[0]);
    expect(findAnnotation(ANNS, "a.py", undefined, undefined)).toBe(ANNS[1]); // file-level note
    expect(findAnnotation(ANNS, "b.py", 3, "old")).toBe(ANNS[2]);
  });

  test("findAnnotation returns undefined when no anchor matches", () => {
    expect(findAnnotation(ANNS, "a.py", 10, "old")).toBeUndefined(); // right file/line, wrong side
    expect(findAnnotation(ANNS, "a.py", 99, "new")).toBeUndefined(); // wrong line
    expect(findAnnotation(ANNS, "z.py")).toBeUndefined(); // unknown file
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
    expect(meta[4]!.kind).toBe("hunk");
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

  test("second hunk in a single-file diff anchors from its own @@ header", () => {
    const TWO_HUNK = [
      "diff --git a/x.py b/x.py",         // 0
      "index 111..222 100644",             // 1
      "--- a/x.py",                        // 2
      "+++ b/x.py",                        // 3
      "@@ -10,2 +10,2 @@ def f():",       // 4 hunk1: old10 new10
      " context1",                         // 5 old10/new10 -> new10
      " context2",                         // 6 old11/new11 -> new11
      "@@ -50,2 +51,2 @@ def g():",       // 7 hunk2: old50 new51
      " context3",                         // 8 old50/new51 -> new51
      " context4",                         // 9 old51/new52 -> new52
    ];
    const meta = mapDiffRows(TWO_HUNK);
    expect(meta[7]!.kind).toBe("hunk");
    expect(anchorForRow(meta, 8)).toEqual({ line: 51, side: "new" });
    expect(anchorForRow(meta, 9)).toEqual({ line: 52, side: "new" });
  });

  test("second file in a multi-file diff anchors to its own line numbers", () => {
    const TWO_FILE = [
      "diff --git a/x.py b/x.py",   // 0
      "index 111..222 100644",       // 1
      "--- a/x.py",                  // 2
      "+++ b/x.py",                  // 3
      "@@ -1,1 +1,1 @@",             // 4 hunk1: old1 new1
      " onlyline",                   // 5 old1/new1 -> new1
      "diff --git a/y.py b/y.py",   // 6 file boundary -> must reset inHunk
      "index 333..444 100644",       // 7
      "--- a/y.py",                  // 8
      "+++ b/y.py",                  // 9
      "@@ -5,1 +5,1 @@",             // 10 hunk2: old5 new5
      " secondline",                 // 11 old5/new5 -> new5
    ];
    const meta = mapDiffRows(TWO_FILE);
    expect(meta[6]!.kind).toBe("meta"); // "diff --git" for second file, not context
    expect(meta[8]!.kind).toBe("meta"); // "--- a/y.py" header, not del
    expect(anchorForRow(meta, 6)).toEqual({});
    expect(anchorForRow(meta, 8)).toEqual({});
    expect(anchorForRow(meta, 11)).toEqual({ line: 5, side: "new" });
  });

  test("'\\ No newline at end of file' marker gets no line anchor", () => {
    const NO_NEWLINE = [
      "diff --git a/x.py b/x.py", // 0
      "index 111..222 100644",     // 1
      "--- a/x.py",                // 2
      "+++ b/x.py",                // 3
      "@@ -1,2 +1,2 @@",           // 4 hunk: old1 new1
      " context1",                 // 5 old1/new1 -> new1
      "-old2",                     // 6 old2 -> old2
      "+new2",                     // 7 new2 -> new2
      "\\ No newline at end of file", // 8 marker, not a real source line
    ];
    const meta = mapDiffRows(NO_NEWLINE);
    expect(meta[8]!.kind).toBe("meta");
    expect(meta[8]!.line).toBeUndefined();
    expect(meta[8]!.side).toBeUndefined();
    expect(anchorForRow(meta, 8)).toEqual({});
  });
});
