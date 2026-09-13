---
dod:
- SR-034 AC-10 Hermes host exposure -- a read-only Hermes plugin invoking the same
  Python-owned execution command surface as the Codex skill and Claude Code command.
- SR-034 one shared host contract extended to four surfaces (direct CLI, Pi, Codex,
  Claude Code, Hermes) all consuming the same ExecutionProjection/handoff JSON.
- All steps in this task complete; tests/gates pass; committed
id: T-047
satisfies:
- SR-034
source_plan: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md
source_task: 9
status: todo
title: Add a Hermes-side governed-execution skill
---

- Create: `.hermes/plugins/governed-execution/plugin.yaml`
- Create: `.hermes/plugins/governed-execution/plugin.py`
- Create: `.hermes/plugins/governed-execution/__init__.py`
- Create: `.hermes/plugins/governed-execution/README.md`
- Create: `tests/unit/hermes/test_governed_execution_plugin.py`
- Modify: `tests/unit/codex/test_governed_execution_surface.py`

Full steps: docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md, Task 9.

Depends on Task 6 (T-044) being landed and committed first.
