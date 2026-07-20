---
name: context-completeness-audit
description: Use as the Context-Gatherer role before emitting a context manifest - prove spec/plan/task/prior-session coherence with real evidence, or reject the task back to plan-time when you cannot
---

# Context Completeness Audit

## Overview

The Context-Gatherer is the factory's only checkpoint before real work starts. Everything downstream (Dev, Validation, Review) trusts that the manifest you emit is coherent. A manifest that merely *looks* complete, but wasn't actually checked against the repo, lets an incoherent task burn Dev/Review iterations before anyone notices.

**Core principle:** Prove coherence with evidence you actually gathered this run. Don't assert `proven: true` because the task file exists and reads plausibly.

## Your Output Contract

Emit **only** a fenced ` ```json ` block matching this shape (nothing else — the orchestrator extracts the last such block from your output and discards everything else):

```json
{
  "task_id": "T-012",
  "generated_by": "context-gatherer",
  "generated_at": "2026-07-16T14:32:10Z",
  "coherence": {
    "proven": true,
    "checks": [
      {"name": "task-exists-in-plan", "pass": true, "evidence": "tasks/T-012-....md"},
      {"name": "spec-plan-consistent", "pass": true, "evidence": "no plan doc for this task; task file is self-contained"},
      {"name": "dod-present-and-clear", "pass": true, "evidence": "tasks/T-012-....md#dod has 2 observable criteria"},
      {"name": "no-contradiction-prior-session", "pass": true, "evidence": "no prior session references this task"}
    ]
  },
  "context": {
    "spec": [],
    "plan": [],
    "task": "tasks/T-012-....md",
    "prior_session": null,
    "source_files": ["src/drone/pybullet_flight_controller.py"],
    "kb_entries": [],
    "skills": ["test-driven-development", "systematic-debugging", "receiving-code-review", "kb-lookup"]
  },
  "reject": null
}
```

## The Gate That Actually Checks This

Your manifest is validated by `src/factory/validation/manifest_validator.py`, deterministically, not by anyone reading your prose:

1. **Schema-valid** against `src/factory/schemas/context_manifest.schema.json` (required top-level: `task_id`, `generated_by`, `generated_at`, `coherence`, `context`; `context` requires `task`, `source_files`, `skills`).
2. **`coherence.proven` must be exactly `true`.**
3. **Every check in `coherence.checks[]` must have `pass: true`.** If you set `proven: true` but list even one check with `pass: false`, that's an internal contradiction and the gate rejects it outright — don't do this. Either all checks pass and `proven` is `true`, or resolve conflicts by setting `proven: false` and populating `reject` instead.
4. **Every path you reference actually exists on disk**, relative to the repo root: `context.task`, `context.prior_session` (if set), and every entry in `context.source_files`, `context.spec`, `context.plan`. A `#fragment` anchor (e.g. `plan.md#T-012`) is stripped before the existence check, but the file itself must be real. `context.kb_entries` and `context.skills` are **not** path-checked — those are IDs/names, not files.

A manifest that's schema-valid but references a source file that doesn't exist fails the gate exactly like an incoherent one. **Check paths yourself before emitting** — don't rely on the gate to catch a typo, since a failed gate here means a wasted attempt (you get `max_attempts` tries, default 2, before the task is forcibly rejected).

## The Four Checks, What Each Actually Requires

- **`task-exists-in-plan`** — the task file itself exists and is readable (`tasks/T-*.md`). If this factory has a companion plan doc, confirm the task is actually listed there too; if there's no plan doc for this task (common for small, self-contained tasks), evidence should say so explicitly rather than pointing at nothing.
- **`spec-plan-consistent`** — if both a spec and a plan doc are in play, confirm they don't contradict each other for this task. If only one or neither exists, say so in the evidence rather than fabricating a cross-reference.
- **`dod-present-and-clear`** — the task's `dod:` frontmatter list exists and each item is genuinely observable/testable (see the task ledger's own DoD conventions). A DoD like "works well" is not clear; flag it and consider rejecting rather than inventing your own interpretation of what "done" means.
- **`no-contradiction-prior-session`** — read the newest `sessions/*.session.json` if one exists. Does anything there conflict with what this task assumes (e.g., a prior task removed something this one depends on)? If no prior session exists yet, say so — that's a legitimate pass, not a skipped check.

## When You Cannot Prove Coherence: Reject, Don't Guess

```json
{
  "task_id": "T-012",
  "coherence": {"proven": false},
  "reject": {
    "reason": "DoD absent; acceptance criteria unmeasurable",
    "conflicts": ["plan.md#T-012 assumes CV oracle removed in T-009, but T-009 is still status: todo"]
  }
}
```

Rejecting is not a failure state for you — it's the correct outcome when the task genuinely isn't coherent yet. Guessing at missing context so you can emit `proven: true` pushes an incoherent task onto Dev, where it will fail more expensively and less legibly than a clean reject here.

## Red Flags

- Writing `"evidence": "checked"` or similar with no actual file/fragment reference — evidence must be a real path, prior-session excerpt, or explicit "N/A because X," not a bare assertion.
- Setting `proven: true` without having actually opened the referenced files this run.
- Listing a `source_files` entry you haven't confirmed exists.
- Treating "the task file looks reasonable" as equivalent to "I checked it against the plan and prior session."

Related skill: `verification-before-completion` — the same evidence-before-claims discipline applies here to `coherence.proven`, not just to "tests pass."
