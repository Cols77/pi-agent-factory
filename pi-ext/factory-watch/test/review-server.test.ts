import { describe, expect, test, vi } from "vitest";

vi.mock("../src/review-diff.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/review-diff.js")>()),
  computeFileDiffText: vi.fn(() => "@@ -1,1 +1,1 @@\n-old\n+new\n"),
}));

import { buildReviewPageData } from "../src/review-server.js";
import type { FileStat } from "../src/review-diff.js";

const FILES: FileStat[] = [{ path: "a.py", status: "M", added: 1, removed: 1 }];

describe("buildReviewPageData", () => {
  test("returns files, diff lines, and row meta per file", () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-1" });
    expect(data.taskId).toBe("T-1");
    expect(data.files).toHaveLength(1);
    expect(data.diffs["a.py"]!.lines).toContain("+new");
    // the "+new" row anchors to the new side
    const addIdx = data.diffs["a.py"]!.lines.findIndex((l) => l === "+new");
    expect(data.diffs["a.py"]!.meta[addIdx]!.side).toBe("new");
  });
});
