---
name: coherence-plan
description: Inspect and continue a named Coherence planning run through a bounded, evidence-first author and review loop.
---

# Coherence plan

Use this project-local skill only when the user explicitly invokes
`$coherence-plan`. Codex's built-in `/plan` remains a separate planning
surface; this skill is the thin host adapter for an existing Coherence
planning run.

## Required inputs

Before reading or changing planning state, require both of these inputs:

1. A named run ID supplied by the user. It must match
   `[A-Za-z0-9][A-Za-z0-9._-]*`. Never infer a current run, run ID, or state
   from the working directory, recent history, or another session.
2. A concrete planning request that says what the user wants planned or
   revised. Do not turn an absent or vague request into an inferred goal.

Require the user to explicitly choose either start or resume. Use the selected
operation exactly; there is no silent fallback from start to
resume or from resume to start. Start and resume are explicit Coherence operations, for
example:

```text
uv run coherence plan start --project-root <root> --run-id <id> --prompt <request> --json
uv run coherence plan resume --project-root <root> --run-id <id> --json
```

Do not substitute a guessed run ID, request, project root, or state.

## Authority and projection

Coherence remains the authority for planning state, legal actions, and
blocking reasons. Never infer state or actions from prose, files, prior chat,
or a host menu. Do not infer state or actions from a host adapter. After every
state-changing operation—including start and
resume—invoke exactly this project helper:

```text
uv run python .agents/skills/coherence-plan/scripts/coherence_plan.py legal-actions --project-root <root> --run-id <id>
```

Treat the helper's validated backend projection as authoritative. In
particular, use `blocked`, `reason`, `legal_next_actions`, and
`starts_automatically=false` exactly as returned. A missing, contradictory, or
invalid projection is blocked; do not repair it by guessing. When `blocked` is
true, stop state-changing work, report the reason and legal actions, and wait
for an explicit resolution.

The helper accepts only the schema-2 planning projection. A valid response also
contains the current lifecycle `state`, the hash-bound `run_identity` when the
run is ready (or `null` while blocked), and the `action_registry` with its
registry hash. Schema-1
responses, missing identity or registry data, stale hashes, multiple actions,
and ready/blocked contradictions are invalid and must fail closed. The nested
`action_registry.schema` is its own registry version and is not the planning
transport schema.

The helper is a read-only projection. It does not grant permission to invoke
an action, and an action name in a projection is not evidence that the action
was completed.

## Safe fix-review-fix loop

Only these backend-declared actions may enter the bounded loop:

- `author-spec`
- `author-plan`
- `review-spec`
- `review-plan`

Present every backend action exactly as returned in the latest projection.
The current registry may return `inspect-handoff`, `revalidate-handoff`,
`select-downstream-workflow`, `create-downstream-session`, or
`resolve-blocking-input`. These and any other non-allowlisted action are
display-only and must never be translated, renamed, or auto-selected into the
loop. Before each permitted operation, use the latest projection and the
user's explicit planning request.

Enter the loop only when the latest backend projection itself declares one of
the exact four allowlisted IDs above. If no allowlisted action is declared,
report the projection or handoff and stop for human decision; do not claim the
loop was performed.

The loop is sequential and evidence-first:

1. Inspect the bounded context and the current projection.
2. Author the smallest requested spec or plan change when the projection and
   request permit it.
3. Run the focused tests or gates required by the current planning evidence.
4. Perform a fresh requirement review.
5. If the review has findings, apply fixes using the smallest valid change,
   re-check legal actions, and review again.
6. Repeat this fix-review-fix sequence until the review passes, Coherence
   reports a block, or a human decision boundary is reached.

After every authoring, fixing, reviewing, or other operation that changes
state, run the exact helper command above before continuing. A reviewer pass
is not completion by itself: claim completion only with the relevant changed
files and evidence or test results.

## FEAT-017 full planning closure

When the named run is a FEAT-017 planning run, the legal-actions projection is
necessary but not sufficient for handoff. The run must carry a current,
fail-closed planning evidence set. Keep the six canonical source kinds together:
`intent`, `spec`, `plan`, `feature`, `bundle`, and `requirements`.

Use the governed command surface, not hand-written derived JSON:

```text
uv run coherence plan bootstrap --run-id <id> --project-root <root> --intent <intent> --spec <spec> --plan <plan> --decompose --json
uv run coherence plan check --run-id <id> --project-root <root> --intent <intent> --spec <spec> --plan <plan> --json
uv run coherence plan review --run-id <id> --project-root <root> --json
uv run coherence plan write-artifact-manifest --run-id <id> --project-root <root> --artifacts-json '<complete manifest>'
uv run coherence plan record-sr-consent --run-id <id> --project-root <root> --sr-id <sr-id> --requirement-sha256 <sha256> --decision <decision> --reviewer <reviewer> --phrase '<approved phrase>' --reason '<reason>' --json
uv run coherence plan write-cross-artifact-review --run-id <id> --project-root <root> --tasks-json '<complete task mapping>' --workflow feature-planning --json
uv run coherence plan run-planning-gates --run-id <id> --project-root <root> --json
uv run coherence plan handoff --run-id <id> --project-root <root> --workflow standard-development --json
```

The exact flags and payload schema are authoritative in `--help`; never invent
missing values. The artifact manifest must name the complete current source set
with fresh SHA-256 values. A source mutation invalidates transitive evidence:
refresh the manifest, planning report, review decision, SR consent, cross-artifact
review, gate result, and dependent hashes through their producers. Never hand-edit
`.factory/planning/<run-id>/report.json`, `state.json`, `capture/events.jsonl`,
or a published gate result to make a check pass.

Create intent through the session API (`start`/`resume` plus `append`, and
`propose-challenge`/`resolve` where applicable). A hand-written intent snapshot
is not equivalent to journal-replayed evidence. For negative tests, mutate a
source with a freshly recomputed dependent hash and prove the gate fails; stale
hashes are not evidence. Treat `plan check` as live-file validation and
`plan review` as recorded-run evidence—both must be current before handoff.

Handoff is a report, not authorization; starts_automatically remains false.
Present blockers, changed files, evidence, tests, and the next legal action to
the human. Never grant SR consent, adopt requirements, launch downstream work,
merge, or push from this skill.

## Boundaries

This skill is a thin host adapter. It never owns planning state or grants
authority. In particular:

- Never grant consent. Never adopt requirements on the user's behalf.
- Never perform warning acceptance as approval or a gate bypass.
- Never launch downstream work, materialize downstream artifacts, or execute a
  downstream workflow.
- Never merge or push.
- Never claim that a plan is complete without evidence.

Do not treat `starts_automatically=false` as optional. A handoff is a
non-executing report only. It must include the run ID, the authoritative
state/action projection, changed files, evidence and tests, blockers, and the
next legal action. Present the report for an explicit human decision; never
execute its suggested next step automatically.
