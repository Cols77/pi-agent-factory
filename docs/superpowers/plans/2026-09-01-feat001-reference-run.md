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

### S-2 — Make the requirement-quality measure capable of failing

| | |
|---|---|
| **Actor** | agent |
| **Reads** | `src/coherence/navigate/health.py` (`compile_health_dimensions`); the T-1 schema |
| **Writes** | `src/coherence/navigate/health.py`, `tests/unit/coherence/test_health_dimensions.py` |
| **Command** | `rtk proxy uv run coherence navigate health --json` |
| **Commits** | `9e6ac6a`, `85db839`, `9e748db` |

`requirement_quality` computed `req_quality_ok = len(sr_nodes)` and reported `satisfied == expected`.
It was 55/55 and always would be. S-2 replaced it with: **an SR counts only when it carries at least
one acceptance criterion whose verification binding resolves.**

The dimension fell from **55/55 to 0/55** on the same register, unchanged. Nothing got worse; a
measurement that had been reporting a number it never computed started computing it. Any feature
registration process must expect this shape of drop and must not treat it as a regression — the
denominator was always 55, the numerator was never earned.

Review of this step found three integrity defects that only appear once a dimension actually reads
data, and all three are the same species — a permissive resolver manufacturing green:

1. acceptance refs could escape the project root (`../../etc/passwd` resolves, therefore counts);
2. a `test_marker` ref could name a directory or a non-Python file and still count;
3. duplicate register ids silently overwrote each other in the lookup, inflating the denominator.

Settled contract (ruling R-8): a `test_marker` ref must resolve canonically inside the project root
and be a regular `.py` file; a `harness` ref may be any existing in-root path, because harness
directories are legitimate; duplicate ids are ambiguous and fail closed for every affected SR while
the SR-node denominator is preserved.

**Generalisable lesson.** The moment a dimension stops being a tautology, its *resolver* becomes the
attack surface. Every "does this reference resolve?" check needs containment, type and ambiguity
rules decided up front, or the dimension trades one way of lying for a subtler one.

### S-3 — Teach the consent gate to speak about requirements

| | |
|---|---|
| **Actor** | agent (preparation only — no decision is authored) |
| **Reads** | `src/coherence/gate/model.py`, `store.py`, `src/coherence/inbox.py`, `deferrals.py` |
| **Writes** | `src/coherence/gate/model.py`, `src/coherence/inbox.py`, `src/coherence/deferrals.py`, focused tests |
| **Commits** | `c02d87f`, `c48de42`, `7362062` |

Authoring consent (SR-044) is a human gate: a person confirms that a given spec paragraph really is
this requirement. The consent surface is the existing gate `DecisionFile` — one gate protocol, not a
second one, and never chat narration.

**The blocker the plan did not know about.** `ITEM_ID_PREFIXES` in `gate/model.py` allowed
`coverage:`, `doctor:`, `trace:`, `review:` and `suspect:`. There was no `sr:`. A `Decision` with
`item_id="sr:SR-001"` was rejected at construction, so the consent surface the plan designated could
not express the thing it was designated for. Reusing `review:` was rejected: it already means
*verification* review, and overloading it would merge the two gates the requirements model
deliberately separates.

**Consequence for the process — a step splits in two.** T-4 was written as one human task. It is
actually two: an agent step that makes the queue *expressible and visible*, and a human step that
*decides*. Only the first can be automated. The same split applies to `human_review` (S-6 below).
This is recorded as ruling R-9 and is the shape FEAT-017 must encode: **every human gate is a pair —
prepare-and-queue (agent), decide (human) — never one step an agent might drift into completing.**

Three review rounds were needed, and the last two findings were only reachable by direct probing
rather than by reading: a scalar `decisions` value leaked a raw `TypeError` out of DecisionFile
parsing, and a date-only future `review_after` leaked a naive-vs-aware datetime `TypeError`. Both are
now rejected through the module's own error contract, with regression tests covering both directions
of the date comparison.

**Evidence gap, recorded rather than hidden.** No implementer report was written for this step, so it
carries no test/lint/type evidence of its own; Ruff and Pyright were never run against `7362062`. The
final whole-branch review covers the range knowing this.




### S-4 — Author the acceptance criteria, from the source and not from the code

| | |
|---|---|
| **Actor** | agent |
| **Reads** | each SR's `source:` section — `2026-08-18-coherence-toolset-design.md` §4.2/§9.1/§9.2/§10, `00-high-level-requirements.md#HLR-02`, `2026-08-31-sr-code-validation-traceability-design.md`; then each candidate test file |
| **Writes** | `requirements/SR-001.md` and SR-002..007, SR-050 (frontmatter only) |
| **Command** | `rtk proxy uv run coherence navigate health --json` |
| **Commits** | `682cc8b`, `df339ac` |

23 criteria across eight requirements — 17 bound to a test file by `kind: test_marker`, 6 `manual`.
`requirement_quality` moved **0/55 → 8/55**.

**The one rule that decides whether this step is worth doing: derive from the `source:` anchor, never
from the code.** A criterion written by reading the implementation describes what was built, and can
therefore never fail. That is the same defect as `req_quality_ok = len(sr_nodes)`, relocated from the
dimension into the requirement, where it is much harder to see.

The rule is easy to state and hard to follow. Review found three criteria that had absorbed clauses
from the test they were bound to — "without importing the module and without normalising case", "with
a null checksum and its file left byte-identical", "a stale or missing code map yields a diagnostic
rather than a silent file-glob fallback". None appears in any source section. All three were dropped;
no source sentence existed to re-derive them from. They could technically fail, so they were not false
green — but each narrowed its requirement to the shape of the test that already passed.

**Findings the step was designed to surface, and did.** Four places where the source and the code
disagree, none silently reconciled:

- **SR-002's own statement contradicts its source.** The statement claims scope over "SR and BR
  nodes"; §10 of the same design says a `BR-*` tier is "explicitly out of scope here". The code agrees
  with the source. The statement is wrong and needs a separate decision.
- **SR-006's source demands the gate fail unconditionally**; the code gates only under
  `high_assurance`, and the default `prototype` profile yields a non-gating WARNING.
- **SR-004's §9.1 clause** "the audit gains whatever languages the index parses" is unmet — the index
  parses several languages, the import layer returns `unsupported` for anything but Python.
- **SR-050 is entirely unimplemented**, as is SR-001's wikilink clause.

**Two shapes worth copying.** First, SR-004/AC-3 was authored as a criterion the system *currently
fails*, with a `manual` reason stating the gap concretely — a requirement is allowed to be red, and a
register that cannot express "required but absent" is not a register. Second, SR-006's unconditional
demand was split from its profile-scoped half: AC-2 claims only what the bound test actually proves,
AC-3 carries the source's full demand as a failing `manual` criterion. Before the split, AC-2 read as
bound and green for a property the system does not have, because `test_marker` bindings resolve at
**file** granularity and the bound file contained assertions for both outcomes.

**Three of the plan's nine suggested bindings were wrong** and were replaced after reading the tests:
`test_snapshot_navigation.py` tests snapshot freshness, not traceability; `test_kb_signatures.py` and
`test_kb_index.py` test signature extraction and indexing, not selection. A binding table in a plan is
a hypothesis. Reading the test before binding to it is not optional, and rejecting a suggested binding
is the expensive, correct path.

**The trap that caught this run.** A `manual` criterion counts toward `requirement_quality`
*unconditionally* — no automated evidence is required, so its `reason` prose *is* its entire evidence.
One criterion shipped with a reason asserting the gate model accepted no requirement-scoped item-id
prefix, which the code contradicted. Nothing in the tooling caught it; a human reading the text did.
**`manual` is the cheapest possible route to a counted requirement, and nothing gates its prose.**
Any automated registration pipeline must treat `manual` as the privileged, most-scrutinised kind —
never the fallback an agent reaches for when no test fits.

### S-5 — Bind the markers, and make something read them

| | |
|---|---|
| **Actor** | agent |
| **Reads** | each `test_marker` criterion and the test file it names; `src/coherence/register/markers.py`; `src/coherence/policy/compiler.py` |
| **Writes** | 11 test files (decorators only), `src/coherence/policy/compiler.py`, `tests/unit/coherence/policy/test_compiler.py` |
| **Command** | `rtk proxy uv run pytest tests/unit/ -q` |
| **Commits** | `cb6687b` |

The repository began this step with **zero** real `@pytest.mark.sr` decorators. The marker was
registered in `pyproject.toml`, `collect_markers` was implemented and had 27 tests, and SR-006
required the mechanism — but every textual occurrence in the repo was a fixture string inside tests
*of the collector*. This step is the mechanism's first contact with production.

It ended with **32 decorators across 11 files**, and seven of the eight SRs compiling a
`test_marker` obligation as `blocking` and `satisfied` under `high_assurance`.

**Placement is the whole judgement.** `collect_markers` is file-scoped, so a single module-level
`pytestmark` would have satisfied it for every file in one line. That would also have asserted that
the entire file verifies the requirement. Each decorator instead went on the specific function that
verifies its criterion — and where a criterion had two explicit clauses, on one function per clause.
**A mechanism that is satisfied at file granularity must be used at function granularity, or it
records a claim nobody made.**

**The step's own Verify clause could not be satisfied as written**, and that is the most useful thing
it produced. The clause required the `test_marker` obligation to compile `blocking` — but
`_test_marker_obligation` returned `not_applicable` for any SR without a legacy `binding.experiment`,
and none of the eight has one. The acceptance `ref:` was visible to the health dimension and invisible
to the obligation compiler.

The alternative — give each SR a legacy `binding:` naming its test file — is structurally impossible:
an SR has exactly one `binding`, and SR-002's three criteria name three different files. The single
coarse `binding:` is precisely what the acceptance array replaces. So the obligation compiler learned
to resolve through acceptance criteria, with the legacy path checked first and untouched.

One rule in that resolution matters more than the rest: **an SR with several `test_marker` criteria
is satisfied only when every one of them resolves.** `any()` instead of `all()` would report an SR as
proven when most of its criteria had no evidence — false green at its purest. The test that covers
this is written to fail under `any()`, not merely to pass under `all()`.

**First-contact defect, as predicted.** `collect_markers` silently drops a `@pytest.mark.sr(...)`
written with a keyword argument or a non-literal positional: it collects only string-constant
positional args, so a marker written any other way vanishes with no error at all. Nothing in this
step's 32 decorators used such a form, so it changed no result here — but a *silent* drop in the one
mechanism that binds tests to requirements is a false-negative generator, and it survived 27 unit
tests because every one of them used the literal form.

**A seam this step could not close.** `coherence register check` still reports all eight SRs as
"no measurement, task, or deferral accounts for this requirement", even though seven now compile a
satisfied obligation. Two surfaces answer the same question — *is this requirement accounted for?* —
from different data: `classify()` reads `binding`/task/deferral, the obligation compiler reads
acceptance. They disagree, and the older, more visible surface is the one telling the bleaker story.
Closing that seam is S-6's, because "no SR remains unaccounted" is S-6's acceptance sentence.

---

## 4. Ambiguities and how they were resolved

<!-- appended as each is encountered; these are FEAT-017's decision set -->

| ID | Ambiguity | Resolution | Why |
|---|---|---|---|
| A-0 | The plan assumes a clean tree; the real one had 75 uncommitted files | Commit a baseline first, as a named step | Evidence without a commit anchor has no provenance (I-04) |
| A-1 | The plan's example binds a criterion to a test *file path* (`ref:`), but the marker system binds SR→test with an in-file `@pytest.mark.sr` decorator. Two sources for one fact. | The decorator is authoritative for what a test proves; `ref:` is a navigational pointer that must be *consistent* with it, checked at S-4. | Two independent bindings for one fact drift apart — the exact failure NC-D records for FEAT-006's hand-maintained mirror |
| A-2 | "An SR counts only when it carries an acceptance criterion with a *resolvable* verification binding" — resolvable how? Well-formed? Path exists? Marker matches? | Well-formed AND the `ref:` target exists on disk. Not "marker matches" — that is the marker gate's job and would make the dimension a duplicate of it. | A criterion pointing at a deleted file must not count; that is the class of lying the dimension exists to stop |
| A-3 | Tests asserting only that *something* raised look like coverage but prove nothing about *which* rejection fired. | Every malformed-case assertion must name the distinguishing part of the message, and must fail if the parser reported a different one of the 13 cases. | Thirteen tests that cannot tell each other's failures apart are one test wearing thirteen hats |
| A-4 | Once `requirement_quality` reads real data, its *resolver* becomes the surface that can lie. Does a ref "resolve" if it escapes the project root? names a directory? names a non-Python file? belongs to a duplicated SR id? | `test_marker` refs must resolve canonically inside the project root and be regular `.py` files; `harness` refs may be any existing in-root path; duplicate SR ids fail closed for every affected SR while the denominator is preserved. | A permissive resolver trades a tautology for a subtler false green — `../../etc/passwd` resolves, so it would have counted |
| A-5 | The consent gate's item-id vocabulary had no `sr:` family. Add one, or overload the existing `review:`? | Add `sr:`. | `review:` already means *verification* review; overloading it merges the two gates the requirements model deliberately separates |
| A-6 | A human gate is written in the plan as one task. Can an agent do any of it? | Split every human gate into prepare-and-queue (agent) and decide (human). The agent never writes a decision. | One undivided "human" task is a task an agent can drift into completing; the split makes the boundary structural rather than a matter of restraint |
| A-7 | A reconnaissance snapshot taken at slice start said the gate had no `sr:` item-id prefix. That was true when written and false by the time a later task read it — T-4a had added the prefix in between. The task quoted it into a requirement as justification. | Date every reconnaissance artifact, mark it "true at slice start", and re-verify any fact against the working tree before quoting it into a durable artifact. | A run mutates the code its own notes describe. A shared snapshot is stale from the moment the first task commits, and stale facts laundered into a requirement become false evidence |
| A-8 | `collect_markers` is file-scoped. Mark the module once, or each verifying function? | Each verifying function, one per explicit clause of a compound criterion. | A file-scoped check satisfied by a module-level mark records a claim about every test in the file that nobody made |
| A-9 | The acceptance `ref:` was visible to the health dimension but invisible to the obligation compiler, so the step's own Verify clause was unreachable. Give each SR a legacy `binding:`, or teach the compiler to read acceptance? | Teach the compiler; keep the legacy path first and untouched. | An SR has exactly one `binding` but may have criteria naming several files — the legacy shape cannot express the data. The array IS the binding |
| A-10 | An SR with several `test_marker` criteria: satisfied when any resolves, or when all do? | All. And the test for it is written to fail under `any()`, not merely to pass under `all()`. | `any()` reports a requirement proven while most of its criteria have no evidence |

---

## 5. What this plan got wrong

<!-- appended as discovered -->

- **T-4 and T-8 are not single tasks.** Both were written as "human does this". Both are really a
  pair: an agent step that makes the decision expressible and queued, and a human step that decides.
  The plan was amended (R-9) into T-4a/T-4b and T-8a/T-8b. FEAT-017 must model human gates as pairs.
- **The consent surface could not express consent.** The plan names the gate `DecisionFile` as the
  authoring-consent surface, but the gate's item-id vocabulary had no `sr:` family, so no SR consent
  decision could be constructed at all. A plan that designates an existing mechanism should verify
  the mechanism can represent the new subject before depending on it.
- **`human_review` could never be satisfied.** `_human_review_obligation` hard-codes `reviewed = False`
  (`src/coherence/policy/compiler.py:235`) with its field contract recorded as undecided. Under
  `high_assurance` it compiles `blocking` and stays open regardless of what any human decides — so the
  slice's own exit condition was unreachable as written. Wiring this is T-8a.
- **The plan assumed a clean starting tree.** See A-0.
- **T-5's Verify clause was unreachable as written.** It required the `test_marker` obligation to
  compile `blocking`, which was impossible for an SR with no legacy `binding:` — and none of the eight
  has one. The plan assumed the acceptance array was already load-bearing end to end; it was visible
  only to the health dimension. See A-9.
- **T-5's Verify clause also claimed `register check` would surface the marker findings.** It does
  not, and cannot without closing the `classify()`/obligation-compiler seam. Routed to T-6, whose
  acceptance sentence names the same text.
- **Nothing gates the prose in a `manual` criterion's `reason`.** A `manual` criterion counts toward
  `requirement_quality` with no automated evidence, so its `reason` *is* its evidence. During this run
  a criterion shipped with a reason asserting something the code contradicted, and no tool caught it —
  only a human reading the text did. FEAT-002 owns this: either `manual` needs its own gate, or it
  must not count toward a quality dimension unaided.


---

## 6. Step list for registering the next feature by hand

<!-- written at the end, from §3, and checkable without reading the slice plan -->
