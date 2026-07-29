import { describe, expect, test } from "vitest";
import { renderReviewHtml } from "../src/review-html.js";

describe("renderReviewHtml", () => {
  const html = renderReviewHtml();
  test("is a self-contained document with no external resource references", () => {
    expect(html).toMatch(/<!doctype html>/i);
    expect(html).toContain("/api/review");
    expect(html).toContain("/api/decision");
    // no external network references (CSP-friendly, loopback-only)
    expect(html).not.toMatch(/src=["']https?:/);
    expect(html).not.toMatch(/href=["']https?:/);
  });
  test("wires approve/reject controls", () => {
    expect(html).toContain('id="approve"');
    expect(html).toContain('id="reject"');
  });
  test("renders the review-focus guide and task id (parity with the TUI)", () => {
    // F1: the page must surface the guide (confidence/validation/verify/
    // addressed) and the task id, which are fetched from /api/review.
    expect(html).toContain('id="guide"');
    expect(html).toContain("data.guide");
    expect(html).toContain("data.taskId");
    // guide text is inserted via createTextNode, never innerHTML of server data
    expect(html).toContain("g.confidence");
    expect(html).toContain("Verify before approving:");
  });
});
