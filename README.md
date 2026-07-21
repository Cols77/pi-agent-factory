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
uv run python scripts/gates/all.py             # lint + types + unit
uv run python scripts/gates/validate_manifest.py <manifest.json>
uv run python scripts/gates/validate_session.py <session.json>
uv run python scripts/gates/validate_kb.py <kb/kb-XXXX-*.md>
```

Consuming projects run their own `kb/`, `tasks/`, `sessions/`, and
`context-manifests/` stores locally; this repo only ships the orchestrator,
schemas, and validators that operate on them.

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
