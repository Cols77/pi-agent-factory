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

Factory tools: delegation (subagent); trace (trace_next, trace_link, trace_exempt, trace_defer, trace_check); system-navigator (system_context, implementation_history, validation_status, evidence_health, system_scopes, system_briefing, system_matrix, system_timeline, system_guide, system_story, system_reverse); engineering-context (eng_get_vcycle, eng_get_diagram, eng_trace_requirement, eng_get_latest_simulation, eng_get_latest_failure, eng_get_goal, eng_get_goals, eng_get_goal_evidence, eng_get_metric_history, eng_get_simulation_run, eng_evaluate_goal, eng_present); session-review (factory_run_suggest)

Deeper project knowledge lives in project-profile.json; run /factory-init --check for status.

Factory commands: /factory, /factory-run, /factory-init, /trace-fix, /system.
<!-- pi-agent-factory:bootstrap:end -->
