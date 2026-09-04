---
dod:
- task-level `satisfies`/`source_plan` links, FEAT-017 membership, and a test proving
  the produced planning artifacts are named in the trace contract.
- Implement the task's stated behavior and keep all focused gates green; do not push or merge
id: T-037
satisfies:
- SR-050
source_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
source_task: 6
status: todo
title: Register FEAT-17 trace links and prove the feature against the live register
---

- Modify: `requirements/SR-043.md`
- Modify: `requirements/SR-044.md`
- Modify: `requirements/SR-050.md`
- Modify: `requirements/SR-051.md`
- Modify: `requirements/SR-052.md`
- Modify: `requirements/SR-053.md`
- Modify: `requirements/SR-054.md`
- Modify: `bundles/FEAT-017.json`
- Modify: `docs/features/FEAT-017.md`
- Create: `tasks/T-<allocated>-feat17-planning-workflow.md`
- Test: `tests/unit/coherence/test_planning_trace_contract.py`

Full steps: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md, Task 6.