---
dod:
- SR-034 host seam for free/Hermes/Pi backends without a second scheduler or allocator.
- SR-049 workspace identity in worker and checkpoint evidence.
- All steps in this task complete; tests/gates pass; committed
id: T-040
source_plan: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md
source_task: 2
status: todo
title: Bind every worker to one injected execution workspace
---

- Create: `src/factory/orchestrator/execution_workspace.py`
- Create: `tests/unit/orchestrator/test_execution_workspace.py`
- Modify: `src/factory/orchestrator/pi_backend.py`
- Modify: `tests/unit/orchestrator/test_pi_backend.py`

Full steps: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md, Task 2.