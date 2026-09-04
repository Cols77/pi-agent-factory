---
id: coherence-tooling-performance-seed
title: "Coherence tooling must stay usable as the corpus grows — seed"
status: seed
---

# Coherence tooling must stay usable as the corpus grows — seed

> **Status: seed, not a design.** This captures the rationale for one new requirement
> ([[SR-064]]), raised directly by the user while scoping [[SR-050]] T3, and records recon toward
> its eventual design. Not committed here.

## What prompted this

Every FEAT-001 review mechanism built so far (`coherence register review`, `--fidelity`,
`overlap-check`) is correct today, against today's corpus size (dozens of SRs, a handful of
evidence manifests). None of them has a stated performance budget or has been measured against a
larger corpus:

- `coherence.register.review.unaccounted_changed_files`/`evidence_reconciliation_review` load and
  re-parse every requirement's frontmatter and every evidence manifest under `evidence/runs/` on
  each call — no incremental/cached mode.
- `coherence.register.overlap.py` (SR-058) already ships a content-fingerprint cache specifically
  because naive TF-IDF-over-everything was recognized as a scaling risk at design time — the one
  place this concern was already addressed proactively.
- `coherence.policy.compile_obligations` and `coherence.trace.gaps.find_gaps` re-derive the whole
  trace graph on most calls; `coherence.navigate.health` loads it repeatedly across dimensions
  (partially mitigated today by `nodes=`/`edges=` passthrough parameters, not by caching).
- SR-050 T3 (this session) adds one more per-task, per-run reconciliation pass over evidence
  manifests and SR relations — a plausible incremental cost today, an unknown one at real scale.

None of this is a known bug yet. It is an unmeasured, unbounded cost across a system whose whole
premise is running on every task/SR/run as the corpus grows — the user's own framing was avoiding
"a horrible user experience of the whole coherence system when it scales."

## Why this is not fixed by "profile everything now"

Optimizing before measuring risks solving the wrong bottleneck (SR-058's own overlap module
already shows the right instinct: it flagged real embeddings/RAG as deferred future work rather
than building it speculatively). What's missing is not a fix but the requirement itself: a stated
budget, a way to measure against it, and an obligation that the tools stay within it as the corpus
grows — so a future regression has something concrete to fail against, rather than being noticed
only once real usage already hurts.

## What the eventual SR should specify (not committed here)

- What "the corpus" means for a budget: SR count, task count, evidence-manifest count, or all
  three, and at what target scale (10x today's? 100x?) the budget must hold.
- Which operations are in scope: at minimum every `coherence register review`/`overlap-check`/
  `navigate health`/`policy compile_obligations` call path named above; whether CLI/dashboard
  latency and CI-gate wall-clock time are one budget or two.
- Mechanism: a benchmark/regression-test harness with fixture corpora at multiple sizes, run in CI
  or on demand; whether caching (mirroring SR-058's fingerprint cache) or incremental
  recomputation is the general-purpose answer, decided per hot path rather than assumed uniformly.
- Whether this is one requirement or several once real hot paths are profiled — this seed
  deliberately does not commit to a single mechanism up front.
