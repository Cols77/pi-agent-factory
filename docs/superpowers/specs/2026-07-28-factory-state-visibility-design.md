# Factory State Visibility — Design

**Date:** 2026-07-28
**Status:** Approved (brainstorm)

## Goal

Make the factory's real state legible to the human in two places:

1. **Mission control** — each pipeline node row says what that agent is *doing*
   (while running) or what it *produced* (when settled).
2. **The task picker** — a task that was started but did not finish is never
   hidden; instead its last run's stop-point (and why) is shown, so you can
   decide whether to re-run it.

Everything is derived from data the orchestrator already has. No agent prompt
changes, no extra LLM/token cost.

## Motivating evidence

`T-037` (DirectiveExecutor): ledger `status: todo`; both `Create:` deliverables
(`src/drone/mission/directive_executor.py`,
`tests/agent/test_directive_executor.py`) exist **and are committed**; yet the
last run stopped at `dev fail` (unit tests red, escalated). Today the task is
**hidden** from `factory-run` because its files exist — even though it is
genuinely incomplete. File-presence is not completion.

## Non-goals (explicitly out of scope)

- **A checkpoint/resume engine** that persists and replays node outputs to skip
  completed stages. Resume is handled by the existing *already-done routing*:
  the context-gatherer detects existing deliverables and routes to review,
  verifying via the gates, and self-corrects (runs dev) if they fail. The
  per-task run-state added here is **informational only** — nothing feeds back
  into the pipeline. A fuller checkpointed resume is deferred to a later spec.
- **Enriching the developer / validation done-summaries** (would require
  plumbing git `start_commit` / gate-log paths into nodes that lack them). The
  live snippet already answers "what is dev doing"; validation is binary.
- **KB-entry count in the context summary** (computed in the runner *after* the
  context node returns; the node cannot see it without an extra report hop).
- **Finding severity / kind** in review output (findings are plain strings;
  structuring them would need an agent prompt change and tokens — the rejected
  fork of this design).

---

## Component 1 — Per-node activity descriptions (mission control)

### 1a. Live: surface the streaming snippet

Each running node already streams output into the status file via its
`_on_snippet` callback (`status.report(..., snippet=text)`). The mission-control
dashboard does not render it today — only `handoff` and `summary`. Surface it.

- **`status-format.ts`** — `MissionControlRow` gains `snippet: string | null`;
  `formatMissionControlRows` sets `snippet: entry?.snippet ?? null`.
- **`mission-control-dashboard.ts`** — for a row whose `state === "running"`,
  render one line: the snippet's **last line**, trimmed and truncated to the
  panel width, prefixed to read as live activity, e.g. `    … <snippet tail>`.
  Rendered after `handoff`, before `summary`. Non-running rows render no
  snippet.

### 1b. Settled: enrich the context-gatherer summary

`nodes.py:_summarize_manifest` currently returns
`f"{n_files} files, coherence={'yes' if proven else 'no'}"`. Replace with the
actual file basenames from `manifest["context"]["source_files"]`:

```
provided: rtb.py, waypoint.py, nav_state.py (+2) · coherence proven
```

- Up to 3 basenames listed, then `(+k)` for the remainder.
- `coherence proven` / `coherence unproven` from `manifest["coherence"]["proven"]`.
- Empty / missing source_files → `no source files · coherence …`.
- This is the string passed as `summary=` on the context-gather `pass` report;
  it flows through `MissionControlRow.summary` to the existing summary line.

No other node's summary changes in this spec.

---

## Component 2 — Visibility fix (hide by status, never by file-presence)

Hide a task from the picker **only** when `status == "done"`. Stop using
`deliverables_exist` to hide.

- **`runner.py:run_next`** (auto-pick, the no-`--task` branch): change
  `next_todo([t for t in tasks if not deliverables_exist(t.body, repo_root)])`
  to `next_todo(tasks)`. The explicit `--task` path is unchanged (still requires
  `status == "todo"`).
- **`index.ts`** (~line 346): change
  `tasks.filter((t) => t.status === "todo" && !t.already_done)` to
  `tasks.filter((t) => t.status === "todo")`. Update the empty-state notice
  ("no runnable todo tasks …") to drop "already-done tasks are hidden".
- **`__main__.py:list --json`**: keep emitting `already_done` — it is retained
  as *annotation* information (Component 3), no longer used to hide.

The "don't waste a run re-doing finished work" goal is preserved by the
already-done routing at run-time, which verifies via the gates rather than
trusting files on disk.

---

## Component 3 — Durable per-task run-state + picker annotation

### 3a. Persist run-state per task

`sessions/.factory-status.json` is a single global slot the next run overwrites,
so a stopped task's state is lost as soon as anything else runs. A *killed* run
executes no end-of-run code, so archive-on-completion would miss exactly the
stopped tasks we care about.

Therefore **`FileStatusReporter.report` mirrors every write** to a per-task
file, best-effort, using the same record shape and the same
`_atomic_write_json` helper:

```
sessions/.factory-runs/<task_id>.json
```

- Path derived from the reporter's own status path:
  `self.path.parent / ".factory-runs" / f"{task_id}.json"`.
- Written on every `report()` call (last-write-wins), so a run killed at any
  point leaves its most recent state behind.
- Best-effort: a failed mirror write must never affect the run or the primary
  status write (same tolerance as the existing status write).
- `sessions/.factory-runs/` is added to `.gitignore` (runtime artifact,
  consistent with the existing `sessions/.factory-transcripts/` ignore).

### 3b. Read the stop-point for the picker

New reader (Python, e.g. `run_state.py`): `read_last_run(repo_root, task_id)
-> dict | None`. Reads the mirror file and returns a compact summary, or `None`
if there is no mirror:

```python
{
  "node": <current_node>,           # e.g. "dev"
  "state": <current_state>,         # e.g. "fail"
  "outcome": <last non-null outcome in pipeline, or None>,  # e.g. "escalated"
  "handoff": <handoff of the current_node's pipeline entry, or None>,  # reason
  "updated_at": <iso8601>,
}
```

`list --json` includes `last_run` (this dict or `null`) on each task object,
alongside the existing `id/title/status/already_done`.

### 3c. Annotate the picker row

- **`task-picker.ts`** — `TaskSummary` gains
  `last_run?: LastRun | null` where
  `LastRun = { node; state; outcome: string | null; handoff: string | null; updated_at: string }`.
  Add `humanizeAge(seconds): string` → `"just now"` / `"5m ago"` / `"2h ago"` /
  `"3d ago"`.
- `formatTaskOption(task)` returns a **single line** (the `ctx.ui.select`
  widget takes one string per option), with the id first so
  `parseTaskIdFromOption` still works:
  - `last_run` present (any task in the picker is `status == todo`, so a
    recorded run necessarily did not complete): 
    `T-037  DirectiveExecutor  — ⚠ stopped: dev fail (2h ago): unit tests still red`
    (the `: <reason>` clause omitted when `handoff` is null). A concurrent
    live run is prevented by `.factory-run.lock`, so a `running` last-state is
    not expected here; if seen, it renders the same way.
  - no `last_run` but `already_done` true (e.g. done outside the factory):
    `T-029  Foo  — deliverables present (will route to review)`
  - otherwise a clean todo: `T-036  ScriptedPerception`

The mission-control dashboard's data source is unchanged — it still reads the
global `sessions/.factory-status.json` for the current run.

---

## File-by-file summary

| File | Change |
|------|--------|
| `pi-ext/factory-watch/src/status-format.ts` | `snippet` on `MissionControlRow` + populate it |
| `pi-ext/factory-watch/src/mission-control-dashboard.ts` | render snippet line for running rows |
| `src/factory/orchestrator/nodes.py` | enrich `_summarize_manifest` (file basenames) |
| `src/factory/orchestrator/runner.py` | `run_next` auto-pick: drop `deliverables_exist` filter |
| `pi-ext/factory-watch/src/index.ts` | picker filter: hide by status only; empty-state notice |
| `src/factory/orchestrator/status.py` | `FileStatusReporter` mirrors to `.factory-runs/<task_id>.json` |
| `src/factory/orchestrator/run_state.py` (new) | `read_last_run(repo_root, task_id)` |
| `src/factory/orchestrator/__main__.py` | `list --json` adds `last_run` per task |
| `pi-ext/factory-watch/src/task-picker.ts` | `last_run` on `TaskSummary`; `humanizeAge`; annotated `formatTaskOption` |
| `.gitignore` | ignore `sessions/.factory-runs/` |

## Testing

- **Python** (`pytest`, unit): `_summarize_manifest` basename formatting (0/1/3/
  5 files, missing key); `run_next` auto-pick now returns a todo task whose
  deliverables exist; `FileStatusReporter` writes the per-task mirror on every
  report and survives a mirror-dir write failure without raising;
  `read_last_run` returns the stop-point dict / `None` for a missing file / the
  reason from handoff; `list --json` includes `last_run`.
- **TS** (`vitest`): `formatMissionControlRows` carries `snippet`; the dashboard
  renders the snippet line only for running rows; the picker filter keeps a
  `todo` task with `already_done: true`; `formatTaskOption` renders each of the
  three annotation cases; `humanizeAge` boundaries; `parseTaskIdFromOption`
  still extracts the id from an annotated line.

## Rollout

Pure additive display + a filter relaxation; no migration. Existing
`.factory-status.json` and status schema are unchanged (the mirror reuses the
same shape). Old task mirrors simply don't exist until a task next runs.
