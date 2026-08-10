import { describe, expect, test } from "vitest";
import { renderReviewHtml } from "../src/review-html.js";

describe("renderReviewHtml", () => {
  const html = renderReviewHtml();

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

  test("the only non-clearing innerHTML assignment is the rendered plan section", () => {
    // renderMarkdown output is the sole trusted HTML on this page; every other
    // server value must reach the DOM through createTextNode.
    const assignments = html.match(/innerHTML = (?!'')[^;\n]+/g) ?? [];
    expect(assignments).toEqual(["innerHTML = intent.planSection.html"]);
  });
});
