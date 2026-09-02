---
id: FEAT-019
title: "HOST-CONFORMANCE-DOGFOOD"
description: Host conformance dogfood verifies semantic equivalence across Coherence execution adapters.
requirements: []
---

# FEAT-019 — HOST-CONFORMANCE-DOGFOOD

Status: proposed feature dossier (first intent; requirements pending human-approved authoring).

This feature establishes a host-neutral conformance and dogfooding loop for Coherence
execution. It verifies that direct hosts, Hermes/Kanban, and future host/worker adapters
preserve the same run contract, workflow, gate, evidence, traceability, human-boundary, and
final-status semantics while using their native operational capabilities.

No SRs are assigned yet. Formal requirements must be derived from an approved design and
created through the existing human-consent process.

## Initial intent

Coherence should improve the way it implements its own features by exercising its own
planning and execution profiles. A host integration is not successful merely because an
agent starts, a Kanban card reaches `done`, or a plugin registers its tools. The conformance
loop must prove that the expected Coherence execution was materialized, observed, and
finalized without semantic loss.

The feature provides a durable feedback loop:

```text
Coherence feature slice
    → selected execution profile
    → host/transport run
    → conformance observations
    → deterministic reconciliation
    → failure/finding record
    → workflow/profile/adapter improvement
    → repeat dogfood run
```

The scope is intentionally host-neutral. Hermes is the first durable operational backend,
but the same conformance contract applies to Pi direct execution, Claude Code integration,
CI/headless execution, and future external workers.

## Conformance contract

Each adapter/transport must preserve at least:

- canonical run ID and immutable contract hash;
- selected workflow and GatePlan versions;
- stage identity, dependency, attempt, and transition semantics;
- declared workspace and file-scope boundaries;
- gate identity, requiredness, resolver, result, and evidence references;
- traceability links from task and produced artifacts to the owning feature/SR;
- human-review and teaching checkpoints without synthetic approval;
- retry, recovery, handoff, and interruption history;
- final evidence reconciliation and Coherence-owned run status.

The adapter may translate these records into native Hermes Kanban cards, worker prompts,
profiles, comments, or events, but it must not change their meaning.

## Deterministic conformance checks

The conformance harness compares the expected ExecutionProposal/RunContract with the
observed host execution. It must detect at minimum:

- missing, duplicated, orphaned, or unexpectedly added stages/tasks;
- changed parent/dependency links or invalid transition outcomes;
- contract, graph, workflow, or GatePlan hash mismatches;
- omitted, reordered, downgraded, or unknown required gates;
- missing resolver commands, evidence artifacts, or provenance fields;
- workspace/scope violations and invalid worker/profile assignments;
- capability mismatches and silent transport fallback;
- worker completion without the required structured observation;
- human gates that are auto-passed, bypassed, or resolved without a decision record;
- retries or stale-worker recovery that lose identity, evidence, or review history;
- a host reporting success when Coherence cannot reconcile required evidence.

A conformance failure creates a machine-readable finding and prevents the run from being
reported as semantically green. Operational completion and assurance completion remain
separate outcomes.

## Failure-injection and recovery coverage

The first dogfood matrix should exercise:

- unavailable worker profile;
- unavailable Hermes gateway or Kanban dispatcher;
- malformed or partially materialized graph;
- worker crash and stale-claim reclamation;
- bounded retry and fixer/re-review handoff;
- missing or stale evidence;
- contract/gate tampering;
- human-review interruption and resume;
- Goal-mode budget exhaustion;
- unsupported host capability;
- direct execution versus Kanban execution of the same contract.

Every case must record the expected result, observed result, evidence, and whether the
adapter failed closed. No profile may silently downgrade a governed run to advisory or
unvalidated execution.

## Coherence self-dogfooding

Coherence should use this feature to run representative slices of its own roadmap through
multiple profiles. The initial matrix should include at least:

- a direct single-agent governed run;
- a durable Hermes Kanban run;
- an interactive human-gated run;
- a simulation/behavior-change run where applicable;
- a headless validation run;
- a blocked-capability run proving explicit failure rather than fallback.

The results become durable evidence and findings, not informal agent summaries. Repeated
failures should feed approved changes to workflows, profiles, gate contracts, adapters, or
skills through their respective change-control paths.

## Hermes integration boundary

Hermes already supplies the operational primitives this feature should reuse: durable
Kanban state, dependencies, named profiles, worker lifecycle, retries, workspaces, Goal-mode
cards, review handoffs, dashboard views, plugin hooks, MCP, skills, and programmatic APIs.

A Hermes plugin, MCP server, or skill may provide the adapter and user experience. It cannot
become the Coherence acceptance authority. Skills provide procedure and context; plugins and
MCP provide integration surfaces; Coherence performs the deterministic conformance checks
and final semantic reconciliation.

This feature must not fork Hermes, rebuild Kanban, or assume that a community skill is an
enforcement mechanism. Community components may be evaluated as adapters or convenience
layers, but only a versioned Coherence contract and conformance result can authorize a
governed run.

## Out of scope

- replacing Hermes Kanban, Goal mode, profiles, plugins, or skills;
- building a second generic scheduler or worker runtime;
- defining workflow semantics or the gate taxonomy;
- allowing conformance tests to rewrite active contracts;
- treating a passing plugin-load check or Kanban `done` state as assurance success;
- silently falling back when a requested host capability is unavailable.

## Initial acceptance intent

The same representative Coherence run can be exercised through direct and Hermes-backed
profiles, with equivalent stage/gate/evidence semantics and independently verifiable final
status. The harness deterministically detects materialization drift, gate loss, evidence loss,
human-boundary bypass, scope violations, recovery-history loss, and silent capability
fallback. Coherence can use the harness to identify and correct execution issues in its own
feature-development workflow without duplicating Hermes operational infrastructure.

## Related requirements

<!-- derived — generated by `coherence mirrors generate`; do not edit -->
<!-- fingerprint: sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945 -->
- None yet; requirements are pending human-approved authoring.
<!-- end derived -->
