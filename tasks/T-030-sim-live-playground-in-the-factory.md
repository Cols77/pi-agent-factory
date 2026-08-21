---
dod:
- 'SimLivePlayground is a Playground (list_usecases/setup contract) that
  spawns the configured run command with the scenario path appended and a
  teardown that kills the child process tree.'
- 'PLAYGROUND_TYPES["sim-live"] registers SimLivePlayground.from_config;
  load_config builds the playground from a scenarios_dir/run_command block.'
- 'routing test pins that a bug snapshot artifact path survives into the
  routed task body (## Artifacts section).'
- 'polish unit gate green; committed'
id: T-030
satisfies: []
source_plan: docs/superpowers/plans/2026-08-20-sim-polish-playground.md
source_task: 1
status: done
title: 'sim-live Playground in the factory'
---

- Create: `src/factory/polish/sim_live.py`
- Modify: `src/factory/polish/config.py`
- Create: `tests/unit/polish/test_sim_live.py`
- Modify: `tests/unit/polish/test_routing.py`

Full steps: docs/superpowers/plans/2026-08-20-sim-polish-playground.md, Task 1.

Exemption note: config-driven desktop playground (view/session tooling) with no
behavioral simulation claim; no requirement genuinely measures it (same
disposition as the scenario-replay playground).