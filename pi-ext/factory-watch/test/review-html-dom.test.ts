// review-html.test.ts only greps `renderReviewHtml()`'s output as a string, so
// the page's ~200-line inline script -- the layout controller, renderContext,
// showWhy -- was never executed by anything. A runtime error in any of them
// would ship green: the grep tests assert the source *contains* `n.alternatives`
// and `/api/why?file=`, not that either ever runs.
//
// The plan's Task 9 Step 8 answers this with six by-hand browser checks. Five
// of them are mechanical -- does collapsing reflow the grid, does `1` zoom,
// does clicking a second file refetch provenance -- and the systematic risk is
// that a human "verified" them once and no one re-checks after an edit. Those
// five are asserted here against the real document, following the jsdom pattern
// system-page-dom.test.ts established for the same class of gap. What stays
// manual is the judgment the plan actually cares about and no assertion can
// make: whether the pane reads well.
import { JSDOM } from "jsdom";
import { describe, expect, test, vi } from "vitest";

import { renderReviewHtml } from "../src/review-html.js";

const REVIEW = {
  taskId: "T-042",
  banner: "",
  implementing: false,
  guide: null,
  files: [
    { path: "src/alpha.ts", status: "M" },
    { path: "src/beta.ts", status: "A" },
  ],
  diffs: {
    "src/alpha.ts": { lines: ["@@ -1 +1 @@", "-old", "+new"], meta: [{ kind: "hunk" }, { kind: "del", line: 1, side: "old" }, { kind: "add", line: 1, side: "new" }] },
    "src/beta.ts": { lines: ["@@ -0,0 +1 @@", "+fresh"], meta: [{ kind: "hunk" }, { kind: "add", line: 1, side: "new" }] },
  },
  task: {
    id: "T-042",
    path: "tasks/T-042-example.md",
    title: "Example task",
    status: "human-review",
    dod: ["file dod entry"],
    html: "<p>task file</p>",
  },
  intent: {
    chain: [
      { kind: "requirement", id: "SR-007", title: "The reviewer sees intent", alternatives: 1 },
      { kind: "task", id: "T-042", title: "Example task", alternatives: 0 },
    ],
    stopsAt: null,
    planSection: {
      planPath: "docs/superpowers/plans/example.md",
      heading: "Task 3: Do the thing",
      html: "<p>Prose from the plan section.</p>",
    },
    dod: ["intent dod entry"],
    status: "human-review",
    requirements: ["SR-007"],
  },
  layout: { collapsed: [], zoomed: null },
};

const WHY: Record<string, unknown> = {
  "src/alpha.ts": { status: "ok", paths: [{ task_id: "T-041", stops_at: null }] },
  "src/beta.ts": { status: "ok", paths: [] },
};

function jsonResponse(body: unknown): Promise<Response> {
  return Promise.resolve({ ok: true, status: 200, json: async () => body } as Response);
}

interface Loaded {
  dom: JSDOM;
  /** Every POST body sent to /api/layout, in order -- the persistence check. */
  layoutWrites: unknown[];
  /** Every file path /api/why was asked about, in order. */
  whyCalls: string[];
}

/** Loads the real review document into jsdom with `fetch` wired to the fixtures
 * above, and waits for the page's async IIFE to finish its first render. */
async function loadPage(layout: unknown = { collapsed: [], zoomed: null }): Promise<Loaded> {
  const layoutWrites: unknown[] = [];
  const whyCalls: string[] = [];
  const fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://127.0.0.1/");
    if (url.pathname === "/api/review") return jsonResponse({ ...REVIEW, layout });
    if (url.pathname === "/api/layout") {
      layoutWrites.push(JSON.parse(String(init?.body ?? "null")));
      return jsonResponse({ ok: true });
    }
    if (url.pathname === "/api/why") {
      const file = url.searchParams.get("file") ?? "";
      whyCalls.push(file);
      return jsonResponse(WHY[file] ?? { status: "unknown", error: "no evidence" });
    }
    throw new Error(`unmocked fetch: ${String(input)}`);
  });

  const dom = new JSDOM(renderReviewHtml(), {
    runScripts: "dangerously",
    url: "http://127.0.0.1/",
    // The inline script is an async IIFE that fetches immediately, so `fetch`
    // must exist before jsdom parses the <script>.
    beforeParse(window) {
      (window as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
    },
  });
  // The first paint only happens after /api/review resolves.
  await vi.waitFor(
    () => expect(dom.window.document.getElementById("context")?.children.length).toBeGreaterThan(0),
    { timeout: 2000, interval: 5 },
  );
  return { dom, layoutWrites, whyCalls };
}

const columns = (dom: JSDOM): string[] =>
  (dom.window.document.getElementById("panes") as HTMLElement).style.gridTemplateColumns.split(/\s+/);

function press(dom: JSDOM, key: string): void {
  dom.window.document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key, bubbles: true }));
}

describe("the served review page, executed", () => {
  // Step 8 check 2: the context pane shows the chain, the DoD and the plan
  // section prose -- not a "Full steps: ..." pointer.
  test("renders the intent chain, the fan-out marker, the DoD and the plan prose", async () => {
    const { dom } = await loadPage();
    const context = dom.window.document.getElementById("context") as HTMLElement;

    const hops = [...context.querySelectorAll(".chain li")].map((li) => li.textContent);
    expect(hops).toHaveLength(2);
    expect(hops[0]).toContain("requirement · SR-007 — The reviewer sees intent");
    // The fan-out marker is the whole point of walkIntentChain counting
    // alternatives: one of two satisfied requirements shown silently is the
    // failure it exists to prevent.
    expect(hops[0]).toContain("(+1 more)");
    expect(hops[1]).not.toContain("more)");

    // The intent's DoD wins over the task file's -- both are present in the
    // fixture precisely so a silent fallback would be visible here.
    expect(context.textContent).toContain("intent dod entry");
    expect(context.textContent).not.toContain("file dod entry");

    expect(context.textContent).toContain("From plan · Task 3: Do the thing");
    expect(context.querySelector(".plan")?.textContent).toContain("Prose from the plan section.");
    expect(context.textContent).not.toContain("Full steps:");
  });

  test("falls back to the task file when the navigator resolved no intent", async () => {
    const layoutWrites: unknown[] = [];
    const dom = new JSDOM(renderReviewHtml(), {
      runScripts: "dangerously",
      url: "http://127.0.0.1/",
      beforeParse(window) {
        (window as unknown as { fetch: typeof fetch }).fetch = vi.fn((input: string | URL, init?: RequestInit) => {
          const url = new URL(String(input), "http://127.0.0.1/");
          if (url.pathname === "/api/review") return jsonResponse({ ...REVIEW, intent: null });
          if (url.pathname === "/api/layout") { layoutWrites.push(init?.body); return jsonResponse({ ok: true }); }
          throw new Error(`unmocked fetch: ${String(input)}`);
        }) as unknown as typeof fetch;
      },
    });
    await vi.waitFor(
      () => expect(dom.window.document.getElementById("context")?.children.length).toBeGreaterThan(0),
      { timeout: 2000, interval: 5 },
    );
    const context = dom.window.document.getElementById("context") as HTMLElement;
    expect(context.textContent).toContain("T-042 — Example task");
    expect(context.textContent).toContain("file dod entry");
    expect(context.textContent).toContain("(no plan section resolved for this task)");
  });

  // Step 8 check 3: collapsing a pane reflows the others.
  test("collapsing a pane narrows it to a rail and leaves the rest at natural width", async () => {
    const { dom, layoutWrites } = await loadPage();
    expect(columns(dom)).toEqual(["1.2fr", "240px", "2fr", "320px"]);

    const tree = dom.window.document.querySelector('.pane[data-pane="tree"]') as HTMLElement;
    (tree.querySelector(".pane-toggle") as HTMLElement).click();

    expect(columns(dom)).toEqual(["1.2fr", "28px", "2fr", "320px"]);
    expect(tree.classList.contains("collapsed")).toBe(true);
    const others = [...dom.window.document.querySelectorAll(".pane")].filter((p) => p !== tree);
    expect(others.every((p) => !p.classList.contains("collapsed"))).toBe(true);

    (tree.querySelector(".pane-toggle") as HTMLElement).click();
    expect(columns(dom)).toEqual(["1.2fr", "240px", "2fr", "320px"]);
    expect(tree.classList.contains("collapsed")).toBe(false);

    // Every layout change is written through, so the next review restores it.
    expect(layoutWrites).toEqual([
      { collapsed: [], zoomed: null },
      { collapsed: ["tree"], zoomed: null },
      { collapsed: [], zoomed: null },
    ]);
  });

  test("every pane has a working collapse control", async () => {
    const { dom } = await loadPage();
    for (const pane of ["context", "tree", "diff", "comments"]) {
      const el = dom.window.document.querySelector(`.pane[data-pane="${pane}"]`) as HTMLElement;
      (el.querySelector(".pane-toggle") as HTMLElement).click();
      expect(el.classList.contains("collapsed")).toBe(true);
      (el.querySelector(".pane-toggle") as HTMLElement).click();
      expect(el.classList.contains("collapsed")).toBe(false);
    }
  });

  // Step 8 check 4: `1` zooms the context pane to fill the window, Esc restores.
  test("digit keys zoom a pane to the full width and Escape restores the layout", async () => {
    const { dom } = await loadPage();
    press(dom, "1");
    expect(columns(dom)).toEqual(["1fr", "0px", "0px", "0px"]);
    const zoomedOut = [...dom.window.document.querySelectorAll(".pane.zoomed-out")].map(
      (p) => (p as HTMLElement).dataset.pane,
    );
    expect(zoomedOut).toEqual(["tree", "diff", "comments"]);

    press(dom, "Escape");
    expect(columns(dom)).toEqual(["1.2fr", "240px", "2fr", "320px"]);
    expect(dom.window.document.querySelectorAll(".pane.zoomed-out")).toHaveLength(0);

    press(dom, "3");
    expect(columns(dom)).toEqual(["0px", "0px", "1fr", "0px"]);
    // The same key toggles back out, so zoom never becomes a trap.
    press(dom, "3");
    expect(columns(dom)).toEqual(["1.2fr", "240px", "2fr", "320px"]);
  });

  test("a zoomed pane outranks a collapsed one rather than rendering both", async () => {
    const { dom } = await loadPage({ collapsed: ["context"], zoomed: null });
    expect(columns(dom)).toEqual(["28px", "240px", "2fr", "320px"]);
    press(dom, "1");
    const context = dom.window.document.querySelector('.pane[data-pane="context"]') as HTMLElement;
    expect(columns(dom)).toEqual(["1fr", "0px", "0px", "0px"]);
    expect(context.classList.contains("collapsed")).toBe(false);
    press(dom, "Escape");
    expect(context.classList.contains("collapsed")).toBe(true);
  });

  test("typing in a field never triggers a zoom", async () => {
    const { dom } = await loadPage();
    const input = dom.window.document.createElement("input");
    dom.window.document.body.appendChild(input);
    input.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "1", bubbles: true }));
    expect(columns(dom)).toEqual(["1.2fr", "240px", "2fr", "320px"]);
  });

  // Step 8 check 5: clicking a second file updates the "why this file" line.
  test("clicking a file fetches its provenance, and a second click uses the cache", async () => {
    const { dom, whyCalls } = await loadPage();

    clickFile(dom, 0);
    await vi.waitFor(() => expect(why(dom)).toContain("T-041"), { timeout: 2000, interval: 5 });
    expect(whyCalls).toEqual(["src/alpha.ts"]);

    clickFile(dom, 1);
    await vi.waitFor(
      () => expect(why(dom)).toBe("why this file: no recorded evidence names it"),
      { timeout: 2000, interval: 5 },
    );
    expect(whyCalls).toEqual(["src/alpha.ts", "src/beta.ts"]);

    // Re-selecting must not re-spawn the reverse lookup.
    clickFile(dom, 0);
    await vi.waitFor(() => expect(why(dom)).toContain("T-041"), { timeout: 2000, interval: 5 });
    expect(whyCalls).toEqual(["src/alpha.ts", "src/beta.ts"]);
  });

  test("a file with no recorded evidence reports unknown rather than an empty pane", async () => {
    const { dom } = await loadPage();
    delete WHY["src/beta.ts"];
    try {
      clickFile(dom, 1);
      await vi.waitFor(() => expect(why(dom)).toContain("unknown"), { timeout: 2000, interval: 5 });
      expect(why(dom)).toContain("no evidence");
    } finally {
      WHY["src/beta.ts"] = { status: "ok", paths: [] };
    }
  });

  // Step 8 check 6: the layout the server remembered is the layout you get back.
  test("a persisted layout is applied on load", async () => {
    const { dom } = await loadPage({ collapsed: ["tree", "comments"], zoomed: null });
    expect(columns(dom)).toEqual(["1.2fr", "28px", "2fr", "28px"]);
    const collapsed = [...dom.window.document.querySelectorAll(".pane.collapsed")].map(
      (p) => (p as HTMLElement).dataset.pane,
    );
    expect(collapsed).toEqual(["tree", "comments"]);
  });

  test("a missing layout falls back to every pane open", async () => {
    const { dom } = await loadPage(null);
    expect(columns(dom)).toEqual(["1.2fr", "240px", "2fr", "320px"]);
  });
});

function why(dom: JSDOM): string {
  return dom.window.document.getElementById("why")?.textContent ?? "";
}

/** Clicks the nth row of the file tree, failing loudly rather than silently
 * doing nothing if the tree rendered fewer rows than the fixture declares. */
function clickFile(dom: JSDOM, index: number): void {
  const rows = [...dom.window.document.querySelectorAll("#tree .file")];
  const row = rows[index];
  if (row === undefined) throw new Error(`file tree rendered ${rows.length} rows; wanted index ${index}`);
  (row as HTMLElement).click();
}
