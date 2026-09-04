---
dod:
- verified CLI help/output, test/lint/type reports, and a reviewer-confirmed statement
  of deferred human browsing/visualization.
- Implement the task's stated behavior and keep all focused gates green; do not push or merge
id: T-038
satisfies:
- SR-052
source_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
source_task: 7
status: todo
title: Holistic integration review and available-gate deployment
---

- No production file changes expected unless review findings require a scoped fix.
- Reports: `.factory/planning/<run-id>/report.json` is derived evidence and must remain ignored/disposable if the project’s ignore policy requires it.

Full steps: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md, Task 7.