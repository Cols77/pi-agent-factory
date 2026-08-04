# Browser Doc Viewer for `/review-plans` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-blocking browser surface to `/review-plans` — rendered markdown with a per-document TOC and checkbox-derived progress, a sidebar of every artifact, a traceability panel with gaps, and a layered map of the artifact graph with validation state.

**Architecture:** A loopback HTTP server started by `/review-plans`, serving a zero-dependency inline HTML shell that fetches JSON. The traceability model comes entirely from `uv run python -m factory.trace graph --json` (plan 1) — this extension holds **no** traceability rules, only presentation. Markdown rendering, graph layout, and path validation are pure functions; the server and page contain no logic worth testing indirectly.

**Tech Stack:** TypeScript (ES2022, NodeNext), Node `http`, vitest. No new runtime dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-03-review-plans-browser-and-trace-health-design.md`
- Prerequisite: plan `docs/superpowers/plans/2026-08-03-trace-model-and-cli.md` must be complete — `factory trace graph --json` and `factory trace check` must exist.
- **`pi-ext/factory-watch/package.json` has zero runtime dependencies** (everything is `devDependencies`). Do not add any. No markdown library, no graph library, no HTTP framework.
- All page assets are inline. No external requests of any kind from the served HTML.
- `tsconfig.json` sets `strict: true` **and `noUncheckedIndexedAccess: true`** — indexing an array yields `T | undefined`. Use explicit guards or `!`; the code below already does.
- ESM with NodeNext: intra-package imports must use the `.js` extension (`./md-render.js`), including in tests.
- Tests live in `pi-ext/factory-watch/test/<name>.test.ts` and import from `../src/<name>.js`.
- Run tests with `npm test --prefix pi-ext/factory-watch`; typecheck with `npm run typecheck --prefix pi-ext/factory-watch`.
- The existing TUI surface of `/review-plans` must keep working unchanged.

---

### Task 1: Trace CLI client

**Files:**
- Create: `pi-ext/factory-watch/src/trace-cli.ts`
- Test: `pi-ext/factory-watch/test/trace-cli.test.ts`

**Interfaces:**
- Consumes: `factory trace graph --json` and `factory trace check` from plan 1.
- Produces:
  - `TraceGraph` — `{ nodes: TraceNode[]; edges: TraceEdge[]; gaps: TraceGap[]; validation: Record<string, TraceValidation>; health: TraceHealth }`
  - `TraceNode` — `{ id: string; kind: "br"|"sr"|"spec"|"plan"|"task"; title: string; path: string; exempt: boolean; deferred: string | null }`
  - `TraceEdge` — `{ src: string; dst: string; kind: "source_plan"|"satisfies"|"upstream"|"spec_ref" }`
  - `TraceGap` — `{ node_id: string; kind: string; detail: string; disposition: "pending"|"exempt"|"deferred" }`
  - `TraceValidation` — `{ id: string; state: "passed"|"failed"|"error"|"never_validated"; stale: boolean; metric: string | null; value: number | null; assert_expr: string | null; trials: number | null; declared_trials: number | null; artifacts: string[]; error: string | null }`
  - `TraceHealth` — `{ percent: number; satisfied: number; expected: number; dangling: number; deferred: number; classes: { name: string; satisfied: number; expected: number; exempt: number }[] }`
  - `buildTraceCommand(sub: string[]): { bin: string; args: string[] }`
  - `loadTraceGraph(cwd: string): { ok: true; graph: TraceGraph } | { ok: false; error: string }`

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/trace-cli.test.ts`:

```ts
import { describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import { buildTraceCommand, loadTraceGraph } from "../src/trace-cli.js";

const GRAPH = {
  nodes: [{ id: "T-001", kind: "task", title: "t", path: "tasks/T-001.md", exempt: false, deferred: null }],
  edges: [],
  gaps: [],
  validation: {},
  health: { percent: 50, satisfied: 1, expected: 2, dangling: 0, deferred: 0, classes: [] },
};

describe("buildTraceCommand", () => {
  test("runs the trace module through uv, matching process-control.ts", () => {
    expect(buildTraceCommand(["graph", "--json"])).toEqual({
      bin: "uv",
      args: ["run", "python", "-m", "factory.trace", "graph", "--json"],
    });
  });
});

describe("loadTraceGraph", () => {
  test("parses stdout into a graph", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(GRAPH), stderr: "" });
    const result = loadTraceGraph("/repo");
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.graph.health.percent).toBe(50);
  });

  test("reports a non-zero exit instead of throwing", () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "", stderr: "boom" });
    const result = loadTraceGraph("/repo");
    expect(result).toEqual({ ok: false, error: "factory trace exited 2: boom" });
  });

  test("reports unparsable stdout instead of throwing", () => {
    spawnSync.mockReturnValue({ status: 0, stdout: "not json", stderr: "" });
    const result = loadTraceGraph("/repo");
    expect(result.ok).toBe(false);
  });

  test("reports a missing uv binary instead of throwing", () => {
    spawnSync.mockReturnValue({ error: new Error("spawnSync uv ENOENT"), status: null, stdout: "", stderr: "" });
    const result = loadTraceGraph("/repo");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("ENOENT");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- trace-cli`
Expected: FAIL — cannot resolve `../src/trace-cli.js`

- [ ] **Step 3: Write minimal implementation**

Create `pi-ext/factory-watch/src/trace-cli.ts`:

```ts
import { spawnSync } from "node:child_process";

export type TraceNodeKind = "br" | "sr" | "spec" | "plan" | "task";
export type TraceEdgeKind = "source_plan" | "satisfies" | "upstream" | "spec_ref";
export type TraceDisposition = "pending" | "exempt" | "deferred";
export type TraceValidationState = "passed" | "failed" | "error" | "never_validated";

export interface TraceNode {
  id: string;
  kind: TraceNodeKind;
  title: string;
  path: string;
  exempt: boolean;
  deferred: string | null;
}

export interface TraceEdge {
  src: string;
  dst: string;
  kind: TraceEdgeKind;
}

export interface TraceGap {
  node_id: string;
  kind: string;
  detail: string;
  disposition: TraceDisposition;
}

export interface TraceValidation {
  id: string;
  state: TraceValidationState;
  stale: boolean;
  metric: string | null;
  value: number | null;
  assert_expr: string | null;
  trials: number | null;
  declared_trials: number | null;
  artifacts: string[];
  error: string | null;
}

export interface TraceHealthClass {
  name: string;
  satisfied: number;
  expected: number;
  exempt: number;
}

export interface TraceHealth {
  percent: number;
  satisfied: number;
  expected: number;
  dangling: number;
  deferred: number;
  classes: TraceHealthClass[];
}

export interface TraceGraph {
  nodes: TraceNode[];
  edges: TraceEdge[];
  gaps: TraceGap[];
  validation: Record<string, TraceValidation>;
  health: TraceHealth;
}

export type TraceResult<T> = { ok: true; graph: T } | { ok: false; error: string };

// Mirrors process-control.ts:13 -- the established way this extension reaches
// the Python side.
export function buildTraceCommand(sub: string[]): { bin: string; args: string[] } {
  return { bin: "uv", args: ["run", "python", "-m", "factory.trace", ...sub] };
}

export function loadTraceGraph(cwd: string): TraceResult<TraceGraph> {
  const cmd = buildTraceCommand(["graph", "--json"]);
  const result = spawnSync(cmd.bin, cmd.args, { cwd, encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
  if (result.error) {
    return { ok: false, error: String(result.error.message ?? result.error) };
  }
  if (result.status !== 0) {
    return { ok: false, error: `factory trace exited ${result.status}: ${(result.stderr ?? "").trim()}` };
  }
  try {
    return { ok: true, graph: JSON.parse(result.stdout) as TraceGraph };
  } catch (err) {
    return { ok: false, error: `could not parse factory trace output: ${String(err)}` };
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test --prefix pi-ext/factory-watch -- trace-cli`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/trace-cli.ts pi-ext/factory-watch/test/trace-cli.test.ts
git commit -m "feat(factory-watch): client for the factory trace CLI

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Markdown renderer with TOC and progress

**Files:**
- Create: `pi-ext/factory-watch/src/md-render.ts`
- Test: `pi-ext/factory-watch/test/md-render.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `TocEntry { level: number; text: string; slug: string }`,
  `Progress { done: number; total: number }`,
  `RenderedDoc { html: string; toc: TocEntry[]; progress: Progress | null }`,
  `stripDocFrontmatter(src: string): string`,
  `renderMarkdown(src: string): RenderedDoc`.
- Feature set is exactly what spec §1 measured: headings, fenced code (literal, no
  highlighting), bullets, task checkboxes, ordered lists, tables, blockquotes,
  hrules, bold, italic, inline code, links.

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/md-render.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import { renderMarkdown, stripDocFrontmatter } from "../src/md-render.js";

describe("stripDocFrontmatter", () => {
  test("removes a leading frontmatter block", () => {
    expect(stripDocFrontmatter("---\nid: T-1\n---\n\n# Title\n")).toBe("\n# Title\n");
  });

  test("leaves a document with no frontmatter untouched", () => {
    // Plans historically have none, but trace exempt/defer can add one later.
    expect(stripDocFrontmatter("# Title\n\nbody\n")).toBe("# Title\n\nbody\n");
  });

  test("does not treat a mid-document hrule as frontmatter", () => {
    const src = "# Title\n\n---\n\nmore\n";
    expect(stripDocFrontmatter(src)).toBe(src);
  });
});

describe("renderMarkdown", () => {
  test("renders headings and collects a toc with stable slugs", () => {
    const out = renderMarkdown("# One\n\n## Two Words\n");
    expect(out.html).toContain('<h1 id="one">One</h1>');
    expect(out.html).toContain('<h2 id="two-words">Two Words</h2>');
    expect(out.toc).toEqual([
      { level: 1, text: "One", slug: "one" },
      { level: 2, text: "Two Words", slug: "two-words" },
    ]);
  });

  test("disambiguates duplicate heading slugs", () => {
    const out = renderMarkdown("## Steps\n\n## Steps\n");
    expect(out.toc.map((t) => t.slug)).toEqual(["steps", "steps-2"]);
  });

  test("renders fenced code literally without highlighting", () => {
    const out = renderMarkdown("```python\nx = 1 < 2\n```\n");
    expect(out.html).toContain('<pre><code class="language-python">x = 1 &lt; 2\n</code></pre>');
  });

  test("markdown inside a fence is not interpreted", () => {
    const out = renderMarkdown("```\n# not a heading\n**not bold**\n```\n");
    expect(out.html).not.toContain("<h1");
    expect(out.html).not.toContain("<strong>");
  });

  test("escapes html in prose", () => {
    const out = renderMarkdown("a <script>alert(1)</script> b\n");
    expect(out.html).not.toContain("<script>");
    expect(out.html).toContain("&lt;script&gt;");
  });

  test("renders bullets, inline code, bold, italic and links", () => {
    const out = renderMarkdown("- a `code` b **bold** c *it* d [x](http://e)\n");
    expect(out.html).toContain("<ul>");
    expect(out.html).toContain("<code>code</code>");
    expect(out.html).toContain("<strong>bold</strong>");
    expect(out.html).toContain("<em>it</em>");
    expect(out.html).toContain('<a href="http://e">x</a>');
  });

  test("renders ordered lists", () => {
    expect(renderMarkdown("1. first\n2. second\n").html).toContain("<ol>");
  });

  test("renders checkboxes and derives progress", () => {
    const out = renderMarkdown("- [x] done\n- [ ] todo\n- [ ] other\n");
    expect(out.html).toContain('<input type="checkbox" checked disabled>');
    expect(out.progress).toEqual({ done: 1, total: 3 });
  });

  test("progress is null when a document has no checkboxes", () => {
    expect(renderMarkdown("# Spec\n\nprose\n").progress).toBeNull();
  });

  test("renders tables", () => {
    const out = renderMarkdown("| a | b |\n|---|---|\n| 1 | 2 |\n");
    expect(out.html).toContain("<table>");
    expect(out.html).toContain("<th>a</th>");
    expect(out.html).toContain("<td>2</td>");
  });

  test("renders blockquotes and hrules", () => {
    const out = renderMarkdown("> quoted\n\n---\n");
    expect(out.html).toContain("<blockquote>");
    expect(out.html).toContain("<hr>");
  });

  test("renders paragraphs", () => {
    expect(renderMarkdown("hello world\n").html).toContain("<p>hello world</p>");
  });

  test("handles an empty document", () => {
    expect(renderMarkdown("")).toEqual({ html: "", toc: [], progress: null });
  });

  test("an unterminated fence does not lose the rest of the document", () => {
    const out = renderMarkdown("```\nx = 1\n");
    expect(out.html).toContain("x = 1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- md-render`
Expected: FAIL — cannot resolve `../src/md-render.js`

- [ ] **Step 3: Write minimal implementation**

Create `pi-ext/factory-watch/src/md-render.ts`:

```ts
export interface TocEntry {
  level: number;
  text: string;
  slug: string;
}

export interface Progress {
  done: number;
  total: number;
}

export interface RenderedDoc {
  html: string;
  toc: TocEntry[];
  progress: Progress | null;
}

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
};

function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (ch) => ESCAPES[ch] ?? ch);
}

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

// Escaping happens first, so any markup in the source is inert by the time
// emphasis and links are applied.
function renderInline(text: string): string {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]*)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>');
}

function isTableSeparator(line: string | undefined): boolean {
  return line !== undefined && /^\s*\|?[\s:-]*-[\s|:-]*$/.test(line) && line.includes("-");
}

function splitRow(line: string): string[] {
  return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
}

export function stripDocFrontmatter(src: string): string {
  if (!src.startsWith("---\n")) return src;
  const end = src.indexOf("\n---", 3);
  if (end === -1) return src;
  const after = src.indexOf("\n", end + 1);
  return after === -1 ? "" : src.slice(after + 1);
}

export function renderMarkdown(src: string): RenderedDoc {
  const lines = stripDocFrontmatter(src).split("\n");
  const out: string[] = [];
  const toc: TocEntry[] = [];
  const seenSlugs = new Map<string, number>();
  let done = 0;
  let total = 0;
  let index = 0;

  const openLists: string[] = [];

  function closeLists(toDepth: number): void {
    while (openLists.length > toDepth) {
      out.push(`</${openLists.pop()}>`);
    }
  }

  function uniqueSlug(text: string): string {
    const base = slugify(text) || "section";
    const count = (seenSlugs.get(base) ?? 0) + 1;
    seenSlugs.set(base, count);
    return count === 1 ? base : `${base}-${count}`;
  }

  while (index < lines.length) {
    const line = lines[index] ?? "";

    const fence = /^```(\w*)/.exec(line);
    if (fence) {
      closeLists(0);
      const lang = fence[1] ?? "";
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? "").startsWith("```")) {
        body.push(lines[index] ?? "");
        index += 1;
      }
      index += 1; // consume the closing fence, or run off the end harmlessly
      const cls = lang ? ` class="language-${escapeHtml(lang)}"` : "";
      out.push(`<pre><code${cls}>${escapeHtml(body.join("\n"))}\n</code></pre>`);
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      closeLists(0);
      const level = (heading[1] ?? "#").length;
      const text = (heading[2] ?? "").trim();
      const slug = uniqueSlug(text);
      toc.push({ level, text, slug });
      out.push(`<h${level} id="${slug}">${renderInline(text)}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {
      closeLists(0);
      out.push("<hr>");
      index += 1;
      continue;
    }

    if (/^\s*>/.test(line)) {
      closeLists(0);
      const body: string[] = [];
      while (index < lines.length && /^\s*>/.test(lines[index] ?? "")) {
        body.push((lines[index] ?? "").replace(/^\s*>\s?/, ""));
        index += 1;
      }
      out.push(`<blockquote>${renderInline(body.join(" "))}</blockquote>`);
      continue;
    }

    if (/^\s*\|/.test(line) && isTableSeparator(lines[index + 1])) {
      closeLists(0);
      const header = splitRow(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && /^\s*\|/.test(lines[index] ?? "")) {
        rows.push(splitRow(lines[index] ?? ""));
        index += 1;
      }
      const head = header.map((c) => `<th>${renderInline(c)}</th>`).join("");
      const body = rows
        .map((r) => `<tr>${r.map((c) => `<td>${renderInline(c)}</td>`).join("")}</tr>`)
        .join("");
      out.push(`<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
      continue;
    }

    const item = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(line);
    if (item) {
      const indent = (item[1] ?? "").length;
      const depth = Math.floor(indent / 2) + 1;
      const tag = (item[2] ?? "-") === "-" || (item[2] ?? "") === "*" ? "ul" : "ol";
      let text = item[3] ?? "";

      closeLists(depth);
      while (openLists.length < depth) {
        openLists.push(tag);
        out.push(`<${tag}>`);
      }

      const checkbox = /^\[([ xX])\]\s*(.*)$/.exec(text);
      if (checkbox) {
        total += 1;
        const checked = (checkbox[1] ?? " ").toLowerCase() === "x";
        if (checked) done += 1;
        text = checkbox[2] ?? "";
        const attrs = checked ? "checked disabled" : "disabled";
        out.push(`<li><input type="checkbox" ${attrs}>${renderInline(text)}</li>`);
      } else {
        out.push(`<li>${renderInline(text)}</li>`);
      }
      index += 1;
      continue;
    }

    if (line.trim() === "") {
      closeLists(0);
      index += 1;
      continue;
    }

    closeLists(0);
    const paragraph: string[] = [];
    while (index < lines.length && (lines[index] ?? "").trim() !== "") {
      const next = lines[index] ?? "";
      if (/^(#{1,6}\s|```|\s*>|\s*\|)/.test(next) || /^(\s*)([-*]|\d+\.)\s/.test(next)) break;
      paragraph.push(next);
      index += 1;
    }
    if (paragraph.length > 0) {
      out.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
    }
  }

  closeLists(0);
  return {
    html: out.join("\n"),
    toc,
    progress: total > 0 ? { done, total } : null,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test --prefix pi-ext/factory-watch -- md-render`
Expected: PASS — 18 passed

- [ ] **Step 5: Render every real document as a smoke check**

Create `pi-ext/factory-watch/test/md-render.corpus.test.ts`:

```ts
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { renderMarkdown } from "../src/md-render.js";

const ROOT = join(import.meta.dirname, "..", "..", "..");

function docsIn(...parts: string[]): string[] {
  const dir = join(ROOT, ...parts);
  try {
    return readdirSync(dir).filter((f) => f.endsWith(".md")).map((f) => join(dir, f));
  } catch {
    return [];
  }
}

describe("md-render against the real corpus", () => {
  const files = [
    ...docsIn("docs", "superpowers", "specs"),
    ...docsIn("docs", "superpowers", "plans"),
    ...docsIn("tasks"),
  ];

  test("finds the corpus", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  test.each(files)("renders %s without throwing and emits no raw script tag", (file) => {
    const out = renderMarkdown(readFileSync(file, "utf-8"));
    expect(out.html).not.toContain("<script>");
  });
});
```

Run: `npm test --prefix pi-ext/factory-watch -- md-render`
Expected: PASS — every spec, plan and task renders. This is the check that the
subset measured in spec §1 is actually sufficient for real documents.

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/md-render.ts pi-ext/factory-watch/test/md-render.test.ts pi-ext/factory-watch/test/md-render.corpus.test.ts
git commit -m "feat(factory-watch): dependency-free markdown renderer with toc and progress

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Layered graph layout

**Files:**
- Create: `pi-ext/factory-watch/src/graph-layout.ts`
- Test: `pi-ext/factory-watch/test/graph-layout.test.ts`

**Interfaces:**
- Consumes: `TraceNode`, `TraceEdge` (Task 1).
- Produces: `LaidOutNode { id: string; kind: TraceNodeKind; title: string; x: number; y: number }`,
  `LaidOutEdge { src: string; dst: string; x1: number; y1: number; x2: number; y2: number }`,
  `Layout { nodes: LaidOutNode[]; edges: LaidOutEdge[]; width: number; height: number }`,
  `layoutGraph(nodes: TraceNode[], edges: TraceEdge[]): Layout`,
  `neighbourhood(nodes, edges, rootId, hops): { nodes: TraceNode[]; edges: TraceEdge[] }`.
- Rank is the node kind, so no rank-assignment pass is needed: `br=0, sr=1, task=2, plan=3, spec=4`.

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/graph-layout.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import { layoutGraph, neighbourhood } from "../src/graph-layout.js";
import type { TraceEdge, TraceNode } from "../src/trace-cli.js";

function node(id: string, kind: TraceNode["kind"]): TraceNode {
  return { id, kind, title: id, path: `${id}.md`, exempt: false, deferred: null };
}

describe("layoutGraph", () => {
  test("assigns columns by node kind", () => {
    const nodes = [node("SR-001", "sr"), node("T-001", "task"), node("plan:p.md", "plan")];
    const laid = layoutGraph(nodes, []);
    const byId = new Map(laid.nodes.map((n) => [n.id, n]));
    expect(byId.get("SR-001")!.x).toBeLessThan(byId.get("T-001")!.x);
    expect(byId.get("T-001")!.x).toBeLessThan(byId.get("plan:p.md")!.x);
  });

  test("is deterministic regardless of input order", () => {
    const nodes = [node("T-002", "task"), node("T-001", "task"), node("SR-001", "sr")];
    const edges: TraceEdge[] = [{ src: "T-001", dst: "SR-001", kind: "satisfies" }];
    const a = layoutGraph(nodes, edges);
    const b = layoutGraph([...nodes].reverse(), edges);
    expect(a.nodes).toEqual(b.nodes);
  });

  test("edge endpoints resolve to their node coordinates", () => {
    const nodes = [node("SR-001", "sr"), node("T-001", "task")];
    const edges: TraceEdge[] = [{ src: "T-001", dst: "SR-001", kind: "satisfies" }];
    const laid = layoutGraph(nodes, edges);
    const t = laid.nodes.find((n) => n.id === "T-001")!;
    const sr = laid.nodes.find((n) => n.id === "SR-001")!;
    expect(laid.edges[0]).toEqual({ src: "T-001", dst: "SR-001", x1: t.x, y1: t.y, x2: sr.x, y2: sr.y });
  });

  test("edges pointing at absent nodes are dropped from the drawing", () => {
    const laid = layoutGraph([node("SR-001", "sr")], [{ src: "SR-001", dst: "BR-002", kind: "upstream" }]);
    expect(laid.edges).toEqual([]);
  });

  test("barycentre ordering pulls a connected node toward its neighbour", () => {
    // T-002 links to SR-002 (row 1); T-001 links to SR-001 (row 0). Ordering the
    // task column by barycentre should put T-001 above T-002, uncrossing them.
    const nodes = [node("SR-001", "sr"), node("SR-002", "sr"), node("T-002", "task"), node("T-001", "task")];
    const edges: TraceEdge[] = [
      { src: "T-002", dst: "SR-002", kind: "satisfies" },
      { src: "T-001", dst: "SR-001", kind: "satisfies" },
    ];
    const laid = layoutGraph(nodes, edges);
    const t1 = laid.nodes.find((n) => n.id === "T-001")!;
    const t2 = laid.nodes.find((n) => n.id === "T-002")!;
    expect(t1.y).toBeLessThan(t2.y);
  });

  test("reports a canvas size covering every node", () => {
    const laid = layoutGraph([node("SR-001", "sr"), node("SR-002", "sr")], []);
    expect(laid.width).toBeGreaterThan(0);
    expect(laid.height).toBeGreaterThanOrEqual(Math.max(...laid.nodes.map((n) => n.y)));
  });

  test("an empty graph lays out without error", () => {
    expect(layoutGraph([], [])).toEqual({ nodes: [], edges: [], width: 0, height: 0 });
  });
});

describe("neighbourhood", () => {
  const nodes = [node("SR-001", "sr"), node("T-001", "task"), node("plan:p.md", "plan"), node("T-999", "task")];
  const edges: TraceEdge[] = [
    { src: "T-001", dst: "SR-001", kind: "satisfies" },
    { src: "T-001", dst: "plan:p.md", kind: "source_plan" },
  ];

  test("one hop returns the root and its direct neighbours in both directions", () => {
    const sub = neighbourhood(nodes, edges, "T-001", 1);
    expect(sub.nodes.map((n) => n.id).sort()).toEqual(["SR-001", "T-001", "plan:p.md"]);
  });

  test("follows edges backwards too", () => {
    const sub = neighbourhood(nodes, edges, "SR-001", 1);
    expect(sub.nodes.map((n) => n.id).sort()).toEqual(["SR-001", "T-001"]);
  });

  test("an unconnected root returns just itself", () => {
    expect(neighbourhood(nodes, edges, "T-999", 1).nodes.map((n) => n.id)).toEqual(["T-999"]);
  });

  test("an unknown root returns nothing", () => {
    expect(neighbourhood(nodes, edges, "T-404", 1).nodes).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- graph-layout`
Expected: FAIL — cannot resolve `../src/graph-layout.js`

- [ ] **Step 3: Write minimal implementation**

Create `pi-ext/factory-watch/src/graph-layout.ts`:

```ts
import type { TraceEdge, TraceNode, TraceNodeKind } from "./trace-cli.js";

export interface LaidOutNode {
  id: string;
  kind: TraceNodeKind;
  title: string;
  x: number;
  y: number;
}

export interface LaidOutEdge {
  src: string;
  dst: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface Layout {
  nodes: LaidOutNode[];
  edges: LaidOutEdge[];
  width: number;
  height: number;
}

// Rank is the node kind, so layer assignment is free -- only within-rank
// ordering needs a heuristic. Spec section 7.
const RANK: Record<TraceNodeKind, number> = { br: 0, sr: 1, task: 2, plan: 3, spec: 4 };

const COLUMN_WIDTH = 260;
const ROW_HEIGHT = 44;
const BARYCENTRE_PASSES = 4;

export function layoutGraph(nodes: TraceNode[], edges: TraceEdge[]): Layout {
  if (nodes.length === 0) return { nodes: [], edges: [], width: 0, height: 0 };

  const present = new Set(nodes.map((n) => n.id));
  const drawable = edges.filter((e) => present.has(e.src) && present.has(e.dst));

  const columns = new Map<number, TraceNode[]>();
  for (const node of [...nodes].sort((a, b) => a.id.localeCompare(b.id))) {
    const rank = RANK[node.kind];
    const column = columns.get(rank) ?? [];
    column.push(node);
    columns.set(rank, column);
  }

  const rowOf = new Map<string, number>();
  for (const column of columns.values()) {
    column.forEach((node, i) => rowOf.set(node.id, i));
  }

  const neighboursOf = new Map<string, string[]>();
  for (const edge of drawable) {
    neighboursOf.set(edge.src, [...(neighboursOf.get(edge.src) ?? []), edge.dst]);
    neighboursOf.set(edge.dst, [...(neighboursOf.get(edge.dst) ?? []), edge.src]);
  }

  const ranks = [...columns.keys()].sort((a, b) => a - b);
  for (let pass = 0; pass < BARYCENTRE_PASSES; pass += 1) {
    for (const rank of ranks) {
      const column = columns.get(rank) ?? [];
      const barycentre = new Map<string, number>();
      for (const node of column) {
        const rows = (neighboursOf.get(node.id) ?? [])
          .map((id) => rowOf.get(id))
          .filter((r): r is number => r !== undefined);
        const mean = rows.length > 0 ? rows.reduce((a, b) => a + b, 0) / rows.length : rowOf.get(node.id) ?? 0;
        barycentre.set(node.id, mean);
      }
      // id is the final tiebreak, so the result never depends on input order.
      column.sort((a, b) => (barycentre.get(a.id) ?? 0) - (barycentre.get(b.id) ?? 0) || a.id.localeCompare(b.id));
      column.forEach((node, i) => rowOf.set(node.id, i));
    }
  }

  const laidOut: LaidOutNode[] = [];
  for (const rank of ranks) {
    for (const node of columns.get(rank) ?? []) {
      laidOut.push({
        id: node.id,
        kind: node.kind,
        title: node.title,
        x: rank * COLUMN_WIDTH,
        y: (rowOf.get(node.id) ?? 0) * ROW_HEIGHT,
      });
    }
  }

  const positions = new Map(laidOut.map((n) => [n.id, n]));
  const laidOutEdges: LaidOutEdge[] = drawable.map((edge) => {
    const from = positions.get(edge.src)!;
    const to = positions.get(edge.dst)!;
    return { src: edge.src, dst: edge.dst, x1: from.x, y1: from.y, x2: to.x, y2: to.y };
  });

  return {
    nodes: laidOut,
    edges: laidOutEdges,
    width: Math.max(...laidOut.map((n) => n.x)) + COLUMN_WIDTH,
    height: Math.max(...laidOut.map((n) => n.y)) + ROW_HEIGHT,
  };
}

export function neighbourhood(
  nodes: TraceNode[],
  edges: TraceEdge[],
  rootId: string,
  hops: number,
): { nodes: TraceNode[]; edges: TraceEdge[] } {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  if (!byId.has(rootId)) return { nodes: [], edges: [] };

  const reached = new Set([rootId]);
  let frontier = [rootId];
  for (let hop = 0; hop < hops; hop += 1) {
    const next: string[] = [];
    for (const edge of edges) {
      if (frontier.includes(edge.src) && byId.has(edge.dst) && !reached.has(edge.dst)) {
        reached.add(edge.dst);
        next.push(edge.dst);
      }
      if (frontier.includes(edge.dst) && byId.has(edge.src) && !reached.has(edge.src)) {
        reached.add(edge.src);
        next.push(edge.src);
      }
    }
    frontier = next;
  }

  return {
    nodes: nodes.filter((n) => reached.has(n.id)),
    edges: edges.filter((e) => reached.has(e.src) && reached.has(e.dst)),
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test --prefix pi-ext/factory-watch -- graph-layout`
Expected: PASS — 11 passed

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/graph-layout.ts pi-ext/factory-watch/test/graph-layout.test.ts
git commit -m "feat(factory-watch): layered graph layout with barycentre ordering

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Docs server with path validation and singleton lifetime

**Files:**
- Create: `pi-ext/factory-watch/src/docs-server.ts`
- Test: `pi-ext/factory-watch/test/docs-server.test.ts`

**Interfaces:**
- Consumes: `loadTraceGraph` (Task 1), `renderMarkdown` (Task 2), `layoutGraph` and
  `neighbourhood` (Task 3), `renderDocsHtml` (Task 5).
- Produces: `resolveDocPath(root: string, relative: string): string | null`,
  `RunningDocsServer { url: string; port: number; close(): void }`,
  `ensureDocsServer(cwd: string): Promise<RunningDocsServer>`,
  `stopDocsServer(): boolean`.
- **Does not block.** There is no decision promise; the server outlives the command
  that started it and is reused on subsequent invocations.

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/docs-server.test.ts`:

```ts
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test, vi } from "vitest";

const spawnSync = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawnSync }));

import { ensureDocsServer, resolveDocPath, stopDocsServer } from "../src/docs-server.js";

const EMPTY_GRAPH = {
  nodes: [], edges: [], gaps: [], validation: {},
  health: { percent: 100, satisfied: 0, expected: 0, dangling: 0, deferred: 0, classes: [] },
};

function repo(): string {
  const root = mkdtempSync(join(tmpdir(), "docs-server-"));
  mkdirSync(join(root, "tasks"), { recursive: true });
  writeFileSync(join(root, "tasks", "T-001.md"), "---\nid: T-001\n---\n\n# Task One\n\n- [x] a\n- [ ] b\n");
  writeFileSync(join(root, "secret.txt"), "do not serve me");
  return root;
}

afterEach(() => {
  stopDocsServer();
  vi.clearAllMocks();
});

describe("resolveDocPath", () => {
  test("resolves a path inside the repo", () => {
    expect(resolveDocPath("/repo", "tasks/T-001.md")).toBe(join("/repo", "tasks", "T-001.md"));
  });

  test("rejects traversal out of the repo", () => {
    expect(resolveDocPath("/repo", "../../etc/passwd")).toBeNull();
  });

  test("rejects an absolute path outside the repo", () => {
    expect(resolveDocPath("/repo", "/etc/passwd")).toBeNull();
  });

  test("rejects a path that merely shares a prefix with the repo", () => {
    expect(resolveDocPath("/repo", "../repo-evil/x.md")).toBeNull();
  });
});

describe("ensureDocsServer", () => {
  test("serves the shell page on /", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(server.url);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("<!doctype html>");
  });

  test("serves the trace graph on /api/graph", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    const body = await (await fetch(`${server.url}/api/graph`)).json();
    expect(body.health.percent).toBe(100);
  });

  test("reports a trace CLI failure as json instead of crashing", async () => {
    spawnSync.mockReturnValue({ status: 2, stdout: "", stderr: "nope" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/graph`);
    expect(res.status).toBe(503);
    expect((await res.json()).error).toContain("nope");
  });

  test("serves a laid-out graph on /api/layout", async () => {
    const graph = {
      ...EMPTY_GRAPH,
      nodes: [
        { id: "SR-001", kind: "sr", title: "s", path: "requirements/SR-001.md", exempt: false, deferred: null },
        { id: "T-001", kind: "task", title: "t", path: "tasks/T-001.md", exempt: false, deferred: null },
      ],
      edges: [{ src: "T-001", dst: "SR-001", kind: "satisfies" }],
    };
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(graph), stderr: "" });
    const server = await ensureDocsServer(repo());
    const full = await (await fetch(`${server.url}/api/layout`)).json();
    expect(full.nodes).toHaveLength(2);
    expect(full.edges).toHaveLength(1);
    const scoped = await (await fetch(`${server.url}/api/layout?root=SR-001&hops=1`)).json();
    expect(scoped.nodes.map((n: { id: string }) => n.id).sort()).toEqual(["SR-001", "T-001"]);
  });

  test("renders a document on /api/doc", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    const body = await (await fetch(`${server.url}/api/doc?path=tasks/T-001.md`)).json();
    expect(body.html).toContain("Task One");
    expect(body.progress).toEqual({ done: 1, total: 2 });
    expect(body.toc[0].text).toBe("Task One");
  });

  test("refuses to serve a file outside the repo", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    const res = await fetch(`${server.url}/api/doc?path=../../etc/passwd`);
    expect(res.status).toBe(403);
  });

  test("404s a document that does not exist", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    expect((await fetch(`${server.url}/api/doc?path=tasks/gone.md`)).status).toBe(404);
  });

  test("reuses the running server rather than starting a second one", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const root = repo();
    const first = await ensureDocsServer(root);
    const second = await ensureDocsServer(root);
    expect(second.port).toBe(first.port);
  });

  test("binds loopback only", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    const server = await ensureDocsServer(repo());
    expect(server.url).toContain("127.0.0.1");
  });

  test("stopDocsServer reports whether anything was running", async () => {
    spawnSync.mockReturnValue({ status: 0, stdout: JSON.stringify(EMPTY_GRAPH), stderr: "" });
    await ensureDocsServer(repo());
    expect(stopDocsServer()).toBe(true);
    expect(stopDocsServer()).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- docs-server`
Expected: FAIL — cannot resolve `../src/docs-server.js`

- [ ] **Step 3: Write minimal implementation**

Create `pi-ext/factory-watch/src/docs-server.ts`:

```ts
import { createServer } from "node:http";
import type { IncomingMessage, Server, ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { isAbsolute, resolve, sep } from "node:path";
import { renderMarkdown } from "./md-render.js";
import { layoutGraph, neighbourhood } from "./graph-layout.js";
import { loadTraceGraph } from "./trace-cli.js";
import { renderDocsHtml } from "./docs-html.js";

export interface RunningDocsServer {
  url: string;
  port: number;
  close(): void;
}

let running: { server: Server; handle: RunningDocsServer } | null = null;

// Loopback binding is not on its own an authorization boundary -- any process on
// the machine can reach the port -- so every served path is confined to the repo.
export function resolveDocPath(root: string, relative: string): string | null {
  if (isAbsolute(relative)) return null;
  const rootResolved = resolve(root);
  const target = resolve(rootResolved, relative);
  if (target !== rootResolved && !target.startsWith(rootResolved + sep)) return null;
  return target;
}

function json(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function handle(cwd: string, req: IncomingMessage, res: ServerResponse): void {
  const url = new URL(req.url ?? "/", "http://127.0.0.1");

  if (req.method === "GET" && url.pathname === "/") {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(renderDocsHtml());
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/graph") {
    const result = loadTraceGraph(cwd);
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    json(res, 200, result.graph);
    return;
  }

  // Layout is computed here, by the tested pure function, so the page never
  // grows a second untested copy of the same arithmetic.
  if (req.method === "GET" && url.pathname === "/api/layout") {
    const result = loadTraceGraph(cwd);
    if (!result.ok) {
      json(res, 503, { error: result.error });
      return;
    }
    const root = url.searchParams.get("root");
    const hops = Number(url.searchParams.get("hops") ?? "1");
    const scoped =
      root === null
        ? { nodes: result.graph.nodes, edges: result.graph.edges }
        : neighbourhood(result.graph.nodes, result.graph.edges, root, Number.isFinite(hops) ? hops : 1);
    json(res, 200, layoutGraph(scoped.nodes, scoped.edges));
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/doc") {
    const relative = url.searchParams.get("path") ?? "";
    const target = resolveDocPath(cwd, relative);
    if (target === null) {
      json(res, 403, { error: "path outside repository" });
      return;
    }
    let raw: string;
    try {
      raw = readFileSync(target, "utf-8");
    } catch {
      json(res, 404, { error: `not found: ${relative}` });
      return;
    }
    json(res, 200, { path: relative, ...renderMarkdown(raw) });
    return;
  }

  res.writeHead(404);
  res.end();
}

export function ensureDocsServer(cwd: string): Promise<RunningDocsServer> {
  if (running !== null) return Promise.resolve(running.handle);
  return new Promise((resolveStart) => {
    const server = createServer((req, res) => handle(cwd, req, res));
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as AddressInfo).port;
      const handleObj: RunningDocsServer = {
        url: `http://127.0.0.1:${port}`,
        port,
        close() {
          stopDocsServer();
        },
      };
      running = { server, handle: handleObj };
      resolveStart(handleObj);
    });
  });
}

export function stopDocsServer(): boolean {
  if (running === null) return false;
  running.server.close();
  running = null;
  return true;
}
```

- [ ] **Step 4: Run test to verify it fails on the missing page module**

Run: `npm test --prefix pi-ext/factory-watch -- docs-server`
Expected: FAIL — cannot resolve `./docs-html.js`. That module is Task 5; write it now, then return here.

- [ ] **Step 5: Commit after Task 5 passes**

Commit this file together with Task 5's page, since neither compiles without the other:

```bash
git add pi-ext/factory-watch/src/docs-server.ts pi-ext/factory-watch/test/docs-server.test.ts
git commit -m "feat(factory-watch): non-blocking docs server with repo-confined paths

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The page

**Files:**
- Create: `pi-ext/factory-watch/src/docs-html.ts`
- Test: `pi-ext/factory-watch/test/docs-html.test.ts`

**Interfaces:**
- Consumes: nothing at build time; the served script fetches `/api/graph` and `/api/doc`.
- Produces: `renderDocsHtml(): string`.
- Mirrors `review-html.ts`: one function returning a complete inline document.

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/docs-html.test.ts`:

```ts
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

  test("carries a legend for all five validation states", () => {
    for (const label of ["pass", "fail", "error", "never validated", "stale"]) {
      expect(html.toLowerCase()).toContain(label);
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test --prefix pi-ext/factory-watch -- docs-html`
Expected: FAIL — cannot resolve `../src/docs-html.js`

- [ ] **Step 3: Write minimal implementation**

Create `pi-ext/factory-watch/src/docs-html.ts`:

```ts
export function renderDocsHtml(): string {
  // Everything inline; no external requests (loopback-only, CSP-friendly),
  // mirroring review-html.ts. Document HTML from /api/doc is produced by
  // md-render.ts, which escapes its input before emitting any markup.
  return `<!doctype html>
<html>
<head><meta charset="utf-8"><title>Docs</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 13px/1.6 system-ui, sans-serif; margin: 0; display: grid;
         grid-template-columns: 280px 1fr 300px; height: 100vh; }
  #sidebar, #right { overflow: auto; padding: 8px; }
  #sidebar { border-right: 1px solid #8884; }
  #right { border-left: 1px solid #8884; }
  #main { overflow: auto; padding: 16px 24px; }
  #doc { max-width: 80ch; }
  #doc pre { background: #8881; padding: 8px; overflow-x: auto; }
  #doc table { border-collapse: collapse; display: block; overflow-x: auto; }
  #doc th, #doc td { border: 1px solid #8884; padding: 3px 6px; }
  #doc code { background: #8881; padding: 0 3px; }
  .item { cursor: pointer; padding: 2px 4px; white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis; }
  .item:hover, .item.active { background: #8884; }
  .group { font-weight: 600; opacity: .7; margin-top: 8px; text-transform: uppercase; font-size: 11px; }
  #toc div { cursor: pointer; padding: 1px 0; opacity: .85; }
  #toc div:hover { opacity: 1; text-decoration: underline; }
  .gap { color: #c80; }
  .gap.exempt { opacity: .55; text-decoration: line-through; }
  .gap.deferred { color: #6ab; }
  .bar { height: 6px; background: #8883; margin: 4px 0; }
  .bar > div { height: 100%; background: #4a4; }
  #map { overflow: auto; }
  #map text { font: 10px sans-serif; fill: currentColor; }
  #map line { stroke: #8886; }
  .legend { font-size: 11px; opacity: .8; margin: 6px 0; }
  button { font: inherit; margin-right: 4px; }
</style></head>
<body>
  <div id="sidebar"><div id="health"></div><div id="list"></div></div>
  <div id="main">
    <div><button id="showMap">Map</button><span id="crumb"></span></div>
    <div id="map"></div>
    <div id="doc"></div>
  </div>
  <div id="right"><div id="toc"></div><hr><div id="trace"></div></div>
<script>
(async () => {
  const KINDS = [["sr","Requirements"],["spec","Specs"],["plan","Plans"],["task","Tasks"],["br","Business"]];
  const STATE_MARK = { passed: "\\u25c9", failed: "\\u25cf", error: "\\u2715", never_validated: "\\u25cb" };
  const el = (id) => document.getElementById(id);
  const text = (node, s) => { node.appendChild(document.createTextNode(s)); return node; };

  let graph = null;
  let active = null;

  const res = await fetch('/api/graph');
  if (!res.ok) {
    text(el('health'), 'trace unavailable: ' + ((await res.json()).error || res.status));
  } else {
    graph = await res.json();
  }

  function badge(id) {
    if (!graph || !graph.validation) return '';
    const v = graph.validation[id];
    if (!v) return ' \\u25cb';
    return ' ' + (STATE_MARK[v.state] || '') + (v.stale ? ' \\u26a0' : '');
  }

  function renderHealth() {
    const box = el('health'); box.innerHTML = '';
    if (!graph) return;
    const h = graph.health;
    text(document.createElement('div'), '');
    const title = text(document.createElement('div'), 'Traceability ' + h.percent + '%');
    title.style.fontWeight = '600';
    box.appendChild(title);
    const bar = document.createElement('div'); bar.className = 'bar';
    const fill = document.createElement('div'); fill.style.width = h.percent + '%';
    bar.appendChild(fill); box.appendChild(bar);
    for (const c of h.classes) {
      box.appendChild(text(document.createElement('div'),
        c.name + '  ' + c.satisfied + '/' + c.expected + (c.exempt ? '  (' + c.exempt + ' exempt)' : '')));
    }
    box.appendChild(text(document.createElement('div'),
      'dangling ' + h.dangling + '   deferred ' + h.deferred));
    box.appendChild(text(document.createElement('div'), '\\u25c9 pass  \\u25cf fail  \\u2715 error  \\u25cb never validated  \\u26a0 stale'))
      .className = 'legend';
  }

  function renderList() {
    const box = el('list'); box.innerHTML = '';
    if (!graph) return;
    for (const [kind, label] of KINDS) {
      const nodes = graph.nodes.filter((n) => n.kind === kind);
      if (nodes.length === 0) continue;
      box.appendChild(text(document.createElement('div'), label + ' (' + nodes.length + ')')).className = 'group';
      for (const n of nodes) {
        const row = text(document.createElement('div'), n.title + (n.kind === 'sr' ? badge(n.id) : ''));
        row.className = 'item' + (active === n.id ? ' active' : '');
        row.title = n.path;
        row.onclick = () => openDoc(n.id);
        box.appendChild(row);
      }
    }
  }

  function renderTrace(nodeId) {
    const box = el('trace'); box.innerHTML = '';
    if (!graph) return;
    box.appendChild(text(document.createElement('div'), 'TRACEABILITY')).className = 'group';
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    const outgoing = graph.edges.filter((e) => e.src === nodeId);
    const incoming = graph.edges.filter((e) => e.dst === nodeId);
    for (const e of outgoing) {
      const target = byId.get(e.dst);
      const row = text(document.createElement('div'), e.kind + ' \\u2192 ' + (target ? target.title : e.dst + '  (missing)'));
      if (target) { row.className = 'item'; row.onclick = () => openDoc(e.dst); }
      box.appendChild(row);
    }
    for (const e of incoming) {
      const source = byId.get(e.src);
      const row = text(document.createElement('div'), e.kind + ' \\u2190 ' + (source ? source.title : e.src));
      if (source) { row.className = 'item'; row.onclick = () => openDoc(e.src); }
      box.appendChild(row);
    }
    const v = graph.validation[nodeId];
    if (v) {
      box.appendChild(text(document.createElement('div'), 'VALIDATION')).className = 'group';
      box.appendChild(text(document.createElement('div'), 'state ' + v.state + (v.stale ? '  \\u26a0 STALE' : '')));
      if (v.metric) box.appendChild(text(document.createElement('div'), v.metric + ' = ' + v.value + '  assert ' + v.assert_expr));
      if (v.trials !== null) box.appendChild(text(document.createElement('div'), 'trials ' + v.trials + '/' + v.declared_trials));
      if (v.error) box.appendChild(text(document.createElement('div'), 'error: ' + v.error));
      for (const a of (v.artifacts || [])) box.appendChild(text(document.createElement('div'), 'artifact ' + a));
    }
    const gaps = graph.gaps.filter((g) => g.node_id === nodeId);
    if (gaps.length) {
      box.appendChild(text(document.createElement('div'), 'GAPS')).className = 'group';
      for (const g of gaps) {
        box.appendChild(text(document.createElement('div'), g.kind + ' \\u2014 ' + g.detail)).className = 'gap ' + g.disposition;
      }
    }
  }

  // Layout arithmetic lives in graph-layout.ts and arrives via /api/layout, so
  // this page only draws. Passing a root scopes it to that node's neighbourhood,
  // which is what keeps the in-document mini-map legible.
  const SVG_NS = 'http://www.w3.org/2000/svg';

  async function drawGraph(box, root, hops) {
    box.innerHTML = '';
    const query = root ? '?root=' + encodeURIComponent(root) + '&hops=' + hops : '';
    const r = await fetch('/api/layout' + query);
    if (!r.ok) { text(box, 'layout unavailable'); return; }
    const layout = await r.json();
    if (layout.nodes.length === 0) { text(box, 'nothing to draw'); return; }
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('width', String(layout.width));
    svg.setAttribute('height', String(layout.height));
    for (const e of layout.edges) {
      const line = document.createElementNS(SVG_NS, 'line');
      line.setAttribute('x1', e.x1); line.setAttribute('y1', e.y1);
      line.setAttribute('x2', e.x2); line.setAttribute('y2', e.y2);
      svg.appendChild(line);
    }
    for (const n of layout.nodes) {
      const t = document.createElementNS(SVG_NS, 'text');
      t.setAttribute('x', n.x); t.setAttribute('y', n.y);
      t.style.cursor = 'pointer';
      t.appendChild(document.createTextNode(n.id + (n.kind === 'sr' ? badge(n.id) : '')));
      t.onclick = () => openDoc(n.id);
      svg.appendChild(t);
    }
    box.appendChild(svg);
  }

  async function renderMap() {
    el('doc').innerHTML = ''; el('toc').innerHTML = ''; el('crumb').textContent = '';
    active = null;
    await drawGraph(el('map'), null, 1);
  }

  async function openDoc(nodeId) {
    if (!graph) return;
    const node = graph.nodes.find((n) => n.id === nodeId);
    if (!node) return;
    active = nodeId;
    el('map').innerHTML = '';
    const r = await fetch('/api/doc?path=' + encodeURIComponent(node.path));
    const doc = el('doc');
    if (!r.ok) { doc.innerHTML = ''; text(doc, 'could not open ' + node.path); return; }
    const data = await r.json();
    doc.innerHTML = data.html;
    el('crumb').textContent = '  ' + node.path +
      (data.progress ? '   [' + data.progress.done + '/' + data.progress.total + ' steps]' : '');
    const toc = el('toc'); toc.innerHTML = '';
    toc.appendChild(text(document.createElement('div'), 'CONTENTS')).className = 'group';
    for (const entry of data.toc) {
      const row = text(document.createElement('div'), '  '.repeat(entry.level - 1) + entry.text);
      row.onclick = () => { const h = document.getElementById(entry.slug); if (h) h.scrollIntoView(); };
      toc.appendChild(row);
    }
    renderTrace(nodeId);
    renderList();
    // The 1-hop mini-map: same layout component, smaller scope.
    const mini = document.createElement('div');
    el('trace').appendChild(mini);
    await drawGraph(mini, nodeId, 1);
  }

  el('showMap').onclick = renderMap;
  renderHealth();
  renderList();
  renderMap();
})();
</script>
</body></html>`;
}
```

- [ ] **Step 4: Run both suites to verify they pass**

Run: `npm test --prefix pi-ext/factory-watch -- docs-html docs-server`
Expected: PASS — 6 passed in docs-html, 14 passed in docs-server

- [ ] **Step 5: Typecheck**

Run: `npm run typecheck --prefix pi-ext/factory-watch`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/docs-html.ts pi-ext/factory-watch/test/docs-html.test.ts
git commit -m "feat(factory-watch): inline zero-dependency docs page

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Wire the surfaces into `/review-plans`

**Files:**
- Modify: `pi-ext/factory-watch/src/review-surface.ts:7-28` (add an optional key)
- Modify: `pi-ext/factory-watch/src/index.ts:492-533` (the `review-plans` handler)
- Modify: `pi-ext/factory-watch/src/doc-lister.ts:32-58` (list `requirements/SR-*.md`)
- Test: `pi-ext/factory-watch/test/review-surface.test.ts` (extend)
- Test: `pi-ext/factory-watch/test/doc-lister.test.ts` (extend)

**Interfaces:**
- Consumes: `ensureDocsServer`, `stopDocsServer` (Task 4), `openInBrowser` (existing).
- Produces: `parseReviewPlansArgs(args: string): { surface: "browser" | "terminal" | null; stop: boolean }`
  exported from `index.ts`'s sibling module `review-surface.ts`.

- [ ] **Step 1: Write the failing tests**

Append to `pi-ext/factory-watch/test/review-surface.test.ts`:

```ts
import { parseReviewPlansArgs, readSurfacePref, writeSurfacePref } from "../src/review-surface.js";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("parseReviewPlansArgs", () => {
  test("defaults to prompting", () => {
    expect(parseReviewPlansArgs("")).toEqual({ surface: null, stop: false });
  });

  test("recognises --browser, --terminal and --stop", () => {
    expect(parseReviewPlansArgs("--browser").surface).toBe("browser");
    expect(parseReviewPlansArgs("--terminal").surface).toBe("terminal");
    expect(parseReviewPlansArgs("--stop").stop).toBe(true);
  });
});

describe("surface preference keys", () => {
  test("docs and review preferences are independent", () => {
    const root = mkdtempSync(join(tmpdir(), "surface-"));
    writeSurfacePref(root, "browser", "docs");
    expect(readSurfacePref(root, "docs")).toBe("browser");
    // choosing browser for docs must not redirect where code review opens
    expect(readSurfacePref(root)).toBe("terminal");
  });

  test("the default key keeps its existing behaviour", () => {
    const root = mkdtempSync(join(tmpdir(), "surface-"));
    writeSurfacePref(root, "browser");
    expect(readSurfacePref(root)).toBe("browser");
  });
});
```

Append to `pi-ext/factory-watch/test/doc-lister.test.ts`:

```ts
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("listDocs requirements", () => {
  test("lists SR files alongside specs, plans and tasks", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-sr-"));
    mkdirSync(join(root, "requirements"), { recursive: true });
    writeFileSync(
      join(root, "requirements", "SR-001.md"),
      "---\nid: SR-001\ntitle: Preempt patrol\nstatement: s\ndomain: d\n---\n",
    );
    const labels = listDocs(root).map((d) => d.label);
    expect(labels).toContain("[req] SR-001 -- Preempt patrol");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test --prefix pi-ext/factory-watch -- review-surface doc-lister`
Expected: FAIL — `parseReviewPlansArgs` is not exported; `[req] SR-001` is not listed

- [ ] **Step 3: Extend `review-surface.ts`**

Replace lines 7-28 of `pi-ext/factory-watch/src/review-surface.ts` with:

```ts
export type SurfaceKey = "review" | "docs";

export function surfacePrefPath(cwd: string): string {
  return join(cwd, "sessions", ".factory-review-surface.json");
}

export function readSurfacePref(cwd: string, key: SurfaceKey = "review"): Surface {
  try {
    const raw = JSON.parse(readFileSync(surfacePrefPath(cwd), "utf-8")) as Record<string, string>;
    // "surface" is the pre-existing key for code review; keep honouring it so
    // an existing preference file is not silently discarded.
    const value = key === "review" ? (raw["surface"] ?? raw["review"]) : raw[key];
    return value === "browser" ? "browser" : "terminal";
  } catch {
    return "terminal";
  }
}

export function writeSurfacePref(cwd: string, pref: Surface, key: SurfaceKey = "review"): void {
  try {
    const path = surfacePrefPath(cwd);
    mkdirSync(dirname(path), { recursive: true });
    let existing: Record<string, string> = {};
    try {
      existing = JSON.parse(readFileSync(path, "utf-8")) as Record<string, string>;
    } catch {
      existing = {};
    }
    existing[key === "review" ? "surface" : key] = pref;
    writeFileSync(path, JSON.stringify(existing), "utf-8");
  } catch {
    // best-effort; a failed write just means we don't remember the choice
  }
}

export function parseReviewPlansArgs(args: string): {
  surface: Surface | null;
  stop: boolean;
} {
  const stop = /(^|\s)--stop(\s|$)/.test(args);
  if (/(^|\s)--browser(\s|$)/.test(args)) return { surface: "browser", stop };
  if (/(^|\s)--terminal(\s|$)/.test(args)) return { surface: "terminal", stop };
  return { surface: null, stop };
}
```

- [ ] **Step 4: Extend `doc-lister.ts`**

In `pi-ext/factory-watch/src/doc-lister.ts`, change the `DocEntry` type on line 6 to:

```ts
  type: "spec" | "plan" | "task" | "req";
```

Then insert this block inside `listDocs`, immediately before the `return entries.sort(...)` line:

```ts
  const reqsDir = join(repoRoot, "requirements");
  for (const file of listMarkdownFiles(reqsDir).filter((f) => f.startsWith("SR-"))) {
    const path = join(reqsDir, file);
    entries.push({
      type: "req",
      label: buildReqLabel(path, file),
      path,
      mtimeMs: statSync(path).mtimeMs,
    });
  }
```

And add this helper beside `buildTaskLabel`:

```ts
function buildReqLabel(path: string, file: string): string {
  try {
    const parsed = parseTaskFrontmatter(readFileSync(path, "utf-8"));
    if (parsed) {
      return `[req] ${parsed.id} -- ${parsed.title}`;
    }
  } catch {
    // fall through to filename fallback
  }
  return `[req] ${file}`;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test --prefix pi-ext/factory-watch -- review-surface doc-lister`
Expected: PASS

Note: `parseTaskFrontmatter` requires `id` and `title`, which SR files always carry;
an SR missing them degrades to `[req] <filename>`, exactly as tasks do.

- [ ] **Step 6: Rewrite the `review-plans` handler**

In `pi-ext/factory-watch/src/index.ts`, add to the imports:

```ts
import { ensureDocsServer, stopDocsServer } from "./docs-server.js";
import { parseReviewPlansArgs } from "./review-surface.js";
```

Then replace the handler body at `index.ts:492-533` — keep the whole existing
terminal path verbatim, and wrap it:

```ts
  pi.registerCommand("review-plans", {
    description: "Browse specs, plans, requirements and tasks (--browser | --terminal | --stop)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const parsed = parseReviewPlansArgs(args);

      if (parsed.stop) {
        ctx.ui.notify(stopDocsServer() ? "docs server stopped" : "no docs server running", "info");
        return;
      }

      let surface = parsed.surface;
      if (surface === null) {
        const remembered = readSurfacePref(ctx.cwd, "docs");
        const pick = await ctx.ui.select(
          "Open docs in",
          remembered === "browser" ? ["Browser", "Terminal"] : ["Terminal", "Browser"],
        );
        if (pick === undefined) return;
        surface = pick === "Browser" ? "browser" : "terminal";
        writeSurfacePref(ctx.cwd, surface, "docs");
      }

      if (surface === "browser") {
        try {
          // Non-blocking by design: open the tab and return, so the session stays
          // usable while the docs stay open beside it. Spec section 4.
          const server = await ensureDocsServer(ctx.cwd);
          ctx.ui.notify(`docs open at ${server.url} (/review-plans --stop to close)`, "info");
          openInBrowser(server.url);
          return;
        } catch (err) {
          ctx.ui.notify(`browser docs failed (${String(err)}); falling back to terminal`, "warning");
        }
      }

      const docs = listDocs(ctx.cwd);
      if (docs.length === 0) {
        ctx.ui.notify("no specs, plans, requirements, or tasks found", "info");
        return;
      }

      const selectedLabel = await ctx.ui.select(
        "Review which document?",
        docs.map((d) => d.label),
      );
      if (selectedLabel === undefined) {
        return;
      }
      const doc = docs.find((d) => d.label === selectedLabel);
      if (doc === undefined) {
        ctx.ui.notify("review-plans: selected document not found", "error");
        return;
      }

      let raw: string;
      try {
        raw = readFileSync(doc.path, "utf-8");
      } catch (err) {
        ctx.ui.notify(`review-plans: failed to read ${doc.path}: ${String(err)}`, "error");
        return;
      }

      let displayText = raw;
      if (doc.type === "task" || doc.type === "req") {
        const parsedDoc = parseTaskFrontmatter(raw);
        displayText = parsedDoc ? `${formatTaskHeader(parsedDoc)}\n\n${parsedDoc.body}` : raw;
      }

      const markdownTheme = getMarkdownTheme();
      await ctx.ui.custom<void>((tui, _theme, _keybindings, done) => {
        return new ScrollableMarkdown(displayText, markdownTheme, tui, () => done(undefined));
      }, { overlay: true, overlayOptions: { width: "90%", maxHeight: "90%", anchor: "center" } });
    },
  });
```

- [ ] **Step 7: Verify the whole suite and typecheck**

Run: `npm test --prefix pi-ext/factory-watch`
Expected: PASS — the full suite, no regressions in `handler.test.ts` or `smoke.test.ts`

Run: `npm run typecheck --prefix pi-ext/factory-watch`
Expected: no errors

- [ ] **Step 8: Manual verification — required, not inferable from unit tests**

Start pi with the extension, then confirm each of these by hand:

1. `/review-plans --browser` opens a tab **and the prompt returns immediately** —
   type another command while the tab is open and confirm the session responds.
2. The sidebar lists requirements, specs, plans and tasks; clicking a plan renders
   headings, code blocks, tables and checkboxes, with a working TOC and a
   `[done/total steps]` count in the breadcrumb.
3. Open `docs/superpowers/plans/2026-07-20-factory-plan-and-run.md` (102 KB) and
   confirm it renders and scrolls without stalling.
4. Click **Map**, confirm nodes are laid out in columns by kind and clicking one
   opens that document.
5. With a task open, confirm the trace panel shows a small 1-hop mini-map beneath
   the gaps, and that it contains strictly fewer nodes than the full map.
5. Edit a task's `status:` in another editor, refresh the tab, and confirm the
   change appears — proving reads are uncached.
6. `/review-plans --stop` closes it; loading the URL again fails.
7. `/review-plans --terminal` still opens the original TUI overlay unchanged.

- [ ] **Step 9: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/src/review-surface.ts pi-ext/factory-watch/src/doc-lister.ts pi-ext/factory-watch/test/review-surface.test.ts pi-ext/factory-watch/test/doc-lister.test.ts
git commit -m "feat(factory-watch): browser surface for /review-plans

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## What this plan deliberately does not build

- **`factory trace` itself** — plan `2026-08-03-trace-model-and-cli.md`. This
  extension holds no traceability rules; it renders what the CLI reports.
- **The `/trace-fix` loop** — plan `2026-08-03-trace-fix-workflow.md`.
- **Write access from the browser.** The viewer is strictly read-only (spec §1.2);
  every disposition is written by the CLI, never by a POST from this page.
