import { describe, expect, test } from "vitest";
import {
  DEFAULT_LAYOUT, columnTemplate, normalizeLayout, restoreLayout, togglePane, zoomPane,
} from "../src/review-layout.js";

describe("columnTemplate", () => {
  test("the default gives every pane its natural width", () => {
    expect(columnTemplate(DEFAULT_LAYOUT)).toBe("1.2fr 240px 2fr 320px");
  });

  test("a collapsed pane becomes a rail and the rest keep their widths", () => {
    expect(columnTemplate(togglePane(DEFAULT_LAYOUT, "tree"))).toBe("1.2fr 28px 2fr 320px");
  });

  test("a zoomed pane takes the window and the rest collapse to zero", () => {
    expect(columnTemplate(zoomPane(DEFAULT_LAYOUT, "context"))).toBe("1fr 0px 0px 0px");
  });

  test("zoom overrides collapse without discarding it", () => {
    const state = zoomPane(togglePane(DEFAULT_LAYOUT, "tree"), "diff");
    expect(columnTemplate(state)).toBe("0px 0px 1fr 0px");
    expect(columnTemplate(restoreLayout(state))).toBe("1.2fr 28px 2fr 320px");
  });
});

describe("togglePane", () => {
  test("toggling twice returns to the default", () => {
    const state = togglePane(togglePane(DEFAULT_LAYOUT, "comments"), "comments");
    expect(state.collapsed).toEqual([]);
  });

  test("collapsing every pane is allowed and reversible", () => {
    let state = DEFAULT_LAYOUT;
    for (const pane of ["context", "tree", "diff", "comments"] as const) {
      state = togglePane(state, pane);
    }
    expect(columnTemplate(state)).toBe("28px 28px 28px 28px");
  });
});

describe("zoomPane", () => {
  test("zooming the already-zoomed pane restores", () => {
    const state = zoomPane(zoomPane(DEFAULT_LAYOUT, "diff"), "diff");
    expect(state.zoomed).toBeNull();
  });
});

describe("normalizeLayout", () => {
  test("unknown pane ids are dropped", () => {
    expect(normalizeLayout({ collapsed: ["tree", "nope"], zoomed: "bogus" }))
      .toEqual({ collapsed: ["tree"], zoomed: null, guide: false });
  });

  test("junk falls back to the default", () => {
    expect(normalizeLayout(null)).toEqual(DEFAULT_LAYOUT);
    expect(normalizeLayout("garbage")).toEqual(DEFAULT_LAYOUT);
    expect(normalizeLayout({ collapsed: "tree" })).toEqual(DEFAULT_LAYOUT);
  });

  test("the guidance flag survives round trips and only true means expanded", () => {
    expect(normalizeLayout({ collapsed: [], zoomed: null, guide: true })).toEqual({
      collapsed: [], zoomed: null, guide: true,
    });
    expect(normalizeLayout({ collapsed: [], zoomed: null, guide: 1 }).guide).toBe(false);
    expect(normalizeLayout({ collapsed: [], zoomed: null }).guide).toBe(false);
  });
});
