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
status: todo
title: Expose the deterministic planning gate through `coherence plan`
---

- Modify: `src/coherence/cli.py`
- Create: `src/coherence/planning/cli.py`
- Test: `tests/unit/coherence/test_planning_cli.py`

Full steps: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md, Task 3.