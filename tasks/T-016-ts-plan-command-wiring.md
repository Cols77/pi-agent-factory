---
dod:
- '`/plan <topic>` command.'
- All steps in this task complete; tests/gates pass; committed
id: T-016
source_plan: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md
source_task: 13
status: done
title: TS -- `/plan` command wiring
---

- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/test/handler.test.ts`
- Modify: `pi-ext/factory-watch/package.json` (move `@earendil-works/pi-coding-agent` usage from types-only to a real runtime import -- no version/dependency-list change needed, it's already installed)

Full steps: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md, Task 13.