---
dod:
- '`load_skill_block(skills_dir: Path, name: str) -> str`, raising `FileNotFoundError`
  if the skill isn''t vendored. Also `write_skill_stubs(root: Path) -> None`, a test-only
  helper reused by later tasks.'
- All steps in this task complete; tests/gates pass; committed
id: T-001
source_plan: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md
source_task: 1
status: done
title: '`load_skill_block` -- pure hard skill loading (Python)'
---

- Create: `src/factory/orchestrator/skills.py`
- Create: `tests/unit/orchestrator/_skill_fixtures.py`
- Test: `tests/unit/orchestrator/test_skills.py`

Full steps: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md, Task 1.