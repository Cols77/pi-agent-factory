---
id: SPEC-FEAT-017-PLANNING-SCHEMA2-TRANSPORT
title: "FEAT-017 planning schema-2 transport boundary"
status: draft
feature: FEAT-017
requirements:
  - SR-065
  - SR-071
---

# FEAT-017 planning schema-2 transport boundary

## Decision

The planning workflow has one externally visible transport schema: `schema: 2`.
The legacy `schema: 1` legal-actions projection and the legacy `schema: 1`
guided-host envelopes are rejected, not normalized or guessed.

This is a breaking contract migration because schema 1 carries no lifecycle
state, run identity, or action-registry integrity. Keeping it in the host
surface would leave two contracts for the same workflow and allow stale hosts
to present weaker evidence.

## Scope

The migration covers:

- the canonical `coherence plan legal-actions` projection and its shared
  Codex/Hermes adapter;
- capture-session and guided-pipeline response envelopes used by host
  adapters;
- Hermes transport validation, the Codex skill helper, the Claude command,
  README examples, and contract fixtures/tests.

The migration does not rewrite unrelated persisted schemas such as audit,
codemap, gate-decision, manifest, planning-report, consent, handoff, journal,
or evidence records. Those records remain internal producer contracts in this
slice. The nested `action_registry.schema: 1` remains the registry-version
field; it is not the outer planning transport schema.

## Contract

`legal-actions` must return schema 2 with the exact requested `run_id`, a
boolean `blocked`, a nullable `reason`, at most one `legal_next_actions` item,
`starts_automatically: false`, lifecycle `state`, a hash-bound `run_identity`
when ready, and the action registry/hash. A blocked response must carry
`run_identity: null`, a reason, and no action. Any schema-1 projection,
missing field, mismatch, malformed digest, multiple action, or contradictory
ready/block state is invalid.

All other guided planning host responses use schema 2 plus their existing
verb-specific fields and exact run ID. Internal persisted payloads may retain
their own schema versions when they are not host transport envelopes.

## Failure behavior

Hosts fail closed on schema 1, schema mismatch, run-ID mismatch, malformed
per-verb data, unsafe project-root options, unsafe run IDs, unexpected backend
exit codes, and invalid JSON. No host starts a run, selects an action, grants
consent, or launches downstream work because a transport response is malformed.

## Traceability

The implementation is an extension of FEAT-017's existing guided entrypoint
and read-only lifecycle projection. Focused contract tests carry SR-065 and
SR-071 pytest markers for later measurement; the current requirement records
remain proposed and the commit carries the same SR trailer.
