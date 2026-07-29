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
});
