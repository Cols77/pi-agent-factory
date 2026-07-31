---
dod:
- updated `buildPlanSeedPrompt` with deterministic-export instruction instead of soft
  "run plan_to_tasks" instruction.
- All steps in this task complete; tests/gates pass; committed
id: T-027
source_plan: docs/superpowers/plans/2026-07-21-deterministic-task-export.md
source_task: 4
status: todo
title: Update seed prompt — drop soft `plan_to_tasks` instruction
---

- Modify: `pi-ext/factory-watch/src/skill-prompt.ts`
- Test: `pi-ext/factory-watch/test/skill-prompt.test.ts`

Full steps: docs/superpowers/plans/2026-07-21-deterministic-task-export.md, Task 4.