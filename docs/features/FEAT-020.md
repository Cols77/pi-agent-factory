---
id: FEAT-020
title: "KANBAN-MAPPING-OPTIMIZATION"
description: Kanban mapping optimization improves operational efficiency without weakening governed assurance.
requirements: []
---

# FEAT-020 — KANBAN-MAPPING-OPTIMIZATION

Status: proposed feature dossier (first intent; requirements pending human-approved authoring).

This feature optimizes the mapping from a Coherence-validated orchestration graph to Hermes
Kanban operational tasks. It reduces avoidable wall-clock time, queue wait, model turns,
retries, and dispatch failures while preserving the approved workflow, GatePlan, evidence
obligations, human boundaries, traceability, and final assurance status.

No SRs are assigned yet. Formal requirements must be derived from an approved design and
created through the existing human-consent process.

## Initial intent

The first Kanban dogfooding runs show that execution time is not explained by model speed
alone. A strictly serial dependency chain in one worktree, large Goal-mode budgets, repeated
expensive validation, fresh review/rework cycles, unavailable reviewer profiles, review
transition failures, and ad hoc continuation cards can make a valid governed workflow much
slower than necessary.

The desired behavior is:

```text
canonical Coherence graph
    → legality and assurance-preserving optimization
    → efficient Kanban mapping
    → deterministic materialization
    → observed execution
    → performance/reliability evidence
```

Optimization is allowed to change operational scheduling. It is not allowed to change what
must be proved.

## Boundary with neighboring features

- **[[FEAT-017]]** sequences planning and requires the execution proposal to be valid before
  handoff.
- **[[FEAT-018]]** produces the semantically valid execution profile, workflow, GatePlan, and
  canonical orchestration graph.
- **FEAT-020** derives an optimized operational mapping from that graph and proves semantic
  equivalence before materialization.
- **[[FEAT-013]]** executes the selected mapping through the chosen transport.
- **[[FEAT-019]]** conformance-tests the mapping and transport, including failure injection and
  cross-host equivalence.

FEAT-020 does not become a second workflow interpreter or scheduler. Hermes Kanban remains
responsible for its native queue, dispatcher, worker lifecycle, workspaces, retries, and
handoffs.

## Optimization dimensions

### 1. Dependency and critical-path optimization

The mapper should:

- identify independent planning, implementation, review, and deterministic-gate stages;
- parallelize only stages whose declared dependencies, workspace ownership, and file scopes
  make parallel execution safe;
- serialize shared-file or shared-worktree operations explicitly;
- calculate critical-path and queue-wait contributions;
- batch independent gates where their GateContracts permit parallel execution;
- avoid recreating a serial chain merely because the source plan was written linearly.

Every optimization must retain the original dependency relation and required evidence. A
shorter graph is valid only when it is a semantically equivalent graph, not when it omits
work.

### 2. Worker capability preflight

Before cards become runnable, the mapper validates:

- assigned worker/reviewer profiles exist;
- required skills and toolsets are available;
- requested workspace kind/path is valid;
- required simulation, visualization, or host capabilities are available;
- model/provider and Goal-mode settings are admissible;
- retry and timeout policies are supported.

A missing reviewer profile or unsupported capability becomes an early, actionable block. It
must not consume repeated dispatcher retries or silently select a different worker.

### 3. Stage-appropriate budgets

Goal-loop and worker budgets should be selected per stage and role rather than using one
large default for every task. The mapping may declare:

- maximum turns;
- maximum runtime;
- bounded continuation behavior;
- stop conditions;
- evidence required before continuation;
- escalation when the budget is exhausted.

A continuation is valid only when it is represented by the approved graph or an explicit,
contract-preserving amendment. Agents may not create uncontrolled continuation work that
bypasses the GatePlan.

### 4. Gate scheduling without gate weakening

The mapper should reduce avoidable gate cost through:

- fast-fail deterministic checks at the earliest useful stage;
- parallel execution of independent gates;
- deferral of expensive composite/final gates until their declared prerequisites exist;
- reuse of evidence only when provenance, scope, content hash, and freshness prove it remains
  applicable;
- clear separation between per-stage validation and final reconciliation.

It must never achieve speed by silently removing, downgrading, or moving a required gate past
the point where its evidence can no longer protect the change.

### 5. Review and transition reliability

The optimized mapping should use deterministic lifecycle transitions and explicit review
handoffs. It should avoid treating a malformed goal-judge or review transition as a reason to
repeat an entire stage when a bounded protocol recovery is sufficient.

The mapping should prefer one coherent review lifecycle per stage—either same-card review or
an explicitly modeled downstream review card—rather than accidentally combining both. Fresh
review after implementation and after fixes remains required where the workflow demands it.

## Optimization contract

The mapper receives:

```text
validated ExecutionProposal
+ canonical graph hash
+ GatePlan hash
+ host/transport capability snapshot
+ project workspace/file-scope data
```

It returns:

```yaml
kanban_mapping:
  source_graph_hash: sha256:...
  mapping_version: 1
  execution_profile: hermes-kanban-durable
  critical_path: [...]
  parallel_lanes: [...]
  serialized_conflicts: [...]
  stage_budgets: [...]
  gate_batches: [...]
  capability_preflight: valid
  semantic_equivalence: valid
```

The optimized mapping must retain references to every source stage, task, gate, evidence
obligation, human boundary, and failure transition. It must be deterministically
serializable and independently revalidated before cards are created.

## Performance and reliability evidence

The feature must establish a baseline on representative Coherence dogfood runs and compare
optimized mappings against it. At minimum, record:

- total wall-clock duration;
- critical-path duration;
- queue wait and worker utilization;
- agent turns and Goal-mode budget consumption;
- gate duration and batching;
- worker dispatch failures;
- review-transition retries;
- continuation/rework-card count;
- stale-worker/crash recovery count;
- evidence and gate coverage equivalence;
- final assurance status equivalence.

A run is not an optimization success merely because it finishes faster. The result must show
that the same required gates, evidence, traceability, human decisions, and final Coherence
status were preserved.

No universal speed target is fixed yet. The first implementation should establish the
current serial/large-budget behavior as a measured baseline, then set profile-specific
improvement targets from observed data.

## Failure handling

If optimization cannot prove semantic equivalence, capability compatibility, or deterministic
materialization, it must return the unoptimized mapping as unavailable rather than silently
fall back to a weaker governed run. The run may:

- use an explicitly selected safe mapping;
- remain blocked for human intervention; or
- be reclassified explicitly as exploratory/advisory.

It must not silently change run class or assurance level.

## Requirement strategy

This needs both a feature and system-level requirements:

- **System requirements** express invariants such as semantic equivalence, no silent
  assurance downgrade, bounded retries, and preserved evidence coverage.
- **FEAT-020 requirements** express the concrete optimization mechanisms, mapping artifact,
  preflight behavior, scheduling policies, and performance/reliability measurements.

Encoding this only as a system requirement would state that Kanban should be efficient, but
would not allocate the mapper, optimization policy, capability preflight, or evidence needed
to prove improvement.

## Out of scope

- replacing or modifying Hermes' Kanban dispatcher, database, profiles, Goal mode, or worker
  lifecycle;
- building a generic scheduler outside the selected transport;
- inferring a new assurance floor from performance data;
- skipping required tests, reviews, simulations, human decisions, or evidence;
- hiding retries, continuation cards, dispatch failures, or gate failures;
- optimizing by silently selecting a different worker or transport;
- treating lower token use or faster completion as sufficient proof of success.

## Initial acceptance intent

For a representative Coherence feature plan, the system produces a deterministic Kanban
mapping that exposes critical path, legal parallel lanes, serialized conflicts, stage budgets,
gate batches, worker capability checks, and recovery behavior. It rejects or blocks invalid
mappings before execution, proves semantic equivalence with the source ExecutionProposal and
GatePlan, and records comparable performance/reliability evidence. At least one optimized
Kanban run demonstrates reduced avoidable orchestration overhead without loss of required
gates, evidence, traceability, human decisions, or final assurance semantics.

## Related requirements

<!-- derived — generated by `coherence mirrors generate`; do not edit -->
<!-- fingerprint: sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945 -->
- None yet; requirements are pending human-approved authoring.
<!-- end derived -->
