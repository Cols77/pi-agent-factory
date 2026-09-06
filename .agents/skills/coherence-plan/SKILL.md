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
