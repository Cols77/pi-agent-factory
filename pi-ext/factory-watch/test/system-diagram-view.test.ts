// Inc 6 Task 5b -- the Diagram view widget (system-diagram-view.ts).
//
// Pure data->DOM over query_diagram's payload (Inc 5 D7): the diagram stub
// plus the canonical committed HTML path. The widget embeds/link-targets
// that path only -- it never re-derives a graph (D7). A stub whose HTML is
// missing renders an explicit "missing diagram" state with the recorded
// errors, never a broken blank. An optional recorded `focus` (from a
// navigation intent) surfaces which node to look at first.
import { JSDOM } from "jsdom";
import { afterEach, describe, expect, test, vi } from "vitest";

import { clear } from "../src/system-renderers.js";
import { renderDiagram } from "../src/system-diagram-view.js";

function mount(payload: unknown, focus?: string): { el: HTMLElement; dom: JSDOM } {
  const dom = new JSDOM("<!doctype html><html><body></body></html>");
  const win = dom.window as unknown as Record<string, unknown>;
  for (const key of ["document", "window", "HTMLElement", "Node", "Element", "Event", "CustomEvent"]) {
    vi.stubGlobal(key, win[key]);
  }
  vi.stubGlobal("clear", clear);
  const el = dom.window.document.createElement("div");
  renderDiagram(el, payload, focus);
  return { el, dom };
}

// Mirrors query_diagram for a stub whose canonical HTML is committed.
const DIAGRAM = {
  id: "DIAG-NAV-001",
  title: "Reacquisition state machine",
  diagram_path: "docs/diagrams/DIAG-NAV-001.html",
  errors: [],
};

// A stub whose diagram_file is missing: addressable, honestly incomplete.
const MISSING = {
  id: "DIAG-NAV-002",
  title: "Unbuilt diagram",
  diagram_path: null,
  errors: ["diagram file missing: docs/diagrams/DIAG-NAV-002.html"],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("system-diagram-view.ts diagram widget", () => {
  test("embeds the canonical HTML via a link target and shows the title", () => {
    const { el } = mount(DIAGRAM);
    expect(el.querySelector(".diagram-id")?.textContent).toBe("DIAG-NAV-001");
    expect(el.querySelector(".diagram-title")?.textContent).toBe("Reacquisition state machine");
    const embed = el.querySelector("iframe.diagram-embed") as HTMLElement | null;
    expect(embed?.getAttribute("src")).toBe("docs/diagrams/DIAG-NAV-001.html");
    const link = el.querySelector("a.diagram-open");
    expect(link?.getAttribute("href")).toBe("docs/diagrams/DIAG-NAV-001.html");
  });

  test("a missing diagram renders the explicit missing state with recorded errors", () => {
    const { el } = mount(MISSING);
    expect(el.textContent).toContain("missing diagram");
    expect(el.textContent).toContain("diagram file missing: docs/diagrams/DIAG-NAV-002.html");
    expect(el.querySelector("iframe.diagram-embed")).toBeNull();
  });

  test("a focus note surfaces which node to look at first when provided", () => {
    const { el } = mount(DIAGRAM, "REACQUIRE_NODE");
    expect(el.textContent).toContain("Focus");
    expect(el.textContent).toContain("REACQUIRE_NODE");
  });

  test("no focus intent renders no focus note", () => {
    const { el } = mount(DIAGRAM);
    expect(el.textContent).not.toContain("Focus:");
  });
});