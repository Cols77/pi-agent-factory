---
id: T-058
status: done
title: 'Fix NC-0004 and NC-0005: coherence.planning.check hardcodes FEAT-017 and
  checks the entire shared tasks/ directory'
dod:
- 'NC-0004: `_planning_reference_paths`/`_check_planning_references` in
  `src/coherence/planning/check.py` no longer spuriously validate FEAT-017''s
  closure metadata against an unrelated run''s own `--spec` argument. A run
  whose run_id is not `FEAT-017` and whose `--spec` is not FEAT-017''s own
  closure spec produces zero `PLANNING_REFERENCE_INVALID` findings caused by
  FEAT-017''s dossier/bundle/requirements, even though
  `docs/features/FEAT-017.md`/`bundles/FEAT-017.json` exist in the repo.'
- 'NC-0004: checking `run_id == "FEAT-017"` itself still correctly validates (and
  still correctly fails on a genuine defect in) FEAT-017''s own closure
  metadata -- the fix narrows scope, it does not delete the check.'
- 'NC-0005: `_check_tasks` in `src/coherence/planning/check.py` no longer flags
  `PLAN_TASK_PARITY` for a task file whose `source_plan` names a different
  plan than the one under review. Decomposing/checking a second, unrelated
  plan into the same shared `tasks/` directory that already holds a first
  plan''s tasks produces zero `PLAN_TASK_PARITY` findings against the first
  plan''s own tasks.'
- 'NC-0005: the existing completeness check (every task NUMBER the plan under
  review declares has a corresponding generated task file, and a task that
  really does claim `source_plan == expected_plan` but has some other
  inconsistency is still flagged) keeps working exactly as before -- the fix
  narrows which files are considered, it does not weaken the check for the
  plan actually under review.'
- 'A new regression test proves NC-0004''s fix: a fixture with
  `docs/features/FEAT-017.md`/`bundles/FEAT-017.json`/FEAT-017''s requirement
  files present, checked under a different run_id, asserts no
  `PLANNING_REFERENCE_INVALID` finding is raised for FEAT-017''s own
  requirements; a paired test proves `run_id == "FEAT-017"` itself still
  validates correctly.'
- 'A new regression test proves NC-0005''s fix: two different plans'' tasks
  coexisting in the same `tasks/` directory, checking the second plan raises
  no `PLAN_TASK_PARITY` finding against the first plan''s tasks, while a
  genuine parity problem introduced into the second plan''s own tasks is still
  caught.'
- Every pre-existing test in `tests/unit/coherence/` (this module and its
  direct dependents) still passes; if a pre-existing test asserted the old
  buggy behavior was correct, that assertion is corrected, not preserved.
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
trace_exempt_reason: 'T-058 is exempt from both open gaps, matching T-029''s
  precedent. (1) task_no_sr: no requirement node governs this bugfix -- it
  corrects behavior documented as a defect (NC-0004, NC-0005), not a feature
  requirement, so there is no SR to satisfy. (2) task_no_plan: this task is
  executed directly from its own brief (this task file IS the spec, per the
  two nonconformance records it implements) -- no separate implementation
  plan was authored, since the fix is small, fully specified by the two NCs''
  Correction sections, and does not warrant a full plan/decompose cycle.'
---

**Provenance note**: originally authored as `T-057`. Renamed to `T-058` before merge after
discovering a real ID collision: a concurrent session's own plan amendment
(`docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md`, "Task identity
reservation amendment") had already reserved `T-057` for its own future task ("Task 12, the
guided host entrypoint"), and its regression test
(`tests/unit/coherence/test_planning_trace_contract.py::test_feat17_plan_amendment_reserves_tasks_and_registers_proposed_sr055_sr065_and_sr071`)
asserts `T-057-*.md` must not exist yet. No content in this task's own scope is affected by the
rename.

## Scope

- `src/coherence/planning/check.py` (+ its existing test file, whichever
  `tests/unit/coherence/test_*.py` currently exercises `check_planning_input`/
  `_check_tasks`/`_check_planning_references` -- find it before writing new
  tests, and follow its existing fixture conventions).

## Background

Discovered during a FEAT-018 planning session's attempt to run
`guided_pipeline bootstrap --decompose`/`check`: both failed with findings
unrelated to FEAT-018's own spec/plan content. Traced to two separate,
independently-reproducing defects in `check_planning_input`'s implementation,
each filed as its own nonconformance with the exact code citation and a
proposed correction:

- `docs/nonconformances/NC-0004-planning-check-hardcodes-feat017.md`
- `docs/nonconformances/NC-0005-plan-task-parity-checks-entire-shared-tasks-dir.md`

Read both files in full before starting -- they contain the precise root
cause (with line numbers as of filing time; re-locate by content, since the
file may have shifted) and the author's proposed correction for each. This
task's Definition of Done restates their substance but the NC files are the
authoritative detail.

## NC-0004 -- hardcoded "FEAT-017" instead of run_id

`_planning_reference_paths(root, run_id)` and `_check_planning_references(root,
spec_path, spec_text, findings)` hardcode `docs/features/FEAT-017.md`/
`bundles/FEAT-017.json` literally instead of using the `run_id` they are
given (or scoping by it), and compare each of FEAT-017's own requirements'
`source` field against the *current run's own* `--spec` argument rather than
FEAT-017's actual closure spec -- so this validation spuriously fires for
every run except one that happens to pass FEAT-017's own closure spec as
`--spec`.

Read the whole function before choosing a fix -- it already makes FEAT-017-
specific assertions throughout (`feature_metadata.get("id") != "FEAT-017"`,
literal error text "FEAT-017 dossier has invalid closure metadata"/"FEAT-017
bundle is invalid JSON"), so it was written to validate FEAT-017's own
closure specifically, not as a generic per-run validator. The likely minimal,
faithful fix is to scope the whole check to only execute when
`run_id == "FEAT-017"`, threading `input.run_id` through to
`_check_planning_references`'s call site in `check_planning_input`
(~line 533) -- but verify this against the function's full logic and its
existing tests before committing to that approach.

## NC-0005 -- PLAN_TASK_PARITY checks the entire shared tasks/ directory

`_check_tasks` globs every `T-*.md` file in the single, shared, repo-wide
`tasks/` directory and flags any whose `source_plan` frontmatter is not the
plan currently under review -- so it flags every other feature's already-
merged tasks (in the live repo: every task from before this fix, including
this very task, T-058, once it exists) on every check.

Read the whole function, including how its `mappings`/return value get used
further down in `check_planning_input` for the completeness check ("does
every plan-declared task number have a corresponding generated file"),
before changing anything -- the fix must skip files that belong to a
*different* plan entirely (not this check's business) while still catching a
genuine parity problem within tasks that actually claim
`source_plan == expected_plan`, and still catching the reverse case (a task
number the plan under review declares with no generated file at all).

## Verification

1. `rtk uv run pytest tests/unit/coherence/ -q -o addopts=''` -- all green,
   including new and pre-existing tests.
2. `rtk uv run ruff check src/coherence/planning/check.py <new/changed test
   file(s)>`
3. `rtk uv run pyright src/coherence/planning/check.py`
4. Do not touch any FEAT-018 planning artifact -- see the Definition of Done.
