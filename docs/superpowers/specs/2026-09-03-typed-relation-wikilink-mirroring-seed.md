---
id: typed-relation-wikilink-mirroring-seed
title: "Typed-relation wikilink mirroring across artifact families — seed"
status: seed
---

# Typed-relation wikilink mirroring across artifact families — seed

> **Status: seed, not a design.** This captures the rationale for one new requirement
> ([[SR-057]]) discovered during FEAT-001's authoring-consent walkthrough, so the requirement has
> a real source anchor. It is deliberately minimal. The full design — which node kinds declare
> which typed relation fields, the exact new `GapKind` name for an uncovered spec, and how far
> "other artifacts" extends beyond specs — is not committed here.

## What the walkthrough found

While presenting [[SR-003]] (spec frontmatter as canonical `spec:<id>` trace nodes) for
authoring consent, the human asked whether a spec should be required to have at least one
covering system requirement, mirrored as an `[[id]]` wikilink the same way [[SR-001]]/AC-3
already requires for a requirement's own `upstream` field. Checking the code before answering
found the gap is real and larger than one missing acceptance criterion:

- `missing_upstream_wikilinks()` (`src/coherence/register/register.py`, the mechanism SR-001/AC-3
  binds to) only ever reads a **requirement's** `upstream` field. No other artifact family's
  typed relations are checked for a wikilink mirror at all.
- `spec_ref` edges — the only relation that currently touches a `spec:` node — are built
  exclusively from a **plan's** frontmatter/body (`trace/model.py`'s `edges_from_frontmatter`,
  the `plan` branch). Nothing lets a requirement declare a spec as covered; the relation doesn't
  exist, not just the check.
- `trace/gaps.py`'s `GapKind` taxonomy has `plan_no_spec` (a plan must reference >= 1 spec) but
  nothing in the reverse direction — no gap reports a spec that no requirement's declared
  relation reaches.

[[SR-001]]'s own AC-3 narrowing note (2026-09-02) already anticipated needing "a broader
typed-relation vocabulary (`relates_to`, `distinguished_from`, ...)" before its dropped reverse-
wikilink direction could become well-defined, and pointed at "[[SR-056]]'s territory" for it.
That citation was wrong — SR-056 turned out to be [[SR-056]] Progressive review-decision
presentation, an unrelated capability registered the same day. SR-001's body note is corrected to
point at this SR instead as part of registering it.

## Why this is one SR under FEAT-001, not a new FEAT

FEAT-001 REQ-TRACEABILITY already owns exactly this mechanism: it registers requirements and
connects them to other trace nodes, and already houses both halves of this gap — [[SR-001]]
(the existing, narrower wikilink-mirror check) and [[SR-003]] (the spec node this SR gives a
real inbound relation to). Generalizing an existing FEAT-001 mechanism belongs in FEAT-001, not
a new feature.

## What the eventual SR should specify (not committed here)

- A typed relation letting a requirement declare a spec (and, if warranted on review, other
  artifact families) as covered — not overloading `upstream`, which SR-001/AC-3 already scopes
  to requirement-to-requirement relations.
- Generalizing `missing_upstream_wikilinks()` (or a successor) so the wikilink-mirror check runs
  against every artifact family's own typed relation fields, not only a requirement's `upstream`.
- A new `GapKind` (mirroring `plan_no_spec`'s shape) reporting a spec that no requirement's
  declared relation reaches, surfaced through `trace/gaps.py` the same way every other lifecycle
  gap is.
- Whether "other artifacts" extends this beyond specs (to features, plans, goals, ...) or stays
  scoped to the spec-coverage gap this walkthrough actually found — a design decision, not
  assumed here.
