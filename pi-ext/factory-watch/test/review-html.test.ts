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

  test("carries the three panes a review needs, each collapsible", () => {
    for (const pane of ["tree", "diff", "comments"]) {
      expect(html).toContain(`data-pane="${pane}"`);
    }
    // The context/guidance content is not a pane any more: Task, Plan, Spec
    // and Verify open as read-only pages in new windows.
    expect(html).not.toContain('data-pane="context"');
    expect(html.match(/class="pane-toggle"/g) ?? []).toHaveLength(3);
  });

  test("the reference buttons open Task / Plan / Spec / Verify in a new window", () => {
    for (const id of ["refTask", "refPlan", "refSpec", "refVerify"]) {
      expect(html).toContain(`id="${id}"`);
    }
    expect(html).toContain("window.open('/reference/' + kind, '_blank')");
  });

  test("drives the grid from a column template rather than a fixed one", () => {
    expect(html).not.toContain("grid-template-columns: 240px 1fr 320px");
    expect(html).toContain("gridTemplateColumns");
  });

  test("posts layout changes to the server rather than using localStorage", () => {
    expect(html).toContain("/api/layout");
    expect(html).not.toContain("localStorage");
  });

  test("fetches per-file provenance lazily from /api/why", () => {
    expect(html).toContain("/api/why?file=");
  });

  test("the page script performs no innerHTML writes at all", () => {
    // The review page renders everything (tree, diff, comments, header)
    // through createTextNode/textContent/replaceChildren. Trusted rendered
    // markdown lives only in the reference pages (review-reference.ts), which
    // escape every server string and splice renderMarkdown output.
    expect(html).not.toMatch(/outerHTML/);
    expect(html).not.toMatch(/insertAdjacentHTML/);
    expect(html).not.toMatch(/document\.write/);
    const sink = /(?:\.innerHTML|\[\s*['"]innerHTML['"]\s*\])\s*=\s*([^;\n]+)/g;
    const assignments = [...html.matchAll(sink)]
      .map((m) => m[1]!.trim())
      .filter((rhs) => rhs !== "''" && rhs !== '""');
    expect(assignments).toEqual([]);
  });
});