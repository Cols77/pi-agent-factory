# AGENTS.md

This file is partly managed by the pi-agent-factory bootstrap.

<!-- pi-agent-factory:bootstrap:start schema=1 -->
# Project (factory bootstrap)
pi-agent-factory

Key components & boundaries: factory orchestrator; evidence model; traceability CLI; requirements doctor; requirement register; system navigator; polish workflow; sim/validation harnesses; pi extension (commands + tools).

Canonical documents: specs docs/superpowers/specs; plans docs/superpowers/plans.

Common commands: factory gate: {python} -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py | factory gate: {python} -m pytest -m sim -q | factory gate: {python} -m pytest tests/integration/ -q -m integration | factory gate: {python} -m ruff check . | unit: uv run python -m pytest -m unit -q | integration: uv run python -m pytest -m integration -q | lint: uv run ruff check . | typecheck: uv run pyright | extension test: npm test --prefix pi-ext/factory-watch.

Rule: The gate vocabulary is fixed: unit, sim, integration, full.

Rule: Python is 3.11-3.12, ruff line-length 100, pyright standard mode.

Rule: The deterministic factory pipeline is documented in engineering-context plans.

Deeper project knowledge lives in project-profile.json; run /factory-init --check for status.

Factory commands: /factory, /factory-run, /factory-init, /trace-fix, /system.
<!-- pi-agent-factory:bootstrap:end -->
