---
id: SPEC-FEAT-017-CLOSURE-SLICE
title: "FEAT-017 coordinated closure slice"
status: draft
feature: FEAT-017
requirements:
  - SR-043
  - SR-044
  - SR-053
  - SR-054
  - SR-055
  - SR-065
  - SR-071
---

# FEAT-017 coordinated closure slice

## Goal

Close the remaining FEAT-017 planning-assurance gaps with one authoritative,
evidence-first lifecycle projection. The projection makes a planning run usable
before handoff while preserving its non-executing boundary.

## Scope and boundary

The closure slice owns planning-stage composition, requirement authoring and
consent progression, cross-artifact review, task trace declarations, planning
gate-pack enforcement, and the host-guided lifecycle projection. It does not
execute implementation validation gates, grant consent, adopt requirements,
write artifacts from a projection, or start downstream work.

The visualizer in SR-071 is a proposed future host presentation. This slice
creates its read-only projection seam but does not implement a browser or TUI
visualizer.

Existing host workflows remain available as an explicit compatibility path.
In particular, Claude Code's documented command-and-hook workflow continues to
use the sanctioned adapters and its existing boundary hooks. The lifecycle
projection is an additive guided mode, not a replacement or a silent migration.
Only the guided mode may represent its sequencing as backend-derived; the
compatibility path must not claim that its prose-directed ordering is an
authoritative lifecycle result.

## Lifecycle contract

`coherence.planning.lifecycle` is a pure projector. It derives a run's one
currently permitted action or its fail-closed blocking reason from the
append-only capture journal, the hash-validated session snapshot, and current
artifacts and evidence. It never accepts caller-supplied state, writes files,
or launches a subprocess.

The ordered lifecycle is:

1. `author-requirements`
2. per-SR human consent
3. `author-spec`
4. `author-plan`
5. `review-spec`
6. `review-plan`
7. planning gate-pack compilation and execution
8. explicit, non-executing handoff

The projection exposes only the current relevant action. It does not display a
full menu, and an advertised action remains display-only: a host must invoke
the corresponding existing guided entrypoint or pipeline operation explicitly.
Hosts may instead explicitly choose their existing compatibility workflow; that
choice preserves its existing hooks and adapter boundary but is not a lifecycle
projection and never receives a derived-stage claim.

## Requirement authoring and consent

`author-requirements` covers both proposed new SRs and revisions to existing
SRs. The host authors the requirement artifacts; the projector only determines
when their authoring is required and whether their evidence is current.

Every candidate or revised SR requires a separate, hash-bound human decision.
No clean review, warning acceptance, consent for another SR, agent response, or
bulk decision can satisfy this prerequisite. Any requirement-content change
invalidates its consent and blocks later stages until a new current decision is
recorded.

## Artifact and evidence transitions

Each later action requires current evidence for all its predecessors. A mere
file's presence is insufficient: references, content hashes, and applicable
gate records must validate. A mutation to an input invalidates successors and
returns a specific block rather than a stale action.

The post-authoring review consumes the captured intent, requirement and consent
records, specification, implementation plan, generated tasks, canonical source
and validation relations, and selected workflow/gate proposal. It reports
missing, dangling, duplicate, weak, overstated, and contradictory links with
cited findings.

Generated tasks that change production or validation artifacts must declare
their affected SRs. Completion remains blocked until those declarations,
canonical `implemented_by` and `verified_by` relations, mirrored docs, task
outputs, and review outputs reconcile.

## Versioned planning gate pack

`coherence.planning.gates` compiles a versioned planning gate pack for every
FEAT-017 workflow. Every pack entry declares its stage, requiredness, resolver,
dependencies, expected evidence, and failure behavior. Handoff is blocked if a
required gate is missing, failed, unevidenced, stale, silently downgraded, or
not executed according to the pack.

This is planning assurance only. The pack can inspect and validate planning
contracts; it cannot execute or claim implementation-validation evidence.

## Integration

`session.py` retains strict journal/state identity validation and delegates
legal-action decisions to the lifecycle projector. Guided adapters and host
documentation render the canonical projection verbatim instead of inferring
stage from host-local state. After a valid handoff, existing downstream actions
remain non-executing and are exposed only when their handoff evidence validates.

Claude Code retains its current slash-command and hook route during the
transition. Its channel and finalize hooks remain defense in depth for that
compatibility route and for the guided route; they do not become an alternate
source of lifecycle truth. Hermes and Codex may likewise retain their existing
host integrations while adding a thin guided-projection presenter.

The later SR-071 visualizer uses this same projection to show current stage,
completed and blocked stages, required evidence and hashes, consent and gate
status, the only permitted action, and an exact blocking reason. It creates no
parallel workflow state or approval path.

## Failure handling and verification

All missing, stale, contradictory, failed, or unevidenced prerequisites fail
closed with an attributable reason. Tests cover every valid lifecycle
transition; mutation-based invalidation; per-SR consent; required gate-pack
enforcement; all cross-artifact finding classes; mandatory task SR declarations
and reconciliation; strict non-execution; and adapters rendering the same
projection without duplicated sequencing logic.

## Requirement alignment

- SR-043 gains the requirement authoring/revision stage and ordered lifecycle.
- SR-044 gains separate hash-bound consent for new and revised candidate SRs.
- SR-053 names consent records, gate-pack evidence, and canonical trace
  relations as review inputs.
- SR-054 requires applicable generated-task SR declarations and reconciliation.
- SR-055 owns compiled, versioned planning gate-pack enforcement.
- SR-065 owns the sole guided, state- and evidence-derived action projection.
- SR-071 reserves the read-only visualizer extension point.
