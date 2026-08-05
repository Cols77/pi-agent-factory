import { describe, expect, test } from "vitest";
import { renderDocsHtml } from "../src/docs-html.js";

describe("renderDocsHtml", () => {
  const html = renderDocsHtml();

  test("is a complete document", () => {
    expect(html).toContain("<!doctype html>");
    expect(html).toContain("</html>");
  });

  test("makes no external requests", () => {
    // Zero runtime dependencies means zero remote assets. Spec section 7.
    expect(html).not.toMatch(/src="https?:/);
    expect(html).not.toMatch(/href="https?:/);
    expect(html).not.toContain("cdn");
  });

  test("fetches only the three local apis", () => {
    expect(html).toContain("/api/graph");
    expect(html).toContain("/api/doc?path=");
    expect(html).toContain("/api/layout");
  });

  test("does not reimplement layout arithmetic in the page", () => {
    // Layout is graph-layout.ts's job, served via /api/layout. A rank table here
    // would be a second, untested copy.
    expect(html).not.toContain("br: 0, sr: 1");
  });

  test("renders the panes the spec calls for", () => {
    for (const id of ["sidebar", "doc", "toc", "trace", "health", "map"]) {
      expect(html).toContain(`id="${id}"`);
    }
  });

  test("labels list entries by node id, not title alone", () => {
    // The sidebar used to render n.title only, so a task the factory reports as
    // T-051 was unfindable by that id while the map labelled it T-051.
    expect(html).toContain("shortId(n.id)");
  });

  test("offers a filter so a known id can be found directly", () => {
    expect(html).toContain('id="filter"');
    expect(html).toContain("T-051");
  });

  test("draws graph nodes as boxes over the edges, not as bare anchors", () => {
    expect(html).toContain("layout.width");
    expect(html).toContain("'rect'");
    // edges are appended before nodes so opaque boxes paint over them
    expect(html.indexOf("class: 'gedge'")).toBeLessThan(html.indexOf("class: 'gnode'"));
  });

  test("is responsive rather than a fixed three-column slab", () => {
    expect(html).toContain("@media");
    expect(html).toContain("viewBox");
    expect(html).toContain('name="viewport"');
  });

  test("carries a legend for all five validation states", () => {
    for (const label of ["pass", "fail", "error", "never validated", "stale"]) {
      expect(html.toLowerCase()).toContain(label);
    }
  });
});
