# pi-agent-factory

Deterministic substrate for an agent dev factory (see
`docs/superpowers/specs/2026-07-16-deterministic-agent-dev-factory-design.md`),
plus the Pi coding-agent extensions (`pi-ext/`) that integrate it into an
interactive `pi` session.

This was originally developed inside a single drone/physical-AI project
repo and split out here since none of it is domain-specific -- any project
can install and use it standalone.

## Setup
```
uv sync
sh scripts/install-pif.sh   # installs a global `pif` command pointed at this repo
```

## Gates (exit-code only)
```
# gate commands are declared in .factory/factory.yaml; run them directly:
uv run ruff check . && uv run pyright && uv run pytest -m unit -q && uv run pytest -m agent -q
uv run python scripts/gates/validate_manifest.py <manifest.json>
uv run python scripts/gates/validate_session.py <session.json>
uv run python scripts/gates/validate_kb.py <kb/kb-XXXX-*.md>
```

### Declaring a project's gates

Each project names its own gate commands in `.factory/factory.yaml`, run by
`ConfigGateRunner`:

```yaml
gates:
  unit:
    - { cmd: "uv run pytest -m unit -q" }
  full:
    - { cmd: "uv run ruff check ." }
    - { cmd: "uv run pyright" }
    - { cmd: "uv run pytest -m unit -q" }
```

- Gate names are a fixed vocabulary — `unit`, `sim`, `integration`, `full`.
  Projects don't invent new names; a gate that isn't one of these is never run.
- `cmd` is a shell command; `cwd` is optional and relative to the repo root.
- Steps run in order and stop at the first non-zero exit, except exit code
  `5` (pytest's "no tests collected"), which is treated as a pass.
- A gate name that isn't declared passes automatically and is recorded as
  skipped, rather than failing or being silently invented.
- A project that declares no `gates:` section at all is a hard error — some
  gates being skipped is fine, no gates ever running is not.
- **`{python}` expands to the interpreter running the factory itself**, not
  the target project's. It's correct only for gates on this repo — write it
  bare (`{python} -m pytest -q`, not `"{python}" -m pytest -q`; the runner
  quotes the expansion itself). A project with its own environment must name
  its interpreter explicitly instead, e.g. `.venv/Scripts/python -m pytest -q`
  or `uv run pytest -q`. A bare `python` is not a safe substitute either — the
  gate subprocess inherits the factory's `VIRTUAL_ENV`/`PATH` and can resolve
  back to the factory's own interpreter depending on how `factory-run` was
  launched.

Consuming projects run their own `kb/`, `tasks/`, `sessions/`, and
`context-manifests/` stores locally; this repo only ships the orchestrator,
schemas, and validators that operate on them.

## System navigator

`factory.system` answers "what is actually true about this feature/
requirement, and where is the evidence" from what is already recorded in the
repo -- it never guesses and never invokes a model. Every fact it prints is
labeled with where it came from (recorded/derived/synthesized/missing) and
whether it is still current (fresh/stale/degraded/n/a).

```
uv run python -m factory.system brief    --scope <ref> --json
uv run python -m factory.system matrix   --scope <ref> --json
uv run python -m factory.system timeline --scope <ref> --json
uv run python -m factory.system guide    --scope <ref> --json [--export <path>]
uv run python -m factory.system scope    --json
```

- `brief` -- one-page summary for the scope: what's declared, what resolved,
  what's missing.
- `matrix` -- one row per SR, with its recorded validation outcome
  (`passed|failed|error|blocked|never-run|unknown`) and freshness.
- `timeline` -- chronological decisions (signed reviews) for the scope.
- `guide` -- grounded prose assembled deterministically from the above (no
  LLM call); `--export <path>` writes a point-in-time snapshot to disk
  (never inside `evidence/`, `bundles/`, or `requirements/` -- an export can
  never be cited back in as evidence).
- `scope` -- lists every scope the navigator can open, plus any bundle files
  that failed to load and why.

Drop `--json` for a human-readable rendering instead. Add `--repo-root <path>`
to target a repo other than the current directory.

**Openable scopes** are exact refs, never fuzzy: `bundle:<id>` (a declared
feature-scope bundle, see below) or `sr:<id>` (a requirement from
`requirements/`, the same register `factory.requirements` uses).

### Authoring a bundle

A bundle is a feature scope you declare by hand: a label plus a flat list of
member refs, nothing else -- no status, no claims, no rationale (those are
all *derived* by the navigator from the real artifacts the refs point at).
Bundle files live in `bundles/<id>.json` at the repo root and are validated
against `src/factory/schemas/system_bundle.schema.json`.

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

- **The filename must equal `id`.** `bundles/evidence-lifecycle.json` must
  declare `"id": "evidence-lifecycle"` -- this is what lets `bundle:<id>`
  resolve exactly rather than by filesystem happenstance. A mismatch loads
  as a visible error (`python -m factory.system scope` reports it), not a
  silent failure or a fuzzy fallback.
- Members may be `spec:<path>`, `plan:<path>`, `task:<id>`, or `sr:<id>`
  only. A member ref that doesn't parse, or names something that doesn't
  exist in the repo, is reported `missing` and degrades the bundle -- it is
  never dropped silently.
- An absent `bundles/` directory is a legitimate state (no bundle scopes,
  not an error).

## Polish workflow

`factory polish` lets a human exercise a project use case and turn feedback into
fix-tickets. A project declares its playgrounds (and validation harnesses)
declaratively in `.factory/factory.yaml` — each entry names a built-in factory
type (`dev-server`, `scenario-replay`, …) plus params. No project code is
executed. Drive it conversationally with the `polish` skill, or directly:

- `python -m factory.polish list` — list `<playground>:<usecase>` options
- `python -m factory.polish run --playground <name> --usecase <uc> --from-json <findings.json>`
  — route findings to `T-###` tasks

## Layout
- `src/factory/` — orchestrator, schemas, validators, deterministic KB retrieval
- `pi-ext/factory-watch/` — Pi extension: `/factory`, `/factory-run`,
  `/factory-tasks`, `/plan`, `/review-plans` commands, plus the write-chunk
  guard mitigating large single `write` tool calls
- `pi-ext/scope-guard/` — Pi extension enforcing task scope
- `.pi/skills/` — vendored skill content so `ROLE_SKILLS` resolve for the
  factory's sub-agents
- `scripts/install-pif.sh` — installs the global `pif` shim (`pi` with
  `factory-watch` loaded, always rooted at this repo)
