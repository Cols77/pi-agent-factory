---
dod:
- an argv-only `/plan-gate` host adapter that invokes `uv run coherence plan bootstrap --decompose ... --json` with validated root-relative paths and a safe run id;
- the seed prompt tells the authoring session to use `/plan-gate`, preserve the human-review/consent seam, and never execute downstream work;
- Implement the task's stated behavior and keep all focused gates green; do not push or merge
id: T-035
satisfies:
- SR-053
source_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
source_task: 4
status: todo
title: Wire the existing `/plan` authoring host to the backend gate
---

- Modify: `pi-ext/factory-watch/src/skill-prompt.ts`
- Modify: `pi-ext/factory-watch/src/index.ts`
- Test: `pi-ext/factory-watch/test/skill-prompt.test.ts` (or the existing test file that covers plan seed prompts)

Full steps: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md, Task 4.