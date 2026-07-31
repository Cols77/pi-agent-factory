---
dod:
- '`run(plan_path: Path, repo_root: Path) -> list[str]`; `NoTasksFoundError`; CLI
  entry `main()`, invoked as `uv run python -m factory.orchestrator.plan_to_tasks
  <plan-file> [--repo .]`.'
- All steps in this task complete; tests/gates pass; committed
id: T-011
source_plan: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md
source_task: 8
status: done
title: '`plan_to_tasks` -- CLI wrapper (id assignment, idempotency, file writing)'
---

- Modify: `src/factory/orchestrator/plan_to_tasks.py`
- Modify: `tests/unit/test_plan_to_tasks.py`

Full steps: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md, Task 8.