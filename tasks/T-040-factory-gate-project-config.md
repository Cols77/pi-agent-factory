---
dod:
- pytest markers `agent`, `sim`; gate pipeline `lint → typecheck → unit → agent`
- All steps in this task complete; tests/gates pass; committed
id: T-040
source_plan: docs/superpowers/plans/2026-07-21-mission-agent-navigation.md
source_task: 12
status: done
title: Factory Gate & Project Config
---

- Modify: `pyproject.toml` — add `agent` and `sim` pytest markers, add LLM dependencies
- Modify: `scripts/gates/_proc.py` — add `AGENT_CMD`
- Modify: `scripts/gates/all.py` — add agent gate after unit

Full steps: docs/superpowers/plans/2026-07-21-mission-agent-navigation.md, Task 12.