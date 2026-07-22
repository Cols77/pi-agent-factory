---
dod:
- '`run_next(..., task_id: str | None = None) -> Path | None`.'
- All steps in this task complete; tests/gates pass; committed
id: T-005
source_plan: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md
source_task: 5
status: done
title: '`run_next(task_id=...)` -- target one specific task'
---

- Modify: `src/factory/orchestrator/runner.py`
- Test: `tests/unit/orchestrator/test_run_next.py`

Full steps: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md, Task 5.