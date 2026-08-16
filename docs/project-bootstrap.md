# Project Bootstrap (`/factory-init`)

The pi-agent-factory ships a deterministic project-bootstrap layer so that every
parent and subagent session starts from the **same approved knowledge** without
re-scanning the repository or asking a model to reinterpret it.

This document covers the three knowledge layers, the command surface, how to edit
generated knowledge, how subagents inherit context, and the size/staleness
trade-offs.

## 1. Why stable knowledge lives in `AGENTS.md`

Pi loads `<project-root>/AGENTS.md` natively into every session's system prompt. By
putting the compact project capsule inside a **managed block** in that file, the same
facts reach the parent agent and — because children run in the project root with
context files enabled (see §6) — every subagent, with **zero per-session discovery**.

The managed block is the *project bootstrap*: stable facts that are true about the
repository. It is deliberately small (≈500–900 tokens) and free of volatile state.

## 2. Three knowledge layers

| layer | where | what | volatility |
|---|---|---|---|
| **Project bootstrap** | `AGENTS.md` managed block | purpose, components, canonical docs, commands, rules | low; changes only when the repo does |
| **Active task state** | in-session conversation / task files | current task, current `/goal`, active requirement | high; per session, survives only in prompts |
| **Durable project memory** | `kb/`, evidence store, `docs/superpowers/{specs,plans}` | design decisions, requirements, ADRs, validation artefacts | low; long-lived, queried on demand |

Do not put active task state into the managed block — it is volatile and would churn
the prompt cache. Do not load the full spec/plan tree into every prompt; point to it
(the docs server, `/review-plans`, `/system`) instead.

## 3. Files owned by the bootstrap

- `<project-root>/AGENTS.md` — the managed block between stable markers; all other
  content is preserved byte-for-byte.
- `<project-root>/.pi/factory/project-profile.json` — schema-versioned, machine-readable
  profile: detected project root; name and purpose; components and packages; source dirs;
  canonical docs/requirements/tasks paths; **evidence-backed** commands; architectural
  invariants with evidence paths; `generated_at`; and **hashes** of every evidence source
  file for drift detection.

No secrets, environment-variable values, generated build output, dependency contents, or
arbitrary repo dumps are stored. `.venv`, `node_modules`, build/cache dirs and `.env*`
are excluded by construction.

## 4. Commands

```
/factory-init            initialise if missing; otherwise validate and report status
/factory-init --refresh  rediscover and update only factory-managed content
/factory-init --check    read-only validation and drift check (writes nothing)
/factory-doctor          diagnostics: root, profile, block, tools, subagent metadata
```

Behaviour guarantees:

- Resolves the project root via Git with a safe fallback to the session cwd.
- Verifies project trust before honoring project-local config (trust is Pi's own gate;
  project-local extensions load only after trust).
- Collects evidence **deterministically**; every recorded fact carries an evidence path.
- Shows the proposed capsule / a concise diff before replacing an existing managed block
  when interactive, with a noninteractive fallback.
- **Idempotent**: running twice with no repository changes produces no file changes.
- Writes **atomically** (temp file + rename).
- After an actual change, calls `ctx.reload()` and returns; on a no-op run it does not.
- Never rewrites the bootstrap automatically on ordinary `session_start`.

## 5. Editing / overriding generated knowledge

The managed block is a projection of `project-profile.json`. Regenerate it with
`/factory-init --refresh` after the repo changes (new commands, new components).

- **Content outside the managed markers is yours**: edit it freely; `/factory-init` never
  touches it.
- The managed block itself is generated — edit `project-profile.json` or let `--refresh`
  rediscover. Do not hand-edit the block if you want `--refresh` to keep it in sync.
- To override a *fact* (e.g. a wrong command), fix the underlying evidence
  (e.g. `pyproject.toml`, `.factory/factory.yaml`) and refresh; the profile records the
  evidence path so the source of each fact is traceable.
- If `AGENTS.md` already exists, content outside the markers is preserved byte-for-byte;
  markers are never duplicated; malformed/ambiguous markers cause a safe failure (no
  writes) rather than a guess.

## 6. How subagents inherit project context

Both the orchestrator's subagent launcher (`src/factory/orchestrator/pi_backend.py`) and
the in-session `subagent` tool start children with:

- working directory = the **resolved project root**, so the root `AGENTS.md` (with the
  managed block) loads;
- **no `--no-context-files` / `-nc`**, so context files are never stripped;
- a **concise task packet**, not the parent transcript;
- `--mode json` so structured results return to the parent.

Recursion is bounded: `pi_backend.py` and the `subagent` tool refuse to spawn a deeper
child once `PI_FACTORY_SUBAGENT_DEPTH` reaches the configured limit, instead of starting
a runaway chain.

Tool knowledge travels with the tool registration: the `subagent` tool (and `trace_*`,
`system_context`) carry `promptSnippet` and `promptGuidelines` so the parent model learns
when/how to delegate from the tool metadata itself, independent of `AGENTS.md`.

## 7. Prompt-size and staleness considerations

- **Size**: the managed block is capped (~500–900 tokens), keeping the static prompt
  prefix small and stable and prompt-cache friendly. Deeper knowledge is pointed to, not
  inlined.
- **Staleness**: drift is detected from hashes of evidence source files.
  `/factory-init --check` (or `/factory-doctor`) reports which files changed and whether
  the profile/block are fresh; `--refresh` reconciles.
- **Do not rescan per session**; `session_start` never rewrites the bootstrap. Only an
  explicit `/factory-init --refresh` (or a changed-content init) does.

## 8. Migration / rollback

- **Migration**: `/factory-init` creates `AGENTS.md` and
  `.pi/factory/project-profile.json` on first run. Existing `AGENTS.md` content is
  preserved; no other repo files are modified.
- **Rollback**: remove the managed markers from `AGENTS.md` (and optionally delete
  `.pi/factory/project-profile.json`) to fully opt out. Nothing else depends on these
  files, so removal is safe and non-destructive. The `schema` field versions the profile;
  future schema changes gate migration.

## 9. Representative generated block for this repository

Rendered by the current discovery against the factory's own checkout
(`/factory-init --refresh`):

```markdown
<!-- pi-agent-factory:bootstrap:start schema=1 -->
# Project (factory bootstrap)
pi-agent-factory

Key components & boundaries: factory orchestrator; evidence model; traceability CLI;
requirements doctor; requirement register; system navigator; polish workflow;
sim/validation harnesses; pi extension (commands + tools).

Canonical documents: specs docs/superpowers/specs; plans docs/superpowers/plans.

Common commands: factory gate: {python} -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py
| factory gate: {python} -m pytest -m sim -q | factory gate: {python} -m pytest tests/integration/ -q
-m integration | factory gate: {python} -m ruff check . | unit: uv run python -m pytest -m unit -q
| integration: uv run python -m pytest -m integration -q | lint: uv run ruff check .
| typecheck: uv run pyright | extension test: npm test --prefix pi-ext/factory-watch.

Rule: The gate vocabulary is fixed: unit, sim, integration, full.
Rule: Python is 3.11-3.12, ruff line-length 100, pyright standard mode.
Rule: The deterministic factory pipeline is documented in engineering-context plans.

Deeper project knowledge lives in project-profile.json; run /factory-init --check for status.

Factory commands: /factory, /factory-run, /factory-init, /trace-fix, /system.
<!-- pi-agent-factory:bootstrap:end -->
```

The exact text is generated from evidence on disk, so it may drift from this copy; treat
this as illustrative of shape and tone, not as the source of truth.
