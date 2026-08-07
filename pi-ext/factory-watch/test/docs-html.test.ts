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

  test("fetches only local workspace apis", () => {
    expect(html).toContain("/api/graph");
    expect(html).toContain("/api/doc?path=");
    expect(html).toContain("/api/layout");
    expect(html).toContain("/api/evidence/task?task=");
    expect(html).toContain("/api/artifact/");
    expect(html).toContain("/api/reviews?task=");
    expect(html).toContain("/api/run-state");
  });

  test("does not reimplement layout arithmetic in the page", () => {
    // Layout is graph-layout.ts's job, served via /api/layout. A rank table here
    // would be a second, untested copy.
    expect(html).not.toContain("br: 0, sr: 1");
  });

  test("renders the panes the spec calls for", () => {
    for (const id of ["sidebar", "doc", "toc", "trace", "health", "recovery", "map", "reviews"]) {
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

  test("renders the recorded implementation, validation, reviews, and decisions for task runs", () => {
    for (const label of [
      "Implementation evidence", "Implementation", "Validation", "Reviews", "Design decisions",
    ]) {
      expect(html).toContain(label);
    }
    expect(html).toContain("provenance('recorded')");
    expect(html).toContain("View implementation patch");
    expect(html).toContain("View validation report");
  });

  test("uses local review archives only as an explicitly-labelled legacy fallback", () => {
    expect(html).toContain("Local legacy review history");
    expect(html).toContain("provenance('local')");
    expect(html).toContain("before archival was enabled");
  });

  test("shows interrupted-run recovery with explicit human guards", () => {
    for (const label of [
      "Interrupted run", "Inspect evidence", "Resume", "Abandon", "Abandonment rationale",
    ]) {
      expect(html).toContain(label);
    }
    expect(html).toContain("window.confirm('Resume this run");
    expect(html).toContain("A non-blank abandonment rationale is required");
    expect(html).toContain("setInterval(renderRunState, 2000)");
    expect(html).toContain("pagehide");
  });

  test("honours task/run focus query params without relaxing repo confinement", () => {
    expect(html).toContain("new URLSearchParams(window.location.search)");
    expect(html).toContain("initialTaskFocus");
    expect(html).toContain("initialRunFocus");
    expect(html).toContain("details.open = true");
    expect(html).toContain("scrollIntoView({ block: 'center' })");
    expect(html).toContain("openDoc(focusNode.id)");
  });

  test("carries a legend for all five validation states", () => {
    for (const label of ["pass", "fail", "error", "never validated", "stale"]) {
      expect(html.toLowerCase()).toContain(label);
    }
  });
});
