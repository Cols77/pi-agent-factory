---
spec: coherence-product-definition
plan: 2026-09-01-feat001-first-vertical-slice
---

# FEAT-001 Reference Run — the record of how one feature was registered by hand

**Date:** 2026-09-01 · **Status:** written during the run, not reconstructed
**Parent plan:** [[2026-09-01-feat001-first-vertical-slice]] · **Parent spec:**
[[2026-09-01-coherence-product-definition]] (D-P18)

---

## 0. What this document is for

FEAT-001 is the one feature registered by hand. Every feature after FEAT-002 registers through
[[FEAT-017]] PLANNING-BOOTSTRAP. This record is FEAT-017's input specification: the ordered steps
actually performed, what each read and wrote, who performed it (agent or human), and — most
valuably — **every place the process was ambiguous and how the ambiguity was resolved**. Those
ambiguities are the decisions FEAT-017 would otherwise have to invent.

Read §3 as the step list. Read §4 as the decision set FEAT-017 must encode. Read §5 for what this
plan got wrong.

**Convention.** Each step is `S-<n>`. `Actor` is `agent` or `human`; a `human` step is a boundary
that cannot be automated, and FEAT-017 must model it as a queue-and-wait, never as a step it
performs.

---

## 1. Ground truth this run started from

Verified in the worktree immediately before S-1:

| Signal | Value |
|---|---|
| `requirement_quality` | 55/55 (structurally incapable of failing — NC-B) |
| `verification_strategy` | 55/55 (same defect, second half) |
| `executed_evidence` | 0/55 |
| `validation_scenarios` | 0/55 |
| `implementation_trace` | 2/24 |
| `human_review` | 0/0 |
| `decomposition_allocation` | 17/20 |
| `deferrals_waivers` | 57/173 |
| Real `@pytest.mark.sr` decorators in the repo | 0 |
| Shape | 55 requirements · 17 features · 24 tasks · 0 validated |

---

## 2. Setup (before any task)

| Step | Actor | Did | Read | Wrote |
|---|---|---|---|---|
| S-0a | agent | Committed the pending corpus (product-definition spec, slice plan, SR-050..055, FEAT-018..020, register index) as a baseline commit so the slice starts from a known tree | working tree | commit `edd7bdb` on `feat/feat001-slice` |
| S-0b | agent | Created an isolated worktree `pi-agent-factory-wt/feat001-slice`; left the shared root checkout on `main` | — | worktree |
| S-0c | agent | Recorded the baseline signals above | `coherence navigate health --json` | ledger |
| S-0d | agent | Pre-flight scan of the plan for cross-task and internal conflicts; ruled on five before execution | plan, parent spec | ledger rulings R-1..R-5 |

**Ambiguity A-0 (setup).** The plan assumes a clean tree. The real tree carried 75 uncommitted
files of corpus work, including the two documents the plan is *about*. Registering a feature
therefore begins with a step the plan does not name: **establish a committed baseline**, because
evidence with no commit to anchor to has no provenance (I-04). FEAT-017 must own this step.

---

## 3. The steps

<!-- appended as each task completes -->

### S-1 — Give the requirement schema a place to hold testable detail

| | |
|---|---|
| **Actor** | agent |
| **Reads** | `src/coherence/register/register.py` (the SR model, `parse_requirement`, `content_checksum`); the slice plan's T-1 field example |
| **Writes** | `src/coherence/register/register.py`, `tests/unit/requirements/test_acceptance.py` |
| **Command** | `rtk proxy uv run pytest tests/unit/requirements/ tests/unit/coherence/ -q` |
| **Commits** | `1e884d6`, `7d52c3e` |

Before anything can be *proved*, a requirement needs something provable in it. An SR carried a
statement and, optionally, a single `binding:`. That is one measurement for a whole decision-grain
requirement — too coarse to bind a test to. S-1 adds an optional `acceptance:` array: a tuple of
individually addressable criteria, each with its own verification method.

Landed shape:

```yaml
acceptance:
  - id: AC-1
    criterion: "A spec carrying duplicate ids with differing content fails deterministically."
    verification:
      kind: test_marker            # test_marker | harness | manual
      ref: "tests/unit/coherence/trace/test_spec_frontmatter.py"
```

- `VerificationBinding(kind, ref=None, reason=None)` — `test_marker` and `harness` require a
  non-blank `ref`; `manual` requires a non-blank `reason` and satisfies only via `human_review`.
- `AcceptanceCriterion(id, criterion, verification)` with `.qualified_id(req_id)` returning the
  `SR-###/AC-#` address form.
- `Requirement.acceptance: tuple[AcceptanceCriterion, ...] = ()`.

**The rule that made this safe: optional, but strict when present.** `parse_requirement` calls the
acceptance parser only when the key is in the frontmatter, so all 55 existing SRs parse byte-for-byte
as before and `requirements/index.json` is unchanged. When the key *is* present, any malformed entry
raises and the whole requirement is rejected — never partially kept. Silently dropping a malformed
criterion would violate I-03 (missing evidence is reported, never inferred) by turning an unverifiable
requirement into an apparently-fine one.

**Two things checked because they would have failed silently.** `content_checksum` hashes only the
statement and binding fields, never `acceptance` — so adding the field did not invalidate 55 stamped
checksums. `cmd_index` builds its output dict field-by-field rather than via `dataclasses.asdict`, so
`index.json` could not pick the new field up. Both were verified against the code, not assumed.

**Review outcome.** Spec-compliant on the first pass; one Important finding on test quality (below),
fixed in round 1.



---

## 4. Ambiguities and how they were resolved

<!-- appended as each is encountered; these are FEAT-017's decision set -->

| ID | Ambiguity | Resolution | Why |
|---|---|---|---|
| A-0 | The plan assumes a clean tree; the real one had 75 uncommitted files | Commit a baseline first, as a named step | Evidence without a commit anchor has no provenance (I-04) |
| A-1 | The plan's example binds a criterion to a test *file path* (`ref:`), but the marker system binds SR→test with an in-file `@pytest.mark.sr` decorator. Two sources for one fact. | The decorator is authoritative for what a test proves; `ref:` is a navigational pointer that must be *consistent* with it, checked at S-4. | Two independent bindings for one fact drift apart — the exact failure NC-D records for FEAT-006's hand-maintained mirror |
| A-2 | "An SR counts only when it carries an acceptance criterion with a *resolvable* verification binding" — resolvable how? Well-formed? Path exists? Marker matches? | Well-formed AND the `ref:` target exists on disk. Not "marker matches" — that is the marker gate's job and would make the dimension a duplicate of it. | A criterion pointing at a deleted file must not count; that is the class of lying the dimension exists to stop |
| A-3 | Tests asserting only that *something* raised look like coverage but prove nothing about *which* rejection fired. | Every malformed-case assertion must name the distinguishing part of the message, and must fail if the parser reported a different one of the 13 cases. | Thirteen tests that cannot tell each other's failures apart are one test wearing thirteen hats |

---

## 5. What this plan got wrong

<!-- appended as discovered -->

---

## 6. Step list for registering the next feature by hand

<!-- written at the end, from §3, and checkable without reading the slice plan -->
