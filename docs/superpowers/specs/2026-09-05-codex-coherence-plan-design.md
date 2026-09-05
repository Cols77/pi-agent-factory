# Codex Coherence Plan Skill

**Date:** 2026-09-05

## Goal

Provide a native Codex entrypoint for the existing Coherence planning workflow
through an explicit `$coherence-plan` skill. The skill must let Codex inspect and
continue a named planning run while keeping Coherence as the sole authority for
state, legal actions, gates, decisions, consent, and handoff.

This is a host adapter. It does not replace Codex's built-in `/plan` mode and
does not add a second planning state machine.

## Context

The repository already exposes a machine-readable planning projection through:

```text
uv run coherence plan legal-actions \
  --project-root <project-root> \
  --run-id <run-id> \
  --json
```

The target worktree also contains tested Pi and Hermes adapters over this
projection. The Codex integration should use the same backend contract and
preserve the same non-executing host boundary.

Codex skills are the native reusable-workflow surface. The project-local skill
will live under `.agents/skills/coherence-plan/` and be explicitly invokable as
`$coherence-plan`. The skill is not a user-defined `/coherence-plan` slash
command; Codex's `/plan` remains its built-in plan mode.

## Scope

### In scope

- A project-local Codex skill named `coherence-plan`.
- A standard-library helper script that invokes the legal-actions backend with
  an argv list and validates its structured response.
- Codex presentation metadata for skill discovery.
- Contract and helper tests.
- Documentation showing how to invoke the skill and how it relates to the
  existing Coherence, Pi, and Hermes surfaces.
- Explicit fix-review-fix guidance for authorized authoring and review work.

### Out of scope

- Changing the canonical Coherence planner, session model, or action registry.
- Replacing or modifying Codex's built-in `/plan` command.
- Creating a second workflow interpreter, scheduler, or durable state store.
- Inferring a run ID, planning action, consent decision, gate result, or
  downstream workflow from conversation history.
- Granting consent, adopting requirements, accepting warnings, bypassing gates,
  materializing downstream work, launching implementation, merging, or pushing.
- Packaging or publishing a universal Codex plugin/marketplace entry.
- Modifying the existing Hermes or Pi adapters except where documentation or a
  shared contract test demonstrates a required parity correction.

## Design

### Components

#### Codex skill

Create `.agents/skills/coherence-plan/SKILL.md` with required `name` and
`description` frontmatter. The skill will:

1. Require a safe named run ID and a planning request. It must ask the user for
   missing identity or intent rather than inventing either.
2. Start or resume the named run through the existing Coherence CLI using the
   documented command and JSON output.
3. Query the helper for `legal-actions` before every planning transition.
4. Treat `blocked`, `reason`, and `legal_next_actions` as backend authority.
5. Present only backend-declared actions and distinguish display-only actions
   from authoring/review actions safe for this host workflow.
6. Re-check the projection after every state-changing operation or session
   replacement.
7. Keep handoff non-executing and require an explicit human decision whenever
   Coherence reports one.

The skill will include a sequential fix-review-fix loop for an authorized
authoring or review action:

1. Read the current backend projection and bounded task context.
2. Make the smallest change required by the requirement or current review
   finding.
3. Run the focused tests and applicable declared gates.
4. Perform a fresh review against the requirement and the new evidence.
5. Apply valid findings and return to the projection check.
6. Stop on reviewer acceptance, a Coherence block, or a human decision
   boundary. It must not continue into downstream execution automatically.

#### Helper script

Create `.agents/skills/coherence-plan/scripts/coherence_plan.py`. It will be a
small standard-library adapter with no project-state authority of its own. Its
legal-actions operation will:

- Validate the project root and run ID before spawning anything.
- Reject path separators, whitespace, shell syntax, empty IDs, and other
  characters outside the existing safe run-ID grammar.
- Invoke `uv run coherence plan legal-actions --project-root ... --run-id ...
  --json` via `subprocess.run([...], shell=False)`.
- Accept exit code `0` for ready and exit code `1` for the backend's normal
  blocked signal.
- Parse and validate the JSON object, including schema `1`, exact run ID,
  boolean `blocked`, string-or-null `reason`, string action IDs, and
  `starts_automatically == false`.
- Treat malformed output, a mismatched run ID, automatic start permission, an
  unexpected exit code, or an OS failure as a blocked adapter error.
- Emit a stable JSON result suitable for Codex to read without reinterpreting
  the backend contract.

Start, resume, and other state-changing operations remain explicit Coherence
workflow commands in the skill. The helper does not infer whether to create a
new run or resume an existing one.

#### Codex metadata

Create `.agents/skills/coherence-plan/agents/openai.yaml` with concise display
metadata and a default prompt that points users to `$coherence-plan`. Metadata
must not claim that the skill can approve, adopt, execute, or bypass planning
state.

### Data flow

```text
$coherence-plan request
        |
        v
named run + planning request validated
        |
        v
Coherence start/resume (explicit state change)
        |
        v
legal-actions JSON projection via helper
        |
        +--> blocked: render reason and recovery action; stop
        |
        +--> ready: present only backend-declared actions
                       |
                       v
               authorized author/review work
                       |
                       v
               tests/gates -> fresh review -> fix if needed
                       |
                       v
               re-query projection; non-executing handoff
```

The helper and skill never treat the host conversation, model output, Codex
session state, or displayed action text as a substitute for this projection.

## Error handling and safety

- Missing or unsafe run ID: print usage and do not invoke the backend.
- Invalid project root: return a blocked adapter result without writing.
- Valid exit code `1` with a valid projection: preserve the backend's block
  reason and action list.
- Malformed JSON, mismatched run ID, invalid schema, or
  `starts_automatically: true`: return `BACKEND_INVALID` and no usable action.
- Unexpected nonzero exit code: return a bounded error using stderr, never
  trusting stdout merely because it resembles a projection.
- A legal action outside the host's safe authoring/review allowlist is
  display-only; the helper never executes actions.
- Any state-changing Coherence command failure stops the skill and reports the
  failure rather than retrying a different transition.
- Handoff remains non-executing. The skill may report that a downstream action
  is legal, but it must not start that work.

## Testing and verification

Add `tests/unit/codex/test_coherence_plan_skill.py` covering:

- Safe run IDs produce the exact argv-only backend invocation.
- Unsafe run IDs do not spawn a subprocess.
- A valid ready projection is returned unchanged in authority fields.
- A valid blocked projection and normal exit code `1` preserve the declared
  reason and actions.
- Malformed JSON, invalid fields, automatic start permission, and mismatched
  run IDs fail closed.
- Unexpected backend exit codes fail closed even when stdout contains valid
  JSON.
- The skill contract contains the explicit invocation, legal-actions
  checkpoint, non-executing boundary, and fix-review-fix loop.

Verification must include the focused Codex tests, the existing planning,
Hermes, and Pi adapter tests, lint/type checks for changed executable files,
and `git diff --check`. Repository-wide baseline failures must be reported
separately from failures introduced by this change.

## Acceptance criteria

The change is accepted when:

1. A fresh Codex session can discover and explicitly invoke `$coherence-plan`
   from the project-local skill path.
2. The skill requires a named run and uses the existing Coherence workflow
   instead of duplicating planning state.
3. Every legal-action decision is derived from and revalidated against the
   backend JSON projection.
4. Unsafe input, malformed output, stale state, unexpected failure, and
   automatic-start contradictions fail closed.
5. The fix-review-fix loop is documented and cannot silently cross consent,
   adoption, gate, or downstream-execution boundaries.
6. Existing Hermes and Pi adapter behavior remains green.

