# Design: In-Session Mission Control

**Date:** 2026-07-27
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Problem

Today `/factory-run` shows mission control by spawning a **second OS window**: a
standalone Node process running `mission-control-dashboard.ts`'s own `main()`
(its own `ProcessTerminal` + `TUI`), launched through `spawnTerminalWindow`
(`cmd /c start "" node …` on Windows, `open -a Terminal` on macOS, `xterm`
elsewhere) executing a `.ts` file directly.

The dashboard *logic* is a single pi-tui `Component` (`MissionControlDashboard`).
Everything else — the standalone host, the cross-platform console spawning, the
`node <file>.ts` execution — exists only to put that component in a separate
window, and it is the source of a recurring class of bugs: `q` didn't quit, an
over-width diff line crashed the whole session, module-resolution and
`.ts`-execution fragility, and stale/disconnected status.

The user's usage pattern is **watch-until-it-needs-me**: during a run they are
not simultaneously chatting with the pi agent. That removes the only real reason
for a separate window (concurrent watch + chat), so the dashboard can be hosted
**inside the pi session** via `ctx.ui.custom(...)`, deleting all the second-host
machinery and the bugs that come with it.

## 2. Decisions (settled during brainstorming)

- **Host the dashboard in-session** via `ctx.ui.custom`, reusing
  `MissionControlDashboard` as-is for rendering, driven by an **action-dispatch
  loop** (the proven `runReviewLoop` pattern).
- **Inspect an agent row** → a **read-only, scrollable transcript** of that
  agent's session, shown in-session; plus a pop-out key (`o`) to `pi --session
  <file>` for an actual takeover. The pop-out is the *only* surviving use of a
  separate window.
- **Validation row** → the gate log in a scrollable in-session view.
- **Human-review** → the existing in-session `runReviewLoop`, **auto-opened**
  when the poll detects the human-review row entering `blocked` (preserving
  today's "it needs me → here's the diff" behavior).
- **`q`** closes the overlay back to chat; the non-blocking status **widget**
  (`ctx.ui.setWidget("factory", …)`) stays for at-a-glance progress.
- **`/factory-run --auto`** keeps today's widget-only, no-modal background
  behavior (true fire-and-forget). The overlay is for interactive `/factory-run`.

This was chosen over keeping the separate window because the watch-only pattern
makes the window's one advantage moot, and hosting in-session removes the
standalone host, the platform-specific spawning, and the `.ts`-execution path.

## 3. Architecture — the action-dispatch loop

`/factory-run` (interactive) becomes:

```
launch orchestrator detached (unchanged: logs to .factory-run.log)
loop:
    action = await ctx.ui.custom(open MissionControlDashboard overlay)   # blocks until the overlay resolves
    switch action.type:
        "inspect"     -> await showTranscriptOverlay(sessionId)           # read-only; may itself pop out to pi --session
        "gate-log"    -> await showGateLogOverlay(factoryRunId)
        "review"      -> runReviewLoop(...) + writeReviewDecision(...)     # auto-triggered when human-review blocks
        "quit"        -> break
        "run-finished"-> show a final "run finished — q to close" state, then break on next quit
```

Each branch runs an in-session overlay (or, for `review`, the existing review
loop), then the top of the loop **reopens** the dashboard — the same
resolve-do-reopen shape `runReviewLoop` already uses for its comment/edit
actions. Overlays are **sequential, never nested**: the dashboard resolves
(`done(action)`) before the next overlay opens.

The orchestrator runs **detached** the whole time and writes
`.factory-status.json`; the dashboard only reads it. The one point the
orchestrator blocks for input is human-review (`FileHumanReviewGate` polling
`review-decision.json`) — serviced by the `review` action.

## 4. The dashboard overlay — live updates hosted by the pi TUI

`MissionControlDashboard` is already a `Component` (`render`, `handleInput`,
`invalidate`). Two changes let it live in-session:

1. **Live polling moves into the overlay's lifetime.** The standalone `main()`
   ran `setInterval(() => { dashboard.updateRecord(readRecord()); tui.requestRender(); }, 500)`.
   In-session, the same poll is started when the overlay opens (the
   `ctx.ui.custom` factory receives the `tui`, so the component can hold it,
   `setInterval`-poll `.factory-status.json`, call `tui.requestRender()`), and
   **cleared when the overlay resolves** (on `done()`), so no timer leaks across
   the loop.

2. **`handleEnter` resolves with an action instead of spawning a window.** Today
   `handleEnter` calls `openAgentSession` / `tailGateLog` / `openReviewBrowser`,
   which spawn windows. Instead it calls a `done(action)` callback with a typed
   `MissionControlAction` (§5). The component no longer imports
   `spawnTerminalWindow`, `resolveSessionPath`, or the review-browser spawn.

`q` resolves with `{ type: "quit" }`. `render()` is unchanged except the footer
hint (`o` appears only in the transcript overlay, not here).

## 5. Action protocol

```ts
type MissionControlAction =
  | { type: "inspect"; node: string; sessionId: string | null }
  | { type: "gate-log" }
  | { type: "review"; startCommit: string; alreadyDone: boolean; deliverables: string[] }
  | { type: "quit" };
```

- **`inspect`** — emitted by Enter on an agent row (`context-gather`/`dev`/
  `review`/`session-review`). If `sessionId` is null the handler shows the
  existing "session not ready" inline message and reopens (no overlay).
- **`gate-log`** — Enter on the `validation` row.
- **`review`** — NOT user-triggered; the overlay's poll emits it automatically
  when it first sees `human-review` in `node_state === "blocked"` with a
  `start_commit`, carrying `already_done`/`deliverables` (from Task work already
  shipped) so the review shows the implementing diff. A per-round guard (moved
  out of the deleted `launchInteractiveReview` poll into the loop's state)
  prevents re-emitting for the same blocked round.
- **`quit`** — `q`.

## 6. Drill-down overlays

### 6.1 Inspect agent session (read-only + pop-out)
- Resolve the session `.jsonl` via `resolveSessionPath(sessionId)`.
- Parse it into readable lines: for each `message_start`/`message_end` event,
  extract the role and its text content blocks (the same shape used elsewhere:
  `event.message.content[].text` for `type === "text"`). Tool calls render as a
  one-line summary (`> [tool] <name>`).
- Show the parsed text in a **scrollable read-only overlay** (reuse
  `ScrollableMarkdown`, already used by `/review-plans`, or a thin scroll view if
  markdown rendering of a transcript is awkward).
- Footer: `q back   o open in pi --session (takeover)`. `o` calls
  `spawnTerminalWindow("pi", ["--session", path], { cwd })` — the sole surviving
  window spawn — then stays in the transcript overlay.
- If the `.jsonl` can't be resolved, show "session not ready" and return.

### 6.2 Validation gate log
- Read `sessions/.factory-transcripts/<factoryRunId>/sim-gate.log` and show it in
  the same scrollable overlay. (Live `-Wait` tailing is dropped; a re-openable
  snapshot is enough for watching — reopening re-reads the file.)

### 6.3 Human-review
- The `review` action runs the existing `runReviewLoop` (already in-session),
  using `computeImplementingFiles`/the banner for already-done tasks and
  `computeReviewFiles` otherwise (both already implemented), then
  `writeReviewDecision(reviewDecisionPath(cwd, sessionId), decision)`. Control
  returns to the dashboard loop.

## 7. Run lifecycle & exit

- The loop keeps reopening the dashboard until `quit`, OR until the run finishes.
- **Run-finished detection:** the run lock (`sessions/.factory-run.lock`)
  disappears when the orchestrator exits (`remove_lock` in `__main__.py`). The
  dashboard's poll surfaces a "run finished" state; the handler stops re-arming
  the auto-review and the user `q`s out. The `/factory-run` handler still awaits
  the orchestrator child's `exit` (as today) so the command completes cleanly.

## 8. `--auto` mode

`launchAndWatch` (the `--auto` path) is unchanged: it keeps updating the
`ctx.ui.setWidget("factory", …)` status widget in the background and never opens
the modal overlay. This preserves a true fire-and-forget option.

## 9. What is removed

- `mission-control-dashboard.ts`'s standalone `main()` and its
  `if (process.argv[1]?.endsWith("mission-control-dashboard.ts")) …` bootstrap.
- `launchMissionControl(ctx)` (the dashboard window spawn).
- `launchInteractiveReview`'s separate review-poll `setInterval` (folded into the
  loop's `review` action + guard).
- The dashboard's direct window spawns (`openAgentSession`, `tailGateLog`,
  `openReviewBrowser`) — replaced by action resolutions.
- `spawnTerminalWindow` is retained ONLY for the `pi --session` pop-out (§6.1).
- `mission-control-review.ts` (the standalone review-browser window the old
  dashboard spawned via `openReviewBrowser`) becomes **unreferenced** once
  `openReviewBrowser` is deleted — the in-session `runReviewLoop` supersedes it.
  Leaving the now-dead file in place and deleting it as a separate cleanup is out
  of scope here; this spec does not depend on it either way.

## 10. Edge cases

- **No status file yet / null record:** the dashboard renders "(no task)" + all
  stages pending and updates once the orchestrator writes — same as today.
- **Over-width lines:** already fixed globally (`truncateToWidth` in the review
  overlay); the transcript/gate-log overlays must truncate/scroll the same way.
- **Timer leaks:** the poll interval is cleared on every `done()`; reopening
  starts a fresh one.
- **Human-review while a drill-down overlay is open:** the orchestrator simply
  stays blocked until the user returns to the dashboard, where the poll then
  emits `review`. No lost decisions (the block is patient by design).
- **`pi --session` pop-out failure** (binary missing): surfaced via
  `ctx.ui.notify`, transcript overlay stays open.

## 11. Testing

- **Dashboard component:** Enter on each row type resolves with the correct
  `MissionControlAction` (replacing today's spawn assertions); `q` resolves
  `{ type: "quit" }`; the poll emits `{ type: "review" }` exactly once per blocked
  round (guard works).
- **Transcript parsing:** a `.jsonl` fixture of pi events → expected readable
  lines (user/assistant text, tool-call summaries); unresolved session → "session
  not ready".
- **Handler loop:** `/factory-run` opens the dashboard overlay (not
  `spawnTerminalWindow`); an `inspect` action opens the transcript overlay; a
  `review` action calls `runReviewLoop` + `writeReviewDecision`; `quit` ends the
  loop; the orchestrator is still spawned detached with stdout/stderr to the log.
- **`--auto`:** still updates the widget and never opens the overlay.
- **Regression:** `q` quits (now trivially — it resolves the overlay); no
  standalone `main()` remains.

## 12. Files touched (anticipated)

- `pi-ext/factory-watch/src/mission-control-dashboard.ts` — component resolves
  with actions + hosts its poll via the injected `tui`; delete `main()` and the
  window-spawning methods.
- `pi-ext/factory-watch/src/index.ts` — `/factory-run` runs the action-dispatch
  loop; delete `launchMissionControl` and the review-poll `setInterval`.
- `pi-ext/factory-watch/src/session-transcript.ts` (new) — parse a session
  `.jsonl` into readable lines.
- A scrollable read-only viewer for transcript + gate log (reuse
  `ScrollableMarkdown` or a thin new component).
- Tests under `pi-ext/factory-watch/test/`.
