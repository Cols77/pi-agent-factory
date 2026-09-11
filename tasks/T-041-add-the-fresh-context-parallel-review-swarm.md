---
dod:
- SR-034 independent spec-compliance and code-quality review invocations using the
  existing `AgentRole.REVIEW`.
- SR-049 review session ids and findings as ordinary `NodeEvent` evidence inputs.
- All steps in this task complete; tests/gates pass; committed
id: T-041
source_plan: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md
source_task: 3
status: todo
title: Add the fresh-context parallel review swarm
---

- Create: `src/factory/orchestrator/review_swarm.py`
- Create: `tests/unit/orchestrator/test_execution_review_swarm.py`

Full steps: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md, Task 3.