---
id: T-060
status: done
title: 'Fix NC-0008: coherence.planning.cli''s review handler emits schema 1
  instead of PLANNING_TRANSPORT_SCHEMA (2)'
dod:
- 'NC-0008: `guided_pipeline review --run-id <run>` succeeds (passes the
  adapter''s own transport-shape check: `schema == PLANNING_TRANSPORT_SCHEMA`)
  for a run with a valid, already-produced `.factory/planning/<run-id>/
  report.json`, both when the report is clean (no findings) and when it has
  findings.'
- '`_review` in `src/coherence/planning/cli.py` (or `build_escalation` in
  `src/coherence/planning/run.py`, whichever is the more correct fix point --
  check for other callers of `build_escalation` before choosing so as not to
  break them) emits `schema: 2` (the current `PLANNING_TRANSPORT_SCHEMA`
  value), matching every sibling handler in `cli.py`.'
- A new regression test proves the fix by driving the real payload shape
  `guided_pipeline.run_pipeline_command`''s own validation checks (schema
  field, run_id field) rather than only unit-testing `build_escalation`/
  `_review` in isolation.
- 'Every pre-existing test in `tests/unit/coherence/` still passes; if a
  pre-existing test asserted `schema: 1` was correct for this payload, that
  assertion is corrected, not preserved.'
- 'Verification commands (this repo''s documented convention): `rtk uv run
  pytest tests/unit/coherence/ -q -o addopts=''''''` all green; `rtk uv run
  ruff check <changed file(s)>` clean; `rtk uv run pyright <changed
  file(s)>` clean.'
- No FEAT-018 planning artifact (`.intent/`, `.factory/planning/FEAT-018/`,
  `docs/superpowers/specs/2026-09-14-feat018-*`,
  `docs/superpowers/plans/2026-09-14-feat018-*`, `tasks/T-048-*` through
  `tasks/T-056-*`) is modified by this task -- that is a separate, concurrent
  planning run, not this task's concern.
- Tests/gates pass and the change is committed.
trace_exempt: true
trace_exempt_reason: 'T-060 is exempt from both open gaps, matching T-029''s,
  T-058''s, and T-059''s precedent. (1) task_no_sr: no requirement node
  governs this bugfix -- it corrects behavior documented as a defect
  (NC-0008), not a feature requirement, so there is no SR to satisfy. (2)
  task_no_plan: this task is executed directly from its own brief (this task
  file IS the spec, per the nonconformance record it implements) -- no
  separate implementation plan was authored, since the fix is small and fully
  specified by NC-0008''s Correction section.'
---

**Provenance note**: checked before authoring -- no existing reservation of `T-060` was found in
`docs/` or `tests/` at time of writing (unlike `T-057`, which collided with a concurrent
session's own reservation; see `T-058`'s provenance note).

## Scope

- `src/coherence/planning/cli.py` (`_review`, ~line 415) and/or
  `src/coherence/planning/run.py` (`build_escalation`, ~line 124) -- whichever
  is the correct fix point once you've checked for other callers.
- Its existing test file(s) -- search `tests/unit/coherence/` for
  `build_escalation`, `_review`, or a `review` CLI-verb test.

## Background

Discovered while driving FEAT-018's own `/coherence-plan` workflow through
step 10 (`guided_pipeline review`) after `bootstrap`/`check` both passed
cleanly. Filed as:

- `docs/nonconformances/NC-0008-review-verb-emits-schema-1.md`

Read it in full before starting -- it contains the precise root cause (exact
line citations as of filing time; re-locate by content) and the proposed
correction. This task's Definition of Done restates its substance but the NC
file is the authoritative detail.

## Root cause

`PLANNING_TRANSPORT_SCHEMA = 2`
(`src/coherence/planning/legal_actions_adapter.py:56`). `_review`
(`cli.py`) prints `build_escalation(...)`'s dict with only `ok`/`hashes`
merged in afterward -- it never overwrites `schema`. `build_escalation`
(`run.py:124-149`) hardcodes `"schema": 1`. Every other `cli.py` transport
handler explicitly sets `payload["schema"] = PLANNING_TRANSPORT_SCHEMA` (or
builds the dict with that key directly) before printing --
`_review` is the one handler that omits this. `guided_pipeline.py`'s
`run_pipeline_command` (the sanctioned adapter every host must use instead of
calling `coherence plan` directly) rejects any payload whose `schema` field
doesn't equal `PLANNING_TRANSPORT_SCHEMA`, so `review`'s output always fails
this check, for every run, unconditionally.

Before changing anything: grep for every call site of `build_escalation` (not
just `_review`) to confirm none of them depend on the literal `1` -- if
another caller exists and legitimately needs schema `1` for a different
reason, prefer fixing `_review`'s own print site (add `escalation["schema"] =
PLANNING_TRANSPORT_SCHEMA` there) over changing `build_escalation`'s default.

## Verification

1. `rtk uv run pytest tests/unit/coherence/ -q -o addopts=''` -- all green,
   including new and pre-existing tests.
2. `rtk uv run ruff check <changed file(s)>`
3. `rtk uv run pyright <changed file(s)>`
4. Do not touch any FEAT-018 planning artifact -- see the Definition of Done.
5. Re-run FEAT-018's own review as final confirmation (not required for this
   task's own DoD, but useful evidence): `uv run python -m
   coherence.planning.guided_pipeline review --run-id FEAT-018 --project-root
   .` should return `ok: true` with a valid schema-2 payload (FEAT-018's
   `check` already passes cleanly, so its `report.json` should have no
   findings).
