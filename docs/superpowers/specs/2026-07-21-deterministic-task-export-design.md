# Design: Deterministic Task Export from Plans

**Date:** 2026-07-21
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Framing

The `/plan` command (implemented per `docs/superpowers/specs/2026-07-20-factory-plan-and-run-design.md`)
seeds a fresh session with the `brainstorming` and `writing-plans` skills. The
seed prompt includes a soft instruction telling the model to run
`uv run python -m factory.orchestrator.plan_to_tasks <plan-file>` once the plan
is saved. This is the only path from a written plan to `tasks/T-*.md` files that
`/factory-tasks` and `/factory-run` can discover.

In practice the model often skips it, misformats the path, or just doesn't do it.
Result: plan file exists, `tasks/` stays empty, `/factory-tasks` says "no tasks."

A secondary bug: `plan_to_tasks.py`'s `### Task N:` regex matches inside fenced
code blocks, creating spurious tasks from fixture strings embedded in plans
(e.g., T-008 "First Component" from the test fixture in the factory-plan-and-run
plan).

### 1.1 Goals

- **Deterministic post-session export**: after `/plan`'s session ends, the
  extension code itself detects the new plan file and runs `plan_to_tasks`,
  removing any reliance on the model's discretion.
- **Interactive mark-done**: after export, offer the user a picker loop to mark
  tasks that are already implemented as "done," so the board shows only real
  remaining work.
- **Fix fenced-code-block false matches** in `plan_to_tasks.py`'s parser.

### 1.2 Non-Goals

- Not rebuilding plan-time as a factory node.
- Not adding batch/queue execution of tasks.
- Not adding a general-purpose task status management command surface beyond
  the single `set-status` CLI and the `/plan` mark-done loop.

---

## 2. Architecture

```
/pi <topic>
    |
    v
ctx.newSession(seed prompt)  -- session starts
    |
    v
MODEL + USER TALK (brainstorming -> writing-plans)
    |
    v
writing-plans saves plan to docs/superpowers/plans/
    |
    v
ctx.newSession() resolves  -- session ends
    |
    v
PLAN HANDLER (deterministic, TypeScript):
  1. Scan docs/superpowers/plans/ for .md files newer than pre-session timestamp
  2. For each new plan: spawnSync plan_to_tasks <plan-file>
  3. Parse "created: T-XXX, ..." from stdout
  4. Refresh /factory-tasks widget
  5. Notify: "exported T-003, T-004 from <plan-file>"
  6. If new tasks created: enter mark-done picker loop
     - ctx.ui.select("Mark which task as done?", [...new task options])
     - User picks one -> spawnSync set-status <id> done -> remove from list
     - Repeat until user cancels or list empty
     - Notify: "T-001, T-002 marked done" (if any)
  7. Refresh /factory-tasks widget again
```

No model discretion anywhere after step 2. The seed prompt drops the soft
"run plan_to_tasks" instruction and instead says: *"Once the plan is saved under
`docs/superpowers/plans/`, tasks are exported automatically."*

---

## 3. Components

### 3.1 Seed prompt update (`pi-ext/factory-watch/src/skill-prompt.ts`)

`buildPlanSeedPrompt` changes the third instruction from:

> Override writing-plans' own "Execution Handoff" step: once the plan is saved,
> do not offer subagent-driven or inline execution. Instead run `uv run python
> -m factory.orchestrator.plan_to_tasks <plan-file>` and report the task ids it
> created. Actual execution happens later via /factory-run.

to:

> Once the plan is saved under `docs/superpowers/plans/`, tasks are exported
> automatically — do not run plan_to_tasks yourself. Actual execution happens
> later via /factory-run.

### 3.2 Post-session auto-export (`pi-ext/factory-watch/src/index.ts`)

The `/plan` handler gains post-session logic after `ctx.newSession()` resolves:

1. Record `Date.now()` before the session starts.
2. After the session (and only if `cancelled === false`), scan
   `docs/superpowers/plans/` for `.md` files with `mtimeMs > beforeMs`.
3. For each new plan, `spawnSync` the existing `plan_to_tasks` CLI
   (`uv run python -m factory.orchestrator.plan_to_tasks <plan-file>`).
4. Parse stdout for `"created: T-XXX, ..."` lines.
5. Refresh the `/factory-tasks` widget (same `spawnSync` + `setWidget` pattern
   already used by the `/factory-tasks` command).
6. Notify: `"exported T-003, T-004 from <plan-file>"`, or
   `"no new plan files found"` if none.

Extracted into a pure helper `exportNewTasks(ctx, beforeMs)` for testability,
following the extension's existing pattern of thin handlers calling pure-ish
helpers.

### 3.3 Interactive mark-done loop (`pi-ext/factory-watch/src/index.ts`)

After export, if any new task ids were created:

1. Call `list --json`, filter to only the newly created ids.
2. Show `ctx.ui.select("Mark which task as done?", [...options])`.
3. If user picks one: `spawnSync` `factory.orchestrator set-status <id> done`,
   remove from the list, loop back to step 2.
4. If user cancels or list is empty: stop.
5. Notify: `"T-001, T-002 marked done"` (if any were marked), or nothing.

After the loop, refresh the `/factory-tasks` widget one final time.

### 3.4 `set-status` CLI subcommand (`src/factory/orchestrator/__main__.py`)

New subcommand:

```
uv run python -m factory.orchestrator set-status <task-id> <status>
```

Reads `tasks/`, finds `<task-id>`, calls `ledger.set_status()`, exits 0.
Raises `TaskNotFoundError` if not found. The `status` argument is free-form
(matching the ledger's existing design) — callers pass `"done"`, `"todo"`,
`"rejected"`, or `"escalated"`.

Minimal: argparse gains `set-status` as a third command choice alongside
`run` and `list`, with positional `task_id` and `status` arguments.

### 3.5 Fenced-code-block stripping in `plan_to_tasks.py`

New preprocessing step inside `parse_plan_tasks`:

```python
_CODE_FENCE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~", re.MULTILINE)

def parse_plan_tasks(text: str) -> list[ParsedPlanTask]:
    stripped = _CODE_FENCE.sub("", text)
    # ... existing regex logic on `stripped` instead of `text`
```

All existing callers are unaffected — `parse_plan_tasks`'s signature and
return type don't change. The CLI wrapper (`run()`) is unchanged. Existing
tests that use fixture plan strings outside code blocks keep passing.

---

## 4. Error Handling

- **`ctx.newSession()` returns `{ cancelled: true }`**: user bailed without
  saving. Skip the entire post-session flow. No scan, no notify.
- **New plan found but `plan_to_tasks` exits non-zero** (zero task sections):
  notify error with stderr content. Don't crash the `/plan` handler — the user
  can fix the plan and re-run `plan_to_tasks` manually.
- **No new plan files found after session**: notify "no new plan files found",
  skip export and mark-done entirely.
- **Mark-done picker cancelled immediately**: no tasks marked, no error. User
  can mark tasks later.
- **`set-status` CLI fails** (task not found): notify error for that task,
  continue the picker loop with remaining tasks.

---

## 5. Testing Strategy

**Python:**
- `plan_to_tasks`: add test that `### Task N:` inside a fenced code block is
  ignored; add test that `### Task N:` outside code blocks still parses
  normally; add test for `~~~`-delimited blocks too.
- `__main__.py`: add tests for `set-status` subcommand — happy path (status
  changes in file), not-found error, and unknown status accepted (ledger is
  free-form).

**TypeScript:**
- `skill-prompt.test.ts`: verify the old "run plan_to_tasks" instruction is
  absent and the new "exported automatically" line is present.
- `process-control.ts`/tests: add `buildPlanToTasksCommand(planFile)` and
  `buildSetStatusCommand(taskId, status)` pure functions with tests.
- `handler.test.ts`: add tests for `/plan`'s post-session flow — mock
  `spawnSync` to return plan_to_tasks output, verify widget refresh, notify,
  and mark-done picker invocations. Test cancelled-session path skips
  everything. Test no-new-plans path skips export.

---

## 6. Cross-Plan Dependencies

Consumes, unchanged: `plan_to_tasks.py` (the CLI itself, only its parser gains
code-fence stripping), the orchestrator's `list --json` output format, and
`ledger.set_status()` (newly exposed via CLI).

No changes to `pi-ext/scope-guard/`, no new dependencies.
