# AGENTS.md

This file is partly managed by the pi-agent-factory bootstrap.

<!-- pi-agent-factory:bootstrap:start schema=1 -->
# Project (factory bootstrap)
pi-agent-factory

Architecture & boundaries: `factory` is the execution engine (orchestrator,
gates, run state, evidence, and polish); `coherence` is the canonical
assurance/navigation CLI; `substrate` provides shared primitives (paths,
schemas, ledgers, evidence, freshness, codemap, and policy). Pi extensions are
thin host adapters over those Python-owned contracts.

Canonical documents: specs `docs/superpowers/specs`; plans
`docs/superpowers/plans`.

Canonical CLI examples:
- status: `uv run coherence status --json`
- navigation: `uv run coherence navigate brief --scope <ref> --json`,
  `matrix`, `timeline`, `guide`, `scope`, `health`, and
  `membership --gate`
- trace/register checks: `uv run coherence trace check --project-root .` and
  `uv run coherence register check --project-root .`
- requirements context: `uv run coherence doctor context --project-root . --json`
- audit/measurement: `uv run coherence audit run <feature> --project-root .` and
  `uv run coherence measurement run --project-root . --satisfies SR-###`

Gate vocabulary is fixed: `unit`, `integration`, and `full`. Gates are declared
in `.factory/factory.yaml` and executed in order by the factory's
`ConfigGateRunner`. The `full` gate directly requires
`{python} scripts/gates/ext.py` and `{python} scripts/gates/watch_ext.py`, in
addition to lint, typecheck, and unit commands. `{python}` means the interpreter
running the factory; consuming projects should name their own environment.

Execution and evidence commands remain factory-owned:
`uv run python -m factory.orchestrator list --repo . --json`,
`uv run python -m factory.orchestrator run --repo . --task T-###`, and
`uv run python -m factory.evidence reconcile --repo . --json`.

Pi integration: `pi-ext/factory-watch` provides `/factory`, `/factory-run`,
`/factory-tasks`, `/plan`, `/review-plans`, and read-only navigator tools;
`pi-ext/scope-guard` enforces task write scope. `/factory-init --check` reports
bootstrap status. The deterministic factory pipeline is documented in the
engineering-context plans.

Compatibility: `factory.*` paths are transitional deprecation-warning shims.
Use `coherence.*` and `substrate.*` for new code and documentation; the shims
remain until downstream projects and Pi extensions migrate. This file documents
implemented surfaces only; planned interactive console, MCP, and workflow
surfaces are not assumed to be available.

Deeper project knowledge lives in `project-profile.json`; run
`/factory-init --check` for status.
<!-- pi-agent-factory:bootstrap:end -->
