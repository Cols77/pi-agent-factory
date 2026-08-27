---
dod:
- '`write_planning_run(root, report) -> Path`, `build_downstream_suggestion(report)
  -> dict[str, object] | None`, and a strict review-decision reader for `.factory/planning/<run_id>/review-decision.json`.'
- Implement the task's stated behavior and keep all focused gates green; do not push or merge
id: T-033
satisfies:
- SR-054
- SR-053
source_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
source_task: 2
status: todo
title: Add planning run evidence, review seam, and downstream suggestion
---

- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/check.py`
- Create: `src/coherence/planning/run.py`
- Test: `tests/unit/coherence/test_planning_run.py`

Full steps: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md, Task 2.