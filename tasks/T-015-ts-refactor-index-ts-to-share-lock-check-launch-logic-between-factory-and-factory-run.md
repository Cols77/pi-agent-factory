---
dod:
- internal `isAlreadyRunning(ctx, lockPath)` and `launchAndWatch(ctx, cmd, label)`
  helpers, extracted from `/factory`'s existing handler with identical behavior.
- All steps in this task complete; tests/gates pass; committed
id: T-015
source_plan: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md
source_task: 12
status: done
title: TS -- refactor `index.ts` to share lock-check/launch logic between `/factory`
  and `/factory-run`
---

- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/test/handler.test.ts`

Full steps: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md, Task 12.