---
id: FEAT-017
title: "PLANNING-BOOTSTRAP"
status: draft
authority_spec: docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md
implementation_plan: docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
requirements:
  - SR-043
  - SR-044
  - SR-050
  - SR-051
  - SR-052
  - SR-053
  - SR-054
---

# FEAT-017 — PLANNING-BOOTSTRAP

Status: draft feature dossier for the mature FEAT-017 planning workflow. Structural closure is
validated through the current planning checker and Coherence trace surfaces; implementation,
human review, SR consent, and executed evidence remain pending.

This feature registers **PLANNING-BOOTSTRAP** in the Coherence / pi-agent-factory feature set. It
covers the host-neutral planning pipeline: adaptive intent capture -> provisional authority spec
-> three semantic checkpoints -> plan/task decomposition -> thin SR/feature/bundle derivation
-> explicit consent -> text summary and hash-bound downstream handoff.

Owned requirements: SR-043, SR-044, SR-050, SR-051, SR-052, SR-053, SR-054.

The authority spec is canonical. The implementation plan is the executable roadmap. The bundle
contains exactly this feature and its seven owned SR projections. No planning artifact may infer
human approval or automatically start FEAT-13.

## Mature workflow acceptance boundary

The mature design contract is frozen by these source-level acceptance rows:

1. `adaptive-brainstorming` preserves the request and answers verbatim and may produce a
   `provisional-spec` before every question is resolved.
2. `three-checkpoints` reviews the spec, plan/tasks, and candidate SR/FEAT/bundle derivation in
   that order, with `complete-sr-context` supplied to every reviewer.
3. `selected-review-model` uses the configured classifier and one user-selected reviewer model
   for the run; unavailable catalog/model data fails closed rather than falling back.
4. `fresh-review-loop` permits only scoped agent fixes, followed by deterministic rereads and a
   fresh independent review; `append-only-journal` preserves every resolution event.
5. `explicit-sr-consent` requires the explicit consent phrase after clean derivation; semantic
   cleanliness, an escalation answer, or an agent response is not consent.
6. `text-summary-handoff` is the first milestone. The interactive `/system` planning projection
   is `deferred-browser`, and the clean result offers an explicit downstream menu plus a
   hash-bound handoff for a separately started session.
7. `no-auto-execution` and deterministic Coherence gates remain in force: this contract records
   design scope only. Implementation is not present, agent review may be pending, human
   escalation may be pending, SR consent remains pending, and formal defer/waiver is distinct
   from unimplemented work.
