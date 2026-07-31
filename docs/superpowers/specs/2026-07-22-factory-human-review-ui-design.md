# Design: Human Code Review UI for the Factory Pipeline

**Date:** 2026-07-22
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Framing

The factory pipeline (`src/factory/orchestrator/runner.py`) today runs `dev -> validation -> review` fully automatically: `run_review` is an LLM-based agent role, and a task's outcome (done vs. escalated back for another dev iteration) is decided without any human in the loop. There is no existing human review step anywhere in this pipeline, and no diff-viewing UI in `pi-ext/factory-watch/` (only `/review-plans`, which views prose docs, not code diffs).

### 1.1 Goals

- Add a human review gate to the pipeline: once automated dev+validation+review pass for a task, pause and let a human look at the actual diff before the task is marked done.
- An "efficient and welcoming" review experience inside the `pif` TUI: a file-list summary (stats per file, like GitHub's "Files changed" tab) that drills into a full-width, syntax/diff-colored view per file — not a raw-text dump.
- The human can approve, reject with feedback, leave file-level comments, or shell out to a real editor to fix something directly, all without leaving the terminal.
- Rejections and comments feed into the *same* `feedback` mechanism the automated review already uses, so the dev agent's next iteration sees human feedback exactly like it sees automated-review feedback today.

### 1.2 Non-Goals

- **Not line-level comment anchoring.** Comments are file-level. True line-anchored comments would need mapping screen position through scrolling back to source lines and hunks — a lot of fragile bookkeeping for a TUI, and not worth it for v1.
- **Not a rewrite of the orchestrator.** It stays Python. The process bridge below (stdio JSON-lines) gets nearly all the benefit of a same-language rewrite for this one feature, without the risk of rewriting ~13 working, tested files.
- **Not general terminal-editor support.** `pi-tui` doesn't expose a way to suspend its own raw-mode/redraw loop so a child process can take over the terminal, and extensions have no access to do this themselves. `e` (edit) only reliably supports GUI/wait-mode editors (`code -w`, etc.) for v1, with an optional tmux-based path (Section 6) that unlocks real terminal editors *if* the user happens to already be running `pif` inside tmux.
- **Not a replacement for `/factory-stop`.** The review UI itself has no "abandon this run" action; that's what the existing `/factory-stop` command is for.

---

## 2. Architecture: process bridge

The review UI (pi-tui, TypeScript, inside the `pif` process) and the orchestrator (Python) are different processes in different languages. The bridge reuses the same "primitive IPC over a well-known channel" spirit as the existing lock/status files, but as a **blocking stdio JSON-lines protocol** rather than file polling (no polling loop needed on either side):

```
runner.py: run_task(...)
    |
    v
capture git rev-parse HEAD as start_commit, before the dev loop
    |
    v
dev -> validation -> automated review  (unchanged)
    |
    v  (only when not --auto)
write ONE line to stdout:
  {"type": "review_pending", "task_id", "start_commit"}
flush stdout
    |
    v
BLOCK on sys.stdin.readline()  <- no polling; a single blocking read
    |
    v
read one JSON line: {"decision": "approve"|"reject", "comments": [{file, text}], ...}
    |
    v
if approve: commit any uncommitted working-tree changes (from `e` edits), mark task done
if reject:  feedback = format comments the same shape run_task already uses for
            automated-review findings ("\n".join(...)); loop back to dev
```

```
pif extension: `/factory` (no flag)
    |
    v
spawn orchestrator NON-detached, stdio: ["pipe", "pipe", "pipe"]
    |
    v
readline() on child.stdout
    |
    v (line has type: "review_pending")
compute file list + stats itself: `git diff --stat start_commit..HEAD`
    |
    v
open review overlay (Section 3), passing {task_id, start_commit, files}
    |
    v
human decides (approve/reject/comment/edit) inside the overlay
    |
    v
write ONE JSON line to child.stdin: {"decision", "comments", ...}
    |
    v
close overlay, keep reading child.stdout for either the next
review_pending line or the child process exiting
```

**Important implementation detail:** today's detached mode redirects both stdout and stderr to `sessions/.factory-run.log`. In the new foreground mode, stdout is reserved *only* for this JSON-lines protocol — the orchestrator's regular logging must go to stderr (or its own log file) instead, so it never interleaves with and corrupts the protocol stream.

The existing status-file mechanism (`.factory-status.json`, used for the live progress widget) is untouched — it's not part of this handshake.

### 2.1 Command flags

`/factory` and `/factory-run` both gain an `--auto` flag, parseable anywhere in the args string (stripped before the remainder is parsed as usual, e.g. a task id). No flag is the new default (foreground, interactive, human-gated, as above). `--auto` reproduces today's exact behavior unchanged: detached spawn, status-file polling only, no gate, fully automated.

---

## 3. Review screens

Approach: summary-first with drill-down (chosen over a persistent VSCode-style split pane, which cramps the diff column in a typical terminal width, and over a plain sequential file-by-file flow, which loses the overview).

### 3.1 Summary screen (root of the overlay)

```
Task T-014: add battery-aware RTB                    3 files, +42/-11

  M  src/drone/rtb.py            +31/-8
  M  src/drone/interfaces.py      +6/-2
  A  tests/unit/test_rtb.py      +5/-1   [commented]

↑↓ select  Enter open  c comment  e edit  a approve  r reject
```

File stats come from `git diff --stat start_commit..HEAD`, computed by the pif extension (it has repo access directly; no need to have the orchestrator compute and pass full diff text over the stdio channel -- only the file list needs to cross that boundary).

`Esc`/`q` at this screen is a no-op: there is nothing to "go back" to, and closing the overlay here would abandon the orchestrator mid-`readline()`. Use `/factory-stop` (existing command) to abort the whole run instead.

### 3.2 File diff view (drill-down)

Full-width, reusing `renderDiff()` from `@earendil-works/pi-coding-agent` (already public, already used by pi's own `edit` tool-call rendering -- dim/gray context lines, red/green +/- lines with intra-line highlighting on changed tokens). Scrolling matches `/review-plans`'s `ScrollableMarkdown` exactly: arrows/PageUp/PageDown/Home/End. `c` and `e` work here too, contextual to the open file. `Esc`/`q` returns to the summary -- safe, since it only closes this sub-view and doesn't affect the blocked orchestrator.

### 3.3 Comments

`c` opens `ctx.ui.editor()` (pi's built-in multi-line editor overlay), prefilled with any existing comment for that file. The summary marks commented files with `[commented]`. Comments are held in the overlay component's own state (`Map<file, string>`) until the review ends.

### 3.4 Approve / reject

Both go through `ctx.ui.confirm()` so a stray keypress can't end the review by accident.

- **Reject** requires at least one comment somewhere (the dev agent needs something to act on) -- refused via `ctx.ui.notify(..., "error")` if attempted with zero comments.
- **Approve**: if `e` (edit) left uncommitted working-tree changes, those are committed (`review: address direct edits during human review`) before the task is marked done, so the pipeline's existing "committed" DoD item still holds.

---

## 4. Comments -> dev feedback

On reject, comments are formatted into the same `feedback: str | None` parameter `runner.py` already threads through `run_task` for automated-review rejections (`feedback = "\n".join(findings) if findings else "review requested changes"`), which already flows into `prompts.py`'s dev prompt construction. No new plumbing -- just a formatting function:

```
human review requested changes:
- src/drone/rtb.py: <comment text>
- tests/unit/test_rtb.py: <comment text>
```

---

## 5. Edit-directly (`e`)

Editor resolution order: `$VISUAL`, then `$EDITOR`, then a platform default (`code -w` if `code` is on PATH, else `notepad` on Windows).

Only GUI/wait-mode editors are supported for v1 (see Non-Goals) -- if the resolved editor is a known terminal editor (`vim`, `nvim`, `nano`, `emacs -nw`, etc.), or if no GUI editor can be resolved at all (no `$VISUAL`/`$EDITOR` set to a GUI editor, no `code` on PATH, not Windows), the action fails with a clear error (e.g. "edit requires a GUI editor -- set $VISUAL, or use tmux, see Section 6") rather than falling back to a terminal editor and corrupting the display.

## 6. Optional: tmux-enhanced editing

If `process.env.TMUX` is set (i.e. `pif` is already running inside a tmux session), `e` can instead use `tmux split-window -h "<editor> <file>; tmux wait-for -S <signal>"` followed by blocking on `tmux wait-for <signal>` -- the editor gets its own separate pane/pty, never touching pi-tui's raw-mode terminal, so any terminal editor works. This is purely additive: absent tmux, behavior falls back to Section 5 unchanged. (Not available in the current dev environment -- tmux isn't installed there -- but the mechanism doesn't depend on that environment specifically.)

---

## 7. Testing

Following this codebase's existing conventions:

- **TS side:** unit tests for the review overlay components (summary navigation, drill-down, comment state, approve/reject confirm flow) using the same fake-`ctx`/fake-`PiApi` pattern as `handler.test.ts`; mock `child_process.spawn` for both the orchestrator subprocess and the edit-shell-out, and a fake readable stream for the stdout JSON-lines reading logic.
- **Python side:** unit tests for the new gate in `runner.py`/`nodes.py` (writing the `review_pending` line, blocking `readline()` for the decision, formatting comments into `feedback`), in the style of the existing `test_runner_e2e.py`/`test_backends.py`.
- **Manual verification:** this is fundamentally a real-terminal feature (TUI overlay, blocking stdio handoff, external editor shell-out); like `/review-plans`'s own manual-verification step, automated tests exercise the logic but not the live experience end-to-end.
