---
dod:
- '`coherence plan bootstrap --project-root <dir> --intent <path> --spec <path> --plan
  <path> --run-id <id> [--decompose] [--json]`.'
- Implement the task's stated behavior and keep all focused gates green; do not push or merge
id: T-036
satisfies:
- SR-043
source_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
source_task: 5
status: todo
title: Add the bootstrap composition and available deterministic gates
---

- Create: `src/coherence/planning/bootstrap.py`
- Modify: `src/coherence/planning/cli.py`
- Test: `tests/unit/coherence/test_planning_bootstrap.py`
- Modify: `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md` only if implementation facts require an update.

Full steps: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md, Task 5.