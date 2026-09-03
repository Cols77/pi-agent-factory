# T5 — Fidelity review agent: implementation plan

**Spec:** [[docs/superpowers/specs/2026-08-31-sr-code-validation-traceability-design|SR code and validation traceability design]], "Review agents" section (Fidelity reviewer)
**Feature:** [[FEAT-001]] REQ-TRACEABILITY
**Related:** [[FEAT-007]] MEASURE-AUDIT, [[FEAT-014]] VALIDATION-GATES, [[FEAT-017]] PLANNING-BOOTSTRAP, [[SR-050]] (closes AC-4), [[SR-023]] (import-overlap mechanism reused), [[SR-004]]/[[SR-006]] (code map / pytest markers reused), [[SR-059]] (tracks the separate, pre-existing gap that `human_review` is `not_applicable` outside `high_assurance` — not this plan's concern to close)

This elaborates work package **T5** of
[[docs/superpowers/plans/2026-08-31-sr-code-validation-traceability-plan|the parent plan]]
into concrete, TDD-orderable steps. It targets **[[SR-050]] AC-4** only, and is a planning
document — no implementation code is written or scaffolded here, and `requirements/SR-050.md`
is not touched: AC-4 stays `kind: manual` until a human reads and approves this plan and the
reviewer it describes actually exists.

**Revised 2026-09-03 (post-review).** An independent review approved this plan but found it had
gone stale within its own drafting window: T4 landed 17 minutes after this plan was first
committed, and three organizational assumptions below guessed wrong. Corrected in place: the
module home is `coherence.register` (not a new `coherence.review` package), the CLI extends
`coherence register review` (not a new top-level command family), and the persistence open
question no longer defers to a T4 convention that turned out not to exist.

## Status at drafting time (2026-09-03)

- **T1 (relation schema/resolver)** is done and merged: `coherence.register.relations.resolve_sr_relations`
  (`src/coherence/register/relations.py`) resolves `implemented_by`/`verified_by` structured
  entries against the real repo, reusing the existing code map
  (`substrate.codemap.store.ensure_fresh` + `substrate.codemap.build.file_signatures`), and
  rejects duplicates and line-number identity. AC-1 is `test_marker`-backed.
- **T4 (structural reviewer) + evidence reconciliation reviewer**, closing AC-2, has now **landed
  and merged to `main`** (`6a2e4a2`, fixed up at `42e6fca`): `src/coherence/register/review.py`
  (`structural_review`, `evidence_reconciliation_review`, `unaccounted_changed_files`), wired into
  the existing `coherence register review <SR-ID>|--all` CLI (`src/coherence/register/cli.py`'s
  `cmd_review`) — extending `coherence.register`, not a new package, and printing JSON, never
  persisting to a file. Every place below that originally deferred to "whatever T4 picks" has been
  corrected to name T4's actual, now-confirmed choices instead of guessing.
- **`_human_review_obligation`** (`src/coherence/policy/compiler.py:273`), and its exhaustive
  tests in `tests/unit/coherence/policy/test_compiler.py` (six of them bound to SR-050 AC-3 via
  `@pytest.mark.sr("SR-050")`, lines 441–498+), are the **already-built, already-tested** gate
  this plan routes AC-4's enforcement through. T5 adds **zero new obligation kinds** and makes
  **no change** to `compile_obligations` or `_human_review_obligation`'s closure logic — see
  "Enforcement mechanics" below.
- **SR-023's import-overlap mechanism exists**: `substrate.codemap.imports` (`src/substrate/codemap/imports.py`)
  — `compute_overlap`/`transitive_imports` (does a test's import closure reach a changed file) and
  `reachable_symbols` (which qualified symbols are reachable from a set of files through the
  import graph), both built on the durable, fingerprint-freshness-checked `CodeIndex`. There is no
  separate `coherence.audit` "SR-023 module" distinct from this — `coherence.audit.audit.classify`
  (the older subagent-verdict coverage pipeline) already consumes `compute_overlap`'s `OverlapResult`
  as its own "overlap" input. T5 reuses `substrate.codemap.imports` directly, not `coherence.audit`.

## Goal

Give the per-SR review a **judgement** reviewer that AC-2's two deterministic reviewers cannot be:
whether a resolved `implemented_by`/`verified_by` relation actually substantiates the SR's claim,
not merely whether it points at something that exists. Its verdict is never self-certifying — it
produces visible, citable findings, and only a human `accept` decision recorded through the exact
same `review:<sr_id>` gate AC-3 already enforces can close the requirement.

## Evidence packet

### What T5 does *not* reinvent

The packet-building step is a pure **reader/composer** over four already-real sources — it parses
nothing new and re-implements no existing resolver:

1. **T1's resolver** (`coherence.register.relations.resolve_sr_relations`) for path/symbol/test
   resolution and duplicate detection.
2. **The code map** (`substrate.codemap.store.ensure_fresh`, `substrate.codemap.build.file_signatures`,
   `substrate.codemap.model.CodeIndex`/`IndexSignature`) for symbol signatures and (bounded) source
   text.
3. **`substrate.codemap.imports`** (`compute_overlap`, `reachable_symbols`) for import-graph facts.
4. **Evidence manifests** (`substrate.evidence.read.list_run_manifests`) and
   `coherence.trace.validation_status.load_validation` for executed-test outcomes.

### `FidelityPacket` shape

One packet per SR, built fresh for each review run (never cached across source changes — the code
map's own fingerprint freshness check already guards against a stale index being trusted silently,
per `substrate.codemap.build.is_fresh`):

```text
FidelityPacket:
  sr_id: str
  statement: str                       # SR frontmatter `statement`
  acceptance: tuple[AcceptanceCriterion, ...]
    AcceptanceCriterion: id: str, criterion: str, verification_kind: str
  design_source: DesignSourceExcerpt | None
    # SR frontmatter `source:` (e.g.
    # "docs/superpowers/specs/...design.md#canonical-relations") resolved to
    # the referenced doc/section, with a BOUNDED excerpt (matching the
    # existing render_index_slice-style cap pattern in
    # substrate.codemap.build, not the whole file) -- None (with a
    # diagnostic) when the source doc or anchor does not resolve, never a
    # silent empty string standing in for "no design context."
    doc_path: str
    anchor: str | None
    excerpt: str
  profile: str                         # resolve_profile(root, f"sr:{sr_id}")
  implemented: tuple[ResolvedProductionRef, ...]
    ResolvedProductionRef:
      path: str
      symbol: str                      # "<dotted.module>:<name>", T1's own identity shape
      signature: IndexSignatureView     # kind/name/signature/summary (NOT line -- see Citations)
      source_excerpt: str               # bounded body text for this symbol, sliced from the file
                                         # by IndexSignature.line to the next signature's line (or
                                         # EOF); capped like render_index_slice's FACTORY_INDEX_SLICE_CAP
  verified: tuple[ResolvedValidationRef, ...]
    ResolvedValidationRef:
      path: str
      test: str | None                 # pytest node id, or None for file-only validation
      signature: IndexSignatureView | None
      source_excerpt: str | None
      outcome: TestOutcome | None
        TestOutcome: state: Literal["passed","failed","error","never_validated"]
                     stale: bool, last_run_id: str | None, summary: str | None
        # sourced from list_run_manifests (per-node, when the manifest's
        # validation[].requirements[].tests[] carries this node id) falling
        # back to coherence.trace.validation_status.load_validation's
        # SR-level SrStatus when no manifest names the node directly --
        # never invented when neither source has it (state stays
        # "never_validated", not assumed-passing).
  import_overlap: tuple[OverlapFact, ...]
    OverlapFact:
      implemented_ref: str              # "path#symbol" -- stable citation form, see below
      verified_ref: str                 # "path::test" or "path" (file-only)
      reaches: bool | None               # None when compute_overlap's own status is not
                                          # "resolved" (unsupported/stale/missing) -- never
                                          # coerced to False, which would read as a confirmed
                                          # non-overlap fidelity signal it is not
      status: str                        # OverlapResult.status verbatim
  unresolved: tuple[ReferenceIssue, ...]  # T1's own RelationResolution.issues, carried through
                                          # unchanged -- an unresolved relation is NOT a fidelity
                                          # question (that's AC-1/structural territory); the
                                          # packet surfaces it only so the fidelity reviewer never
                                          # silently judges a link that does not even resolve
```

`IndexSignatureView` is `{kind, name, signature, summary}` — `IndexSignature.line` is deliberately
**dropped** at the packet boundary, not merely unused: the design forbids line numbers as identity
(mirroring T1's own `_LINE_SEGMENT_RE` rule), and a fidelity finding's citation must stay valid
across a reformat that shifts lines but not symbols. `line` is used internally, before the packet
is built, only to slice `source_excerpt` — it never appears in a finding or a packet field a
reviewer's output could cite back.

### Packet builder location

`src/coherence/register/fidelity_packet.py` — extends the existing `coherence.register` package,
matching T4's landed precedent (`src/coherence/register/review.py`). T4 did not create a new
`coherence.review` package; this plan's earlier proposal to do so is withdrawn accordingly — there
is no separate reviewer package in this repo, and T5 should not invent one.

## Findings schema

```text
FidelityFinding:
  sr_id: str
  kind: Literal[
    "overstated_link",        # relation claims to implement/verify more of the SR than the
                               # linked symbol/test actually does
    "incidental_helper",      # linked symbol exists and is imported/called in the relevant
                               # path, but is a helper/utility, not the behavior owner the SR
                               # statement describes
    "weaker_subset_test",     # linked test exercises only a strict subset of the claimed
                               # behavior (e.g. the happy path of a criterion that also names a
                               # failure/edge case)
    "different_behavior",     # linked symbol or test implements/verifies something else
                               # entirely -- the relation is simply wrong, not merely weak
    "missing_link_compound",  # the SR statement or an acceptance criterion has a clause no
                               # declared relation covers at all (compound SR, partial coverage)
  ]
  relation: RelationRef
    RelationRef: field: Literal["implemented_by","verified_by"], path: str,
                 identity: str            # symbol or test id -- the SAME (field, path, identity)
                                          # triple T1's own duplicate-detection `seen` set keys on
                                          # (src/coherence/register/relations.py:169), so a finding
                                          # always names a relation T1 itself could locate again
  confidence: float                       # 0.0-1.0; the reviewing agent's own calibrated estimate,
                                          # never defaulted or backfilled when the agent omits it
                                          # (see cli/runner error handling below)
  citations: tuple[str, ...]              # stable, line-free references only:
                                          #   "path#symbol"        (production)
                                          #   "path::test_node_id" (validation, pytest form)
                                          #   "path"                (file-only validation)
                                          #   "doc_path#anchor"     (design source)
                                          # at least one citation required; a finding citing
                                          # nothing is rejected at construction, not merely
                                          # discouraged
  rationale: str                          # free text explaining the judgement, non-empty
  acceptance_ref: str | None              # AC id this finding concerns, when the SR is compound
                                          # and the finding is scoped to one clause (esp.
                                          # missing_link_compound); None for an SR-wide finding
  status: Literal["open","escalated","dispositioned"]
    # "open": produced this run, no disposition yet
    # "escalated": profile is not high_assurance; visible in the run result, does not block
    # "dispositioned": a human review:<sr_id> decision exists that covers the SR (see below) --
    #   the finding is not deleted (SR-050's statement requires a review that "reports ...
    #   findings", not one that erases its own history), it is marked so a re-run does not
    #   re-escalate a finding a human already saw and accepted past
  produced_at: str                        # ISO-8601, when this run emitted the finding
  produced_by_run: str                    # the review run's own id, for provenance
```

A **supported** link produces **no finding** — the reviewer's positive case is silence, matching
every other deterministic checker in this design (T1, and T4's structural checks per the spec
excerpt). `FidelityReviewResult` (the top-level return/persisted shape) is:

```text
FidelityReviewResult:
  sr_id: str
  profile: str
  findings: tuple[FidelityFinding, ...]   # empty == every declared, resolved relation is supported
  unresolved: tuple[ReferenceIssue, ...]  # passthrough from the packet -- visible, but explicitly
                                          # not a fidelity finding (see packet.unresolved above)
  run_id: str
  produced_at: str
```

## Enforcement mechanics — reusing `_human_review_obligation` exactly

AC-4's own text is explicit that this is the one part of AC-4 that **is** mechanical, and that it
must not invent a second gate: *"that review's verdict does not close the requirement until the
same human_review gate AC-3 already enforces records an attributed decision covering it."*

Concretely:

- `compile_obligations` (`src/coherence/policy/compiler.py:86`) already, for every `sr:<id>`
  scope, appends `_human_review_obligation(root, scope_ref, profile, nodes=nodes, edges=edges)`
  (line 122). **T5 adds no new obligation kind and no new branch to this function.** The
  `ob:human_review:sr:<id>` obligation T5 relies on already exists for every SR today, whether or
  not a fidelity reviewer has ever run.
- `_human_review_obligation` already: compiles `requiredness = "blocking"` under `high_assurance`
  and `"not_applicable"` otherwise (line 351); is satisfied **only** by an `accept` `DecisionFile`
  at `decision_path(root, f"review:{sr_id}")` whose `gate_id`, `artifact_ref`, and the single
  decision's `item_id` all match, with non-blank `decided_by` and ISO-8601 `decided_at` (lines
  319–349, `coherence.gate.model`/`coherence.gate.store`). This is **exactly** the closure AC-4
  needs — a fidelity verdict is agent output, and agent output is never, by this obligation's own
  design (its docstring is explicit: "the substrate cannot distinguish an agent-written decision
  from a human one"), sufficient on its own.
- **T5's job is therefore to make sure a human deciding `review:<sr_id>` can see the fidelity
  findings**, not to add a second mechanical gate on top of `_human_review_obligation`. Concretely:
  the resolve guidance a human is pointed at for an open `human_review` obligation should name
  where the fidelity report for that SR lives (see "Open design questions" #2 — whether this is a
  one-line, purely-informational addition to `_human_review_obligation`'s existing `reason`/
  `resolve_cmd` strings, or left entirely to the dossier/CLI surface instead).
- **The design spec's "for `high_assurance` work, unresolved fidelity findings block" is not the
  same clause as AC-4's**, and is proposed here to be realized through a *different*,
  *already-existing* mechanism than `_human_review_obligation`: `_ci_verification_obligation`
  (`src/coherence/policy/compiler.py:128`), which is **always** `requiredness="blocking"` and
  whose commands come straight from `.factory/factory.yaml`'s `gates:` (`factory.config.load_config`).
  The proposal: a new gate command (e.g. `{python} -m coherence review fidelity --check`, alongside
  the existing `coherence mirrors check` line in the `full` gate) that runs the fidelity reviewer
  across every SR in scope and exits non-zero **only** when a `high_assurance`-profile SR has an
  `open` (not `escalated`, not `dispositioned`) finding. Under any other profile the same command
  exits 0 regardless of findings — they are still recorded and visible, just not CI-blocking. This
  reuses `_ci_verification_obligation` completely unmodified (it already treats every configured
  gate command as blocking); the profile-conditional logic lives entirely inside the new CLI
  command, not in `compiler.py`. **This is a design proposal, not something AC-4's text mandates
  — flagged explicitly in "Open design questions" #1 for a human to confirm before it is built.**

Net effect: **`policy/compiler.py` is touched by T5 in at most one place** (optionally, the
`_human_review_obligation` string enrichment in #2 above), and never for new gate logic. Every
actual blocking behavior comes from mechanisms that already exist and are already tested.

## Task breakdown

### T5.1 — `FidelityPacket` builder

Create `src/coherence/register/fidelity_packet.py` (extending `coherence.register`, matching T4's
landed precedent — see "Packet builder location"). Implement
`build_fidelity_packet(root: Path, sr_id: str) -> FidelityPacket`, composing T1's resolver, the
code map, `substrate.codemap.imports`, and evidence/validation-status readers as described above.
No judgement logic lives here — this step is deterministic and independently testable.

**Tests** (`tests/unit/coherence/register/test_fidelity_packet.py`, matching `test_review.py`'s
existing sibling-test convention for this package):
- packet includes every resolved `implemented_by`/`verified_by` entry with signature + bounded
  source excerpt;
- an unresolved relation (T1 issue) appears in `packet.unresolved`, not in `implemented`/`verified`;
- `design_source` resolves the SR's `source:` frontmatter to doc + anchored excerpt; a missing doc
  or unresolvable anchor yields `None` with a diagnostic, never a silently empty excerpt;
- `import_overlap` reports `reaches=None` (not `False`) when `compute_overlap`'s status is not
  `"resolved"`;
- `verified[].outcome` reflects the newest manifest naming that exact test node; falls back to
  SR-level `load_validation` only when no manifest names the node; stays `never_validated` when
  neither source has it — never inferred from the test merely resolving structurally.

### T5.2 — Findings schema and validation

Add `FidelityFinding`/`FidelityReviewResult` dataclasses under `src/coherence/register/fidelity_findings.py`,
with construction-time validation: `kind` in the fixed enum, `confidence` in `[0.0, 1.0]`,
`citations` non-empty, `rationale` non-blank, `relation` naming a `(field, path, identity)` T1
could itself resolve (cross-checked against the packet the finding was produced from, not merely
shape-checked).

**Tests** (`tests/unit/coherence/register/test_fidelity_findings.py`):
- a finding with empty `citations` is rejected at construction;
- a finding whose `relation` does not match any entry in the packet it claims to come from is
  rejected (prevents a hallucinated relation reference from silently becoming a "real" finding);
- `confidence` outside `[0.0, 1.0]` is rejected;
- round-trip to/from the JSON shape used for persistence (T5.4) is lossless.

### T5.3 — Fidelity judgement (the agent-driven step)

Implement `src/coherence/register/fidelity.py`: `review_fidelity(packet: FidelityPacket, judge) ->
FidelityReviewResult`, where `judge` is an injected callable (subagent dispatch or an equivalent
LLM-calling interface — the exact dispatch mechanism is an open question, see below) that receives
the packet and returns raw candidate findings, validated and normalized through T5.2's schema
before anything is persisted. A `judge` that fails to respond, times out, or returns an
unparseable/invalid shape produces **no silent pass**: the result records a distinct
`unavailable`/error status for that SR (never an empty `findings` tuple standing in for "reviewed,
found nothing" — those two must stay distinguishable, matching this design's repeated insistence
elsewhere, e.g. `_human_review_obligation`'s own docstring, that absence is never silently read as
a satisfied state).

**Tests** (`tests/unit/coherence/register/test_fidelity.py`) — one fixture per the plan's own test
list, each a hand-built `FidelityPacket` + a stub `judge` returning a fixed verdict, so these tests
never depend on a real model call:
1. **Supported link** — packet with a production symbol whose body plausibly implements the SR
   statement and a test whose body plausibly exercises it; stub judge returns no findings; assert
   `findings == ()`.
2. **Overstated link** — stub judge returns one `overstated_link` finding; assert it round-trips
   through validation and lands in the result with `status="open"` (or `"escalated"` under a
   non-high-assurance profile — see #4).
3. **Partial/understated link (weaker-subset test)** — packet where the AC compound-describes two
   behaviors but the linked test's excerpt only exercises one; stub judge returns
   `weaker_subset_test`; assert citation includes the specific test node.
4. **Incidental helper link** — packet where `implemented_by` points at a genuinely-called utility
   function, not the behavior owner; stub judge returns `incidental_helper`.
5. **High-assurance vs normal disposition** — same findings, two packets differing only in
   `profile`; assert `status="open"` under `high_assurance` and `status="escalated"` under every
   other compiled profile — this exercises T5's own status-assignment rule, not
   `_human_review_obligation` (that stays covered by its own existing tests, unmodified).

Also (not in the plan's original "Tests:" line, but required by the schema/enforcement work above):
6. **`missing_link_compound`** fixture — packet where one AC's clause has no declared relation at
   all; stub judge returns `missing_link_compound` with `acceptance_ref` set to that AC's id.
7. **`different_behavior`** fixture — linked symbol/test whose excerpt plainly does something else;
   distinguishes this from `incidental_helper` (helper still touches the right area; different
   behavior does not).
8. **Judge unavailable/invalid** — stub judge raises or returns malformed output; assert the result
   carries an explicit unavailable/error status, not an empty `findings` tuple.

### T5.4 — Persistence and re-run disposition tracking

Implement durable storage for a `FidelityReviewResult` (see revised "Open design questions" #3 —
T4 has now landed and, unlike this plan originally anticipated, persists **nothing**: both
`structural_review` and `evidence_reconciliation_review` are computed fresh on every
`coherence register review` CLI call and only ever printed as JSON. There is therefore no T4
storage convention for T5.4 to "agree with" — this justification stands on its own instead:
fidelity review is agent-driven and comparatively expensive to re-run, and needs re-run
disposition tracking (so a human's past `accept` is not silently re-litigated) in a way T4's free,
deterministic checks do not. SR-050's "separately report... never merged" requirement is satisfied
at the *reporting* layer by T5.5's distinct `fidelity` JSON key, not by mirroring T4's storage
choice.) Provisional shape: `review-findings/fidelity/<sr_id>.json`, mirroring
the existing `gate-decisions/sr-<SR-ID>.json` per-artifact file convention already used in this
repo. A re-run reads the previous result (if any); a finding whose `(kind, relation)` pair matches
a prior finding that a `review:<sr_id>` accept decision now post-dates is written back with
`status="dispositioned"` rather than `"open"`/`"escalated"` again.

**Tests** (`tests/unit/coherence/register/test_fidelity_persistence.py`):
- first write creates the file; a second run with identical findings overwrites idempotently (no
  duplicate entries);
- a finding a human has since accepted past (a matching, later `review:<sr_id>` accept
  `DecisionFile` exists) is written back `dispositioned`, not re-`open`ed;
- a finding with no matching prior disposition stays `open`/`escalated` per profile every re-run.

### T5.5 — CLI surface

Extend the existing `coherence register review` command (`src/coherence/register/cli.py`'s
`cmd_review`, landed by T4) rather than adding a new top-level `coherence review` command family —
T4 already prints `structural` and `evidence_reconciliation` as top-level JSON keys from
`coherence register review <SR-ID>|--all`; add a `--fidelity` flag that, when set, also runs
`review_fidelity` and adds a third top-level `fidelity` key to the same JSON output (three
categories, each its own key, never merged — extending AC-2's "never merged into one verdict"
clause in spirit to AC-4's findings too). A `--check` flag on the same command (gated behind
confirming Open design question #1) satisfies the high-assurance CI-gate rule in "Enforcement
mechanics": non-zero exit only per that rule, across every in-scope SR.

**Tests** (`tests/unit/coherence/register/test_cli_review_fidelity.py`, extending T4's existing CLI
test coverage in the same module): `--fidelity` prints/returns a result for a fixture repo as a
distinct `fidelity` key alongside `structural`/`evidence_reconciliation`; `--check` exits 0 for an
all-`escalated` (non-high-assurance) fixture and non-zero for a fixture with an `open`
(high-assurance) finding.

## Verification commands

```bash
uv run python -m pytest tests/unit/coherence/register -q
uv run python -m pytest tests/unit/coherence/policy/test_compiler.py -q
uv run python -m pytest tests/unit/trace -q
uv run ruff check src/coherence/register tests/unit/coherence/register
```

## Open design questions

These are flagged rather than silently resolved, per this task's own instruction:

1. **Does "for `high_assurance` work, unresolved fidelity findings block" get a new CI gate step
   (proposed above, reusing `_ci_verification_obligation`), or is it considered already satisfied
   by `_human_review_obligation` alone** (which already blocks `high_assurance` SR closure on an
   attributed accept, with or without a fidelity reviewer existing)? AC-4's own text only commits
   to the latter; the design spec's "Review agents" section states the former as intent. This plan
   recommends building the CI-gate step, but a human should confirm that reading before T5.5 is
   implemented, since it is the one place T5 would touch `.factory/factory.yaml` gate config (not
   `policy/compiler.py` itself).
2. **Should `_human_review_obligation`'s `reason`/`resolve_cmd` strings be enriched to name the
   fidelity report path** when open findings exist, or should that visibility live entirely in the
   CLI/dossier (T6) instead? A one-line string change to an already-tested function needs its own
   explicit sign-off given how deliberately `_human_review_obligation`'s docstring documents every
   existing line's rationale.
3. **Persistence location and shape** — revised 2026-09-03 post-review: T4 has now landed and
   persists nothing (both deterministic reviewers compute fresh per CLI call, never writing a
   per-SR findings file). There is therefore no T4 storage convention to coordinate with or wait
   for; `review-findings/fidelity/<sr_id>.json` (T5.4) stands on its own justification (re-run
   disposition tracking for an expensive, agent-driven review) and can be implemented independent
   of T4's timeline. AC-2/AC-4's "never merged into one verdict" is satisfied at the *reporting*
   layer (distinct `structural`/`evidence_reconciliation`/`fidelity` JSON keys, see revised T5.5)
   — T5's storage choice does not need to mirror T4's (or vice versa) to stay consistent with that.
4. **The `judge` dispatch mechanism for T5.3** (how the fidelity packet actually reaches a
   model and how its output is parsed back) is deliberately left as an injected interface in this
   plan rather than a concrete subagent-invocation design — this repo's existing subagent dispatch
   conventions (e.g. `coherence.audit.runner`'s verdict collection, if reusable) should be reviewed
   before committing to a shape, since inventing a second dispatch convention here would repeat the
   exact anti-pattern this plan is otherwise avoiding for the packet/findings layers.
5. **`missing_link_compound` scoping**: when an SR has no `acceptance:` block at all (a legacy SR
   with only a bare `statement`), is the whole statement treated as one implicit "clause" for this
   finding kind, or is `missing_link_compound` simply inapplicable to such SRs (only
   `overstated_link`/`incidental_helper`/etc. can fire)? Needs a human answer before T5.3's fixture
   5/6 are finalized against real (non-fixture) SRs.
