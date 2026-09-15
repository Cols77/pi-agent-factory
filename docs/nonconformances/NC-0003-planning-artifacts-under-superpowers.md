---
id: NC-0003
title: Coherence planning artifacts (specs, plans, handoffs) live under docs/superpowers/, not a Coherence-owned location
external_ref: null
detected_by: FEAT-018 spec-authoring session
status: open
---

## Symptom

Every planning artifact the `/coherence-plan` workflow produces — authority specs, implementation
plans, and ad hoc handoffs — is written under `docs/superpowers/` (`docs/superpowers/specs/`,
`docs/superpowers/plans/`, plus loose handoff files and `analysis/`/`records/` subdirectories
directly under `docs/superpowers/`). Counted at time of filing: 83 spec files, 102 plan files, and
several loose top-level handoff/analysis files.

`superpowers` is the name of a vendored third-party skill package (`superpowers:writing-plans`,
`superpowers:executing-plans`, etc.) — a host-side authoring convention, not a Coherence-owned
namespace. Coherence's own durable planning artifacts (the things `requirements/*.md`'s `source:`
field points into, and what `docs/features/*.md`'s `authority_spec`/`implementation_plan`
frontmatter names) being physically nested under a directory named for an unrelated tool conflates
two different ownership domains and makes it look, from the path alone, like these documents belong
to the superpowers skill rather than to Coherence's own planning/traceability chain.

This is load-bearing, not cosmetic: at time of filing, 66 requirement files (`requirements/SR-*.md`)
and at least one feature dossier (`docs/features/FEAT-017.md`) cite `docs/superpowers/...` paths in
their `source`/`authority_spec`/`implementation_plan` fields, and the `/coherence-plan` command
itself (`.claude/commands/coherence-plan.md`) hardcodes `docs/superpowers/specs/<date>-<slug>-design.md`
and `docs/superpowers/plans/<date>-<slug>-plan.md` as the write locations for every future run.

Detected while authoring FEAT-018's design spec: continuing the existing convention placed a new,
purely Coherence-owned artifact under the superpowers directory for lack of any better-established
alternative.

## Correction

Not yet corrected. This needs its own scoped change, not an ad hoc fix inside an unrelated planning
run:

1. Establish a Coherence-owned planning artifact location (e.g. `docs/coherence/specs/`,
   `docs/coherence/plans/`) separate from `docs/superpowers/`.
2. Migrate all existing artifacts under `docs/superpowers/specs/`, `docs/superpowers/plans/`, and
   the loose top-level handoff/analysis files to that location.
3. Update every cross-reference: the 66 requirement files' `source` fields, `docs/features/FEAT-017.md`'s
   `authority_spec`/`implementation_plan`, and any other `docs/features/*.md` frontmatter pointing
   at the old paths.
4. Update `.claude/commands/coherence-plan.md` (and any other skill/command referencing the old
   paths) so every planning run started after this fix writes to the new location by construction.
5. Decide whether `docs/superpowers/analysis/` and `docs/superpowers/records/` are in scope for the
   same migration or are genuinely superpowers-owned content that should stay.

All plannings run after this fix land should create their artifacts in the new dedicated Coherence
folder(s), not under `docs/superpowers/`.
