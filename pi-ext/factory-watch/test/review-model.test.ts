import { describe, expect, test } from "vitest";
import { annotationsForFile, buildDecision } from "../src/review-model.js";
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
