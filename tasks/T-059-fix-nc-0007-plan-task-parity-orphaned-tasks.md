---
id: T-059
status: done
title: 'Fix NC-0007: PLAN_TASK_PARITY flags orphaned tasks (no source_plan at
  all) during any unrelated plan''s check'
dod:
- 'NC-0007: `_check_tasks` in `src/coherence/planning/check.py` no longer flags
  `PLAN_TASK_PARITY` for a task file that has no `source_plan` field at all
  (missing, `None`, or empty/whitespace-only). Such a task declares no
  relationship to any plan and is equally "not this check''s business" as the
  foreign-plan case NC-0005 already fixed.'
- 'The reverse case is unchanged: a task NUMBER the plan under review''s own
  declared tasks expect, with no corresponding generated file at all, is still
  caught. A task that DOES claim `source_plan == expected_plan` but has some
  other real inconsistency (duplicate id, non-integer source_task, etc.) is
  still caught exactly as before.'
- 'A new regression test proves the fix: a standalone, no-`source_plan` task
  (mirroring `T-029`''s real shape -- `trace_exempt: true`, no `source_plan`
  field) coexisting in `tasks/` with a real plan''s own tasks; checking that
  plan raises no `PLAN_TASK_PARITY` finding against the orphaned task, while a
  genuine parity problem introduced into the plan''s own tasks is still
  caught.'
- Every pre-existing test in `tests/unit/coherence/` (this module and its
  direct dependents) still passes; if a pre-existing test asserted the old
  over-eager behavior was correct, that assertion is corrected, not preserved.
- 'Verification commands (this repo''s documented convention): `rtk uv run
  pytest tests/unit/coherence/ -q -o addopts=''''''` all green; `rtk uv run
  ruff check src/coherence/planning/check.py <new/changed test file(s)>`
  clean; `rtk uv run pyright src/coherence/planning/check.py` clean.'
- No FEAT-018 planning artifact (`.intent/`, `.factory/planning/FEAT-018/`,
  `docs/superpowers/specs/2026-09-14-feat018-*`,
  `docs/superpowers/plans/2026-09-14-feat018-*`, `tasks/T-048-*` through
  `tasks/T-056-*`) is modified by this task -- that is a separate, concurrent
  planning run, not this task's concern.
- Tests/gates pass and the change is committed.
trace_exempt: true
trace_exempt_reason: 'T-059 is exempt from both open gaps, matching T-029''s
  and T-058''s precedent. (1) task_no_sr: no requirement node governs this
  bugfix -- it corrects behavior documented as a defect (NC-0007), not a
  feature requirement, so there is no SR to satisfy. (2) task_no_plan: this
  task is executed directly from its own brief (this task file IS the spec,
  per the nonconformance record it implements) -- no separate implementation
  plan was authored, since the fix is small and fully specified by NC-0007''s
  Correction section.'
---

**Provenance note**: `T-057` was reserved by a concurrent session's own plan amendment
(`docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md`) and `T-058` was already
used by this same bugfix stream's prior task (NC-0004/NC-0005). Checked before authoring: no
existing reservation of `T-059` was found in `docs/` or `tests/` at time of writing.

## Scope

- `src/coherence/planning/check.py` (+ its existing test file --
  `tests/unit/coherence/test_planning_check.py`, which now also carries the
  NC-0004/NC-0005 regression tests; follow its established fixture
  conventions).

## Background

Discovered while re-verifying FEAT-018's own `guided_pipeline check` after
`T-058`'s NC-0004/NC-0005 fix landed on `main` (commit `82784a2`):
`PLANNING_REFERENCE_INVALID` dropped from 10 to 0 and `PLAN_TASK_PARITY`
dropped from 40 to exactly 3 -- `tasks/T-029-*.md`, `tasks/T-031-*.md`, and
`tasks/T-058-*.md`, all genuinely orphaned (no `source_plan` field at all, by
design). Filed as:

- `docs/nonconformances/NC-0007-plan-task-parity-flags-tasks-with-no-source-plan.md`

Read it in full before starting -- it contains the precise root cause (with
line numbers as of filing time; re-locate by content) and the proposed
correction. This task's Definition of Done restates its substance but the NC
file is the authoritative detail.

## Root cause

`_check_tasks`'s NC-0005 fix added: `if isinstance(source_plan, str) and
source_plan.strip() and source_plan != expected_plan: continue` -- this only
skips a task when `source_plan` is a non-empty string naming a DIFFERENT real
plan. When `source_plan` is missing/`None`/empty, that condition is `False`,
so the task falls through to `matched_paths.append(task_path)` and then the
unconditional `if source_plan != expected_plan:` check appends a
`PLAN_TASK_PARITY` finding reading "generated task source_plan does not match
the selected plan" -- misleading, since there is no plan to mismatch against;
the task simply declares none.

Read the whole function, including how its `mappings`/return value get used
further down in `check_planning_input` for the completeness check, before
changing anything -- extend the skip condition to also cover the
missing/empty case without weakening the reverse case (a task number the plan
under review's own declared tasks expect, with no generated file, must still
be caught) or the "this task claims OUR plan but is otherwise broken" case
(duplicate id, non-integer `source_task`, etc. -- still caught).

## Verification

1. `rtk uv run pytest tests/unit/coherence/ -q -o addopts=''` -- all green,
   including new and pre-existing tests.
2. `rtk uv run ruff check src/coherence/planning/check.py <new/changed test
   file(s)>`
3. `rtk uv run pyright src/coherence/planning/check.py`
4. Do not touch any FEAT-018 planning artifact -- see the Definition of Done.
5. Re-run FEAT-018's own check as final confirmation (not required for this
   task's own DoD, but useful evidence): `uv run python -m
   coherence.planning.guided_pipeline check --run-id FEAT-018 --project-root .
   --intent .intent/intent.json --spec docs/superpowers/specs/2026-09-14-
   feat018-execution-proposal-validator-design.md --plan
   docs/superpowers/plans/2026-09-14-feat018-execution-proposal-validator-
   plan.md` should report zero `PLAN_TASK_PARITY` findings for `T-029`,
   `T-031`, and `T-058`/`T-059` themselves.
