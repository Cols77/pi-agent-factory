---
id: cross-feat-semantic-overlap-detection-seed
title: "Cross-FEAT/SR semantic overlap detection at scale — seed"
status: seed
---

# Cross-FEAT/SR semantic overlap detection at scale — seed

> **Status: seed, not a design.** This captures the rationale for one new requirement
> ([[SR-058]]) discovered during FEAT-001's authoring-consent walkthrough, and records technical
> recon toward its eventual design. The recon below is a recommendation, not a commitment — the
> real design happens when this SR is planned, most likely against FEAT-017 PLANNING-BOOTSTRAP's
> actual authoring traffic rather than in the abstract here.

## What the walkthrough found

Answering whether FEAT-001 depends on [[SR-023]] surfaced that SR-050 reuses [[SR-023]] (FEAT-007)
and extends [[SR-049]] (FEAT-013) by explicit design-doc statement, with no typed relation
anywhere recording either link — see [[SR-057]], which this SR is deliberately kept separate
from. That case is a **declared-but-unformalized** relation: a human already wrote the connection
down in prose, [[SR-057]]'s generalized mirror check just needs to notice it went undeclared.

The question actually asked was broader: at hundreds or thousands of SRs and FEATs, how do you
reliably catch **semantic overlap that nobody wrote down anywhere** — two requirements making
overlapping or conflicting behavioral claims where neither author knew about the other, so there
is no prose mention for a mirror check to find? That is a fundamentally different detection
problem from [[SR-057]]'s: graph/text consistency checking (SR-057) finds gaps between what was
*declared* and what was *written*; this SR needs to find overlap between what was written and
*other things that were also written*, with no declared or narrated link between them at all —
similarity, not traversal.

## Why this is a distinct SR from SR-057, not the same one

Bundling them would repeat the exact over-broad-criterion mistake this walkthrough spent this
session correcting elsewhere (SR-001, SR-002, SR-004, SR-006, SR-050's narrowings). SR-057's
mechanism is deterministic: parse declared relations and prose mentions, diff them. This SR's
mechanism is necessarily probabilistic/statistical (text similarity) and needs a human or model
judgement on every flagged candidate — it can never be a `test_marker`-style pass/fail check the
way SR-057's generalized mirror can. Keeping them separate keeps each requirement's verification
story honest about what kind of claim it's actually making.

## Why this is one SR under FEAT-001, not a new FEAT

Same reasoning as [[SR-057]]: FEAT-001 REQ-TRACEABILITY already owns "connects requirements to
other trace nodes" as its mission, and already houses the two existing consistency mechanisms
this generalizes ([[SR-001]]'s mirror check, [[SR-057]]'s broader version of it). This SR extends
that mission to overlap nobody declared, rather than starting a parallel ownership home.

## Where it must actually run

The human's requirement: this must be part of the workflows that plan features and SRs, not only
a retroactive audit. That places its actual invocation inside [[FEAT-017]] PLANNING-BOOTSTRAP's
authoring pipeline — flagging candidate overlap **while a new SR or FEAT is being drafted**, so a
human sees "this looks like it overlaps SR-142" before committing the duplicate, not months later
in an audit report. FEAT-017 is the consumer; this SR still specifies the detection capability
itself, mirroring how [[SR-056]] was registered under a different FEAT than the one that will
eventually exercise it.

## Technical recon toward the eventual design (recommendation, not committed)

Two clearly separable layers, because they have different reliability guarantees and belong in
different parts of the system:

**Layer 1 — structural completeness (this is [[SR-057]]'s territory, not this SR's).** Declared
relations vs. prose mentions, diffed. Deterministic, `test_marker`-able, no model judgement
needed. Already scoped there; noted here only to draw the boundary.

**Layer 2 — semantic candidate generation (this SR).** The scale concern the human raised —
hundreds or thousands of SRs — rules out exhaustive pairwise comparison (that's already
`O(n²)`; at even one thousand SRs it's ~500,000 pairs, and each pair worth comparing needs a
model, not a diff). The standard, proportionate architecture for this corpus size:

1. Embed each requirement's statement + acceptance criteria text once, cached by content
   fingerprint (the same "recompute only what changed" pattern `substrate.freshness` already
   uses elsewhere in this codebase for the code index — this is not a new caching philosophy,
   just a new thing to cache).
2. Nearest-neighbor search per SR against every other SR's embedding, kept to a small top-K
   (e.g. 10). At the scale described (hundreds to low thousands of short texts), brute-force
   cosine similarity over an in-memory matrix is milliseconds — no specialized vector database
   is needed at this scale; that becomes worth revisiting only well past it.
3. Keep only candidate pairs that are BOTH highly similar AND carry no declared relation from
   Layer 1 — either signal alone is noisy (similar-and-declared is expected and fine; dissimilar-
   and-undeclared is just two unrelated SRs). This intersection is what turns a large corpus into
   a short, reviewable candidate list.
4. Hand only the surviving candidates to a model for adversarial judgement (the same
   verify-a-claim pattern already used this session for reviewing the manual-AC automation work)
   — never auto-declare a relation or auto-merge requirements. The output is a finding for a
   human to decide, matching this system's whole doctrine: the agent proposes, the substrate
   proves, a human decides.

**On "SQL perhaps?"** Not required for correctness or performance at the scale described —
hundreds to low thousands of SRs is comfortably an in-memory problem, and a client/server SQL
database would cut against this project's filesystem-first, no-external-service doctrine. SQLite
specifically (one embedded file, no server) is a reasonable, proportionate storage choice IF the
design wants ad hoc queryability (e.g. "every SR mentioning FEAT-013 with no declared relation"
as a real query) and a single place to hold both Layer 1's structural cache and Layer 2's
embedding vectors. Either way, whatever storage is chosen must stay a derived, disposable,
rebuildable-from-source cache, never a second system of record — the Markdown requirement files
stay authoritative, the same as every other derived artifact in this repository. If corpus size
ever moves past what brute-force in-memory search comfortably handles, the natural next step is
a lightweight embedded ANN structure (e.g. `sqlite-vec`), not a hosted vector database — but that
decision belongs to whoever designs this against real scale, not this seed.

## What the eventual SR should specify (not committed here)

- The embedding/similarity mechanism and its cache/storage (see recon above).
- The similarity threshold and candidate-list size that make review load proportionate to corpus
  size, and how that's tuned as the corpus grows.
- How a confirmed overlap finding is surfaced and to whom (FEAT-017's authoring flow, per above)
  versus how it's re-run retroactively over the existing corpus.
- Whether "overlap" here means near-duplicate claims, conflicting claims, or both — a
  precision decision this seed does not make.
