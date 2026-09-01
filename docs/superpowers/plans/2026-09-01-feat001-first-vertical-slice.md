---
spec: coherence-product-definition
---

# FEAT-001 REQ-TRACEABILITY — First Vertical Slice

**Date:** 2026-09-01 · **Status:** plan, ready to execute
**Parent spec:** [[2026-09-01-coherence-product-definition]] (D-P4, D-P6, D-P8, D-P14)
**Feature:** [[FEAT-001]] · **Profile:** `high_assurance`
**SRs in scope:** [[SR-001]] [[SR-002]] [[SR-003]] [[SR-004]] [[SR-005]] [[SR-006]] [[SR-007]] [[SR-050]]

---

## 1. Why this feature first

It is the only candidate that satisfies all four selection criteria:

- **Fully implemented** — `coherence/trace/`, `coherence/register/`, `coherence/course/`,
  `substrate/codemap/`, `substrate/kb/` are all on `main`.
- **Tests already exist** — see the binding table in §4. This slice mostly *binds* existing
  evidence rather than writing new tests.
- **Criteria are concrete** — "fail deterministically on duplicate spec ids", "collect pytest SR
  markers", "resolve every course-note id" are directly testable sentences.
- **It is a retrofit** — the right answer is already known, so a wrong result indicts the
  machinery rather than the feature. That is the point of a first slice.

Everything downstream depends on it: if trace and register cannot prove themselves, no other
feature's evidence can be trusted.

## 1a. This slice is also FEAT-017's specification (D-P18)

FEAT-001 is the **one** feature registered by hand. Everything after FEAT-002 registers through
[[FEAT-017]] PLANNING-BOOTSTRAP. That makes this slice dual-purpose: it produces FEAT-001's
evidence *and* the input specification for the bootstrap pipeline.

Practically: **record what you actually did, as you do it** — the ordered steps, the artifacts
each one read and wrote, the decision points, and every place the process was ambiguous or you
had to choose. Ambiguities are the most valuable output; they are the decisions FEAT-017 will
otherwise have to invent. Write them to `T-9`'s reference-run record (§4, T-9).

FEAT-017 cannot be built before this. Its own design lists SR authoring, feature registration
and human consent as already-built prerequisites it *composes* — and those are exactly what is
unproven here. Building bootstrap first would automate a pipeline nobody has run, and would make
bootstrap defects indistinguishable from requirements-model defects.

## 2. What this slice proves

The full loop, end to end, for the first time:

```
author SRs + acceptance criteria
  → human authoring consent (gate DecisionFile)
    → bind criteria to existing tests (@pytest.mark.sr)
      → execute evidence (verification_result obligation)
        → human_review (high_assurance)
          → re-run health
```

**Exit condition:** `coherence navigate health --json` reports FEAT-001's 8 SRs as satisfied
with recorded evidence, and `coherence register check` no longer lists them as unaccounted.

## 3. Ground truth at slice start (verified 2026-09-01)

| Signal | Value |
|---|---|
| `SR satisfied` | 0/55 |
| `SR validated` | 0/0 |
| `executed_evidence` | 0/55 |
| `human_review` | 0/0 |
| `implementation_trace` | 2/24 |
| health | 39% |
| SRs accounted by measurement/task/deferral | 0 |
| **Real `@pytest.mark.sr` decorators in the repo** | **0** |

That last row is the headline. The marker is registered in `pyproject.toml`, `collect_markers`
is implemented and tested, and SR-006 requires it — but every occurrence in the repo is a string
literal inside tests *of the collector*. **No production test has ever been bound to an SR.**
This slice is the first real use of a mechanism that has been built and unused.

## 4. Task breakdown

### T-1 — Add the `acceptance:` schema field

Extend the SR schema (and its validator) with an optional `acceptance:` array. Each entry:

```yaml
acceptance:
  - id: AC-1
    criterion: "A spec carrying duplicate ids with differing content fails deterministically."
    verification:
      kind: test_marker          # test_marker | harness | manual
      ref: "tests/unit/coherence/trace/test_spec_frontmatter.py"
```

`kind: manual` carries `reason:` and satisfies only via a `human_review` decision.

**Verify:** an SR with a malformed `acceptance` entry is rejected at load, not silently ignored.
**Acceptance:** schema round-trips; existing 55 SRs without `acceptance:` still load unchanged
(the field is optional, so this is additive — D3 backward-compatibility).

### T-2 — Give `requirement_quality` a real criterion (closes NC-B, first half)

`compile_health_dimensions` currently sets `req_quality_ok = len(sr_nodes)` — structurally
incapable of failing. Replace with: **an SR counts only when it carries at least one acceptance
criterion with a resolvable verification binding.**

**Verify:** on the current register the dimension drops from 55/55 to ~0/55 and rises as this
slice lands. A dimension that moves is a dimension that measures something.
**Acceptance:** a unit test asserts an SR with no `acceptance:` does not count.

> Do **not** fix `verification_strategy` (NC-B second half) in this slice. It belongs with
> FEAT-002, which owns the obligation compiler. Record it, leave it.

### T-3 — Author acceptance criteria for the 8 SRs

Derive criteria from each SR's `source:` anchor, not from the code — otherwise criteria describe
what was built rather than what was required. Where source and code disagree, that is a finding,
not something to reconcile silently.

Expected shape (indicative, to be settled during authoring):

| SR | Criteria | Binds to |
|---|---|---|
| SR-002 | register closure: proposed / measured / accounted | `tests/unit/requirements/test_register.py` |
| SR-003 | frontmatter-authoritative spec node; duplicate ids fail deterministically; missing frontmatter degrades to filename node | `tests/unit/coherence/test_artifact_families.py` |
| SR-004 | one code map merging symbols + import edges; overlap computed from a single parser | `tests/unit/substrate/test_codemap_imports.py`, `test_codemap_resolver.py` |
| SR-005 | every course-note id resolves; unknown id fails; unreached SRs/specs reported | `tests/unit/coherence/test_course.py` |
| SR-006 | markers collected into the register; bound SR whose experiment names an unmarked file fails the gate | `tests/unit/coherence/test_register_markers.py` |
| SR-007 | KB entries selected by error signature and reached symbols | `tests/unit/substrate/test_kb_signatures.py`, `tests/unit/test_kb_index.py` |
| SR-001 | navigation across the declared lifecycle relations; missing links surface as gaps | `tests/unit/coherence/test_snapshot_navigation.py` + new |
| SR-050 | per-SR review reports structural / evidence / semantic findings separately; agent verdict not authoritative until gated | new |

SR-001 and SR-050 are expected to need new tests. **That is the useful signal** — they are the
two SRs whose sources are the engineering-context HLRs and the newest design, and they are the
least covered. Do not paper over it by binding them to loosely-related tests.

### T-4 — Human authoring consent

Route all 8 through the gate `DecisionFile` (`accept | reject | defer`, reason required on
reject/defer). Not chat narration, not a bulk approval.

**Verify:** a decision file exists per SR under the gate store; `register check` reflects the
outcome.
**Acceptance:** every SR has an explicit accept or decline. An agent cannot self-certify this
step (SR-044, I-01).

### T-5 — Bind the markers

Add real `@pytest.mark.sr("SR-###")` decorators to the tests named in T-3. **First production
use of the marker system.** Expect to find defects in `collect_markers` — it has only ever run
against fixtures.

**Verify:** `coherence register check` surfaces the marker findings; the `test_marker`
obligation compiles as `blocking` for FEAT-001's SRs under `high_assurance`.
**Acceptance:** every bound SR's experiment resolves to a file carrying a matching marker.

### T-6 — Execute evidence and record manifests

Run the gates; record `verification_result` observations for each SR.

**Verify:** `executed_evidence` moves off 0 for FEAT-001's 8 SRs; a manifest is inspectable on
disk for at least one blocking SR.
**Acceptance:** no SR in FEAT-001 remains "no measurement, task, or deferral."

### T-7 — Generated wikilink mirrors (D-P8)

Make the `## Related requirements` block derived output: regenerated from `requirements:`
frontmatter plus the trace graph, fingerprinted, marked *derived — do not edit*, with a check
that fails on divergence.

**Verify:** FEAT-006's `![[SR-019]]` embed defect (NC-D) is corrected by regeneration, not by
hand, and reintroducing it fails the check.
**Acceptance:** every FEAT's mirror matches its frontmatter exactly.

### T-8 — `human_review` and close

FEAT-001 is `high_assurance`, so `human_review` compiles as `blocking`. Real human entries; an
agent cannot produce them.

**Verify:** re-run `coherence navigate health --json`; FEAT-001's dimensions move.
**Acceptance:** the slice's exit condition (§2) holds, evidenced by command output rather than
by prose.

### T-9 — Record the reference run (FEAT-017's input spec)

Written *during* T-3..T-8, not reconstructed afterwards. Produce
`docs/superpowers/plans/2026-09-01-feat001-reference-run.md` capturing:

- The ordered steps actually performed, with the command or edit each one was.
- Inputs and outputs per step: which artifact was read, which was written, by whom (agent or
  human), and which step is a human boundary that cannot be automated.
- Every ambiguity encountered and how it was resolved — these are the decisions FEAT-017 would
  otherwise invent.
- Anything that turned out to be wrong in this plan. A plan that survived contact unchanged is
  usually a plan nobody followed.

**Verify:** the record contains a step list an implementer could follow to register FEAT-002 by
hand without reading this plan.
**Acceptance:** FEAT-017's design cites this record as its source, and FEAT-017's acceptance test
is "registering FEAT-002 through bootstrap reproduces the shape FEAT-001 reached manually."

## 5. Out of scope

- Authoring SRs for any other feature. This is a vertical slice (D-P14); horizontal declaration
  is what produced 0/55.
- NC-A (the layering cycle) — belongs to FEAT-000.
- `verification_strategy` (NC-B second half) — belongs to FEAT-002.
- The console, the transition surface, the bootstrap front door.

## 6. Risks

- **`collect_markers` has never run in production.** Budget for defects; this is its first real
  exercise.
- **T-2 will make health look worse before better.** `requirement_quality` drops from 55/55 to
  near zero. That is the correct behaviour of a dimension that was previously lying, and should
  not be treated as a regression.
- **SR-001 and SR-050 may not be evidenceable as written.** If so, the honest outcome is a
  narrowed SR or a recorded gap — not a stretched binding to an unrelated test.
- **`human_review` depends on the user.** No agent can discharge T-4 or T-8.
