---
id: NC-0005
title: PLAN_TASK_PARITY checks every file in the shared tasks/ directory, not just the plan under review
external_ref: null
detected_by: FEAT-018 plan-authoring session
status: open
---

## Symptom

`guided_pipeline bootstrap --decompose` and `guided_pipeline check` both fail closed with one
`PLAN_TASK_PARITY` finding (`"generated task source_plan does not match the selected plan"`) for
**every** pre-existing task file under `tasks/` whose `source_plan` frontmatter is not the plan
currently being checked — including tasks from long-since-merged, unrelated features.

Root cause, read directly from `src/coherence/planning/check.py`, `_check_tasks` (line 285):

```python
tasks_dir = root / "tasks"
...
task_paths = sorted(tasks_dir.glob("T-*.md"), key=lambda path: path.name)
...
for task_path in task_paths:
    ...
    if metadata.get("source_plan") != expected_plan:
        findings.append(_finding("PLAN_TASK_PARITY", ..., "generated task source_plan does not
        match the selected plan"))
```

This globs **every** `T-*.md` file in the single, shared, repo-wide `tasks/` directory — not just
tasks belonging to the plan under review — and flags each one whose `source_plan` isn't
`expected_plan` (the plan path passed via `--plan`). Since `tasks/` accumulates every feature's
generated tasks over the project's history and is never pruned, this check necessarily flags every
task from every other feature ever decomposed, on every `bootstrap --decompose`/`check` call, for
any plan.

Reproduced on this session's FEAT-018 run: after decomposing FEAT-018's plan (which correctly wrote
`tasks/T-048-*.md` through `tasks/T-056-*.md` with `source_plan` pointing at FEAT-018's plan),
`guided_pipeline check` reports 40 `PLAN_TASK_PARITY` findings — one for each of `tasks/T-001-*.md`
through `tasks/T-047-*.md` (pre-existing tasks from earlier, already-merged features such as the
original factory bootstrap and FEAT-013's governed execution driver) — none of which have any
relationship to FEAT-018's plan. This reproduces after fixing every other finding the same `check`
call raised (spec/plan frontmatter, intent-answer traceability, and independent of NC-0004),
confirming it is purely a function of `tasks/` containing more than one feature's history at all,
not of FEAT-018's own content.

Not fixed here: this is a `src/coherence/planning/check.py` code defect, out of scope for a
planning session (which authors spec/plan/intent content, not backend code) to fix as a side
effect. The compat skill (`/coherence-plan`) explicitly warns "Fix the **plan** on any
`PLAN_TASK_PARITY`-style finding, never hand-edit a generated task" — but no plan content change
can silence a finding raised against a *different* plan's own already-merged tasks.

## Correction

Not yet corrected. Needs its own scoped change:

1. Scope `_check_tasks`'s parity check to only the tasks this decompose/check run actually
   generated or is responsible for (e.g. tasks whose `source_task` numbers correspond to
   `parse_plan_tasks(plan_text)`'s parsed task numbers for *this* plan, resolved via the existing
   `source_plan`-to-owning-task mapping), rather than every file the shared `tasks/` glob returns.
2. Add a regression test that decomposes two different, unrelated plans into the same `tasks/`
   directory and asserts that checking the second plan raises no `PLAN_TASK_PARITY` finding against
   the first plan's already-generated tasks.
3. Until fixed, `bootstrap --decompose`/`check` cannot reach a clean, `ok: true` result for any plan
   decomposed into a `tasks/` directory that already holds a prior plan's tasks — which, in this
   repo's live history, is every plan after the first.
