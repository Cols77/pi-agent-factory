---
dod:
- task-level `satisfies`/`source_plan` links, FEAT-017 membership, and a test proving
  the produced planning artifacts are named in the trace contract.
- Implement the task's stated behavior and keep all focused gates green; do not push or merge
id: T-037
satisfies:
- SR-054
source_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
source_task: 6
status: done
title: Register FEAT-17 trace links and prove the feature against the live register
---

## Closure note

*2026-09-07.* T-037 points at SR-054; FEAT-017 owns the correct eight SRs in
`bundles/FEAT-017.json` and `requirements/index.json`; and
`tests/unit/coherence/test_planning_trace_contract.py` passes. This records T-037's
trace/bookkeeping evidence only, not SR consent, adoption, merge, release, or broader
FEAT-017 completion.

- Modify: `requirements/SR-043.md`
- Modify: `requirements/SR-044.md`
- Modify: `requirements/SR-051.md`
- Modify: `requirements/SR-052.md`
- Modify: `requirements/SR-053.md`
- Modify: `requirements/SR-054.md`
- Read-only dependency: `requirements/SR-050.md`
- Modify: `bundles/FEAT-017.json`
- Modify: `docs/features/FEAT-017.md`
- Test: `tests/unit/coherence/test_planning_trace_contract.py`

Full steps: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md, Task 6.
