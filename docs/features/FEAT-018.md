---
id: FEAT-018
title: "EXECUTION-PLAN-COMPILER"
description: The execution-plan compiler turns a validated feature plan into an inspectable executable proposal.
requirements: []
---

# FEAT-018 — EXECUTION-PLAN-COMPILER

Status: proposed feature dossier (first intent; requirements pending human-approved authoring).

This feature defines the Coherence planning-to-execution bridge. Given a validated feature
plan, change classification, project capabilities, workflow catalog, and gate catalog, it
produces inspectable execution-profile proposals, explicit workflow/gate plans, and a
validated orchestration graph ready for [[FEAT-013]] to compile into an immutable run contract.

No SRs are assigned yet. Formal requirements must be derived from an approved design and
created through the existing human-consent process.

## Initial intent

Planning must not stop at a plan file and a list of Kanban tasks. Before a governed run can
be requested, Coherence must make the proposed execution semantics visible and machine-check
that the proposal is executable. An agent may help suggest a profile, but the accepted
profile, workflow, gates, dependencies, evidence obligations, and failure behavior must be
resolved from versioned catalog entries and deterministic policy.

The user-facing result is an execution proposal that explains:

- the change classification and the reasons for it;
- the recommended execution profile and admissible alternatives;
- the selected workflow and version;
- the selected gate pack/GatePlan and version;
- the expected stage and dependency graph;
- required evidence and human decision boundaries;
- transport and host capabilities required;
- unresolved assumptions, warnings, and blocking errors.

## Workflow position

[[FEAT-017]]'s planning workflow invokes this feature after plan decomposition and feature/bundle
registration. The planning workflow cannot hand off a first governed run until the generated
execution proposal and orchestration graph pass deterministic validation. The validator may
be implemented as a reusable [[FEAT-016]]/[[FEAT-013]] component, but [[FEAT-017]] owns sequencing it as
a mandatory planning checkpoint.

```text
validated FeaturePlan
    → change classification
    → profile candidates
    → workflow + GatePlan expansion
    → orchestration graph generation
    → deterministic graph validation
    → human approval or revision
    → governed-run request
```

## Deterministic graph validation

The validator must reject a proposal rather than rely on an agent or Kanban to discover a
malformed graph later. At minimum it checks:

- artifact presence, supported schema version, parsing, and canonical serialization;
- unique node/task IDs, valid stage types, valid entry/terminal nodes, and reachable paths;
- valid transitions, bounded retry loops, finite budgets, and no accidental infinite cycles;
- complete mapping from planned tasks to features, bundles, and SRs where required;
- valid workspace/scope declarations, assignees, idempotency keys, acceptance criteria, and
  verification commands;
- every gate reference resolves to a versioned GateContract/GatePlan entry;
- required gates are bound to reachable stages and cannot be downgraded or omitted;
- valid gate dependencies, requiredness, resolver commands, inputs, outputs, and evidence
  schemas;
- all required human decisions have explicit blocking/decision-file semantics;
- selected host/transport capabilities satisfy the profile and workflow requirements;
- the same canonical inputs produce the same proposal and graph hash.

The validator produces a machine-readable result containing errors, warnings, referenced
versions, graph hash, and the reason a proposal is admissible or blocked. An invalid graph
cannot be materialized as an executable governed run.

## Execution-profile model

A profile is a versioned preset that references, rather than duplicates, the underlying
workflow and gate contracts:

```yaml
execution_profile:
  id: behavior-change-kanban
  version: 1
  controller: interactive
  transport: hermes-kanban
  worker_strategy: hermes-profiles
  durability: durable
  workflow_ref: behavior-change@1
  gate_pack_ref: behavior-change@1
  capabilities:
    - kanban_dispatch
    - simulation_harness
    - human_visualization
```

The expanded proposal must show the actual gates and orchestration. A profile is not allowed
to lower the workflow floor. A profile that cannot satisfy a required capability is
inadmissible or blocked; it must not silently fall back to a weaker transport.

Initial profile families include direct single-agent execution, direct supervised fan-out,
Hermes Kanban durable workers, interactive-controller plus Kanban workers, constrained
Goal-mode assistance, external-agent workers, headless CI, human-stepwise execution, and
explicitly non-governed exploratory/advisory execution. These are presets over the same
Coherence semantics, not separate assurance authorities.

## Kanban boundary

The feature may generate a Kanban planning/execution projection, but Kanban remains the
operational substrate. The expected graph is canonical before materialization; Kanban cards
carry the run identity, graph/contract hashes, stage IDs, dependencies, and operational
metadata. Kanban does not define the workflow or acceptance authority.

## Out of scope

- implementing a generic scheduler, worker supervisor, retry engine, or worktree manager;
- defining the complete gate taxonomy or gate-onboarding lifecycle ([[FEAT-014]]);
- implementing the general workflow interpreter and template library ([[FEAT-016]]);
- performing the governed run itself ([[FEAT-013]]);
- implementing Hermes' Kanban, Goal mode, plugins, skills, or dashboard;
- allowing an LLM to invent or silently weaken required gates.

## Initial acceptance intent

A feature plan can be inspected before execution and produces a proposal showing profile,
workflow, GatePlan, stages, dependencies, gates, evidence, human boundaries, and capability
requirements. Deterministic validation rejects missing files, malformed schema, unknown
references, orphaned tasks, invalid graph structure, omitted required gates, invalid evidence
obligations, unsatisfied capabilities, and non-reproducible serialization. Only an approved
and valid proposal can be handed to [[FEAT-013]] for immutable run-contract compilation.

## Related requirements

<!-- derived — generated by `coherence mirrors generate`; do not edit -->
<!-- fingerprint: sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945 -->
- None yet; requirements are pending human-approved authoring.
