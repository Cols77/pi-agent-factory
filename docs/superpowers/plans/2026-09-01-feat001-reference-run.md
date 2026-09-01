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

### S-6 — Execute the evidence

| | |
|---|---|
| **Actor** | agent |
| **Reads** | each SR's `test_marker` criteria; `src/substrate/evidence/`; `src/coherence/register/cli.py` |
| **Writes** | `evidence/runs/T-6-evidence-execution-*.json`, `validation/validation-report.json` |
| **Command** | `rtk proxy uv run pytest -m sr -v -o addopts=""` |
| **Commits** | `142b846` |

`executed_evidence` moved **0/55 → 4/55**, and `coherence register check` moved from 55 pending /
0 measured-passing to **51 pending / 4 measured-passing**. This is the first executed evidence the
repository has ever recorded.

**Read that number with S-8's caveat attached: it holds only under the `prototype` profile the
repository actually resolves, and inverts to 0/55 under the `high_assurance` the specification
declares for this feature.**

**Four of the eight SRs are now accounted. Four are not, and that is the correct answer.**
SR-002, SR-003, SR-005 and SR-007 have only `test_marker` criteria; every one executed and passed.
SR-001, SR-004, SR-006 and SR-050 each carry at least one `kind: manual` criterion, satisfiable only
by a human `human_review` decision that does not exist — and for SR-004/AC-3 and SR-006/AC-3 the
behaviour is genuinely absent, so they were authored as failing criteria on purpose. A pipeline that
reported those four as accounted would be forging the human gate. **The honest end state of an
automated registration run is partial.**

**The detail most likely to be got wrong by an automated pipeline.** `_validation_state` tests
`"passed" in entry`, so writing `passed: null` for an unreviewed requirement makes `not None` true
and reports it **measured failing**. Omitting the key entirely yields `None`, which falls through to
`PENDING` — "not measured". The distinction between *failed* and *not yet measured* survives only if
the writer omits the field rather than nulling it. Each withheld entry instead carries a `note`
naming the outstanding criterion and why.

**Two evidence mechanisms, neither documented.** `coherence register check` reads
`evidence/runs/*.json`; `coherence navigate health`'s `executed_evidence` reads
`validation/validation-report.json`. They are separate stores, and both had to be written for the two
surfaces to agree. The legacy `coherence measurement` harness pipeline cannot serve a binding-less SR
at all, so the validation report was written through that module's own writer function rather than
its CLI. **Two stores answering one question is the same seam as S-5's, one layer down** — and any
bootstrap that writes only one of them will produce two surfaces that disagree about whether a
requirement has evidence.

### S-7 — Make the projection derived, and discover what rewriting documents costs

| | |
|---|---|
| **Actor** | agent |
| **Reads** | all 20 `docs/features/FEAT-0##.md`; `substrate.freshness.fingerprint` |
| **Writes** | `src/coherence/mirrors/` (new package), `tests/unit/mirrors/`, all 20 dossiers |
| **Command** | `rtk proxy uv run coherence mirrors generate` / `mirrors check` |
| **Commits** | `af6c275` (+ fix round) |

The `## Related requirements` wikilink block in each feature dossier became **derived output**:
regenerated from the dossier's own `requirements:` frontmatter, fingerprinted with the existing
`sha256_bytes` helper, marked *derived — do not edit*, and guarded by `coherence mirrors check`,
which fails when a block diverges from its derivation.

**The defect it closed is smaller than it sounds, and that is the point.** `FEAT-006.md` had
`- ![[SR-019]]` — an Obsidian *embed* — where all 19 other dossiers used plain links. Membership was
correct; every SR listed matched frontmatter. The drift was pure **syntax**, in one character, in one
line, among 20 files. No human review catches that, and no membership check would have found it
either. It is exactly the drift a hand-maintained mirror is guaranteed to accumulate and unable to
detect, which is why D-P8 requires generation rather than diligence.

**The trace graph contributed nothing.** The task specified deriving from "frontmatter plus the trace
graph". For these 20 dossiers the graph adds no requirement the frontmatter does not already carry.
That was reported as a finding and the cross-check kept only as a safety net, rather than building
machinery to justify the phrasing. A plan's wording is a hypothesis about where data lives; when the
data is not there, say so.

**The real lesson: a generator that rewrites hand-authored documents in place is a data-loss engine.**
Three separate content-destroying paths appeared in one 225-line module, all from a single root
cause — the locator inferred what it owned from **line shape** ("does this look like `- ...`?")
rather than from an owned boundary:

1. A first draft replaced from the heading to end-of-file, **silently deleting** FEAT-017's
   hand-authored closing sentence. Caught only because the author read `git diff` instead of trusting
   a green suite.
2. After that fix, a hand-authored bullet placed *directly* after the entry list — no blank line —
   was still silently swallowed. Continuing a Markdown list is ordinary authoring, not an edge case.
3. A block ending the file with no trailing newline left its stale last entry unconsumed and
   re-appended after the new block, corrupting it.

And a fourth, different in kind: the block regexes hardcoded `

`, so on any LF checkout — the norm
outside Windows — the tool raised an **uncaught exception** rather than reporting a failure, and
aborted the remaining files mid-loop, able to leave the tree half-regenerated. Every test passed,
because every fixture and every file in the repository is CRLF.

The correct shape is an **owned boundary**: an explicit end sentinel so the generated region is a
fact recorded in the file, not a heuristic re-derived on every run. Anything that infers ownership
from content will eventually meet content that looks like something it is not.

**For an automated pipeline the ordering matters.** Generation must be safe *before* it is trusted to
run unattended across a corpus. A bootstrap that regenerates 20 documents on every registration will
destroy hand-authored prose silently, and the loss is only noticed by someone who remembered it was
there.

### S-8 — Wire the human gate so a human decision can actually move it

| | |
|---|---|
| **Actor** | agent (mechanism only — no decision authored) |
| **Reads** | `src/coherence/policy/compiler.py`, `src/coherence/gate/{model,store,service}.py` |
| **Writes** | `src/coherence/policy/compiler.py`, `tests/unit/coherence/policy/test_compiler.py` |
| **Commits** | `9119fed` |

`_human_review_obligation` contained a hard-coded `reviewed = False`, with a comment saying the field
contract was undecided. Under `high_assurance` the obligation compiled `blocking` and stayed open
**no matter what any human decided** — the gate that invariant I-01 runs on could not be passed by a
real reviewer. S-8 decides that contract.

`reviewed` is now computed fail-closed from a durable `review:SR-###` `DecisionFile`, and every one
of these must hold: the file exists, its `gate_id` matches, its `artifact_ref` matches the SR's
canonical path, it carries exactly one decision, that decision's `item_id` matches, and its action is
`accept`. A corrupt file yields False. An `sr:` authoring-consent decision cannot satisfy it, because
the item id is `review:{sr_id}` — **the two human gates stay separate, which is the point of having
two.**

**The agent built the mechanism and authored no decision.** Every test decision lives in a `tmp_path`
fixture. An agent writing an `accept` for a review it performed itself is the exact self-certification
I-01 forbids, and on disk it would be indistinguishable from a real person's.

**What wiring the gate revealed — the most consequential finding of the run.** `human_review` still
reads **0/0**, and not because nothing has been reviewed. Every FEAT-001 requirement resolves to the
`prototype` profile:

```
resolve_profile(root, "sr:SR-001")  -> prototype
resolve_profile(root, "project")    -> prototype
```

`docs/features/FEAT-001.md` has no `profile:` field. `.factory/factory.yaml` declares none. **Nothing
on disk assigns `high_assurance` to anything.** The value exists only in the product specification's
prose feature map and in the slice plan's own header — both of which state "FEAT-001 is
`high_assurance`, so `human_review` compiles as `blocking`."

Under `prototype`, `human_review` compiles `not_applicable`. The denominator is zero. The dimension is
not unsatisfied — it is *structurally absent*, and 0/0 is indistinguishable from a dimension that does
not exist. The same understatement runs through the slice: the `test_marker` obligations compile
`required` rather than `blocking`, and SR-006/AC-3's manual criterion, authored as failing because
gating happens "only under `high_assurance`", is worse than it says — in this repository the marker
gate is not blocking for *any* requirement.

**This is NC-B one level up.** `requirement_quality` was a dimension that could not fail. This is an
assurance *level* that governs a human gate, asserted in a document and never expressed anywhere the
code can read. A profile that lives only in prose gates nothing. Every claim in this slice about
`high_assurance` behaviour was verified by passing the profile explicitly to the compiler — never by
the repository resolving it.

> **The 4/55 is profile-contingent, and the two facts are mutually exclusive.** This was found by the
> final whole-branch review, which declared `profile: high_assurance` on FEAT-001 and re-ran the
> surfaces: `executed_evidence` went **4/55 → 0/55** and `human_review` **0/0 → 0/8**. The evidence
> number exists *because* the repository resolves `prototype`. Under `high_assurance`,
> `_verification_result_obligation`'s harness check (`src/coherence/policy/compiler.py:243-250`)
> runs and rejects every FEAT-001 requirement for having no `binding:` — so the slice's headline
> result and the assurance level the specification declares for this feature **cannot both hold as
> the code stands.** Declaring the profile is a one-line change the resolver already supports; doing
> it would erase the evidence result. That decision belongs to a human, and this record must not be
> read as though 4/55 were unconditional.

**For an automated pipeline the rule is:** a declared assurance level must be a fact on disk that the
resolver reads, and registering a feature must fail loudly when its declared profile and its resolved
profile disagree. Otherwise the gates are ceremonial.

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
| A-11 | For a requirement blocked on unreviewed `manual` criteria, write `passed: false`, `passed: null`, or omit `passed`? | Omit the key entirely, and carry a `note` saying which criterion is outstanding and why. | `_validation_state` tests `"passed" in entry`; a null reports an UNREVIEWED requirement as MEASURED FAILING. Omission is the only encoding that distinguishes "not measured" from "measured and failed" |
| A-12 | Two undocumented evidence stores feed two surfaces that answer the same question. Write one, or both? | Both, and record that they are separate. | Writing one leaves `register check` and `navigate health` disagreeing about whether a requirement has evidence |
| A-13 | How does the generator know which lines it owns? | An explicit end sentinel bounding the generated region — never inference from line shape. | Shape-inference produced three separate silent content-loss paths in one module; ordinary Markdown eventually looks like whatever the heuristic matches |
| A-14 | The plan says derive from "frontmatter plus the trace graph", but the graph adds nothing for these 20 files. Build the machinery anyway? | No — report it, keep the cross-check only as a safety net. | A plan's wording is a hypothesis about where data lives; unused machinery built to satisfy phrasing is cost with no evidence behind it |
| A-15 | `human_review` reads 0/0. Is that "nothing reviewed" or "no requirement is subject to review"? | The latter: under `prototype` the obligation is `not_applicable`, so the denominator is 0. 0/0 is a dimension that is structurally absent, not one that is unsatisfied. | A reader cannot distinguish "0 of 0 done" from "this measure does not exist"; the display must, or the gate looks satisfied |
| A-16 | The spec and plan both say FEAT-001 is `high_assurance`; the code resolves `prototype` for every one of its SRs. Which governs? | The code — and the disagreement is a finding, not something to reconcile by editing either side quietly. | A profile that exists only in prose gates nothing; treating the document as authoritative would make every gate ceremonial |

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
- **The slice's headline evidence number contradicts its declared assurance level.** `executed_evidence
  4/55` holds only under `prototype`; under the `high_assurance` the specification declares for
  FEAT-001 it reads 0/55, because the harness check that runs only at that level rejects every
  binding-less requirement. The plan asserted both as though they were compatible. A registration
  process must resolve the profile *first* and report results against it, or it will publish a number
  that its own assurance claim invalidates.
- **The plan's central profile premise is false as the repository stands.** §2's exit condition and
  T-8's brief both rest on "FEAT-001 is `high_assurance`, so `human_review` compiles as `blocking`".
  Every FEAT-001 SR resolves to `prototype`; no `profile:` field exists on the feature and no profile
  is configured. The plan asserted an assurance level the machinery had never been told about.
- **T-6's Acceptance clause is unreachable by an agent alone.** "No SR in FEAT-001 remains 'no
  measurement, task, or deferral'" cannot be true while four SRs carry unreviewed `manual` criteria
  and the human gates (T-4b, T-8b) are by definition not an agent's to discharge. The plan wrote an
  acceptance sentence that only a human-plus-agent run can satisfy, and did not say so.
- **Three of nine tasks stalled the same way: an implementer backgrounded its own verification suite,
  ended its turn, and waited forever for a notification that never came.** A subagent is not
  reliably re-invoked by its own background watcher. All three needed an explicit nudge from the
  orchestrator to finish. It is the single most reproducible process failure of the run. Any automated registration pipeline must either make verification block,
  or make the orchestrator own the wait and the re-invocation — never leave a worker watching its
  own background job.
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

This is the procedure, extracted from what actually happened. It is written to be followed **without
reading the slice plan**. FEAT-001 needed seven schema/tooling steps that later features do not —
those are marked *(once)* and are already done. A second feature runs only the unmarked steps.

**Actor** is `agent` or `human`. A `human` step is a boundary, not a formality: no agent may perform
it, and an automated pipeline must model it as *queue and wait*, never as a step it completes.

| # | Step | Actor | Done when |
|---|---|---|---|
| 1 | Commit a baseline so the tree is clean and the run has a commit to anchor evidence to | agent | `git status` clean; the SHA is recorded |
| 2 | *(once)* Add the `acceptance:` array to the SR schema | agent | Malformed entries reject the whole SR; existing SRs load unchanged |
| 3 | *(once)* Give `requirement_quality` a real criterion | agent | The dimension can fail, and does |
| 4 | *(once)* Add the `sr:` item-id family so the gate can express authoring consent | agent | A `sr:SR-###` decision constructs and round-trips |
| 5 | Read each SR's `source:` section. Author acceptance criteria **from the source, never from the code** | agent | Every criterion is one checkable sentence traceable to a quoted source line |
| 6 | For each `test_marker` criterion, **open the test** and confirm it verifies that sentence | agent | Every binding is read, not assumed; wrong suggestions are rejected and recorded |
| 7 | Record every place source and code disagree as a finding | agent | Disagreements are reported, never silently reconciled |
| 8 | **Author authoring consent, one decision per SR, through the gate `DecisionFile`** | **human** | A real `accept`/`reject`/`defer` exists per SR |
| 9 | Add `@pytest.mark.sr("SR-###")` to the specific functions that verify each criterion | agent | Function-level, one per explicit clause; never a module-level `pytestmark` |
| 10 | *(once)* Make the `test_marker` obligation resolve through acceptance criteria | agent | An SR with no legacy `binding:` still compiles the obligation |
| 11 | Run the named tests and write a run manifest recording each SR's real result | agent | Every `passed` traces to an exit status observed in this run |
| 12 | For any SR blocked on an unreviewed `manual` criterion, **omit `passed` entirely** and record why | agent | The register shows *not measured*, never *measured failing* |
| 13 | Write **both** evidence stores — `evidence/runs/*.json` and `validation/validation-report.json` | agent | `register check` and `navigate health` agree |
| 14 | *(once)* Make the wikilink mirror derived, bounded by an owned end sentinel | agent | Regeneration is idempotent and preserves hand-authored prose |
| 15 | Regenerate the mirrors and run the divergence check | agent | `mirrors check` exits 0 across every dossier |
| 16 | *(once)* Wire `human_review` to an explicit `review:SR-###` decision | agent | No path reaches `satisfied` without a human decision on disk |
| 17 | **Review the evidence and record a `human_review` decision per SR** | **human** | A real decision exists; the obligation moves |
| 18 | Re-run `register check` and `navigate health --json`; record the numbers | agent | The movement is evidenced by command output, not prose |
| 19 | Write the run record **as you go**, including every ambiguity | agent | An implementer could follow it without this document's parent plan |

### The four rules that carry the most weight

1. **Derive criteria from the source, not the code.** A criterion written by reading the
   implementation cannot fail. It looks like coverage and is a tautology wearing a requirement's
   clothes — the same defect as `req_quality_ok = len(sr_nodes)`, moved somewhere harder to see.
2. **`manual` is the privileged kind, not the fallback.** A `manual` criterion counts toward
   requirement quality with no automated evidence, so its `reason` prose *is* its evidence, and
   nothing gates that prose. Reach for `manual` when no test can exist — never when no test was
   convenient.
3. **Never infer ownership from content.** A generator that decides which lines it owns by looking at
   their shape will eventually meet ordinary text that matches, and delete it silently. Bound
   generated regions with an explicit sentinel so ownership is a fact in the file.
4. **Partial is the honest end state.** A registration run that an agent completes alone finishes
   with the human gates open. Four of FEAT-001's eight SRs remain unaccounted for exactly that
   reason. A pipeline that reports "done" without them has forged the only signal that matters.

### What a second feature should expect

Steps 2, 3, 4, 10, 14 and 16 are already built, so a second feature is steps 1, 5–9, 11–13, 15 and
17–19. The agent-dischargeable part is roughly one working session. It will stop twice — at step 8
and step 17 — and it cannot proceed past either without a person.
