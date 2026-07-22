---
dod:
- '`parse_plan_tasks` now ignores `### Task N:` inside fenced code blocks. Signature
  and return type unchanged.'
- All steps in this task complete; tests/gates pass; committed
id: T-020
source_plan: docs/superpowers/plans/2026-07-21-deterministic-task-export.md
source_task: 1
status: todo
title: Strip fenced code blocks in `plan_to_tasks.py`
---

- Modify: `src/factory/orchestrator/plan_to_tasks.py`
- Test: `tests/unit/test_plan_to_tasks.py`

Full steps: docs/superpowers/plans/2026-07-21-deterministic-task-export.md, Task 1.