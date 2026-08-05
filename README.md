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
