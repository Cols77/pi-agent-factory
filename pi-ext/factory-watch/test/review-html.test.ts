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
  test("the inline-comment '+' affordance is revealed by hovering the whole row, not just the icon itself", () => {
    // Before this fix, only `.row .plus:hover` raised the opacity -- meaning
    // the reviewer had to already be precisely hovering a dim, ~6px-wide "+"
    // glyph in the row's left gutter for it to become visible at all, a
    // chicken-and-egg discoverability trap. GitHub-PR-style diff views (the
    // prior art the design spec cites) reveal the affordance on row hover.
    expect(html).toMatch(/\.row:hover\s+\.plus\s*\{[^}]*opacity:\s*[.\d]+/);
  });

  test("the '+' affordance has a tooltip explaining what it does", () => {
    expect(html).toMatch(/plus\.title\s*=\s*['"][^'"]*comment/i);
  });

  test("the page explains how to add an inline comment, not just the guide/task-id parity text", () => {
    expect(html).toMatch(/hover.{0,20}\+.{0,20}comment/i);
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
