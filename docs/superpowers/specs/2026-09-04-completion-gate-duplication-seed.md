---
id: completion-gate-duplication-seed
title: "Two completion-gate authorities must not silently diverge — seed"
status: seed
---

# Two completion-gate authorities must not silently diverge — seed

> **Status: seed, not a design.** This captures the rationale for one new requirement
> ([[SR-063]]) discovered while scoping [[SR-050]] T3 (the implementation-workflow relation
> obligation), and records recon toward its eventual design. Not committed here.

## What the walkthrough found

Scoping T3 ("require an implementation task that changes production/validation code to declare
the affected SRs and update their relations before completion") meant finding where a task's
completion is actually decided. That turned out to be two places, not one:

- `coherence.policy.compiler.compile_obligations` — the durable Obligation model every prior
  SR-050 step (T1/T4/T5) built against, consumed by `coherence navigate present --why-required`
  and `obligations_open_count`, reading from the durable evidence store
  (`coherence.trace.validation_status.load_validation`) and the trace graph.
- `factory.preflight.checks.run_completion_preflight` — the function actually wired into the live
  orchestrator (`factory/orchestrator/runner.py`): its `BLOCKING` issues flip a real run's outcome
  to `"escalated"` and send the task back to `todo`, *before* the run's own evidence manifest is
  even written. It reads `transcript_dir/validation-report.json` and `transcript_dir/reviews/*.json`
  directly — this run's own live, not-yet-persisted output — and has never consulted
  `compile_obligations` for its `validation_missing`/`validation_failed`/`validation_stale`/
  `review_missing`/`must_fix_unresolved` checks.

Confirmed directly (not assumed): `factory.trace.graph`, which `run_completion_preflight` already
imports `build_graph` from, is itself a deprecated re-export of `coherence.trace.graph` — same for
`factory.orchestrator.ledger` (→ `substrate.ledger.tasks`) and `factory.requirements.register` (→
`coherence.register.register`). The live gate already runs on `coherence`'s own graph/register
objects under a legacy import path; only the validation/review issue-construction logic itself
still duplicates what a durable Obligation would say, and duplicates it against *different* data
(this run's live transcript vs. the durable evidence store already on disk) — not a like-for-like
duplicate, an actual timing mismatch.

## Why this cannot be "just point the live gate at compile_obligations"

At the moment `run_completion_preflight` runs, the current run's own evidence manifest does not
exist yet in `evidence/runs/` — `finalize_run_evidence` writes it afterward. A durable Obligation
built from `load_validation(root)` would therefore be blind to the very validation this run just
performed (it would see only prior runs' evidence, stale or absent). The same is true of
`review_missing`/`must_fix_unresolved`, which read this run's own `transcript_dir/reviews/*.json` —
a live/ephemeral artifact the durable Obligation model has no channel for at all today. A naive
swap would regress these three checks, not unify them.

SR-050 T3 resolves this pragmatically for its own new check (relation-maintenance has no legacy
duplicate to reconcile — it is wired into `compile_obligations` and the live gate together, from
day one). It deliberately leaves `validation_missing`/`validation_failed`/`validation_stale`/
`review_missing`/`must_fix_unresolved` untouched. That leaves the corpus-wide question open:
should the durable Obligation model eventually be able to see live, in-flight run state (so the
legacy checks can retire into it too), or should the two stay permanently separate because they
answer genuinely different questions ("what does the durable record show" vs. "did the run that
just happened succeed")?

## Why this is FEAT-002's territory, not FEAT-001's

The defect lives in obligation compilation and in the live gate that duplicates it
(`factory.preflight.checks`), which is [[FEAT-002]] PROGRESSIVE-ASSURANCE's territory ("compiles
project policy into explicit obligations ... health states") — the same reasoning
[[SR-059]] already used for the adjacent `_human_review_obligation` requiredness-floor gap. It is
not the trace/register mechanism [[SR-050]]/[[SR-057]]/[[SR-058]] extend, which correctly stayed
under [[FEAT-001]].

## What the eventual SR should specify (not committed here)

- Whether the durable Obligation model gains an explicit, typed channel for a run's own live,
  not-yet-persisted validation/review output (so `run_completion_preflight` could fully delegate),
  or whether "durable record" vs. "this run's own result" are kept as two permanently distinct,
  clearly-named checks rather than merged.
- If a live channel is added: how it expires/invalidates once the run finalizes and the durable
  evidence store gains the authoritative record, so the two never disagree silently.
- Whether `factory.preflight.checks` should be renamed/relocated once it is coherence-backed
  end-to-end, given every one of its current imports already resolves through a deprecated
  `factory.*` shim.
