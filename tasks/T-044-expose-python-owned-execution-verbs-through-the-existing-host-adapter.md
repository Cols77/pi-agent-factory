---
dod:
- SR-034 `dispatch_task`, `report_worker_result`, and `stream_progress` verbs through
  the existing FEAT-9/Pi host registration seam.
- SR-034 human-only flaky registration command; the driver has no registry write capability.
- SR-049 JSON event/evidence forwarding without host-side gate or trace interpretation.
- All steps in this task complete; tests/gates pass; committed
id: T-044
satisfies:
- SR-034
- SR-049
source_plan: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md
source_task: 6
status: todo
title: Expose Python-owned execution verbs through the existing host adapter
---

- Create: `src/coherence/execution/cli.py`
- Create: `tests/unit/coherence/test_execution_cli.py`
- Modify: `src/coherence/cli.py`
- Create: `pi-ext/factory-watch/src/execution-tools.ts`
- Create: `pi-ext/factory-watch/test/execution-tools.test.ts`
- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/src/tool-catalog.ts`

Full steps: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md, Task 6.