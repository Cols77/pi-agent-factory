# Design: `/review-plans` — a Scrollable Doc Viewer for Specs, Plans, and Tasks

**Date:** 2026-07-21
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Framing

This repo's plan-time artifacts (`docs/superpowers/specs/*.md`, `docs/superpowers/plans/*.md`) and build-time ledger (`tasks/T-*.md`) already exist and grow every time `/plan` (or a manual brainstorming session) runs. Some plans already exceed 90KB. There is currently no way to read one of these documents from inside a `pi`/`pif` session except opening the file in a separate editor — `pi-ext/factory-watch/` has no viewer, only `/factory-tasks`' one-line-per-task summary board.

### 1.1 Goals

- A single command, `/review-plans`, that lists every spec, plan, and task file and lets you open any one of them in a genuinely readable, scrollable, markdown-rendered view inside the `pi` TUI — not a raw-text dump.
- Task files' YAML frontmatter (`id`/`title`/`status`/`dod`) is presented as a clean header, not raw `---...---` YAML.
- Reuses `pi`'s own real markdown renderer (`Markdown` from `@earendil-works/pi-tui`) rather than reimplementing markdown-to-terminal rendering.

### 1.2 Non-Goals

- **Not an editor.** Read-only viewing only; no in-place editing of the doc from the viewer.
- **Not a search/grep tool across all docs.** The picker lists files; it doesn't do full-text search inside them. A later addition if it turns out to matter.
- **Not a replacement for `/factory-tasks`.** `/factory-tasks`'s status-grouped board view is unchanged; `/review-plans` is for reading one document in full, not summarizing the ledger.
- **Not paginated navigation between documents** (e.g. "next doc" while viewing) — closing the viewer and reopening `/review-plans` to pick a different file is an acceptable round-trip for v1.

---

## 2. Architecture

```
/review-plans
    |
    v
list every file under docs/superpowers/specs/, docs/superpowers/plans/, tasks/T-*.md
sort by mtime, newest first
build labels:
  specs/plans -> "[spec] <filename>" / "[plan] <filename>"
  tasks       -> "[task] <id> -- <title> (<status>)"  (frontmatter parsed)
    |
    v
ctx.ui.select("Review which document?", labels)   <- flat picker, all three types together
    |  (cancelled -> no-op)
    v
read the picked file
  if task: parse frontmatter -> clean header string, body = content after frontmatter
  if spec/plan: use file content as-is (no frontmatter)
    |
    v
ctx.ui.custom(...) -> ScrollableMarkdown component
  wraps pi-tui's real Markdown component
  windows the fully-rendered line array to the terminal's current row count
  Up/Down/PageUp/PageDown/Home/End scroll; q/Escape closes
```

---

## 3. Components

### 3.1 `pi-ext/factory-watch/src/task-header.ts` (new, pure)

- `parseTaskFrontmatter(content: string): { id: string; title: string; status: string; dod: string[]; body: string } | null` — parses a task file's YAML frontmatter block (same shape `ledger.py`'s `Task` dataclass already assumes: `id`, `title`, `status`, `dod`). Returns `null` if the frontmatter block is missing or doesn't parse as YAML with those fields present (malformed file) — callers fall back to showing the raw file content rather than crashing.
- `formatTaskHeader(parsed): string` — builds the clean header text: `` `Task ${id} -- ${title}\nStatus: ${status}\nDoD:\n${dod.map(d => `- ${d}`).join("\n")}` ``.

### 3.2 `pi-ext/factory-watch/src/doc-lister.ts` (new, pure)

- `DocEntry { type: "spec" | "plan" | "task"; label: string; path: string; mtimeMs: number }`.
- `listDocs(repoRoot: string): DocEntry[]` — globs `docs/superpowers/specs/*.md`, `docs/superpowers/plans/*.md`, `tasks/T-*.md` under `repoRoot`, stats each for `mtimeMs`, builds `label` per the rules in §2 (task labels reuse `parseTaskFrontmatter`/`formatTaskHeader` from §3.1 for the `id -- title (status)` portion; malformed task files fall back to `"[task] <filename>"`), sorts descending by `mtimeMs`. Returns `[]` if none of the three directories exist or contain matching files (not an error — a fresh checkout with no plans yet is valid).

### 3.3 `pi-ext/factory-watch/src/scrollable-markdown.ts` (new)

`class ScrollableMarkdown implements Component` (the real `pi-tui` `Component` interface: `render(width): string[]`, `handleInput?(data): void`, `invalidate(): void`).

- Constructed with `(text: string, theme: MarkdownTheme, tui: TUI, onClose: () => void)`.
- Internally holds one `Markdown` instance (from `@earendil-works/pi-tui`) constructed from `text`; caches its `render(width)` output keyed by the `width` it was last computed for — recomputes only when `width` actually changes between calls (handles terminal resize correctly, avoids recomputing on every keystroke for an unchanged width).
- `render(width)`: recompute the cached full-line array if `width` changed; compute `viewportHeight = max(1, tui.terminal.rows - 2)` (leaving 2 rows for a "line X of Y" footer this component also renders); clamp `scrollOffset` to `[0, max(0, totalLines - viewportHeight)]`; return the sliced window plus the footer line.
- `handleInput(data)`: use `matchesKey`/`Key` from `@earendil-works/pi-tui` — `Key.up`/`Key.down` scroll by 1, `Key.pageUp`/`Key.pageDown` scroll by `viewportHeight`, `Key.home` jumps to `0`, `Key.end` jumps to the max offset, `Key.escape` or the literal character `"q"` calls `onClose()`. Any other key is ignored (no-op, not an error).

### 3.4 `/review-plans` command (`index.ts`)

```
pi.registerCommand("review-plans", {
  handler: async (_args, ctx) => {
    const docs = listDocs(ctx.cwd);
    if (docs.length === 0) { ctx.ui.notify("no specs, plans, or tasks found", "info"); return; }
    const selected = await ctx.ui.select("Review which document?", docs.map(d => d.label));
    if (selected === undefined) return;
    const doc = docs.find(d => d.label === selected);
    // guard: doc undefined shouldn't happen (label came from this same list), but
    // handle defensively rather than assume -- notify and return if somehow missing
    const raw = readFileSync(doc.path, "utf-8");
    let displayText = raw;
    if (doc.type === "task") {
      const parsed = parseTaskFrontmatter(raw);
      displayText = parsed ? `${formatTaskHeader(parsed)}\n\n${parsed.body}` : raw;
    }
    await ctx.ui.custom((tui, theme) => {
      const component = new ScrollableMarkdown(displayText, theme.markdown, tui, () => handle?.hide());
      // overlay handle wiring per the real ctx.ui.custom contract (options.onHandle)
      return component;
    }, { overlay: true, overlayOptions: { width: "90%", maxHeight: "90%", anchor: "center" } });
  },
});
```

(Exact `onHandle`/close-callback wiring is a plan-level detail — the real `ctx.ui.custom()` signature's `onHandle` option gives access to the `OverlayHandle` needed to call `.hide()` from inside `onClose()`; the pseudocode above shows intent, not final syntax.)

---

## 4. Error Handling

- **No docs found at all:** notify, no viewer opens (§3.4).
- **Picker cancelled:** no-op.
- **Malformed task frontmatter:** `parseTaskFrontmatter` returns `null`; both the picker label (falls back to `[task] <filename>`) and the viewer (falls back to raw file content) degrade gracefully rather than crashing.
- **Terminal resized while viewing:** `ScrollableMarkdown.render(width)` recomputes wrapped lines when `width` changes, and recomputes `viewportHeight` from `tui.terminal.rows` on every call — both dimensions are always read fresh, never cached stale.
- **Scrolling past either end:** offset is clamped in `render()`, not in the key handler, so it can never go out of range regardless of how many times a key repeats.
- **File deleted between listing and opening** (race, e.g. someone deletes a plan file in another terminal): `readFileSync` throws; the command handler should catch and `ctx.ui.notify(...)`. This is the one case not fully spelled out above and is a plan-level detail to nail down (wrap the read in try/catch), not left ambiguous by omission.

---

## 5. Testing Strategy

- **Pure functions** (`parseTaskFrontmatter`, `formatTaskHeader`, `listDocs`'s sorting/labeling logic): full vitest coverage with fixture files under a `tmp` directory, following this extension's existing pattern exactly (e.g. `task-picker.ts`'s tests).
- **`ScrollableMarkdown`'s scroll-window math** (clamping, viewport height computation): testable in isolation by constructing it with a fake minimal `TUI`-shaped object (`{ terminal: { rows: N } }`) and asserting `render(width)` returns the expected slice for a given `scrollOffset` — doesn't require a real terminal.
- **Key handling and actual on-screen appearance**: can only be confirmed in a real interactive session — same category of limitation already documented for `/factory`'s widget rendering. Required manual verification step, not assumed to work from unit tests alone.

---

## 6. Cross-Plan Dependencies

Consumes, unchanged: `pi-tui`'s real `Markdown`/`MarkdownTheme`/`Key`/`matchesKey`/`TUI` exports (already a transitive dependency via `@earendil-works/pi-coding-agent`, no new package needed), and the existing `docs/superpowers/{specs,plans}/` and `tasks/` directory conventions established by every prior plan in this repo.
