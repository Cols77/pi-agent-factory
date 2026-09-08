---
dod:
- verified CLI help/output, test/lint/type reports, and a reviewer-confirmed statement
  of deferred human browsing/visualization.
- Implement the task's stated behavior and keep all focused gates green; do not push or merge
id: T-038
satisfies:
- SR-052
source_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
source_task: 7
status: todo
title: Holistic integration review and available-gate deployment
---

- No production file changes expected unless review findings require a scoped fix.
- Reports: `.factory/planning/<run-id>/report.json` is derived evidence and must remain ignored/disposable if the project’s ignore policy requires it.

Full steps: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md, Task 7.

## Findings pending resolution

A fresh independent holistic review ran 2026-09-07. This task's own three DoD bullets
(verified CLI help/output; test/lint/type reports; reviewer-confirmed deferred-browsing
statement) are met — see the full report at
`docs/superpowers/plans/2026-09-07-feat017-t038-review-report.md`. `status` stays `todo`
because the review found real, unresolved gaps in what FEAT-017 as a whole delivers:

- **SR-055: NOT SATISFIED.** No versioned planning gate pack is compiled anywhere;
  `src/coherence/planning/gates.py` contains only two consent validators. `coherence plan
  handoff` unconditionally records `gate_summary: {"status": "pass"}` with no gate ever
  executed or evidenced.
- **SR-044: PARTIAL.** `coherence plan handoff` performs no consent check at all (only
  `suggest` does); the SR's required explicit consent-phrase path (`gates.py:177`) has no
  caller anywhere.
- **SR-043: PARTIAL.** `PlanningWorkflow` (the three-checkpoint semantic reviewer) is
  optional and never supplied by the CLI (`bootstrap.py:38`, `cli.py:240`) — built and
  tested, not wired in.
- **SR-053: PARTIAL.** The blocking cross-artifact review does not inspect
  source/validation-artifact relations or the selected workflow/gate proposal, and has no
  "weak"/"dangling" finding class.
- **SR-054: PARTIAL.** Generated tasks carry no affected-SR (`satisfies`) field, and the
  completion-preflight obligation that would enforce it self-disables when the field is
  absent (`compiler.py:229–234`).

None of the above is fabricated, assumed, or worked around — see the full report for every
citation. This task should move to `status: done` only once these are resolved (or
explicitly deferred by the human as separate, tracked work) and a follow-up review confirms
it.

### Resolved since this review

- Commit `269f0ed` fixed both drift items this review found: `tasks/T-037-...md` is now
  `status: done` with a cited closure note, and `.pi/skills/writing-plans/SKILL.md` /
  `docs/superpowers/plans/2026-09-04-commit-claim-traceability-plan.md` no longer claim the
  SR-055 gate pack exists — they now say `gates.py` holds only the shipped consent
  validators and that the compiled gate-pack contract remains future work.

### Candidate SR-055 fix — parked, not reviewed or approved

A candidate fix for part of the SR-055 finding above (report-authenticity binding,
run-id/path-escape safety, and a stable first-blocking failure code in a prototype
`gate_pack.py`) exists on branch `feat/feat17-trace-gate-enforcement`. That branch also
carries SR-054 enforcement work. **Neither has been reviewed or approved by a human** and
neither is merged; do not treat this task's SR-055/SR-054 findings as resolved on the
strength of that branch existing. See that branch's own design doc for its (explicitly
unapproved) direction before reviving it.