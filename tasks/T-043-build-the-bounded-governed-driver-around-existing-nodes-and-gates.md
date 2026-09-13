---
dod:
- SR-034 single-task DEV -> parallel-review -> fixer-until-clean orchestration using
  existing nodes and `TaskResult`.
- SR-034 project-wide fixer budget with explicit retry/defer/block human resolution.
- SR-049 in-loop canonical trace/register/obligation gate before `TaskResult.dod_met`
  can be true.
- All steps in this task complete; tests/gates pass; committed
id: T-043
satisfies:
- SR-034
- SR-049
source_plan: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md
source_task: 5
status: todo
title: Build the bounded governed driver around existing nodes and gates
---

- Create: `src/factory/orchestrator/execution_driver.py`
- Create: `tests/unit/orchestrator/test_execution_driver.py`
- Modify: `src/factory/orchestrator/nodes.py`
- Modify: `src/factory/orchestrator/runner.py`
- Modify: `src/factory/orchestrator/execution.py`
- Modify: `src/factory/config.py`
- Modify: `.factory/factory.yaml` after the human selects the budget value

Full steps: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md, Task 5.