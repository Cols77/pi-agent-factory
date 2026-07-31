# Design: Dual-Surface Human Review UX (TUI + local web)

**Date:** 2026-07-29
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Problem

The human-review step (`runReviewLoop`/`ReviewOverlay`) is a terminal overlay
whose feedback granularity is the **whole file**: a comment is a single string
keyed by file path (`comments: Record<string, string>`), which flows unchanged
through `review-decision.json` → `human_review.py` → `runner.py` back to the dev
agent. A reviewer cannot point at a specific line, cannot see all the comments
they have made across files without re-navigating, cannot mark files as
reviewed to track progress through a large changeset, and has only basic
scrolling to move through long diffs. There is also only one surface — a TUI —
so anyone who prefers a richer, GitHub-PR-like view has no option.

This is the "human review is still not very user friendly" gap. Open-source
prior art for reviewing coding-agent output points at two UX models worth
adopting: **revdiff** (per-line annotations, annotation-list popup, hunk/search
navigation, structured handoff on quit) and **diffx/diffity** (browser PR-like
view, inline line comments, open/resolved comment tracking, per-file reviewed
marks).

## 2. Goal (settled during brainstorming)

Raise the review UX to a real code-review experience while keeping the existing
deterministic handoff intact:

1. **Per-line comments** anchored to `file:line` (+ diff side), replacing the
   per-file-only comment model, so the dev agent receives line-anchored
   feedback.
2. **Comment overview + counts** — see every annotation across all files in one
   place, with per-file counts and a total.
3. **Per-file reviewed marks** — track progress through a large changeset.
4. **Better diff navigation** — hunk-to-hunk jumps and in-diff search.
5. **Two surfaces, user's choice at review time**: the enhanced in-Pi **TUI**
   and a new **local web** review UI, both producing the *same* decision
   payload. The Python orchestrator cannot tell which surface produced a
   decision.

Non-goals (YAGNI): syntax highlighting in the web UI (plain CSS diff coloring to
start; Shiki is a later nice-to-have), GitHub PR comment sync, AI-authored
pre-comments, narrated tours, and any new runtime dependency for the web server.

## 3. Architecture: one shared model, two surfaces

The central decision is that both surfaces are thin renderers over **one shared
data model + one handoff protocol**. This avoids two divergent review
implementations and means the Python side is unchanged in shape regardless of
surface.

```
                     review-model.ts  (shared types + payload build/parse)
                        /                         \
        review-overlay.ts (TUI)          review-server.ts (local web)
                        \                         /
                     review-decision.json  (identical payload)
                                   |
              human_review.py  →  runner.py  (line-anchored feedback to dev)
```

Both TS surfaces reuse the existing `review-diff.ts` helpers
(`computeReviewFiles`, `computeFileDiffText`, `computeImplementingFiles`,
`computeImplementingFileDiffText`) to compute the file list and per-file diffs,
so there is a single source of truth for *what changed*.

## 4. Shared review model (`review-model.ts`, new)

```ts
export interface Annotation {
  file: string;
  line?: number;                 // 1-based line in the diff's `side`; absent = file-level note
  side?: "old" | "new";          // which side the line refers to; default "new"
  body: string;
  severity?: "must-fix" | "suggestion";  // optional label shown in feedback; does not gate anything
}

export interface ReviewDecisionPayload {
  decision: "approve" | "reject";
  annotations: Annotation[];
  reviewedFiles: string[];       // paths the reviewer marked reviewed (informational)
}
```

`review-protocol.ts`'s `ReviewDecisionPayload` is replaced by this shape and its
`writeReviewDecision` writes it (keeping the existing atomic-rename +
Windows-retry logic untouched). `review-model.ts` exports:

- `buildDecision(decision, annotations, reviewedFiles): ReviewDecisionPayload`
- `annotationsForFile(annotations, file): Annotation[]` (used by both surfaces
  to render counts / group comments)

### 4.1 Backward compatibility on the reader side

`human_review.py` currently reads `payload["comments"]` (a `dict[str,str]`). The
new writers emit `annotations`. The Python reader is updated to:

- prefer `annotations` when present, mapping each to feedback (see §6);
- fall back to the legacy `comments` dict when `annotations` is absent, so any
  in-flight `review-decision.json` written by an older extension still parses.

`reviewedFiles` is read if present and ignored by the orchestrator (informational
only — it never gates anything).

## 5. Enhanced TUI (`review-overlay.ts`)

The overlay keeps its two-mode structure (summary / file) and the review-guide
header (unchanged from the 2026-07-27 focus-guide design). Changes:

### 5.1 Per-line comments
File view gains a **line cursor** (a highlighted current line, moved with
up/down; the existing scroll follows it). Pressing `c` opens the editor for an
annotation on the line under the cursor, capturing `{file, line, side}` derived
from the diff hunk headers. The mapping from a rendered diff row to
`{line, side}` is computed once per file when its diff is built (a parallel array
alongside `diffLinesFor`), so a comment on a `+` row records the new-side line
number, a `-` row the old-side, and a context row the new-side. A file-level
comment is still possible: `C` (shift-c) comments with `line`/`side` absent.

The internal store changes from `Map<string,string>` to `Annotation[]` (helper
methods add/replace/remove by `{file, line, side}` identity).

### 5.2 Comment overview + counts
- `v` opens an **annotation-list popup** (reusing the `ui.custom` overlay
  pattern): each row `file:line  [severity]  body-first-line`, selectable to jump
  to that file+line in file view.
- The summary file list shows a per-file annotation **count badge**
  (`M  foo.py  +40/-2  (2)`), and the footer shows the running total
  (`3 comments`). This replaces the current `[commented]` tag.

### 5.3 Per-file reviewed marks
`space` toggles the selected file reviewed; a `✓` renders in the summary row and
the path is added/removed from `reviewedFiles`. Purely informational; does not
gate approve/reject.

### 5.4 Navigation
In file view: `[` / `]` jump the cursor to the previous/next hunk header; `/`
prompts for a search string and jumps to the next matching row, with `n` / `N`
repeating forward/backward. These operate on the already-computed diff line
array; no new diff computation.

### 5.5 Reject gating (unchanged intent, new shape)
Reject still requires at least one annotation (`annotations.length > 0`) — the
same guard as today, now over the new store.

### 5.6 Keymap summary (footer strings updated)
```
summary: ↑↓ select  Enter open  space reviewed  v comments  a approve  r reject
file:    ↑↓ line  [ ] hunk  / search (n/N)  c comment  C file-comment  e edit  q back
```

## 6. Python handoff (`human_review.py`, `runner.py`)

`HumanReviewDecision.comments: dict[str,str]` is replaced by
`annotations: list[Annotation]` (a small dataclass mirroring §4). `format_review_feedback`
renders line-anchored feedback:

```
human review requested changes:
- src/foo.py:42 [must-fix]: guard the empty list here
- src/foo.py (file): naming is inconsistent across this module
- src/bar.py:88 [suggestion]: consider extracting this branch
```

`runner.py`'s `addressed` accumulator (from the focus-guide design) is updated to
the same anchored form: `your comment (round {h+1}) on {file}:{line}: {text}`.

Reader tolerance: a payload with only legacy `comments` maps each `(file, text)`
to an `Annotation(file=file, body=text)` (no line), so old and new decisions both
produce sensible feedback.

## 7. Local web review server (`review-server.ts`, new)

A **zero-dependency** review surface using only Node built-ins (`node:http`,
`node:fs`) — consistent with this repo's built-ins-only style and avoiding
Windows build friction (no Vite/Express/Shiki). Structure:

- **Server**: binds to `127.0.0.1` on an ephemeral port (0 → OS-assigned; the
  chosen port is reported back to the caller). Routes:
  - `GET /` → the self-contained HTML page (one string; inline `<style>` +
    `<script>`, no external requests, CSP-friendly).
  - `GET /api/review` → JSON `{ taskId, files: FileStat[], diffs: Record<file,
    string>, guide, banner, implementing }`, built from `review-diff.ts` +
    `readReviewGuide` (same inputs the TUI path uses).
  - `POST /api/decision` → body is a `ReviewDecisionPayload`; the server writes
    `review-decision.json` via the shared `writeReviewDecision` and responds
    `{ ok: true }`, then shuts down.
- **Client (in-page JS)**: renders a file tree (with change-type indicators and a
  reviewed checkbox per file), a diff pane per file (unified to start; split is a
  later toggle), inline line comments (a `+` affordance on each diff row opens a
  small comment box → pushes an `Annotation`), a comment sidebar listing all
  annotations with open counts, and approve/reject buttons. Diff coloring is CSS
  (add/remove/context classes) — no syntax highlighter.
- **Diff-row → {line, side} mapping** reuses the same parse logic as the TUI (see
  §5.1); the mapping is computed server-side per file and sent in the
  `/api/review` payload so client and TUI agree on anchoring.
- **Lifecycle**: the server lives only for one review. It resolves a Promise with
  the posted decision (or a rejection if the window is closed without submitting
  — handled by the caller as "no decision yet", identical to the TUI being
  dismissed). No decision is written until the reviewer submits.

Security: bound to loopback only, no auth (local single-user tool, same trust
model as the TUI), no external network calls from the page.

## 8. Surface choice at review time (`index.ts`)

The `case "review"` dispatch currently calls `runReviewLoop` directly. It gains a
one-line `ui.select` prompt — **"Open review in → Terminal / Browser"** — with
the previous choice remembered as the default (persisted in the extension's
existing settings/state; if none exists yet, default to Terminal to preserve
current behavior).

- **Terminal** → the enhanced `runReviewLoop` (§5), unchanged call site plus the
  new options already threaded (`guide`, `implementing`, `banner`).
- **Browser** → start `review-server.ts`, open the URL
  (`spawn` the platform opener: `start`/`cmd` on Windows via the existing
  spawn helpers, matching how other windows are launched), await the decision
  Promise, then `writeReviewDecision`.

Both branches converge on the identical payload writer; nothing downstream
changes.

## 9. Data flow (unchanged handshake)

The `review-decision.json` file handshake (extension writes, Python
`FileHumanReviewGate` polls + consumes + unlinks) is unchanged — only the payload
*shape* is richer. The `review-guide.json` read path (focus-guide design) is
reused verbatim by both surfaces.

## 10. Edge cases

- **Empty changeset** (`files.length === 0`): both surfaces show "no changes"
  and allow approve; reject stays blocked (needs an annotation) — mirrors the
  current empty-list guard in the TUI.
- **Legacy decision payload** (only `comments`): Python reader maps it to
  file-level annotations (§6); no crash.
- **Diff-row anchoring on renamed/binary files**: a row with no resolvable line
  falls back to a file-level annotation (`line` omitted) rather than guessing.
- **Browser closed without submitting**: no `review-decision.json` written; the
  Python gate keeps polling exactly as when the TUI is dismissed. The user can
  re-open review.
- **Port in use / server bind failure**: report an error via `ui.notify` and
  fall back to the Terminal surface for that review.
- **`--auto` mode**: no human-review step, so neither surface is shown
  (unchanged).
- **Already-done route**: both surfaces honor `implementing`/`banner` opts and
  compute diffs from implementing commits (unchanged inputs).

## 11. Testing

- **TS — shared model**: `buildDecision`/`annotationsForFile` round-trip;
  `writeReviewDecision` writes the new shape with the atomic-rename retry intact.
- **TS — diff anchoring**: the diff-row → `{line, side}` mapper yields correct
  new-side/old-side/context line numbers across multi-hunk diffs, and falls back
  to file-level when unresolvable. Shared by TUI and server (test once).
- **TS — TUI**: per-line `c` records `{file, line, side}`; `C` records a
  file-level annotation; the annotation-list popup lists and jumps; count badges
  and the total render; `space` toggles reviewed into `reviewedFiles`; `[`/`]`
  and `/`+`n`/`N` move the cursor as specified; reject still requires ≥1
  annotation.
- **TS — web server**: `/api/review` returns files+diffs+guide;
  `/api/decision` writes a valid `ReviewDecisionPayload` and resolves the
  Promise; server binds to loopback and shuts down after submit; closing without
  submit resolves as "no decision".
- **TS — surface choice**: `index.ts` review dispatch honors the remembered
  choice and routes to the correct surface; a browser bind failure falls back to
  the TUI.
- **Python**: `human_review.py` reads `annotations`, falls back to legacy
  `comments`, and `format_review_feedback` emits `file:line [severity]: body`;
  `runner.py`'s `addressed` accumulates the anchored form.

## 12. Files touched (anticipated)

**Plan A — shared model + enhanced TUI + Python handoff:**
- `pi-ext/factory-watch/src/review-model.ts` (new) — types, `buildDecision`,
  `annotationsForFile`, diff-row anchoring helper.
- `pi-ext/factory-watch/src/review-protocol.ts` — payload shape → shared model.
- `pi-ext/factory-watch/src/review-overlay.ts` — per-line cursor + comments,
  annotation-list popup, counts, reviewed marks, hunk/search navigation.
- `src/factory/orchestrator/human_review.py` — `annotations` decision shape +
  legacy fallback; `format_review_feedback` line-anchored.
- `src/factory/orchestrator/runner.py` — `addressed` anchored form.
- Tests under both test trees.

**Plan B — local web server:**
- `pi-ext/factory-watch/src/review-server.ts` (new) — HTTP server + in-page
  client (self-contained HTML/JS/CSS), reusing `review-model.ts` + `review-diff.ts`.
- `pi-ext/factory-watch/src/index.ts` — surface-choice `ui.select` in the
  `review` dispatch; browser launch + await decision.
- Tests for the server + surface choice.

## 13. Sequencing

Two implementation plans off this one spec:

- **Plan A** ships independently and delivers immediate value: the shared model,
  the enhanced TUI, and the Python line-anchored handoff. After Plan A the
  existing Terminal review is strictly better and the payload is already the new
  shape.
- **Plan B** adds the web surface on top of the shared model with no further
  Python changes.
