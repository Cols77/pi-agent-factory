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

import { startReviewServer } from "../src/review-server.js";

async function post(url: string, body: unknown): Promise<Response> {
  return fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

describe("startReviewServer", () => {
  test("serves /api/review and accepts a decision, resolving the promise", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-9" });
    const srv = await startReviewServer(data);
    try {
      const review = await (await fetch(`${srv.url}/api/review`)).json();
      expect(review.taskId).toBe("T-9");

      const payload = { decision: "approve", annotations: [], reviewedFiles: ["a.py"] };
      const res = await post(`${srv.url}/api/decision`, payload);
      expect((await res.json()).ok).toBe(true);

      const decided = await srv.decision;
      expect(decided).not.toBeNull();
      expect(decided!.decision).toBe("approve");
      expect(decided!.reviewedFiles).toEqual(["a.py"]);
    } finally {
      srv.close();
    }
  });

  test("close() before any post resolves the decision to null", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-0" });
    const srv = await startReviewServer(data);
    srv.close();
    expect(await srv.decision).toBeNull();
  });

  test("malformed JSON body returns 400 without hanging or settling the decision", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-bad" });
    const srv = await startReviewServer(data);
    try {
      const badRes = await fetch(`${srv.url}/api/decision`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "not json{{{",
      });
      expect(badRes.status).toBe(400);
      const badBody = await badRes.json();
      expect(badBody.error).toBeTruthy();

      // Prove the server is still alive and the decision promise is still unsettled:
      // a subsequent valid POST must still be able to resolve it.
      const payload = { decision: "approve", annotations: [], reviewedFiles: ["a.py"] };
      const goodRes = await post(`${srv.url}/api/decision`, payload);
      expect(goodRes.status).toBe(200);
      expect((await goodRes.json()).ok).toBe(true);

      const decided = await srv.decision;
      expect(decided).not.toBeNull();
      expect(decided!.decision).toBe("approve");
    } finally {
      srv.close();
    }
  }, 5000);
});
