# /review-plans Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/review-plans` to `pi-ext/factory-watch/` — a flat picker over every spec, plan, and task file, opening a scrollable, real-markdown-rendered viewer built on `pi-tui`'s own `Markdown` component.

**Architecture:** Same shape as the rest of this extension: pure, unit-tested functions/classes for parsing and scroll math, thin command wiring for the actual file I/O and `ctx.ui.custom()` call.

**Tech Stack:** TypeScript, vitest, `@earendil-works/pi-tui` (new explicit devDependency, pinned to the version already resolved transitively via `@earendil-works/pi-coding-agent` — no new *behavior*, just making an already-present package explicit rather than relying on hoisting).

## Global Constraints

- Every task ends green (`npm --prefix pi-ext/factory-watch run typecheck`, `npm --prefix pi-ext/factory-watch test`) and is committed.
- TypeScript strict mode, NodeNext (existing `tsconfig.json`, unchanged).
- No new runtime dependencies beyond `@earendil-works/pi-tui` (already physically present in `node_modules`, made explicit).

Full design: `docs/superpowers/specs/2026-07-21-review-plans-command-design.md`.

---

## File Structure

```
pi-ext/factory-watch/
  package.json                    # modified: + @earendil-works/pi-tui devDependency
  src/
    task-header.ts                 # new: parseTaskFrontmatter, formatTaskHeader
    doc-lister.ts                   # new: listDocs
    scrollable-markdown.ts            # new: ScrollableMarkdown component
    pi-types.ts                        # modified: + UiApi.custom, TUI/Component/OverlayOptions/Theme imports
    index.ts                             # modified: + /review-plans command
  test/
    task-header.test.ts
    doc-lister.test.ts
    scrollable-markdown.test.ts
    handler.test.ts                # modified: + /review-plans tests
  README.md                        # modified: document /review-plans
```

---

### Task 1: `task-header.ts` — pure frontmatter parsing

**Files:**
- Create: `pi-ext/factory-watch/src/task-header.ts`
- Test: `pi-ext/factory-watch/test/task-header.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `ParsedTask { id, title, status, dod, body }`; `parseTaskFrontmatter(content: string): ParsedTask | null`; `formatTaskHeader(parsed: ParsedTask): string`.

- [ ] **Step 1: Write the failing test**

```typescript
// test/task-header.test.ts
import { describe, expect, test } from "vitest";
import { formatTaskHeader, parseTaskFrontmatter } from "../src/task-header.js";

const TASK_MD = `---
id: T-001
title: "Example: FlightController.goto reaches waypoint"
status: todo
dod:
  - "goto(x,y,z) moves pose to within 0.5m of target in the fake"
  - "unit test covers success and battery decrement"
---

Implement \`goto\` waypoint behavior on the fake and pybullet controllers.
`;

const TASK_SCALAR_DOD_MD = `---
id: T-002
title: Single-line task
status: done
dod: a single scalar criterion
---
body here
`;

const NOT_A_TASK_MD = "# Just a doc\n\nNo frontmatter here.\n";

describe("parseTaskFrontmatter", () => {
  test("parses a task with a list dod", () => {
    const parsed = parseTaskFrontmatter(TASK_MD);
    expect(parsed).toEqual({
      id: "T-001",
      title: "Example: FlightController.goto reaches waypoint",
      status: "todo",
      dod: [
        "goto(x,y,z) moves pose to within 0.5m of target in the fake",
        "unit test covers success and battery decrement",
      ],
      body: "Implement `goto` waypoint behavior on the fake and pybullet controllers.",
    });
  });

  test("parses a task with a scalar dod", () => {
    const parsed = parseTaskFrontmatter(TASK_SCALAR_DOD_MD);
    expect(parsed).toEqual({
      id: "T-002",
      title: "Single-line task",
      status: "done",
      dod: ["a single scalar criterion"],
      body: "body here",
    });
  });

  test("returns null when there's no frontmatter block", () => {
    expect(parseTaskFrontmatter(NOT_A_TASK_MD)).toBeNull();
  });

  test("returns null when a required field is missing", () => {
    const missingTitle = "---\nid: T-003\nstatus: todo\ndod: x\n---\nbody\n";
    expect(parseTaskFrontmatter(missingTitle)).toBeNull();
  });
});

describe("formatTaskHeader", () => {
  test("formats id, title, status, and dod as a clean header", () => {
    const parsed = parseTaskFrontmatter(TASK_MD)!;
    expect(formatTaskHeader(parsed)).toBe(
      "Task T-001 -- Example: FlightController.goto reaches waypoint\n" +
        "Status: todo\n" +
        "DoD:\n" +
        "- goto(x,y,z) moves pose to within 0.5m of target in the fake\n" +
        "- unit test covers success and battery decrement",
    );
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL -- `../src/task-header.js` not found.

- [ ] **Step 3: Implement `src/task-header.ts`**

```typescript
export interface ParsedTask {
  id: string;
  title: string;
  status: string;
  dod: string[];
  body: string;
}

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;

function unquote(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

export function parseTaskFrontmatter(content: string): ParsedTask | null {
  const match = content.match(FRONTMATTER_RE);
  if (!match) {
    return null;
  }
  const frontmatter = match[1] ?? "";
  const body = (match[2] ?? "").trim();

  let id: string | undefined;
  let title: string | undefined;
  let status: string | undefined;
  const dod: string[] = [];
  let inDodList = false;

  for (const line of frontmatter.split(/\r?\n/)) {
    const listItem = line.match(/^\s+-\s+(.*)$/);
    if (inDodList && listItem) {
      dod.push(unquote(listItem[1] ?? ""));
      continue;
    }
    inDodList = false;

    const kv = line.match(/^(\w+):\s*(.*)$/);
    if (!kv) {
      continue;
    }
    const key = kv[1];
    const rawValue = kv[2] ?? "";
    if (key === "id") {
      id = unquote(rawValue);
    } else if (key === "title") {
      title = unquote(rawValue);
    } else if (key === "status") {
      status = unquote(rawValue);
    } else if (key === "dod") {
      if (rawValue.trim() === "") {
        inDodList = true;
      } else {
        dod.push(unquote(rawValue));
      }
    }
  }

  if (!id || !title || !status || dod.length === 0) {
    return null;
  }
  return { id, title, status, dod, body };
}

export function formatTaskHeader(parsed: ParsedTask): string {
  const dodLines = parsed.dod.map((d) => `- ${d}`).join("\n");
  return `Task ${parsed.id} -- ${parsed.title}\nStatus: ${parsed.status}\nDoD:\n${dodLines}`;
}
```

- [ ] **Step 4: Run to pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: all pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/task-header.ts pi-ext/factory-watch/test/task-header.test.ts
git commit -m "feat: pure task frontmatter parsing for the doc viewer"
```

---

### Task 2: `doc-lister.ts` — pure file listing

**Files:**
- Create: `pi-ext/factory-watch/src/doc-lister.ts`
- Test: `pi-ext/factory-watch/test/doc-lister.test.ts`

**Interfaces:**
- Consumes: `parseTaskFrontmatter` (Task 1).
- Produces: `DocEntry { type, label, path, mtimeMs }`; `listDocs(repoRoot: string): DocEntry[]`.

- [ ] **Step 1: Write the failing test**

```typescript
// test/doc-lister.test.ts
import { mkdirSync, mkdtempSync, writeFileSync, utimesSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { listDocs } from "../src/doc-lister.js";

function makeRepo(root: string): void {
  mkdirSync(join(root, "docs", "superpowers", "specs"), { recursive: true });
  mkdirSync(join(root, "docs", "superpowers", "plans"), { recursive: true });
  mkdirSync(join(root, "tasks"), { recursive: true });

  writeFileSync(join(root, "docs", "superpowers", "specs", "2026-01-01-a-design.md"), "# A spec\n");
  writeFileSync(join(root, "docs", "superpowers", "plans", "2026-01-02-a.md"), "# A plan\n");
  writeFileSync(
    join(root, "tasks", "T-001-a.md"),
    "---\nid: T-001\ntitle: A task\nstatus: todo\ndod:\n  - x\n---\nbody\n",
  );
  writeFileSync(join(root, "tasks", "T-002-b.md"), "not even frontmatter\n");

  // Make mtimes deterministic and distinguishable: spec oldest, task-001 middle, plan newest.
  const old = new Date("2026-01-01T00:00:00Z");
  const mid = new Date("2026-01-02T00:00:00Z");
  const newest = new Date("2026-01-03T00:00:00Z");
  utimesSync(join(root, "docs", "superpowers", "specs", "2026-01-01-a-design.md"), old, old);
  utimesSync(join(root, "tasks", "T-001-a.md"), mid, mid);
  utimesSync(join(root, "tasks", "T-002-b.md"), mid, mid);
  utimesSync(join(root, "docs", "superpowers", "plans", "2026-01-02-a.md"), newest, newest);
}

describe("listDocs", () => {
  test("lists specs, plans, and tasks, newest first", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-test-"));
    makeRepo(root);

    const docs = listDocs(root);

    expect(docs.map((d) => d.type)).toEqual(["plan", "task", "task", "spec"]);
    expect(docs[0]!.label).toBe("[plan] 2026-01-02-a.md");
  });

  test("formats a task label with id/title/status when frontmatter parses", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-test-"));
    makeRepo(root);

    const docs = listDocs(root);
    const task001 = docs.find((d) => d.path.endsWith("T-001-a.md"));
    expect(task001!.label).toBe("[task] T-001 -- A task (todo)");
  });

  test("falls back to the filename when a task's frontmatter doesn't parse", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-test-"));
    makeRepo(root);

    const docs = listDocs(root);
    const task002 = docs.find((d) => d.path.endsWith("T-002-b.md"));
    expect(task002!.label).toBe("[task] T-002-b.md");
  });

  test("returns an empty list when none of the three directories exist", () => {
    const root = mkdtempSync(join(tmpdir(), "doc-lister-empty-"));
    expect(listDocs(root)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL -- `../src/doc-lister.js` not found.

- [ ] **Step 3: Implement `src/doc-lister.ts`**

```typescript
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { parseTaskFrontmatter } from "./task-header.js";

export interface DocEntry {
  type: "spec" | "plan" | "task";
  label: string;
  path: string;
  mtimeMs: number;
}

function listMarkdownFiles(dir: string): string[] {
  try {
    return readdirSync(dir).filter((f) => f.endsWith(".md"));
  } catch {
    return [];
  }
}

function buildTaskLabel(path: string, file: string): string {
  try {
    const parsed = parseTaskFrontmatter(readFileSync(path, "utf-8"));
    if (parsed) {
      return `[task] ${parsed.id} -- ${parsed.title} (${parsed.status})`;
    }
  } catch {
    // fall through to filename fallback
  }
  return `[task] ${file}`;
}

export function listDocs(repoRoot: string): DocEntry[] {
  const entries: DocEntry[] = [];

  const specsDir = join(repoRoot, "docs", "superpowers", "specs");
  for (const file of listMarkdownFiles(specsDir)) {
    const path = join(specsDir, file);
    entries.push({ type: "spec", label: `[spec] ${file}`, path, mtimeMs: statSync(path).mtimeMs });
  }

  const plansDir = join(repoRoot, "docs", "superpowers", "plans");
  for (const file of listMarkdownFiles(plansDir)) {
    const path = join(plansDir, file);
    entries.push({ type: "plan", label: `[plan] ${file}`, path, mtimeMs: statSync(path).mtimeMs });
  }

  const tasksDir = join(repoRoot, "tasks");
  for (const file of listMarkdownFiles(tasksDir).filter((f) => f.startsWith("T-"))) {
    const path = join(tasksDir, file);
    entries.push({
      type: "task",
      label: buildTaskLabel(path, file),
      path,
      mtimeMs: statSync(path).mtimeMs,
    });
  }

  return entries.sort((a, b) => b.mtimeMs - a.mtimeMs);
}
```

- [ ] **Step 4: Run to pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: all pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/doc-lister.ts pi-ext/factory-watch/test/doc-lister.test.ts
git commit -m "feat: pure doc lister for specs/plans/tasks, newest first"
```

---

### Task 3: `scrollable-markdown.ts` + real `pi-tui` devDependency

**Files:**
- Modify: `pi-ext/factory-watch/package.json`
- Create: `pi-ext/factory-watch/src/scrollable-markdown.ts`
- Test: `pi-ext/factory-watch/test/scrollable-markdown.test.ts`

**Interfaces:**
- Consumes: `Markdown`, `MarkdownTheme`, `Key`, `matchesKey`, `Component`, `TUI` (all real, from `@earendil-works/pi-tui`).
- Produces: `ScrollableMarkdown implements Component`.

- [ ] **Step 1: Add `@earendil-works/pi-tui` as an explicit devDependency**

In `pi-ext/factory-watch/package.json`, replace:
```json
  "devDependencies": {
    "@earendil-works/pi-coding-agent": "^0.74.2",
    "@types/node": "^18.19.130",
    "typescript": "^5.5.0",
    "vitest": "^2.0.0"
  }
```
with:
```json
  "devDependencies": {
    "@earendil-works/pi-coding-agent": "^0.74.2",
    "@earendil-works/pi-tui": "^0.74.2",
    "@types/node": "^18.19.130",
    "typescript": "^5.5.0",
    "vitest": "^2.0.0"
  }
```
Run `cd pi-ext/factory-watch && npm install` and confirm it resolves without error (it's already present transitively, so this should be instant/no-op beyond updating the lockfile).

- [ ] **Step 2: Write the failing test**

```typescript
// test/scrollable-markdown.test.ts
import { describe, expect, test, vi } from "vitest";
import type { MarkdownTheme } from "@earendil-works/pi-tui";
import { ScrollableMarkdown } from "../src/scrollable-markdown.js";

const IDENTITY_THEME: MarkdownTheme = {
  heading: (t) => t,
  link: (t) => t,
  linkUrl: (t) => t,
  code: (t) => t,
  codeBlock: (t) => t,
  codeBlockBorder: (t) => t,
  quote: (t) => t,
  quoteBorder: (t) => t,
  hr: (t) => t,
  listBullet: (t) => t,
  bold: (t) => t,
  italic: (t) => t,
  strikethrough: (t) => t,
  underline: (t) => t,
};

function fakeTui(rows: number): { terminal: { rows: number } } {
  return { terminal: { rows } };
}

function manyLinesText(n: number): string {
  return Array.from({ length: n }, (_, i) => `line ${i + 1}`).join("\n\n");
}

describe("ScrollableMarkdown", () => {
  test("renders a windowed slice sized to the terminal's row count, plus a footer", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    const lines = view.render(80);
    // 10 rows - 2 reserved for the footer = 8 content lines + 1 footer line = 9
    expect(lines.length).toBe(9);
    expect(lines[0]).toBe("line 1");
    expect(lines[lines.length - 1]).toContain("of 50");
  });

  test("Down arrow scrolls forward, Up arrow scrolls back", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.render(80);
    view.handleInput("\x1b[B"); // Down
    const after = view.render(80);
    expect(after[0]).toBe("line 2");
    view.handleInput("\x1b[A"); // Up
    const back = view.render(80);
    expect(back[0]).toBe("line 1");
  });

  test("cannot scroll above the top", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.render(80);
    view.handleInput("\x1b[A"); // Up, already at top
    const lines = view.render(80);
    expect(lines[0]).toBe("line 1");
  });

  test("End jumps to the bottom, clamped so the last page is full", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.render(80);
    view.handleInput("\x1b[F"); // End
    const lines = view.render(80);
    expect(lines[lines.length - 2]).toBe("line 50");
  });

  test("q closes the view", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.handleInput("q");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("Escape closes the view", () => {
    const onClose = vi.fn();
    const view = new ScrollableMarkdown(manyLinesText(50), IDENTITY_THEME, fakeTui(10) as any, onClose);
    view.handleInput("\x1b");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL -- `../src/scrollable-markdown.js` not found.

- [ ] **Step 4: Implement `src/scrollable-markdown.ts`**

```typescript
import { Key, Markdown, matchesKey } from "@earendil-works/pi-tui";
import type { Component, MarkdownTheme } from "@earendil-works/pi-tui";

/** Minimal structural subset of pi-tui's TUI that this component actually needs. */
export interface TuiLike {
  terminal: { rows: number };
}

export class ScrollableMarkdown implements Component {
  private readonly markdown: Markdown;
  private scrollOffset = 0;
  private cachedWidth: number | undefined;
  private cachedLines: string[] = [];

  constructor(
    text: string,
    theme: MarkdownTheme,
    private readonly tui: TuiLike,
    private readonly onClose: () => void,
  ) {
    this.markdown = new Markdown(text, 1, 0, theme);
  }

  invalidate(): void {
    this.cachedWidth = undefined;
    this.markdown.invalidate();
  }

  handleInput(data: string): void {
    const viewportHeight = this.getViewportHeight();
    if (matchesKey(data, Key.down)) {
      this.scrollOffset += 1;
    } else if (matchesKey(data, Key.up)) {
      this.scrollOffset -= 1;
    } else if (matchesKey(data, Key.pageDown)) {
      this.scrollOffset += viewportHeight;
    } else if (matchesKey(data, Key.pageUp)) {
      this.scrollOffset -= viewportHeight;
    } else if (matchesKey(data, Key.home)) {
      this.scrollOffset = 0;
    } else if (matchesKey(data, Key.end)) {
      this.scrollOffset = Number.MAX_SAFE_INTEGER;
    } else if (matchesKey(data, Key.escape) || data === "q") {
      this.onClose();
    }
  }

  private getViewportHeight(): number {
    return Math.max(1, this.tui.terminal.rows - 2);
  }

  render(width: number): string[] {
    if (this.cachedWidth !== width) {
      this.cachedWidth = width;
      this.cachedLines = this.markdown.render(width);
    }
    const viewportHeight = this.getViewportHeight();
    const maxOffset = Math.max(0, this.cachedLines.length - viewportHeight);
    this.scrollOffset = Math.min(Math.max(0, this.scrollOffset), maxOffset);

    const visible = this.cachedLines.slice(this.scrollOffset, this.scrollOffset + viewportHeight);
    const lastShown = Math.min(this.scrollOffset + viewportHeight, this.cachedLines.length);
    const footer = `-- line ${this.scrollOffset + 1}-${lastShown} of ${this.cachedLines.length} (arrows/PgUp/PgDn/Home/End, q to close) --`;
    return [...visible, footer];
  }
}
```

- [ ] **Step 5: Run to pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: all pass; typecheck clean.

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/package.json pi-ext/factory-watch/package-lock.json pi-ext/factory-watch/src/scrollable-markdown.ts pi-ext/factory-watch/test/scrollable-markdown.test.ts
git commit -m "feat: scrollable markdown viewer component on pi-tui's real renderer"
```

---

### Task 4: `pi-types.ts` — add `UiApi.custom`

**Files:**
- Modify: `pi-ext/factory-watch/src/pi-types.ts`

**Interfaces:**
- Consumes: real `TUI`, `Component`, `OverlayOptions` (from `@earendil-works/pi-tui`), real `Theme` (from `@earendil-works/pi-coding-agent`).
- Produces: `UiApi.custom<T>(...)`.

This task only extends types -- no new tests (the existing `type-compat-check.ts`, run via `npm run typecheck`, is what validates this addition stays assignable-from the real package).

- [ ] **Step 1: Replace the whole file**

```typescript
// Minimal structural subset of Pi's real ExtensionAPI/ExtensionContext that
// this extension actually uses. Pinned against the real
// @earendil-works/pi-coding-agent package's types by type-compat-check.ts
// so drift is caught at typecheck time, not discovered later.
//
// TUI/Component/OverlayOptions (from @earendil-works/pi-tui) and Theme (from
// @earendil-works/pi-coding-agent) are imported directly rather than
// hand-duplicated -- they're exactly the real types ScrollableMarkdown and
// the /review-plans command interoperate with, so redeclaring minimal
// subsets of them would be pure risk with no benefit.

import type { Component, OverlayOptions, TUI } from "@earendil-works/pi-tui";
import type { Theme } from "@earendil-works/pi-coding-agent";

export interface ModelInfo {
  provider: string;
  id: string;
}

export interface ReplacedSessionCtx {
  sendUserMessage(
    content: string,
    options?: { deliverAs?: "steer" | "followUp" },
  ): Promise<void>;
}

export interface UiApi {
  notify(message: string, type?: "info" | "warning" | "error"): void;
  setStatus(key: string, text: string | undefined): void;
  setWidget(key: string, content: string[] | undefined): void;
  select(title: string, options: string[]): Promise<string | undefined>;
  custom<T>(
    factory: (tui: TUI, theme: Theme, done: (result: T) => void) => Component,
    options?: { overlay?: boolean; overlayOptions?: OverlayOptions },
  ): Promise<T>;
}

export interface ExtCommandCtx {
  cwd: string;
  ui: UiApi;
  model: ModelInfo | undefined;
  newSession(options?: {
    withSession?: (ctx: ReplacedSessionCtx) => Promise<void>;
  }): Promise<{ cancelled: boolean }>;
}

export interface CommandDef {
  description?: string;
  handler: (args: string, ctx: ExtCommandCtx) => Promise<void>;
}

export interface PiApi {
  registerCommand(name: string, def: CommandDef): void;
}
```

- [ ] **Step 2: Run to verify it compiles**

Run: `cd pi-ext/factory-watch && npm run typecheck && npm test`
Expected: typecheck clean (this is the step that proves `custom`'s signature stays assignable-from the real `ExtensionUIContext.custom`); existing tests unaffected.

- [ ] **Step 3: Commit**

```bash
git add pi-ext/factory-watch/src/pi-types.ts
git commit -m "feat: add UiApi.custom for the doc viewer overlay"
```

---

### Task 5: `/review-plans` command wiring

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/test/handler.test.ts`

**Interfaces:**
- Consumes: `listDocs` (Task 2), `parseTaskFrontmatter`/`formatTaskHeader` (Task 1), `ScrollableMarkdown` (Task 3), `getMarkdownTheme` (real, from `@earendil-works/pi-coding-agent`), `ctx.ui.custom` (Task 4).
- Produces: `/review-plans` command.

- [ ] **Step 1: Write the failing tests**

Add to the end of the `describe("factory-watch commands", ...)` block in `pi-ext/factory-watch/test/handler.test.ts` (immediately before its closing `});`):

```typescript
  test("/review-plans notifies when no docs are found, without opening a viewer", async () => {
    const { commands } = capture();
    const ctx = fakeCtx({ cwd: "/nonexistent/path/for/this/test/only" });
    await commands.get("review-plans")!.handler("", ctx);
    expect(ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining("no specs, plans, or tasks"), "info");
  });

  test("/review-plans does nothing further when the picker is cancelled", async () => {
    const select = vi.fn().mockResolvedValue(undefined);
    const custom = vi.fn();
    const ui: UiApi = { notify: vi.fn(), setStatus: vi.fn(), setWidget: vi.fn(), select, custom };
    const { commands } = capture();
    // This repo's real cwd has real specs/plans/tasks (Task 2's listDocs will find some),
    // so the picker is genuinely shown here rather than short-circuited by the empty-list path.
    const ctx = fakeCtx({ cwd: process.cwd(), ui });
    await commands.get("review-plans")!.handler("", ctx);
    expect(select).toHaveBeenCalledTimes(1);
    expect(custom).not.toHaveBeenCalled();
  });
```

Update the import line at the top of `handler.test.ts` that imports `UiApi`/`ExtCommandCtx` etc. from `../src/pi-types.js` -- no new names are needed there (`UiApi` is already imported); this step only adds the two test bodies above.

- [ ] **Step 2: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test`
Expected: FAIL -- `commands.get("review-plans")` is `undefined`.

- [ ] **Step 3: Wire `/review-plans` into `src/index.ts`**

Add these imports at the top (alongside the existing ones):
```typescript
import { readFileSync } from "node:fs";
import { getMarkdownTheme } from "@earendil-works/pi-coding-agent";
import { listDocs } from "./doc-lister.js";
import { formatTaskHeader, parseTaskFrontmatter } from "./task-header.js";
import { ScrollableMarkdown } from "./scrollable-markdown.js";
```
(`readFileSync` may already be imported from `node:fs` in this file -- if so, add `readFileSync` to that existing import instead of a new line.)

Add the new command registration at the end of `factoryWatch` (after the `plan` command registered in an earlier plan):

```typescript
  pi.registerCommand("review-plans", {
    description: "Browse and view specs, plans, and tasks in a scrollable, rendered view",
    handler: async (_args: string, ctx: ExtCommandCtx) => {
      const docs = listDocs(ctx.cwd);
      if (docs.length === 0) {
        ctx.ui.notify("no specs, plans, or tasks found", "info");
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
      if (doc.type === "task") {
        const parsed = parseTaskFrontmatter(raw);
        displayText = parsed ? `${formatTaskHeader(parsed)}\n\n${parsed.body}` : raw;
      }

      const markdownTheme = getMarkdownTheme();
      await ctx.ui.custom<void>((tui, _theme, done) => {
        return new ScrollableMarkdown(displayText, markdownTheme, tui, () => done(undefined));
      }, { overlay: true, overlayOptions: { width: "90%", maxHeight: "90%", anchor: "center" } });
    },
  });
```

- [ ] **Step 4: Run to pass**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: all pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat: /review-plans command -- scrollable spec/plan/task viewer"
```

---

### Task 6: Docs, gate, and required manual verification

**Files:**
- Modify: `pi-ext/factory-watch/README.md`

- [ ] **Step 1: Update `pi-ext/factory-watch/README.md`**

Add to the `## Commands` list:

```markdown
- `/review-plans` — lists every file under `docs/superpowers/specs/`,
  `docs/superpowers/plans/`, and `tasks/T-*.md` (newest first, labeled
  `[spec]`/`[plan]`/`[task]`; task labels show `id -- title (status)`),
  and opens the picked one in a scrollable, real-markdown-rendered view
  (`pi-tui`'s own `Markdown` component, not a raw-text dump). Task
  frontmatter is reformatted into a clean header instead of shown as raw
  YAML. Keys: Up/Down/PageUp/PageDown/Home/End to scroll, `q` or Escape
  to close.
```

- [ ] **Step 2: Run the full gate**

Run: `uv run python scripts/gates/all.py; echo "exit=$?"` -> exit=0.
Run: `uv run python scripts/gates/watch_ext.py; echo "exit=$?"` -> exit=0.

- [ ] **Step 3: Commit**

```bash
git add pi-ext/factory-watch/README.md
git commit -m "docs: document /review-plans in factory-watch's README"
```

- [ ] **Step 4: Required manual verification**

Same category as this extension's prior manual-verification steps -- rendering and keyboard interaction can only be confirmed in a real interactive session, not headlessly:

1. From a real interactive `pif` session, type `/review-plans`. Confirm the picker shows every spec/plan/task file, newest first, with the `[type]` prefix and (for tasks) the `id -- title (status)` label.
2. Pick a large plan file (e.g. `docs/superpowers/plans/2026-07-20-factory-plan-and-run.md`, ~97KB). Confirm it renders with real markdown formatting (headings, code blocks) rather than raw text, and that Up/Down/PageUp/PageDown/Home/End all move the visible window correctly, with the footer line's "line X-Y of Z" staying accurate.
3. Pick `tasks/T-001-example.md`. Confirm the header shows `Task T-001 -- <title>`, `Status: todo`, and a `DoD:` bulleted list -- not raw `---` YAML.
4. Press `q`, then Escape (in a separate run), confirming both close the viewer back to the normal session.
5. Record what was actually observed (not what was expected) in this task's commit message or a follow-up note.

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-07-21-review-plans-command-design.md`):
- §3.1 task frontmatter parsing -> Task 1.
- §3.2 doc listing -> Task 2.
- §3.3 `ScrollableMarkdown` -> Task 3.
- §3.4 command wiring -> Tasks 4 (types) and 5 (wiring).
- §4 error handling -> no docs found / picker cancelled (Task 5's tests), malformed frontmatter (Task 1/2's fallback tests), file deleted between listing and opening (Task 5's try/catch), scroll clamping (Task 3's tests).
- §5 testing strategy -> pure functions/scroll math vitest-covered (Tasks 1-3), thin wiring covered for its two safely-testable branches (Task 5), required manual verification explicit (Task 6).

**Placeholder scan:** none. Every step ships exact, complete code and exact commands with expected output.

**Type consistency:** `ParsedTask` (Task 1) fields used unchanged by `doc-lister.ts` (Task 2) and `index.ts` (Task 5). `DocEntry` (Task 2) fields (`type`, `label`, `path`, `mtimeMs`) match exactly what `index.ts`'s handler reads (`docs.map(d => d.label)`, `doc.path`, `doc.type`). `ScrollableMarkdown`'s constructor signature (Task 3) matches its one call site in `index.ts` (Task 5) exactly (`text, theme, tui, onClose`).

**Cross-task dependency note:** Task 5 is the only task that touches `index.ts`, and it's the last functional task -- by the time it runs, `listDocs`, `parseTaskFrontmatter`/`formatTaskHeader`, `ScrollableMarkdown`, and `UiApi.custom` all already exist and are independently tested, so Task 5's own diff is pure wiring with no new logic to unit-test beyond the two branches its tests already cover.
