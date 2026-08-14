import { describe, expect, test } from "vitest";
import { renderReviewHtml } from "../src/review-html.js";

describe("renderReviewHtml", () => {
  const html = renderReviewHtml();

  // --- Pre-existing coverage, restored after Task 9's wholesale test-file
  // replacement dropped it even though the code it guards still ships. ---

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

  // --- Task 9: collapsible, zoomable panes and the intent context pane. ---

  test("declares all four panes", () => {
    for (const pane of ["context", "tree", "diff", "comments"]) {
      expect(html).toContain(`data-pane="${pane}"`);
    }
  });

  test("gives every pane a collapse control", () => {
    expect(html.match(/class="pane-toggle"/g) ?? []).toHaveLength(4);
  });

  test("drives the grid from a column template rather than a fixed one", () => {
    expect(html).not.toContain("grid-template-columns: 240px 1fr 320px");
    expect(html).toContain("gridTemplateColumns");
  });

  test("no longer caps the task context at 35vh", () => {
    expect(html).not.toContain("35vh");
  });

  test("posts layout changes to the server rather than using localStorage", () => {
    expect(html).toContain("/api/layout");
    expect(html).not.toContain("localStorage");
  });

  test("fetches per-file provenance lazily from /api/why", () => {
    expect(html).toContain("/api/why?file=");
  });

  test("renders the fan-out marker so a partial chain is never silent", () => {
    // walkIntentChain counts the requirements and specs it did not show. A page
    // that computes that count and never renders it leaves the reviewer looking
    // at one of two satisfied requirements with no sign the second exists --
    // precisely the failure the count was added to prevent.
    expect(html).toMatch(/n\.alternatives/);
    expect(html).toContain("more)");
  });

  test("the only DOM-writing sink for server-controlled markup is the rendered plan section", () => {
    // renderMarkdown output (intent.planSection.html) is the sole trusted HTML
    // on this page; every other server value must reach the DOM through
    // createTextNode. This guard must survive reformatting -- whitespace
    // changes around `=`, bracket-notation property access -- and must also
    // catch sinks other than innerHTML that would bypass it entirely.
    expect(html).not.toMatch(/outerHTML/);
    expect(html).not.toMatch(/insertAdjacentHTML/);
    expect(html).not.toMatch(/document\.write/);

    // innerHTML via dot or bracket-notation property access, any amount of
    // whitespace around `=`. Clearing assignments (`= ''` / `= ""`) are
    // filtered out in JS rather than via a lookahead: a lookahead here is
    // defeated by `\s*` backtracking past it when the RHS is a clearing
    // assignment, silently letting the excluded form back in. Each surviving
    // match is normalized to "innerHTML = <rhs>" so the assertion below does
    // not itself depend on which notation or spacing the source used.
    const sink = /(?:\.innerHTML|\[\s*['"]innerHTML['"]\s*\])\s*=\s*([^;\n]+)/g;
    const assignments = [...html.matchAll(sink)]
      .map((m) => m[1]!.trim())
      .filter((rhs) => rhs !== "''" && rhs !== '""')
      .map((rhs) => `innerHTML = ${rhs}`);
    expect(assignments).toEqual(["innerHTML = intent.planSection.html"]);
  });
});
