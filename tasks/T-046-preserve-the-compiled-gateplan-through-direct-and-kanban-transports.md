---
dod:
- SR-034 host-neutral transport projection of one already-compiled workflow-specific
  `GatePlan`.
- SR-049 card/event metadata carrying the run id, contract hash, GatePlan hash/version,
  workflow version, stage id, and attempt.
- All steps in this task complete; tests/gates pass; committed
id: T-046
satisfies:
- SR-034
- SR-049
source_plan: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md
source_task: 8
status: todo
title: Preserve the compiled GatePlan through direct and Kanban transports
---

- Create: `src/factory/orchestrator/execution_transport.py`
- Create: `tests/unit/orchestrator/test_execution_transport.py`
- Modify: `src/factory/orchestrator/execution_contract.py`
- Modify: `tests/unit/orchestrator/test_execution_contract.py`
- Modify: `src/factory/orchestrator/execution_driver.py`
- Modify: `tests/unit/orchestrator/test_execution_driver.py`

Full steps: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md, Task 8.