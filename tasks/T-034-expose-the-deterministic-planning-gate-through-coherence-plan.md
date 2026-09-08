---
dod:
- '`coherence plan check --intent <path> --spec <path> --plan <path> --run-id <id>
  [--project-root <dir>] [--json]`, plus `coherence plan suggest --run-id <id> --project-root
  <dir> [--json]`.'
- Implement the task's stated behavior and keep all focused gates green; do not push or merge
id: T-034
satisfies:
- SR-051
source_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
source_task: 3
status: done
title: Expose the deterministic planning gate through `coherence plan`
---

## Closure note

Verified done on 2026-09-07: `coherence plan check` and `coherence plan suggest`
are both registered in `src/coherence/planning/cli.py` and wired from
`src/coherence/cli.py`'s `"plan"` group entry. No further implementation
required; remaining FEAT-017 work is per-SR human consent, tracked
separately from this task.

- Modify: `src/coherence/cli.py`
- Create: `src/coherence/planning/cli.py`
- Test: `tests/unit/coherence/test_planning_cli.py`

Full steps: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md, Task 3.