---
dod:
- '`get_task(tasks: list[Task], task_id: str) -> Task | None`; `TaskNotFoundError(RuntimeError)`;
  `TaskNotTodoError(RuntimeError)`.'
- All steps in this task complete; tests/gates pass; committed
id: T-004
source_plan: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md
source_task: 4
status: done
title: '`ledger.py` -- `get_task`, `TaskNotFoundError`, `TaskNotTodoError`'
---

- Modify: `src/factory/orchestrator/ledger.py`
- Test: `tests/unit/orchestrator/test_ledger.py`

Full steps: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md, Task 4.