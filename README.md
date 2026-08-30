# pi-agent-factory

`pi-agent-factory` is a deterministic, filesystem-first agent development system. It
can be used standalone by any project and also ships Pi coding-agent extensions
under `pi-ext/`.

The repository is organized around three layers:

- **`factory`** is the execution engine: it owns orchestration, worker dispatch,
  configured gates, run state, evidence production, and the polish workflow.
- **`coherence`** is the canonical assurance and navigation CLI: it reads and
  derives truthful status from recorded project artifacts, requirements,
  traceability, audits, measurements, and freshness data.
- **`substrate`** contains shared primitives: paths, schemas, ledgers, evidence
  read models, freshness, codemap, knowledge-base, and policy models. It is the
  common foundation rather than another execution surface.

Pi integrations are thin host adapters over those Python-owned contracts. They
render or dispatch the canonical data; they do not reimplement assurance or
execution rules.

## Setup

```text
uv sync
sh scripts/install-pif.sh   # installs a global `pif` command pointed at this repo
```

## Gates (exit-code only)

Gate commands are declared in `.factory/factory.yaml` and run by the factory's
`ConfigGateRunner`. The supported project-wide gate protocol has a fixed
vocabulary: **`unit`, `sim`, `integration`, and `full`**. This repository's own
`.factory/factory.yaml` declares only **`unit`, `integration`, and `full`**; it
intentionally has no local `sim` or `agent` declaration.

The factory's own configuration is representative:

```yaml
gates:
  unit:
    - { cmd: "{python} -m pytest -m unit -q" }
  integration:
    - { cmd: "{python} -m pytest tests/integration/ -q -m integration" }
  full:
    - { cmd: "{python} -m ruff check ." }
    - { cmd: "{python} -m pyright" }
    - { cmd: "{python} -m pytest -m unit -q" }
    - { cmd: "{python} scripts/gates/ext.py" }
    - { cmd: "{python} scripts/gates/watch_ext.py" }
```

The full gate requires the extension checks directly through
`scripts/gates/ext.py` and `scripts/gates/watch_ext.py`; those checks are not a
separate gate name. The assurance command compiler also appends the structural
checks `coherence trace check` and `coherence register check` when compiling the
project's required CI commands.

Gate behavior:

- Steps run in declaration order and stop at the first non-zero exit. Pytest
  exit code `5` (no tests collected) is treated as a pass.
- An undeclared gate is recorded as skipped rather than invented. A project with
  no `gates:` section is a configuration error.
- `{python}` resolves to the target repository's `.venv` interpreter when one
  is present, with the factory interpreter as the fallback. The runner quotes
  the resolved path for the host shell, so gate declarations should use the
  literal `{python}` token.

## Canonical Coherence CLI

Use the `coherence` entry point for assurance and navigation. Query and check
commands are read-only and never guess or invoke a model to fill missing
evidence. Outputs retain provenance such as
`recorded`, `derived`, `synthesized`, or `missing`, together with freshness such
as `fresh`, `stale`, or `degraded`.

The status snapshot is the canonical machine-readable starting point:

```text
uv run coherence status --json
```

Navigation views use exact scope references and support JSON or human-readable
output:

```text
uv run coherence navigate brief    --scope <ref> --json
uv run coherence navigate matrix   --scope <ref> --json
uv run coherence navigate timeline --scope <ref> --json
uv run coherence navigate guide    --scope <ref> --json [--export <path>]
uv run coherence navigate scope    --json
uv run coherence navigate health   --json
uv run coherence navigate membership --gate --json
```

Use `coherence navigate memberships <ref> --json` when the question is which
bundles contain one particular reference. Add `--repo-root <path>` to any
navigation command to inspect a repository other than the current directory.
The navigator's scope refs are exact, never fuzzy; common refs include
`bundle:<id>`, `sr:<id>`, `task:<id>`, `feat:<id>`, `file:<path>`, and
`goal:<id>`.

- `brief` summarizes what is declared, resolved, and missing for a scope.
- `matrix` reports one row per requirement with its recorded validation outcome
  and freshness.
- `timeline` reports chronological recorded decisions for the scope.
- `guide` assembles deterministic, grounded prose. An exported guide is a
  point-in-time view, not evidence, and must not be cited back as evidence.
- `scope` lists discoverable scopes and reports bundle files that failed to
  load instead of hiding them.
- `health` composes traceability, requirement, bundle, and freshness signals.
- `membership --gate` checks that artifacts are assigned to a declared bundle.

Other assurance groups retain their own focused verbs:

```text
uv run coherence trace check --project-root .
uv run coherence register check --project-root .
uv run coherence doctor context --project-root . --json
uv run coherence audit run <feature> --project-root .
uv run coherence measurement run --project-root . --satisfies SR-###
```

The query/check forms (`status`, `navigate` without `--export`, `trace check`,
`register check`, and `doctor context`) do not write project state. The
state-changing `coherence audit run` creates
`coverage-reviews/<feature>-<run_id>/status.json` and `audit.json`; a completed
run also writes `report.json` and per-SR files under `verdicts/`. The
state-changing `coherence measurement run` writes
`validation/validation-report.json`. `navigate guide --export <path>` is an
explicit point-in-time export and writes the requested snapshot path.

### Authoring a bundle

A bundle is an authored feature-scope declaration: a label and a flat list of
exact member refs. Status, claims, and rationale are derived by the navigator
from the artifacts named by those refs. Bundle files live in
`bundles/<id>.json` and are validated against
`src/substrate/schemas/system_bundle.schema.json`.

```json
{
  "id": "evidence-lifecycle",
  "label": "Evidence lifecycle",
  "members": [
    "spec:docs/superpowers/specs/2026-08-08-evidence-lifecycle-design.md",
    "plan:docs/superpowers/plans/2026-08-08-evidence-lifecycle.md",
    "task:T-045",
    "sr:SR-012"
  ]
}
```

- The filename stem must equal `id`: the file above is
  `bundles/evidence-lifecycle.json`. A mismatch is reported as an explicit
  load error, not resolved by filesystem coincidence.
- A member that does not parse or does not exist is reported as `missing` and
  degrades the bundle; it is never silently dropped.
- An absent `bundles/` directory is legitimate: it means there are no declared
  bundle scopes.

## Execution, evidence, and polish

The factory executes the configured project pipeline; Coherence inspects the
resulting assurance records. The orchestrator is available directly for task
listing and a targeted run:

```text
uv run python -m factory.orchestrator list --repo . --json
uv run python -m factory.orchestrator run --repo . --task T-###
```

Run manifests and task-scoped records live under the consuming project's
`evidence/` store. Inspect or reconcile them with the execution-side evidence
commands:

```text
uv run python -m factory.evidence list --repo . --json
uv run python -m factory.evidence task T-### --repo . --json
uv run python -m factory.evidence reconcile --repo . --json
```

Evidence is recorded with its source and outcome. Reconciliation surfaces
missing or inconsistent records; it does not turn a task claim into proof.

`factory.polish` lets a human exercise a configured project use case and route
structured findings into fix tickets. Playgrounds and validation harnesses are
declared in `.factory/factory.yaml`:

```text
uv run python -m factory.polish list
uv run python -m factory.polish run \
  --playground <name> --usecase <use-case> --from-json <findings.json>
```

The polish bridge writes task records; execution and validation still go
through the factory pipeline and its configured gates.

## Compatibility window

The old `factory.*` module paths remain available as transitional,
deprecation-warning compatibility shims. Use `coherence.*` for assurance and
navigation and `substrate.*` for shared primitives in all new code and
examples. The shims remain only until downstream projects and Pi extensions
have migrated; removing them is a separate, announced change.

## Layout

- `src/factory/` — execution engine: orchestrator, gate runner, evidence,
  polish, schemas, validators, and deterministic retrieval
- `src/coherence/` — canonical assurance/navigation CLI groups and projections
- `src/substrate/` — shared paths, schemas, ledgers, evidence/freshness models,
  codemap, policy, and agent primitives
- `pi-ext/factory-watch/` — Pi extension exposing `/factory`, `/factory-run`,
  `/factory-tasks`, `/plan`, `/review-plans`, and read-only navigator tools
- `pi-ext/scope-guard/` — Pi extension enforcing task write scope
- `.pi/skills/` — vendored skill content used by factory sub-agents
- `scripts/install-pif.sh` — installs the global `pif` shim with
  `factory-watch` loaded and rooted at this repository

Consuming projects keep their own `kb/`, `tasks/`, `sessions/`,
`context-manifests/`, `requirements/`, `bundles/`, and `evidence/` stores. This
repository supplies the engine, assurance tools, shared primitives, schemas,
and extensions that operate on those stores.
