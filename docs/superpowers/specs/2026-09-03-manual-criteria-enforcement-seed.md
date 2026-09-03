---
id: manual-criteria-enforcement-seed
title: "Manual criteria must not silently rot — seed"
status: seed
---

# Manual criteria must not silently rot — seed

> **Status: seed, not a design.** This captures the rationale for one new requirement
> ([[SR-059]]) discovered while splitting [[SR-050]]/AC-2 into AC-2 and AC-4, and records recon
> toward its eventual design. Not committed here.

## What the walkthrough found

Pushing back on "AC-1/AC-2 stay manual because there's no implementation" surfaced a sharper,
corpus-wide question: manual review is not just labor-intensive at scale, it can be **structurally
unenforced**. Checked directly against `src/coherence/policy/compiler.py`'s
`_human_review_obligation`:

```python
requiredness = "blocking" if profile == "high_assurance" else "not_applicable"
```

Outside `high_assurance`, a `human_review` obligation compiles to `not_applicable` — not
`WARNING`, not visible-but-non-gating like [[SR-006]]'s `test_marker` graduation, but literally
not required at all. Under this repository's own default (`prototype`) profile, a `manual`-kind
acceptance criterion's human review is not merely easy to forget — nothing in the system asks for
it. This affects every `manual` criterion in the corpus, not only [[SR-050]]'s.

## Why this is not fixed by "just automate everything"

Some manual criteria (per [[SR-050]]/AC-1, the structural half of AC-2) are manual only because a
capability doesn't exist yet; once built they become a bare deterministic `test_marker` with zero
judgement involved. Others ([[SR-050]]/AC-4, fidelity) are manual because the underlying claim is
inherently a judgement call — whether a link genuinely substantiates a requirement's claim is not
a graph fact a test can assert, however good the tooling gets. The fix cannot be "eliminate manual
review"; it must be "make reliance on agent-assisted review with human consent as trustworthy,
trackable, and impossible to silently skip as a passing automated check is." [[SR-050]]/AC-3
already proves the mechanism for one specific gate (`human_review`/`review:<sr_id>`): an
attributed, correctly-scoped `accept` decision, fail-closed on everything else. What's missing is
making that mechanism's own *requiredness* profile-independent, and generalizing it as a real
verification kind other criteria across the corpus can bind to, rather than a bespoke case.

## Why this is one SR under FEAT-002, not FEAT-001

The defect lives in obligation compilation (`_human_review_obligation`'s profile-graduated
`requiredness`), which is [[FEAT-002]] PROGRESSIVE-ASSURANCE's territory ("compiles project policy
into explicit obligations ... health states"), not the trace/register mechanism [[SR-057]] and
[[SR-058]] extend (both correctly stayed under [[FEAT-001]]). A candidate implementation touchpoint
is register.py's `verification.kind` vocabulary (`test_marker` / `manual` today) — formalizing a
third kind for "agent-reviewed, gate-enforced" evidence would live there, in FEAT-001 — but the
requirement's own claim (manual-equivalent evidence must not silently rot) is a policy/obligation
claim, so FEAT-002 owns it.

## What the eventual SR should specify (not committed here)

- Whether `human_review`-equivalent requiredness should be profile-independent (always at least
  visible, e.g. WARNING under every profile, blocking only under `high_assurance` — mirroring
  [[SR-006]]'s already-accepted profile-graduation pattern for `test_marker`, rather than
  `not_applicable` anywhere) or something else.
- Whether "agent-reviewed with human consent" becomes a named third `verification.kind` in
  register.py's schema (alongside `test_marker`/`manual`), with its own deterministic freshness
  and escalation contract, or stays modeled as `manual` with a required, checked
  `review:<sr_id>` gate decision.
- How staleness/expiry applies: a `human_review` accept recorded once should not silently cover
  a requirement whose statement or acceptance criteria later change without a fresh decision
  (an analogous concern to `is_checksum_current`'s existing binding-staleness check in
  `coherence.register.register`, generalized to review decisions).
