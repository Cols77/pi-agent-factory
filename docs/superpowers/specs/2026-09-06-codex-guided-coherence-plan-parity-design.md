# Codex Guided Coherence Plan Parity Design

## Goal

Bring the project-local Codex `$coherence-plan` skill into behavioral parity with
the guided Claude Code planning entrypoint already implemented on
`feat/guided-planning-entrypoint`, without copying host hooks or giving Codex
planning authority.

## Scope

The change updates the Codex skill instructions, its OpenAI metadata, and the
skill contract tests. The skill will describe and route the complete planning
lifecycle:

1. Resolve an explicit run ID and, for `FEAT-NNN` inputs, inspect drafted
   artifacts through `artifact_navigator`.
2. Inspect or start the capture session through `guided_entrypoint`, ask one
   semantic question at a time, append the human's answer, and transport human
   challenge resolutions and terminal status choices.
3. Author and review the spec and decomposable plan as model work, using the
   captured intent and drafted artifact context.
4. Run `guided_pipeline bootstrap --decompose`, `check`, `review`, and
   `handoff`; repair the plan when deterministic checks find parity issues.
5. Query the authoritative legal-actions projection, report the non-executing
   handoff, and stop without launching downstream work.

The change does not merge the Claude worktree, duplicate its hooks, create a
second planning state machine, adopt requirements, grant consent, or execute
generated tasks.

## Authority and safety

Coherence remains authoritative for planning state, structural validity,
durability, identity, ordering, hashes, decomposition, legal actions, and
blocking reasons. The Codex model owns semantic questions, authored document
content, and review judgments. The human owns challenge dispositions, terminal
capture status, consent, and any downstream execution decision.

The skill must use the fail-closed guided adapters and argv-only commands. It
must treat trusted exit codes `0` and `1` as structured data, reject malformed
or contradictory payloads, and never infer a state that the backend does not
project. It must preserve provenance (`user` for human input and
`intent-review-agent` for review findings), treat challenge detection as a
hint rather than a completeness gate, and stop on blocked or invalid output.

The only backend session states the skill may narrate are `capture`,
`intent_provisional`, and `blocked`. A handoff is display-only and must report
the run ID, projection, changed artifacts, evidence/tests, blockers, and next
legal action; `starts_automatically=false` remains a hard invariant.

## Files and contracts

- `.agents/skills/coherence-plan/SKILL.md` becomes the Codex host workflow and
  records the authority split, guided commands, fix-review-fix behavior, and
  stop boundaries.
- `.agents/skills/coherence-plan/agents/openai.yaml` describes the guided
  planning entrypoint while retaining the distinction from Codex's built-in
  `/plan` surface.
- `tests/unit/codex/test_coherence_plan_contract.py` asserts the new workflow
  vocabulary and safety boundaries while retaining the existing projection and
  allowlist checks.

The skill references backend modules implemented by the guided planning work:
`coherence.planning.artifact_navigator`,
`coherence.planning.guided_entrypoint`, and
`coherence.planning.guided_pipeline`. It does not reimplement those contracts
inside the skill.

## Validation

The focused Codex contract suite must pass. The updated tests must prove that
the skill names every lifecycle phase, preserves human-only decisions and
non-execution boundaries, and continues to require the authoritative
legal-actions projection after state-changing operations.
