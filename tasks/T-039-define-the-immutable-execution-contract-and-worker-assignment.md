---
dod:
- SR-034 backend-neutral contract for one selected task, one workflow version, one
  workspace, and the configured fixer budget.
- SR-049 traceable contract hash that can be included in existing `NodeEvent.extra`
  and run evidence.
- All steps in this task complete; tests/gates pass; committed
id: T-039
satisfies:
- SR-034
- SR-049
source_plan: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md
source_task: 1
status: todo
title: Define the immutable execution contract and worker assignment
---

- Create: `src/factory/orchestrator/execution_contract.py`
- Create: `tests/unit/orchestrator/test_execution_contract.py`

Full steps: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md, Task 1.