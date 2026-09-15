---
id: NC-0007
title: PLAN_TASK_PARITY flags orphaned tasks (no source_plan at all) during any unrelated plan's check
external_ref: null
detected_by: FEAT-018 check re-verification, after the NC-0005 fix landed
status: open
---

## Symptom

After NC-0005's fix landed (`src/coherence/planning/check.py`'s `_check_tasks`, ~line 317: `if
isinstance(source_plan, str) and source_plan.strip() and source_plan != expected_plan: continue`
— correctly skips a task that names a *different* real plan), `guided_pipeline check` for
FEAT-018 still reported 3 `PLAN_TASK_PARITY` findings, all reading `"generated task source_plan
does not match the selected plan"`, for `tasks/T-029-*.md`, `tasks/T-031-*.md`, and
`tasks/T-058-*.md` — none of which are part of FEAT-018's plan, and none of which name any other
plan either: all three have **no `source_plan` field at all** (by design; they are standalone
tasks executed directly from their own brief, matching this repo's established `T-029` precedent
— see that task's own `trace_exempt_reason`).

Root cause: the skip condition added for NC-0005 only fires when `source_plan` is a non-empty
string naming a different plan (`isinstance(source_plan, str) and source_plan.strip() and
source_plan != expected_plan`). When `source_plan` is missing/`None`/empty, that condition is
`False`, so execution falls through to `matched_paths.append(task_path)` (line ~322) and then the
unconditional `if source_plan != expected_plan:` check (line ~338, `None != "docs/superpowers/
plans/<expected>.md"` is always `True`) appends the same `PLAN_TASK_PARITY` finding — treating an
orphaned, no-plan task exactly like a task that claims to belong to *this* plan but doesn't. The
error message ("does not match the selected plan") is also actively misleading for this case:
there is no plan to mismatch against.

This is the same class of defect as NC-0005 — `_check_tasks` still considers a task outside the
plan under review to be this check's business — just for the complementary case (no plan at all,
rather than a different plan).

Reproduced on FEAT-018's own `guided_pipeline check` run: after the NC-0004/NC-0005 fix (commit
`82784a2` on `main`), `PLANNING_REFERENCE_INVALID` findings dropped from 10 to 0 and
`PLAN_TASK_PARITY` findings dropped from 40 to exactly 3 — all 3 being this distinct, unfixed
case.

## Correction

Not yet corrected. Needs its own scoped change, same TDD discipline as NC-0004/NC-0005:

1. Extend `_check_tasks`'s skip condition to also skip a task whose `source_plan` is missing,
   `None`, or empty/whitespace-only — such a task declares no relationship to *any* plan, so it is
   equally "not this check's business" as a task that names a different plan. It should not be
   silently added to `matched_paths`/counted toward parity for the plan actually under review.
2. Do not weaken the reverse case: a task the plan under review's own declared task numbers expect
   but that has no generated file at all must still be caught (unchanged from NC-0005's fix).
3. Add a regression test: a standalone, no-`source_plan` task (mirroring `T-029`'s real shape)
   coexisting in `tasks/` with a real plan's tasks; checking that plan raises no `PLAN_TASK_PARITY`
   finding against the orphaned task, while a genuine parity problem in the plan's own tasks is
   still caught.
4. Whether an orphaned (no-`source_plan`) task should be surfaced by *some* separate, explicitly-
   named check (project-wide task hygiene, not folded into an unrelated plan's parity gate) is a
   design question for whoever picks this up — out of scope for this correction to decide
   unilaterally.
