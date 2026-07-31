---
dod:
- '`compose_prompt(..., *, skills_dir: Path) -> str` (new required kwarg); `run_dev`/`run_review`
  gain a `repo_root: Path` parameter (matching `run_context_gatherer`''s existing
  one).'
- All steps in this task complete; tests/gates pass; committed
id: T-002
source_plan: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md
source_task: 2
status: done
title: Wire hard skill loading into every sub-agent role's prompt
---

- Modify: `src/factory/orchestrator/prompts.py`
- Modify: `src/factory/orchestrator/nodes.py`
- Modify: `src/factory/orchestrator/runner.py`
- Modify: `tests/unit/orchestrator/test_prompts.py`
- Modify: `tests/unit/orchestrator/test_nodes_context_dev.py`
- Modify: `tests/unit/orchestrator/test_nodes_val_review.py`
- Modify: `tests/unit/orchestrator/test_run_next.py`
- Modify: `tests/unit/orchestrator/test_runner_e2e.py`

Full steps: docs/superpowers/plans/2026-07-20-factory-plan-and-run.md, Task 2.