---
id: FEAT-014
title: "VALIDATION-GATES"
description: Validation gates enforce workflow assurance floors and produce deterministic, provenance-backed evidence.
requirements:
  - SR-035
  - SR-036
  - SR-037
---

# FEAT-014 — VALIDATION-GATES

Status: declared feature dossier (Inc-9 health-resolution, decision-level register).

This feature registers **VALIDATION-GATES** in the Coherence / pi-agent-factory feature set. It covers workflow-specific assurance floors, precompiled GatePlans, project-local gate discovery/onboarding, deterministic evidence, integrity checks, and human change-control.


## Design boundary

Every workflow has an unbypassable Coherence-compiled minimum gate floor. The floor may
differ by workflow and change class, but an agent cannot remove or weaken it. Acceptance
criteria, thresholds, applicability policy, protected acceptance tests, and gate versions
are contract data rather than editable Kanban instructions.

Project-local gates are discovered from a conventional gate directory with a minimal manifest
and a command returning the standard Coherence observation JSON. The host-neutral
gate-onboarding workflow validates command/schema shape, bounded side effects, declared
inputs/outputs, fixed-snapshot repeatability, evidence-fixture validity, and
provenance/security before registering a gate as advisory-active.

Validated additional gates are included in the next run's advisory set by default. An agent
may reject one from that next run only with rationale and independent review; rejection
cannot remove a workflow-floor gate, and the candidate remains visible for reconsideration.
A failed advisory gate leaves the run conditional/non-green until its underlying result
passes. Human-owned change-control creates future contract revisions for gate definitions,
thresholds, applicability, protected acceptance tests, or workflow floors; it never rewrites
the active run's contract.

Direct modification of a registered gate or active contract pauses the run and creates a
control-plane finding. A reviewer may classify it as an intentional revision request, but
only the human change-control workflow may authorize a new version.

## Related requirements

- [[SR-035]]
- [[SR-036]]
- [[SR-037]]
