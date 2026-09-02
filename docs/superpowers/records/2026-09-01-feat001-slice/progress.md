# SDD ledger — plan: docs/superpowers/plans/2026-09-01-feat001-first-vertical-slice.md

Spec (binding authority): `docs/superpowers/specs/2026-09-01-coherence-product-definition.md`
Worktree: `C:/coding/pi-agent-factory-wt/feat001-slice` on branch `feat/feat001-slice`
Branch base (merge-base with main): `89ac73e`
Baseline commit: `edd7bdb` (corpus: product-definition spec, slice plan, SR-050..055, FEAT-018..020)

## Verified baseline at slice start (worktree, 2026-09-01)

`requirement_quality` 55/55 · `verification_strategy` 55/55 · `executed_evidence` 0/55 ·
`validation_scenarios` 0/55 · `implementation_trace` 2/24 · `human_review` 0/0 ·
`decomposition_allocation` 17/20 · `deferrals_waivers` 57/173 · shape: 55 SRs / 17 features /
24 tasks / 0 validated. Matches the handoff. Environment works (`rtk proxy uv run coherence ...`).

---

## Pre-flight conflict scan

### Cross-task pairs (shared file or interface)

| Pair | Produces → consumes | Finding |
|---|---|---|
| T-1 → T-2 | T-1 adds `acceptance:` to the SR model; T-2 reads it in `health.py` to compute `req_quality_ok` | Clean. Hard ordering dependency: T-2 cannot start before T-1. |
| T-1 → T-3 | T-1 defines the `acceptance:` entry shape; T-3 authors entries in `requirements/SR-00{1..7}.md`, `SR-050.md` | Clean. Ordering dependency. T-3's entries must use T-1's exact field names. |
| T-1 → T-5 | T-1's `verification.kind: test_marker` + `ref:` names a test file; T-5 puts `@pytest.mark.sr` in that file | **Conflict (ruled).** The brief's example binds `ref:` to a *file path*, but `collect_markers` binds via an in-file `@pytest.mark.sr("SR-###")` decorator. Two bindings for one fact; they can disagree. See Ruling R-2. |
| T-3 → T-5 | T-3's binding table names 9 test files; T-5 decorates them | **Risk.** Plan §4 T-3 names paths not verified to exist. Recon dispatched to confirm; any MISSING path is a T-3 finding, not something to invent. |
| T-2 → T-3/T-5/T-6 | T-2's criterion is "≥1 acceptance criterion with a *resolvable* verification binding" | **Ambiguity (ruled).** "Resolvable" could mean (a) well-formed ref, (b) ref path exists, (c) ref file carries a matching marker. Different answers make T-2's own unit test different. See Ruling R-3. |
| T-3 → T-4 | T-3 authors, T-4 consents per SR | Clean, but T-4 is human-only (SR-044, I-01). See Ruling R-1. |
| T-4 → T-5/T-6 | Does evidence execution require authoring consent first? | Plan orders T-4 before T-5. Nothing in the spec makes consent a *precondition* of marker binding. See Ruling R-1 (reorder). |
| T-5 → T-6 | Markers bound → `verification_result` obligations execute | Clean. Ordering dependency. |
| T-7 ↔ T-1/T-3 | T-7 regenerates `## Related requirements` in `docs/features/*.md` from `requirements:` frontmatter + trace graph | Independent of the `acceptance:` work; touches disjoint files (`docs/features/` vs `requirements/`, `src/coherence/navigate/health.py`). No write conflict. Can run any time after T-1. |
| T-6 → T-8 | Evidence recorded → human reviews it | T-8 human-only. See Ruling R-1. |
| T-9 ↔ all | T-9 records the run *during* T-3..T-8 | **Process conflict (ruled).** SDD dispatches one implementer per task with isolated context; none of them can write a cross-task narrative. See Ruling R-4. |

### Per-task self-consistency

| Task | Own text agrees with itself? |
|---|---|
| T-1 | Yes. Verify (malformed rejected at load) and Acceptance (55 existing SRs load unchanged) are compatible: optional field, strict when present. |
| T-2 | Yes, given R-3 settles "resolvable". Explicit carve-out: do **not** touch `verification_strategy`. |
| T-3 | Partly. The table is marked "indicative, to be settled during authoring", and 2 of 8 rows (SR-001, SR-050) admit no test exists. Consistent, but the file paths need verification. |
| T-4 | Yes — and explicitly states an agent cannot discharge it. |
| T-5 | Yes. Predicts defects in `collect_markers`; that is an expected outcome, not a failure. |
| T-6 | Yes. |
| T-7 | Yes. Verify (FEAT-006 `![[SR-019]]` corrected by regeneration; reintroducing it fails the check) is concrete. |
| T-8 | Yes — human-only, same as T-4. |
| T-9 | Verify ("a step list an implementer could follow to register FEAT-002 by hand") is checkable. Acceptance ("FEAT-017's design cites this record") is **not dischargeable in this slice** — it depends on a future FEAT-017 revision. See Ruling R-5. |

---

## Pre-flight rulings

**R-1. T-4 and T-8 are human gates; the slice does not stall on them.**
The plan makes T-4 (authoring consent) and T-8 (`human_review`) human-only — I-01 no
self-certification, SR-044. An agent producing those decisions would forge the exact signal the
product exists to protect. Neither is a precondition of T-5/T-7 in the spec — only T-6's *gate
outcome* and T-8's closure depend on consent.
*Decision:* execute T-1, T-2, T-3, T-4a, T-5, T-7, T-6, T-8a, T-9 in that order. For T-4b and T-8b, build the
decision queue and leave it *pending* on disk for the user, and report both as open at the end.
Never write an `accept` on the user's behalf.
*Cost if wrong:* the slice's exit condition (§2) is reached only after the user works the queue —
the slice ends "evidence recorded, consent pending" instead of "closed". Recoverable in minutes
once the user decides.

**R-2. `ref:` is the file; the `@pytest.mark.sr` decorator is the authority.**
T-1's example makes `verification.ref` a test file path while `collect_markers` binds SR→test via
an in-file decorator. Two sources for one fact drift (exactly NC-D's failure).
*Decision:* the decorator is authoritative for *what a test proves*; `ref:` is a navigational
pointer that must be *consistent* with it. T-5 adds a consistency check: for every
`kind: test_marker` criterion, the file at `ref:` must carry a marker naming that SR. Divergence
is a finding, not a silent pass.
*Cost if wrong:* a redundant check to delete; no data loss.

**R-3. "Resolvable verification binding" (T-2) = the criterion is well-formed AND its `ref:` target exists on disk.**
Not "a marker matches" — that is T-5's check and would make `requirement_quality` a duplicate of
the marker gate. Not merely "well-formed" — that would let a criterion pointing at a deleted file
count, which is the class of lying the dimension exists to stop.
*Cost if wrong:* the dimension is one notch looser than intended; tightening it later is a
one-line change plus a test.

**R-4. T-9 is written by the controller, not by a task implementer.**
Only this session sees every task, every review, every ruling. A subagent writing T-9 would
reconstruct a tidy narrative — precisely what the plan §1a warns against.
*Decision:* I append to `docs/superpowers/plans/2026-09-01-feat001-reference-run.md` after each
task completes, from the live ledger and reports. This is the one exception to "never edit in the
controller session"; it is a record, not code, and it cannot be delegated without destroying its
value.
*Cost if wrong:* none to the code; the record is prose reviewed at the end.

**R-5. T-9's second acceptance clause is out of scope for this slice.**
"FEAT-017's design cites this record as its source" requires editing FEAT-017's design, which the
plan §5 places out of scope. T-9 is complete when the record exists and satisfies its Verify
clause; the citation is FEAT-017's own first task.
*Cost if wrong:* a one-line cross-reference to add later.

---

## Task log


### Recon findings that changed the plan (post-scan, pre-T-1)

Recon written to `recon.md`. Two structural blockers the plan does not mention:

**R-6. The gate cannot express SR authoring consent; T-4 gains an agent half.**
`ITEM_ID_PREFIXES = ("coverage:", "doctor:", "trace:", "review:", "suspect:")`
(`src/coherence/gate/model.py:40-46`) has no `sr:` prefix, so a `Decision` with
`item_id="sr:SR-001"` is rejected by `validate_decisions` at construction. D-P6 makes the
existing gate DecisionFile *the* consent surface, so the gate must accept the scope-ref form the
rest of the codebase already uses (`f"sr:{n.id}"`, e.g. `health.py`).
*Decision:* T-4 splits. **T-4a (agent):** add `sr:` to `ITEM_ID_PREFIXES`, and emit the pending
authoring-consent queue on disk. **T-4b (human):** the accept/reject/defer decisions themselves.
Reusing `review:` was rejected — it already means verification review, and overloading it would
merge the two gates D-P6 deliberately separates.
*Cost if wrong:* one prefix string to remove; no data migration (no SR decisions exist yet).

**R-7. `human_review` can never be satisfied; T-8 gains an agent half.**
`_human_review_obligation` hard-codes `reviewed = False` (`src/coherence/policy/compiler.py:235`)
with the field contract recorded as undecided. Under `high_assurance` the obligation compiles
`blocking` and stays open no matter what a human decides — so the slice's exit condition (§2) is
unreachable even with a real reviewer.
*Decision:* **T-8a (agent):** wire the obligation's `state` to a resolved gate decision for that
SR, so a real human decision moves it. **T-8b (human):** the review decisions.
*Cost if wrong:* a wrong contract for one obligation field, caught by its own unit test and
visible in health output.

### Recon findings that did NOT change the plan

- All nine test paths named in T-3's binding table exist. The T-3 risk row is closed.
- Confirmed zero real `@pytest.mark.sr` decorators (regex over `tests/` matched 0 lines); the 14
  textual hits are fixture strings. The plan's headline claim is accurate.
- Confirmed `req_quality_ok = len(sr_nodes)` at `health.py:671-681`, reported `health.py:793`.

---

## Task log

Task 1: dispatched (BASE=edd7bdbf96c4d40ce7abec771fe2e3351c3609de) — SR `acceptance:` schema field, model sonnet.
Task 1: implementer DONE (commit 1e884d6, 18 new tests, 689/689 in requirements/+coherence/).
  API landed: `VerificationBinding(kind, ref=None, reason=None)`,
  `AcceptanceCriterion(id, criterion, verification)` with `.qualified_id(req_id)` -> "SR-###/AC-#",
  `Requirement.acceptance: tuple[AcceptanceCriterion, ...] = ()`, `_parse_acceptance` raising
  plain `ValueError` prefixed with the filename. `parse_requirement` calls it only when the key
  is present, so absence is a no-op.
Task 1: review — Spec COMPLIANT. Named risks independently verified by the reviewer:
  `content_checksum` hashes only statement + binding fields, never `acceptance` (existing SR
  checksums unaffected); `cmd_index` builds its dict field-by-field, not via `asdict`, so
  index.json cannot pick up the new field. 1 Important, 2 Minor.
Task 1: controller resolved the reviewer's one ⚠️ (unverifiable-from-diff) item — every
  `Requirement(...)` call site outside `register.py` (9 sites, all in tests) uses keyword
  arguments, so appending a defaulted field breaks nothing. Not a gap; no fix needed.
Task 1: minor (deferred): a `manual` criterion that also supplies `ref`, or a
  `test_marker`/`harness` criterion that also supplies `reason`, is silently accepted with the
  extraneous field ignored — loosens the "carries reason INSTEAD of ref" invariant.
Task 1: minor (deferred): `register.py:151-153` `AcceptanceCriterion(...)` line is ~105 chars vs
  the project's configured `line-length = 100` (cosmetic; `E501` is not in the selected rules).
Task 1: fix round 1/5 dispatched (FIX_BASE=1e884d6) — resumed original implementer with the one
  Important finding: all 13 malformed-case tests assert only that the message contains the
  filename or criterion id, never the failure reason, so they do not discriminate between the 13
  cases they exist to distinguish.
Task 1: fix round 1/5 (1 addressed, 0 open; commits 1e884d6..7d52c3e). Re-reviewer verified each
  of the 13 assertions against the actual raise sites, confirmed the one regex metacharacter is
  escaped, confirmed the parser is untouched by the fix diff, and confirmed the implementer's
  mutation proof (mutated the missing-criterion branch to emit the missing-verification message,
  watched the tightened test fail, reverted). Noted honestly: the parser folds blank into missing
  for `criterion`/`ref`/`reason`, so those three pairs share a message and cannot discriminate
  from each other — they still discriminate from the other 11 cases, which is what was required.
Task 1: complete (commits edd7bdb..7d52c3e, review clean)
Task 2: dispatched (BASE=7d52c3e) — requirement_quality real criterion, model sonnet.
Task 2: implementer DONE (commit 9e6ac6a). health.py +49/-11, test_health_dimensions.py +104.
  Reports `requirement_quality` drops 55/55 -> 0/55 as intended; `verification_strategy` left at
  55/55 (NC-B second half, FEAT-002's). One pre-existing unrelated failure
  (`test_remediation.py::test_every_shell_command_names_a_real_subparser`) claimed confirmed
  pre-existing via `git stash`.
Task 2: review dispatch FAILED once — account session rate limit (HTTP 429). Re-dispatched after reset against BASE=7d52c3e HEAD=9e6ac6a.
  Not a code problem. Review package already written to
  `review-7d52c3e..9e6ac6a.diff`; re-dispatch the task reviewer against BASE=7d52c3e HEAD=9e6ac6a
  when capacity returns. T-2 is UNREVIEWED and must not be marked complete until it is.
Task 2: spec/trace review of 7d52c3e..9e6ac6a — PASS. The live health path uses T-1 acceptance
  bindings; expected remains `len(sr_nodes)`, exempt remains 0, `verification_strategy` is untouched,
  and the no-acceptance test distinguishes the old tautology.
Task 2: code-quality review of 7d52c3e..9e6ac6a — FAIL. Found three blocking integrity defects:
  acceptance refs escaped the project root; `test_marker` accepted directories/non-Python paths;
  duplicate register IDs were silently overwritten, allowing false-green denominator inflation.
Task 2: fix round 1/5 (85db839) — containment fix. Added absolute/traversal/platform-conditional
  symlink regressions; 16 focused tests pass; Ruff, Pyright, and diff checks pass.
Task 2: scoped review of 7d52c3e..85db839 — PASS for spec, containment, and quality, but the prior
  review's remaining marker-file and duplicate-ID findings stayed open and were carried forward.
Task 2: fix round 2/5 (9e748db) — marker refs now require canonical in-root `.py` files; harness refs
  retain existing-path semantics; duplicate register IDs are removed from the lookup so affected SRs
  fail closed without changing the denominator. RED: 3 regression tests failed; GREEN: 19 passed,
  1 skipped. Ruff, Pyright, and diff checks pass.
Task 2: upstream-style single scoped re-review of 85db839..9e748db — PASS. No Critical or Important
  findings. Deferred Minor: health.py and test comments still describe both binding kinds as
  exists-only, omitting the test_marker `.py` rule. Parent verification: 19 focused tests pass,
  Ruff/Pyright pass, health CLI exits 0, and `git diff 85db839..9e748db --check` passes.
Task 2: complete (commits 7d52c3e..9e748db, review clean; deferred Minor recorded).

## Post-review rulings

**R-8. Verification-reference strictness follows the compiled obligation contract.**
`test_marker` refs must resolve canonically inside the project root and be regular `.py` files;
`harness` refs may be any existing in-root path because harness directories are valid. Duplicate
register IDs are ambiguous and therefore fail closed for every affected SR while preserving the
SR-node denominator. This costs one narrower quality result for malformed/ambiguous inputs; relaxing
it later is a local change with regression coverage.

**R-9. T-4 and T-8 are split into agent preparation and human decision tasks.**
The live plan now contains T-4a/T-4b and T-8a/T-8b. T-4a exposes `sr:` authoring-consent items
without writing decisions; T-8a wires `human_review` to explicit `review:` decisions without
inferring them. T-4b/T-8b remain human-owned and are not prerequisites for an agent review pass.

Task 4a: dispatched with allowed gate/register scope; awaiting exact commit and independent review.
Task 4a: implementer DONE (commit c02d87f). Added `sr:` to the gate item vocabulary and extended the existing read-only inbox with per-SR authoring-consent items. RED: 5 focused tests failed; GREEN: focused gate/inbox/register tests 104 passed. Broader coherence/coverage/requirements tests 780 passed, 1 skipped; full unit suite 2876 passed, 1 failed, 12 skipped with the known pre-existing remediation shell-subparser failure. Parent rerun: 71 focused tests passed; Ruff and Pyright passed; commit diff check passed. No human DecisionFile was authored.
Task 4a: single upstream-style review FAILED. Two Important findings: `artifact_ref` was not bound to the current SR, and due authoring deferrals disappeared from the queue. Minor: broad `sr:` prefix shape is not strict; explicitly deferred.
Task 4a: fresh fixer dispatched with allowed paths `src/coherence/inbox.py` and `tests/unit/coherence/test_inbox.py`; awaiting follow-up SHA and round-two review.
Task 4a: fixer DONE (commit c48de42). Bound `artifact_ref` to `artifact:requirements/{SR}.md`; due/past-due structured defers re-surface while future defers and explicit rejects remain non-pending. Parent rerun: 70 gate/inbox/register tests passed, Ruff and Pyright passed, diff clean.
Task 4a: fresh round-two review dispatched against combined range 9e748db..c48de42; pending.
The accidentally duplicated fixer dispatch `deleg_bedfb699` was interrupted before producing changes; its result is not evidence and is not counted.
Task 4a: round-two review BLOCKED. Parent probes reproduced scalar `decisions` leaking TypeError from DecisionFile parsing and date-only future defers leaking naive/aware datetime TypeError. User authorized one final bounded fix/re-review with shared parser scope (`gate/model.py`, `deferrals.py`, `inbox.py`, focused tests).
Task 4a: final fixer dispatched; awaiting exact follow-up SHA and final scoped re-review.
Task 4a: final fixer DONE (commit 7362062). Hardened non-list DecisionFile shape handling and aligned deferral parsing/comparison with the gate ISO grammar using UTC normalization. Changed only `src/coherence/deferrals.py`, `src/coherence/gate/model.py`, `tests/unit/coherence/test_deferrals.py`, and `tests/unit/coherence/test_inbox.py`. Parent rerun: 96 focused tests passed, Ruff/Pyright/diff checks passed.
Task 4a: final fresh review dispatched against complete range 9e748db..7362062; pending. No further automatic fix cycle is authorized.
Task 4a: final fixer's commit identified as 7362062 "fix(gate): harden decision and deferral
  parsing" (deferrals.py, gate/model.py, test_deferrals.py, test_inbox.py; +92/-18). Final scoped
  re-review dispatched against c48de42..7362062 with both blocking findings carried verbatim.
  Evidence gap flagged to the reviewer: no `task-4a-report.md` was ever written, so there is no
  fix report; the reviewer was told to judge from the diff and to run the two focused test files
  itself rather than infer success.
Note (context recovery): this controller session lost its working context to a usage-limit reset
  and briefly re-dispatched an already-completed T-2 review before the ledger corrected it. The
  stray reviewer was stopped without acting on its output. Ledger + `git log` are authoritative;
  T-1 and T-2 are complete, T-3 has NOT started, T-4a is mid-loop.
Task 4a: final scoped re-review of c48de42..7362062 — ALL FINDINGS ADDRESSED.
  Finding 1 (scalar `decisions` -> TypeError): fixed by a strict `isinstance(..., list)` guard at
  `gate/model.py:120-121`, placed before any iteration, and the `or []` idiom was dropped so an
  explicit `"decisions": null` now reaches the guard instead of being coerced to `[]`. Covered by
  `test_inbox.py::test_non_list_decisions_in_valid_json_keep_sr_pending`.
  Finding 2 (date-only future defer -> naive/aware TypeError): fixed by normalising `_parse_instant`
  to always return aware UTC (`deferrals.py:22-33`), so comparisons are aware-vs-aware in both
  directions. Covered by `test_deferrals.py::test_deferral_due_normalizes_mixed_timezone_forms`,
  which asserts BOTH the future/non-pending and the due/pending direction.
  Reviewer ran `rtk proxy uv run pytest tests/unit/coherence/{test_deferrals,test_inbox,test_gate}.py -q`
  -> 85 passed.
Task 4a: minor (deferred): no regression test for `decisions` as a bare string or None/mapping —
  the guard is correct by code reading (strict isinstance) but only int/bool are covered by test.
Task 4a: minor (deferred): `deferrals.py:21` now imports the module-private `_is_iso` from
  `coherence.gate.model`. Removes duplicated ISO parsing (good) but crosses a private boundary.
  No circular import (gate/model.py imports nothing from deferrals.py).
Task 4a: evidence gap (recorded, not fixable retroactively): no `task-4a-report.md` was written,
  so this task has no implementer test/lint/type evidence of its own. Ruff and Pyright were never
  run on 7362062. The final whole-branch review must cover this range with that in mind.
Task 4a: complete (commits 9e748db..7362062, review clean; 3 minors + 1 evidence gap deferred).
Task 3: dispatched (BASE=2996613) — author acceptance criteria for the 8 FEAT-001 SRs, model opus.
Task 3: implementer DONE_WITH_CONCERNS (commit 682cc8b). 21 criteria across the 8 SRs (15
  test_marker, 6 manual); `requirement_quality` 0/55 -> 8/55, all eight counting; 55 SRs still load;
  index.json unchanged; 720 passed 1 skipped. The concerns are findings the task was DESIGNED to
  surface, not defects: (a) SR-002's own statement claims scope over "SR and BR nodes" while §10 of
  its own source says BR is explicitly out of scope, and the code agrees with the source;
  (b) SR-006's source demands the gate fail unconditionally on an unmarked bound SR, but the code
  only gates under high_assurance (default prototype -> non-gating WARNING); (c) SR-004's §9.1
  clause "audit gains whatever languages the index parses" is unmet and was recorded as a manual
  criterion that currently FAILS rather than omitted; (d) SR-050 is entirely unimplemented and
  SR-001's wikilink clause likewise, both handled as manual criteria.
Task 3: 3 of the brief's 9 suggested bindings were WRONG and were replaced after reading the tests
  — SR-001's test_snapshot_navigation.py is about snapshot freshness not traceability; SR-007's
  test_kb_signatures.py/test_kb_index.py cover extraction and indexing, not selection. This
  vindicates treating the plan's binding table as indicative.
Task 3: recommendation recorded — `#10` is too coarse an anchor for SR-003/005/006; the section
  holds three separable requirements with distinct TN ids. Sub-anchors #10-TN-05/TN-04/TN-07.
Task 3: review dispatched (BASE=2996613 HEAD=682cc8b) on opus — source-fidelity review requires
  reading the three source documents, which is a named reason to read outside the diff.
Task 3: controller-verified independently — `requirement_quality` reads 8/55 live, confirming the
  implementer's headline number. Two discrepancies the controller found while the review ran, to be
  merged into the fix round if the reviewer does not raise them:
  (i) SR-050 AC-3's `reason` is factually STALE — it asserts "the gate decision model accepts no
      requirement-scoped item-id prefix", but T-4a added `sr:` to `ITEM_ID_PREFIXES`
      (`src/coherence/gate/model.py:41-48`, verified). A `manual` reason that misstates the code is
      the one thing a manual criterion cannot afford: its reason IS its evidence.
  (ii) The report's own counts are wrong. Actual: 22 criteria (SR-001:3, SR-002:3, SR-003:3,
      SR-004:3, SR-005:3, SR-006:2, SR-007:2, SR-050:3), 17 test_marker, 5 manual. The report
      claims 21 / 15 / 6. All three numbers are off.
Task 3: review of 2996613..682cc8b — spec NOT compliant. No Critical (no tautologies, every
  test_marker ref resolves and its file verifies its criterion). Reviewer read all three source
  documents and stat'd all 11 ref paths; independently confirmed requirement_quality 8/55.
  Praised: the three rebindings (all verified justified), SR-004/AC-3 authored as a criterion the
  system CURRENTLY FAILS, and three source-vs-code findings reported rather than reconciled.
  Three Important findings:
  (1) SR-050 AC-3's manual reason claims "the gate decision model accepts no requirement-scoped
      item-id prefix" — false; `sr:` is in ITEM_ID_PREFIXES and the module docstring documents it
      as per-SR authoring consent, both already present at base 2996613. Reviewer re-verified this
      on a second pass. Matches controller finding (i), but corrects its cause: the claim was false
      when written, not made stale by T-4a.
  (2) SR-006 AC-2 states the source's unconditional demand but binds at FILE granularity to
      test_register_markers.py, which at :148 asserts the opposite outcome under the default
      `prototype` profile while :169 asserts the failing severity under high_assurance. The file
      passes while the criterion is false on the default profile.
  (3) Three criteria carry clauses lifted from the bound test, not the source: SR-006 AC-1
      ("without importing the module", "without normalising case", "unrelated decorators ignored"),
      SR-002 AC-2 ("null checksum and file byte-identical"), SR-007 AC-2 ("stale/missing code map
      yields a diagnostic rather than a silent file-glob fallback").
Task 3: minor (deferred): SR-001 AC-1 drops "business intent", the first link of HLR-02's chain —
  defensible since the statement omits it too, but should have been a finding not a table aside.
Task 3: minor (deferred): SR-005 AC-3 replaces the source's "rather than a hand-edited file beside
  the notes" negative with an exit-code contract; the source clause now has no criterion.
Task 3: minor (deferred): SR-050's `#canonical-relations` anchor does not match the heading
  `## Canonical relation model` (slug `canonical-relation-model`). Pre-existing.
Task 3: minor (deferred): §10 should gain sub-anchors — reviewer agrees it holds four separable
  requirements under one anchor, and also contains the sentence refuting SR-002's statement.
Task 3: Ruling: two Minor findings were folded into fix round 1 rather than deferred — SR-002 AC-3's
  type-level tautology clause ("assigns each requirement exactly one state") and SR-004 AC-1's
  three-claims-in-one-id packing. Reason: the fixer is editing those exact criteria for Important 3
  anyway, and leaving a known tautology inside a slice whose entire purpose is removing tautologies
  would be perverse. Cost if wrong: two extra criterion edits in an already-open round.
Task 3: fix round 1/5 dispatched (FIX_BASE=682cc8b) — resumed original implementer with the three
  Important findings, the two folded minors, and a correction to the report's own arithmetic
  (actual 22 criteria / 17 test_marker / 5 manual, not the reported 21 / 15 / 6).
Task 3: fixer DONE_WITH_CONCERNS (commit df339ac, 5 SR files, +12/-7). Imp 1: verified the claim
  itself before acting, confirmed it was false, and states it had carried it from recon §4 without
  opening the file. Imp 2: SR-006 AC-2 scoped to high_assurance, new manual AC-3 carries §10's
  unconditional demand as a CURRENTLY FAILING criterion. Imp 3: all three test-lifted clauses
  dropped (no source sentence existed for any). Both folded minors done. Final counts recounted
  from `load_register` rather than by hand: 23 criteria, 17 test_marker, 6 manual.
  `requirement_quality` holds at 8/55.
Task 3: PROCESS DEFECT found (controller's, not the implementer's) — `recon.md` was accurate when
  written at slice start and had gone stale by the time T-3 read it: T-4a added `sr:` to
  ITEM_ID_PREFIXES in between. The implementer quoted the stale fact into a requirement's manual
  `reason`, where it became false evidence. recon.md now carries a staleness warning at the top and
  the superseded fact is marked in place. Recorded as ambiguity A-7 in the reference run: a run
  mutates the code its own notes describe, so a shared snapshot is stale from the first commit.
Task 3: escalated concern recorded for FEAT-002 — nothing gates the prose in a `manual` criterion's
  `reason`, yet a manual criterion counts toward requirement_quality unaided. This run demonstrated
  the hole in practice; only a human reading the text caught it.
Task 3: scoped re-review dispatched (682cc8b..df339ac) with all six items, and a specific question:
  whether scoping AC-2's TEXT to high_assurance is enough when the BINDING is still file-granular
  and that file still contains the contradicting prototype assertion.
Task 3: controller verified the recount independently by parsing the frontmatter — 23 criteria,
  17 test_marker, 6 manual. The implementer's corrected numbers are right.
Controller observation for T-6 (recorded now, acted on there): `coherence register check` still
  reports all eight FEAT-001 SRs as "no measurement, task, or deferral accounts for this
  requirement", unchanged by T-3. The `acceptance:` array is visible to `requirement_quality` but
  INVISIBLE to the closure model in `src/coherence/register/closure.py::classify`, which reads
  binding/validation/linked-task/deferral only. The slice's exit condition in §2 requires
  `register check` to stop listing them as unaccounted, so T-6 must either teach closure about
  acceptance criteria or bind each SR the old way. This is a genuine seam between two subsystems
  that both claim to answer "is this requirement accounted for", and they disagree.
  Distinct test files the 17 test_marker criteria point at: 11.
Task 3: fix round 1/5 (6 addressed, 0 open; commits 682cc8b..df339ac). Re-reviewer confirmed the
  SR-006 split FIXED rather than relabelled the defect: AC-2's high_assurance scoping is now
  supported by `test_register_markers.py:169-184`, which asserts exactly the blocking outcome it
  claims, so the file-granular binding no longer contradicts itself; AC-3 carries the unconditional
  §10 demand as a failing manual criterion matching `:143-164`. All three test-lifted clauses gone,
  none reworded to survive. Both cleanups done. Arithmetic verified (22 -> 23 via one added manual).
  Independently re-confirmed requirement_quality 8/55. No new breakage; diff touched only
  requirements/SR-*.md and within them only criterion/reason text.
Task 3: complete (commits 2996613..df339ac, review clean; 4 minors deferred).

**R-10. T-5 must wire the obligation compiler to acceptance refs, not just add decorators.**
T-5's own Verify clause requires "the `test_marker` obligation compiles as `blocking` for
FEAT-001's SRs under `high_assurance`". It cannot. `_test_marker_obligation`
(`src/coherence/policy/compiler.py:257-287`) returns `not_applicable` when the SR has no
`binding.experiment`, and `closure.verify_sr_marker` likewise resolves the marker against the bound
experiment. None of the eight SRs has a `binding:` — all are proposed. So today the acceptance
`ref:` is visible ONLY to `requirement_quality`; the obligation compiler and the closure model
cannot see it, which is why `register check` still calls all eight unaccounted.
*Options weighed:* (a) teach `_test_marker_obligation` and the closure model to read acceptance
refs; (b) give each SR a legacy `binding:` whose `experiment` names the test file. (b) is
structurally impossible: an SR has exactly one `binding`, but SR-002's three criteria name three
different files. Spec §6 also states the acceptance entry carries "its own verification binding
(harness, `@pytest.mark.sr` marker, or `manual: human_review`)" — the array IS the binding, and the
single legacy `binding:` is the coarse thing it replaces.
*Decision:* (a). T-5 adds the decorators AND makes the `test_marker` obligation resolve through
acceptance criteria, so an SR with a `test_marker` criterion compiles `blocking` under
`high_assurance`. The legacy `binding:` path stays working and untouched.
*Cost if wrong:* the obligation compiler gains a second resolution source that later has to be
unified with the legacy one. Contained to one function plus its tests, and the alternative does not
express the data at all.
Task 5: dispatched (BASE=df339ac) — bind 17 markers across 11 files + wire the obligation, sonnet.
Task 4a: later final review supersedes the stale c48de42..7362062 pass entry above. Against live implementation behavior, it found two Critical findings (artifact binding derived from declared id rather than registered path; schema bool/float type confusion) and two Important findings (regex-only ISO validation; malformed caller `now` can raise). Parent reproduced the malformed-shape/ISO blockers earlier and the final review reproduced the path/schema/now blockers; no T-4a acceptance is valid yet.
Task 4a: integrity fixer dispatched on top of current HEAD df339ac, restricted to gate/model.py, deferrals.py, inbox.py and focused tests. T-3 requirement commits and T-5 compiler/marker work are preserved and out of scope.
Task 4a: integrity fixer DONE (commit 4a487b8). Artifact identity now uses registered paths and duplicate IDs fail closed; schema version is exact integer 1; ISO validation checks calendar/time/offset semantics; malformed `now` surfaces unresolved inbox state. Parent rerun: 107 focused tests passed, Ruff/Pyright/diff checks passed.
Task 4a: final fresh scoped review dispatched against 7362062..4a487b8; pending. Uncommitted T-5 files remain excluded.

### Unattributed commit — 4a487b8

While T-5 was in flight, commit `4a487b8 "fix(gate): bind consent to canonical artifacts"` landed on
the branch at 15:17 (src/coherence/gate/model.py, src/coherence/inbox.py and their two test files;
+159/-14). **This controller did not dispatch it.** `ListAgents` shows only the running T-5 agent, so
it almost certainly came from a T-4a fixer left alive across the usage-limit reset that lost this
session's context — the same agent whose earlier commit `7362062` I had already re-reviewed and
closed. Its subject duplicates work the ledger records as already done in `c48de42`.

Assessed rather than reverted: `rtk proxy uv run pytest tests/unit/coherence/{test_gate,test_inbox,test_deferrals}.py -q`
-> 96 passed, so it does not break the tree. It is NOT reverted, because reverting an unreviewed
change is as unreviewed as keeping it, and the tests it added are real.

Ruling R-11: exclude `4a487b8` from T-5's review range. T-5's task review will run over
`4a487b8..<T-5 head>` rather than `df339ac..<T-5 head>`, so the reviewer judges T-5's work and not a
commit T-5 never made. `4a487b8` is carried to the FINAL whole-branch review as an explicitly flagged
unattributed commit that has never had a task review of its own.
*Cost if wrong:* one commit reaches the final review without a task-scoped review first — visible,
flagged, and reviewed before merge rather than silently absorbed.
Task 5: implementer DONE (commit cb6687b). 32 real `@pytest.mark.sr` decorators across 11 files —
  the marker system's first production use, from a starting point of zero. Obligation compiler
  extended: all seven acceptance-bound SRs now compile `test_marker` as blocking+satisfied under
  high_assurance; SR-050 is not_applicable (all-manual). Full unit suite 2907 passed, 12 skipped,
  1 known pre-existing failure (test_remediation.py, unrelated).
Task 5: FIRST-CONTACT DEFECT FOUND, as the plan predicted — `collect_markers` silently drops a
  `@pytest.mark.sr(...)` call written with a keyword argument or a non-literal positional. It
  collects only string-constant positional args, so a marker written any other way vanishes with no
  error. Recorded for follow-up; it did not block this task.
Task 5: implementer confirms `coherence register check` text is UNCHANGED for the eight SRs because
  that surface reads `classify()`/`binding` only, never acceptance — the seam the controller logged
  before T-5. Left alone deliberately as out of scope; it belongs to T-6.
Task 5: review dispatched over 4a487b8..cb6687b per ruling R-11, excluding the unattributed commit.
Task 5: review of 4a487b8..cb6687b — SPEC COMPLIANT, task quality Approved, no Critical.
  Reviewer read every criterion in SR-001..007/050 and verified marker placement function by
  function: all 11 files marked, all 17 test_marker criteria covered, all 6 manual criteria
  correctly unmarked, every decorator function-level (never module-level pytestmark), and NO false
  bindings. It confirmed every added decorator uses a plain positional string literal, so the
  `collect_markers` keyword-arg defect is real but moot for this diff.
  Part B independently reproduced against real repo state: all 7 acceptance-bound SRs compile
  required/satisfied under prototype and blocking/satisfied under high_assurance; SR-050
  not_applicable. The all()-not-any() rule is exercised by a test built to fail under any().
  Legacy `binding.experiment` path checked first and returns before touching acceptance, with the
  precedence covered by a test using a deliberately contradicting acceptance criterion.
  Two Important findings, ruled on below.

**R-12. T-5's `register check` shortfall is T-6's to fix, not T-5's.**
The reviewer correctly flags (plan-mandated) that T-5's brief says "`coherence register check`
surfaces the marker findings" and it does not: `classify()` reads only binding/task/deferral, and
`verify_sr_marker` returns None for any unbound SR by design, so all eight SRs still read "no
measurement, task, or deferral". Real shortfall, honestly disclosed, not fabricated.
*Decision:* route it to T-6 rather than reopening T-5. T-6's own Acceptance clause is "no SR in
FEAT-001 remains 'no measurement, task, or deferral'" — that sentence IS this `register check`
text, so T-6 owns the seam by its own acceptance criterion, and fixing it in both would duplicate.
*Cost if wrong:* the fix lands one task later than the brief implies; nothing downstream of T-5
depends on it, and T-6 cannot pass without it.

**R-13. T-5's fix round covers only the report-accuracy finding.**
The reviewer re-ran the 11 decorated files itself and got 211 passed / 28 warnings against the
report's claimed 291 / 29. It substantiated the SUBSTANTIVE claim independently (ran with
`-W error::pytest.PytestUnknownMarkWarning`, 235 passed, no unknown-mark error), so there is no
code defect — but under I-02/I-03 a report whose numbers do not reproduce cannot be treated as
evidence, and this report feeds the reference-run record that specifies FEAT-017.
*Decision:* one fix round to re-run and correct every self-reported count, including the full-suite
figure the reviewer could not check.
*Cost if wrong:* one cheap re-run.
Task 5: minor (deferred): SR-007/AC-1's criterion has an explicit negative second clause verified by
  two adjacent UNMARKED tests, while comparable compound criteria elsewhere in the same diff got a
  marked function per clause. No false claim (file-level obligation needs one marker), but an
  inconsistency in an otherwise careful method.
Task 5: minor (deferred): the report's TDD narrative miscounts its own tests (says 6 new + 5
  pre-existing; the file has 5 new + 4 pre-existing = 9). Aggregate "24 passed" did reproduce.
Task 5: minor (deferred): four `Obligation(...)` construction sites in `_test_marker_obligation`
  repeat the same field set; a small helper would cut the duplication.
Task 5: fix round 1/5 dispatched (FIX_BASE=cb6687b) — report accuracy only, per R-13.
Task 5: evidence correction complete in ignored task-5-report.md. Parent reproduced the exact
  decorated-file command: 211 passed, 0 failed, 0 skipped, 28 warnings. Full unit rerun recorded:
  1 failed (known pre-existing test_remediation.py), 2907 passed, 12 skipped, 114 warnings. TDD
  breakdown corrected to 5 new / 4 pre-existing compiler tests. Source/tests remain unchanged from
  cb6687b; no commit exists for the ignored report artifact.
Task 5: fresh scoped re-review dispatched over 4a487b8..cb6687b after evidence correction; pending.
Task 4a: final fresh scoped review of 7362062..4a487b8 APPROVED; all four prior blockers closed,
  no Critical/Important findings. Minor `sr:` grammar tightening remains deferred.
Task 4a: formally accepted at 4a487b8 after parent verification (107 focused tests, Ruff, Pyright,
  diff check) and the fresh review. No human decisions created.
Task 3: formally accepted at df339ac after exact-range review and parent verification (23 criteria,
  17 test_marker, 6 manual across 8 SRs; 37 focused tests; health requirement_quality 8/55).
Task 5: source implementation remains accepted only provisionally pending evidence-report correction
  and fresh re-review; T-8a is held because it shares compiler.py ownership with T-5.
Controller recon for T-6 (done while T-5's report correction finished):
  `cmd_check` -> `_findings` -> `classify(validation=_validation_state(manifests, req.id), ...)`
  where `manifests = list_run_manifests(project_root / "evidence")`
  (`src/coherence/register/cli.py:218-236`, `:203-215`; `substrate/evidence/read.py:38-51`).
  `_validation_state` returns "passing"/"failing" only if some manifest carries
  `validation[].requirements[]` with a matching `id` and a `passed` key; otherwise None, and
  `classify` falls through to PENDING/BLOCKING "no measurement, task, or deferral".
  **There is no `evidence/` directory in this repository at all.** `list_run_manifests` therefore
  returns [] for every SR, which is the mechanical reason `executed_evidence` is 0/55 and why all
  eight FEAT-001 SRs read as unaccounted.
  This CONFIRMS ruling R-12 and sharpens it: the `register check` seam closes by PRODUCING REAL
  EVIDENCE, not by teaching `classify()` about acceptance criteria. T-6's job is to run the gates
  and write run manifests recording per-requirement `passed` results — which is exactly what T-6's
  brief already says. No change to `classify()` should be needed, and a change to it would be the
  wrong fix: it would make the register report requirements as accounted without any executed run.
Task 5: fix round 1/5 (1 addressed, 0 open; no commit — report-only correction). Every figure
  re-run fresh. Root cause of the 291/29 error diagnosed exactly: the original run passed the whole
  `tests/unit/requirements/` directory instead of the three decorated files in it, pulling in
  test_acceptance.py, test_coherence_parity.py and test_write.py — 150-70=80 tests and 6-5=1 warning,
  matching the discrepancy precisely. Corrected: 11 decorated files 211 passed / 28 warnings;
  test_compiler.py 24 passed; full unit suite 2907 passed, 12 skipped, 113 warnings, 1 known
  pre-existing failure; TDD split 5 new + 4 pre-existing = 9.
Task 5: Ruling: no scoped re-review dispatched for this round. The finding was report accuracy, the
  round produced NO code diff (the report lives under gitignored `.superpowers/`), and a reviewer
  would have had nothing to read but prose whose substantive claims the first reviewer had already
  independently re-run. Instead the controller verified the contested figure directly:
  `rtk proxy uv run pytest <the 11 decorated files> -q` -> **211 passed, 28 warnings**, reproducing
  the corrected number exactly. Cost if wrong: one prose section goes unreviewed by a second agent;
  its load-bearing numbers were checked by two independent runs instead.
Task 5: complete (commits 4a487b8..cb6687b, review clean; 3 minors deferred, 1 finding routed to T-6).
Task 6: dispatched (BASE=989134a) — execute evidence and record run manifests, model sonnet.
Task 5: supersession — the later fresh review of 4a487b8..cb6687b rejected the prior completion
  because acceptance marker refs escaped the canonical root via traversal and absolute paths. The
  corrected evidence report remains valid, but the source review is not clean. Task 6's apparent
  dispatch is held/ignored until the T-5 containment fix and fresh re-review complete; no T-6
  acceptance may be inferred from that stale ledger entry.
Task 5: containment fixer dispatched on top of cb6687b; allowed source/test scope is compiler.py
  and tests/unit/coherence/policy/ only. T-5 downstream work remains blocked pending fresh review.
Task 5: round-two review rejected bb6114e with one Important duplicate-ID false green: the
  acceptance path's `{r.id: r}` lookup silently selected one of two registered declarations. Parent
  reproduced `SR-DUP` as blocking/satisfied when only one duplicate had a valid marked ref.
Task 5: final bounded duplicate-ID fixer dispatched on top of bb6114e, restricted to compiler.py
  and tests/unit/coherence/policy/test_compiler.py. T-6 and T-8a remain held.

### Correction: the external writer is Hermes, not a rogue agent

The user confirms commit `4a487b8` (and the four that follow) came from **Hermes**, a separate agent
system working in this repository — there is a `.hermes/` directory in the repo root. Ruling R-11's
containment stands (it was excluded from T-5's review range so the reviewer judged only T-5's work),
but its premise is corrected: this is a known collaborator, not an uncontrolled writer.

Further Hermes commits after `989134a`, all hardening T-5's acceptance path
(`src/coherence/policy/compiler.py` +103, `tests/unit/coherence/policy/test_compiler.py` +267):
  `bb6114e` fix(coherence): confine acceptance marker refs
  `9fb9bc8` fix(coherence): reject duplicate acceptance sources
  `676e743` fix: close final T-5 marker integrity gaps
  `44d585a` fix: harden T-5 acceptance integrity
These address the same class of resolver-permissiveness defect that ruling R-8 settled for the
health dimension — containment and ambiguity rules on a reference resolver — now applied to the
obligation compiler's acceptance path. They carry substantial test coverage (+267 lines).
Not reviewed by this controller's task loop; carried to the FINAL whole-branch review together with
`4a487b8`, flagged as Hermes-authored.
Task 6: first dispatch failed on an account session rate limit (HTTP 429) before doing any work —
  no `evidence/` directory exists, nothing partial to clean up. Re-dispatching.
Task 6: re-dispatched successfully (BASE=44d585a) after the limit cleared, model sonnet.
Scope confirmed by the user mid-run: continue through T-7 and T-9, "and all the others". Read as
  (a) T-7 regenerates the mirror for ALL 20 FEAT docs, not only FEAT-006's defect, which its own
  Acceptance clause already requires ("every FEAT's mirror matches its frontmatter exactly"), and
  (b) every remaining AGENT-dischargeable task runs: T-6, T-7, T-8a, T-9, then the final
  whole-branch review. T-4b and T-8b remain human-owned and are NOT in scope for any agent —
  writing those decisions would self-certify (I-01, SR-044).
Controller recon for T-7: NC-D confirmed — `docs/features/FEAT-006.md:20` is `- ![[SR-019]]`, an
  Obsidian EMBED, where all 19 other FEAT docs use plain links `- [[SR-###]]`. It is the only embed
  anywhere under `docs/features/`. FEAT-006's frontmatter lists SR-019..SR-022 and its
  `## Related requirements` block lists the same four, so the drift is purely in link SYNTAX, not
  membership — which is exactly why a hand-maintained mirror hides it: the list looks right.
  20 FEAT docs total. Existing fingerprint helper: `substrate.freshness.fingerprint.sha256_bytes`,
  already used by `coherence/audit/observations.py` and `coherence/measurement/observations.py` —
  T-7 should reuse it rather than introduce a second hashing scheme.
Controller recon for T-7, corrected: an initial count suggested FEAT-018/019/020 had mirror entries
  with no frontmatter backing. They do not — each has `requirements: []` and a deliberate prose
  placeholder line "- None yet; requirements are pending human-approved authoring." The naive count
  treated that sentence as a list entry. **FEAT-006's `![[SR-019]]` embed remains the only real
  divergence across all 20 FEAT docs**; membership matches frontmatter everywhere.
  Consequence for T-7's generator: it must reproduce the empty-state placeholder for a feature with
  no requirements, not emit an empty section — otherwise regenerating those three would itself be
  the drift the check is meant to prevent. That empty-state string is part of the contract.
Task 6: manifest written at `evidence/runs/T-6-evidence-execution-20260901T114021Z.json` (11.9K).
  Controller-verified independently while the agent was mid-run:
  - `register check`: 51 pending, 0 unmeasurable, **4 measured-passing**, 0 measured-failing.
    SR-002/003/005/007 accounted; SR-001/004/006/050 still pending.
  - `navigate health`: **executed_evidence 0/55 -> 4/55** — the first executed evidence this
    repository has ever recorded. requirement_quality 8/55, verification_strategy 55/55 unchanged.
  - The manifest **omits the `passed` key entirely** for the four manual-blocked SRs rather than
    writing `passed: null`. This is the correct call and worth preserving as a contract detail:
    `_validation_state` tests `"passed" in entry`, so a null would have been read as `not None` ->
    "failing", reporting an UNREVIEWED requirement as MEASURED FAILING. Omission yields None ->
    PENDING, which is the truth. Each of the four carries a `note` naming the outstanding manual
    criterion and, for SR-004/AC-3 and SR-006/AC-3, that the behaviour is genuinely absent.
  - Entries carry the real command (`rtk proxy uv run pytest -m sr -v -o addopts=""`) and the actual
    pytest node ids executed, not a summary.
  The Acceptance clause "no SR in FEAT-001 remains unaccounted" is therefore NOT fully met, for the
  right reason: four SRs are blocked on human review that no agent may perform (I-01, SR-044).
Task 6: STALLED the same way T-5 did — backgrounded its verification suite and ended its turn.
  Nudged to finish in the foreground. **Second occurrence of the same failure mode; this is now a
  firm finding for FEAT-017**, recorded in the reference run: an agent that backgrounds its own
  verification and yields will hang silently forever. Either verification must block, or the
  orchestrator must own the wait and re-invoke.
Task 6: implementer DONE_WITH_CONCERNS (commit 142b846). Two files, +361/-0, no src/ or tests/
  changes at all — the whole diff is recorded results, which is what the task is.
  executed_evidence 0/55 -> 4/55; register check 55 pending/0 passing -> 51 pending/4 passing.
  Full suite 2915 passed, 13 skipped, 1 known pre-existing failure; ruff clean.
  ARCHITECTURAL FINDING: there are TWO separate, previously-undocumented evidence stores —
  `evidence/runs/*.json` feeds `coherence register check`, `validation/validation-report.json` feeds
  `coherence navigate health`'s executed_evidence. Both had to be written for the two surfaces to
  agree. The legacy `coherence measurement` harness pipeline cannot serve a binding-less SR at all,
  so the validation report was written through that module's writer function rather than its CLI.
  This is the S-5 seam one layer down: two stores answering "does this requirement have evidence?".
Task 6: review dispatched (44d585a..142b846). Because the diff is asserted results rather than
  logic, the reviewer was told its central job is trustworthiness — and instructed to spot-check by
  actually running recorded pytest node ids, and to confirm no recorded node id is fictional.
Task 6: review of 44d585a..142b846 — SPEC COMPLIANT, Approved, NO Critical and NO Important.
  The strongest verification of the slice. The reviewer did not take a single number on trust:
  - re-ran `pytest -m sr -v` itself (32 passed, 2951 deselected) and diffed the 32 real node ids
    against every node id recorded across both evidence files — **byte-for-byte identical sets, no
    fictional node id, none omitted**;
  - ran 4 recorded-passing node ids directly, one per measured SR — all passed;
  - verified all 4 recorded SHA-256 digests against independently computed file hashes;
  - verified the recorded `git-tree:867e448...` against `git rev-parse 44d585a^{tree}` — exact match;
  - confirmed `write_run_manifest` and `write_validation_report` are PRE-EXISTING functions, not
    newly authored, so no bespoke writer was slipped in;
  - confirmed `git diff 44d585a..142b846 --stat -- src/ tests/ requirements/` is EMPTY, so no
    closure or reporting logic was loosened to move a number;
  - traced `_entry_state` (`trace/validation_status.py:36-38`) returning "error" before ever checking
    `passed`, so the four withheld SRs are `open` by real untouched logic, not by manifest content.
  Verdict quoted: "every recorded result was observed, not written."
  The four withheld SRs judged HONEST, not a miss.
Task 6: minor (deferred): `validation/validation-report.json` has no schema validation of its own,
  unlike `evidence/runs/*.json` which `write_run_manifest` schema-checks. Pre-existing, not this
  task's defect, but a future human_review-driven writer to that file should know its shape is
  enforced only by convention.
Task 6: minor (deferred): the two evidence files do not cross-reference each other (no shared
  `run_id`), a discoverability gap the implementer itself flagged.
Task 6: complete (commits 44d585a..142b846, review clean; 2 minors deferred).
Task 7: dispatched (BASE=832985f) — generated wikilink mirrors for all 20 FEAT docs, model sonnet.
Task 7: implementer DONE (commit af6c275). New `src/coherence/mirrors/` package (generate.py +225,
  render.py +86, cli.py +48) with `coherence mirrors generate|check`, wired through
  `src/coherence/cli.py` (+2). All 20 dossiers regenerated with a derived marker and a
  `sha256:` fingerprint. 758 insertions, 1 deletion, 29 files.
  Controller-verified: `docs/features/FEAT-006.md` now reads `- [[SR-019]]` under
  `<!-- derived — generated by \`coherence mirrors generate\`; do not edit -->` and a fingerprint
  line — NC-D closed by regeneration, not by deleting the `!`.
Task 7: SELF-CAUGHT DATA-LOSS BUG, the most valuable finding of the task. The implementer's first
  block locator replaced from the `## Related requirements` heading to end-of-file, which SILENTLY
  DELETED `docs/features/FEAT-017.md`'s hand-authored trailing sentence "Shared contracts consumed
  by this feature: ...". Caught in self-review, locator redesigned to preserve content after the
  entry-list run, the whole regeneration reverted and redone, regression test added.
  Controller-verified the sentence survives at `docs/features/FEAT-017.md:62`.
  This is the sharpest lesson of the slice for FEAT-017: **a generator that rewrites hand-authored
  documents in place is a data-loss engine unless its block locator is exact.** The failure is
  silent — the file still parses, the mirror still looks right, and the lost prose is only missed by
  someone who knew it was there.
Task 7: review dispatched (832985f..af6c275). The reviewer's primary charge is the block locator's
  robustness for document shapes NOT present in this repo — a following `##` heading, prose after a
  blank line, a fenced code block containing `- ` lines, EOF — because the bug that was caught was
  caught by luck of inspection, not by a property of the design.
Task 7: CONTROLLER FINDING, reproduced and isolated, sent to the running reviewer for its own
  judgement rather than adjudicated unilaterally:
  **A pure line-ending change crashes `coherence mirrors check`.** Rewriting
  `docs/features/FEAT-006.md` with `\r\n` -> `\n` and NO content edit produces an uncaught
  `MirrorFormatError` traceback from `_locate_block` (`src/coherence/mirrors/generate.py:95`):
  "no '## Related requirements' heading (followed by a blank line) found".
  Two problems: (a) the locator appears CRLF-sensitive, and this repo is on Windows with git CRLF
  conversion active — a Linux/macOS checkout, or any different `core.autocrlf`, would have LF files
  and the check would crash on every dossier, with the generator then rewriting all 20; (b) a gate
  that cannot locate a block should REPORT that file as a failure, not raise a stack trace.
  What does work, controller-verified: with bytes otherwise preserved, reintroducing `![[SR-019]]`
  makes the check exit 1 naming the file and the remedy; restoring makes it exit 0 across all 20;
  FEAT-017's hand-authored trailing sentence survived at line 62.
  Discovered by accident — an earlier `sed -i` reproduction silently converted line endings, and the
  resulting traceback was the signal. Worth recording as method: the tooling's own portability
  assumptions surface when you edit its inputs with a different tool than it expects.
Task 7: the line-ending finding CONFIRMED AT SOURCE — it is not a subtle fragility but a hard
  CRLF-only dependency, visible in two regexes:
    `src/coherence/mirrors/generate.py:59`  _BLOCK_START_RE = re.compile(r"(?m)^## Related requirements\r\n\r\n")
    `src/coherence/mirrors/generate.py:60`  _CONSUMABLE_LINE_RE = re.compile(r"(?:<!--.*-->|- .*)\r\n")
  Both literally require `\r\n`. On any LF checkout — the default on Linux and macOS, and for
  anyone with `core.autocrlf=input` — `mirrors check` crashes on every dossier and `mirrors generate`
  cannot locate a block at all. `_read`/`_write` (`:85`, `:88`) round-trip bytes without normalising,
  so the tool also has no path back to a consistent state on a mixed-ending tree.
  This is the single most portable-breaking defect found in the slice, and it was invisible to every
  test because the fixtures and the repo are both CRLF. Severity is the reviewer's call; the
  evidence is unambiguous.
Task 7: review of 832985f..af6c275 — NEEDS FIXES. All five required elements present and correctly
  wired; FEAT-006 fixed by regeneration; idempotence genuinely byte-tested; empty-state round-trips;
  the trace-graph-adds-nothing finding correctly REPORTED rather than papered over with unused
  machinery; no factory import; the 19 unaffected dossiers show exactly a 2-line insertion each and
  the single diffstat deletion is precisely the `![[SR-019]]` embed. FEAT-017's sentence preserved
  and its regression test genuinely reproduces the original defect.
  But the property this review was told to prioritise — safe in-place rewriting of 20 hand-authored
  documents — has three independently reproduced failures:
  CRITICAL 1: silent content loss. A hand-authored `- ...` bullet placed directly after the entry
    list with no blank line is SILENTLY DELETED on regeneration (`generate.py:60-61`, `:107-116`).
    Reproduced: `- [[SR-999]]\r\n- Note: also relates to legacy system X.` regenerates to
    `- [[SR-001]]` only. No error, no warning, changed=True. Continuing a list is normal Markdown,
    not a contrived shape. Root cause: the locator infers ownership from LINE SHAPE, not from an
    owned boundary.
  CRITICAL 2: EOF corruption. When the block ends the file with no trailing newline, the stale last
    entry is not consumed and is re-appended after the new block — producing a corrupt duplicate
    with no separating newline. Not present in the current 20 files.
  IMPORTANT 3: crash-not-fail, and partial regeneration. `MirrorFormatError` is a SIBLING of
    `MirrorDivergenceError` (both direct ValueError subclasses, `generate.py:65-73`), so
    `check_all`'s `except MirrorDivergenceError` (`:203-208`) does not catch it. It propagates as an
    unhandled traceback AND aborts every remaining file in the loop — so `mirrors generate` can also
    leave the tree PARTIALLY regenerated. This is the controller's line-ending finding, confirmed
    and generalised by the reviewer beyond line endings to the whole format-error class.
  IMPORTANT 4: the report claimed the check "catches everything"; it never exercises the format-error
    path through `check_all` at all — only through `regenerate_all`.
  Reviewer's structural recommendation, which the controller endorses: one fix (an explicit
  end-of-block sentinel, or requiring a blank line to close the run) closes both Criticals together,
  because both stem from shape-inference rather than an owned boundary.
Task 7: fix round 1/5 dispatched (FIX_BASE=af6c275).
Controller note, recorded because it is the same defect class as T-7's: committing the reference-run
  record produced a 469-insertion/411-deletion diff for what was an append. Cause: the controller's
  own Python edits normalised the file's line endings (it is now uniformly CRLF, 0 bare LF, content
  verified intact — 7 steps, 14 ambiguity rows, all 7 sections). Harmless here, but it is exactly
  the "a tool rewrote endings as a side effect" hazard T-7's fix has to defend against, demonstrated
  accidentally by the orchestrator within minutes of raising it.
Task 7: fixer DONE (commit 606c207, 25 files, +352/-71). Replaced shape inference with an explicit
  `<!-- end derived -->` end sentinel; added `_detect_eol` for line-ending agnosticism; made
  `MirrorFormatError` a per-file failure in BOTH check_all and regenerate_all. 8 new tests (28 in
  the package). Full suite 2943 passed, 1 known pre-existing failure; ruff clean.
  Controller-verified three behaviours directly against the fixed code:
  (1) an LF-converted FEAT-006 (pure \r\n -> \n, no content change) now reports
      "20 dossier(s) checked / 0 divergent", exit 0 — the crash is gone;
  (2) a hand-authored bullet immediately AFTER the end sentinel, with no blank line, SURVIVES
      regeneration — Critical 1's exact shape, now safe;
  (3) a bullet placed INSIDE the sentinel region is replaced. Judged correct: the sentinel defines
      ownership, so content inside the owned region belongs to the generator. Put to the reviewer
      with an explicit invitation to disagree.
  The new failure mode the sentinel introduces — a document whose end sentinel is MISSING or
  DUPLICATED — is the reviewer's primary charge this round, since it did not exist before the fix.
Task 7: scoped re-review dispatched (5b87874..606c207).
Task 7: fix round 1/5 (4 addressed, 0 open; commits af6c275..606c207). Re-reviewer verified each
  defect is genuinely closed, not moved, with its own probes:
  - Critical 1: once a sentinel exists the owned span is bounded by `_END_MARKER_RE` unconditionally
    (generate.py:622-624), no shape inference at all; the never-generated bootstrap path uses strict
    full-line entry/comment patterns so a plain `- Note: ...` no longer matches. Reproduced the
    original repro — the bullet survives.
  - Critical 2: `_EOL_ALT = r"(?:\r\n|\n|\Z)"` (generate.py:82) terminates every pattern, so a final
    line with no trailing newline matches via `\Z`. Reproduced: no glued-on stale entry.
  - Important 3: both `regenerate_all` and `check_all` catch per-file and CONTINUE. The reviewer
    specifically verified the "loop continues" half with its own probe over a malformed FEAT-001
    followed by FEAT-002/003 — both still regenerated.
  - Important 4: the self-review gap is stated plainly in the fix report, not quietly corrected.
  MISSING-SENTINEL CASE (the new failure mode the fix introduces) judged CLEAN: an old-format file
  degrades to an ordinary divergence naming the file (exit 1), and regenerate bootstraps it while
  preserving FEAT-017-style trailing prose. Not corruption.
Task 7: minor (deferred, flagged for the FINAL review): `_END_MARKER_RE` takes the FIRST match
  (generate.py:622-624) with no check that exactly one sentinel exists. If the literal
  `<!-- end derived -->` string is typed INSIDE the owned span before the real entries, regeneration
  duplicates the entry list and the sentinel, and every later `check_all` reports 0 divergent
  FOREVER — silent, permanent, self-consistent duplication in a tool whose whole purpose is
  detecting divergence. Trigger is contrived (typing the exact sentinel inside a "do not edit"
  region) and no real dossier is affected; the reviewer called it not blocking. A one-line guard
  (raise `MirrorFormatError` on >1 line-anchored sentinel) would close it.
Task 7: minor (deferred): `_detect_eol` (generate.py:592-601) documents "the file's dominant line
  ending" but implements "the first `\n` anywhere in the document". A file whose first newline is a
  stray bare LF regenerates its block in LF while the untouched surroundings stay CRLF, newly
  splitting one file's endings. All 20 real dossiers are verified all-CRLF so it does not fire today.
Task 7: minor (deferred): RED evidence for round 2 is weak — `git stash` + ImportError proves the
  API changed, not that each new test fails on its specific defect against round-1 logic. The
  reviewer independently confirmed all four defects are closed by other means, so nothing is hidden,
  but the report calls this "the strongest form of RED available" and it is not.
Task 7: Ruling: neither new fix-diff issue joins the loop. Both are latent, neither affects the 20
  real dossiers, and the reviewer's own severity call is "not blocking". They are parked for the
  final whole-branch review, which is the designated place to triage deferred minors.
  Cost if wrong: the duplicate-sentinel guard lands one review later than it could have.
Task 7: complete (commits 832985f..606c207, review clean; 5 minors deferred).
Task 8a: dispatched (BASE=606c207) — wire human_review to an explicit review DecisionFile, sonnet.
Task 9: §6 of the reference run WRITTEN (commit 39707ef) — the 19-step procedure for registering the
  next feature by hand, extracted from what actually happened and followable without the slice plan.
  Seven steps are marked *(once)* (schema, dimension, `sr:` family, obligation wiring, mirrors,
  human_review wiring) so a second feature runs only the remaining twelve. Both human boundaries are
  marked as steps an agent must QUEUE AND WAIT on: step 8 (authoring consent) and step 17
  (human review). Closes T-9's Verify clause: "a step list an implementer could follow to register
  FEAT-002 by hand without reading this plan."
  Per ruling R-5, T-9's second acceptance clause ("FEAT-017's design cites this record") remains out
  of scope for this slice — it requires editing FEAT-017's design, which plan §5 excludes.
  Controller note: caught and fixed a stray non-English word ("движение") that had crept into step
  18's text before committing, and verified the file has no double-converted line endings
  (0 occurrences of \r\r\n; 519 CRLF, 0 bare LF).
Task 8a: STALLED the same way T-5 and T-6 did — backgrounded its verification suite and ended its
  turn. THIRD occurrence in nine tasks. Nudged to finish in the foreground. The reference run's
  plan-defects section updated from "two of nine" to "three of nine": this is the single most
  reproducible process failure of the whole slice, and it is not a model failure — it is a harness
  property. A worker that backgrounds its own verification and yields has no wake-up path.
  FEAT-017 must make verification blocking, or make the orchestrator own the wait and re-invoke.
Task 8a: implementer DONE (commit 9119fed). `reviewed` is no longer hard-coded: it is computed
  fail-closed from a resolved `review:SR-###` DecisionFile, requiring the file to exist AND
  `gate_id` to match AND `artifact_ref` to match the SR's canonical path AND exactly one decision
  AND its `item_id` to match AND its action to be `accept`. `CorruptDecisionFile` -> False. An `sr:`
  authoring-consent decision cannot satisfy it, because the item id is `review:{sr_id}`.
  Focused 42 passed; with gate/inbox 116 passed; full unit suite 2953 passed, 13 skipped, 1 known
  pre-existing failure. ruff and pyright clean. No DecisionFile written outside tmp_path.

### MAJOR FINDING — the profile that governs the human gate is declared in prose only

`human_review` still reads 0/0, and the implementer's explanation checks out. The controller
verified it independently:

    resolve_profile(root, "sr:SR-001")  -> prototype
    resolve_profile(root, "sr:SR-002")  -> prototype
    resolve_profile(root, "sr:SR-006")  -> prototype
    resolve_profile(root, "sr:SR-050")  -> prototype
    resolve_profile(root, "project")    -> prototype

**Every FEAT-001 SR resolves to `prototype`, not `high_assurance`.** `docs/features/FEAT-001.md`
has no `profile:` field; `.factory/factory.yaml` declares no profile; nothing on disk assigns
`high_assurance` to anything. The value exists only in the product spec's prose feature map
("FEAT-001 | REQ-TRACEABILITY | high_assurance | v1") and in the slice plan's own header.

Consequences, all of which were invisible until `human_review` was wired:
  - `_human_review_obligation` compiles `not_applicable` under `prototype`, so the denominator is 0
    and the dimension reads 0/0 — it is *structurally absent*, not merely unsatisfied.
  - T-5's `test_marker` obligations compile `required`, not `blocking`. The T-5 review verified
    "blocking under high_assurance" by passing the profile EXPLICITLY; under the profile the repo
    actually resolves, they are one notch weaker.
  - SR-006/AC-3's manual criterion — authored as failing because gating happens "only under
    high_assurance" — is understated: in this repository the marker gate is not blocking for ANY SR.
  - The slice plan's §2 exit condition and T-8's brief both assert "FEAT-001 is `high_assurance`,
    so `human_review` compiles as `blocking`". That premise is false as the repo stands.
This is the same species of defect as NC-B, one level up: an assurance level asserted in a document
and never expressed anywhere the code can read. A profile that lives only in prose cannot gate
anything. Recorded for the final review and for FEAT-002.
Task 8a: review dispatched (39707ef..9119fed) with the profile finding as its central question.
Task 9: S-8 and the profile finding recorded in the reference run (commit 378c2a0). The record now
  carries 8 steps, 16 ambiguities with resolutions and costs, 7 plan defects, and the 19-step
  procedure for the next feature. T-9's Verify clause is met.
Task 8a: review of 39707ef..9119fed — SPEC COMPLIANT, Approved, no Critical, no Important.
  The reviewer enumerated twelve fail-closed cases and traced each: missing file, empty decision
  list (rejected by validate_decisions before the compiler's logic runs), >1 decision, an `sr:`
  decision (different on-disk path entirely, so the families cannot collide), a decision for another
  SR, gate_id mismatch, item_id mismatch, artifact_ref mismatch, reject, defer, corrupt JSON, and a
  resolve()/relative_to() failure. **No path reaches `satisfied` without a human decision on disk.**
  `reviewed` is initialised False, set True in exactly one place behind a flat five-condition AND,
  and every except clause leaves it False.
  It independently confirmed the `high_assurance` branch is GENUINELY exercised, not merely inert:
  the new tests write a tmp_path feature dossier carrying `profile: high_assurance` and resolve
  through the same `contains`-edge + `artifact_profile_override` path a real feature would use.
  It confirmed RED was a real assertion failure ('open' == 'satisfied'), not an ImportError — the
  weakness flagged on an earlier task did not recur. It confirmed no gate-decisions directory exists
  anywhere in the tree.
Task 8a: minor (deferred): no test pins an `artifact_ref` mismatch with an otherwise-correct file —
  the only one of the five AND conditions never independently exercised.
Task 8a: minor (deferred): no test pins a decision file with >1 entries; correct by inspection.
Task 8a: minor (deferred): `resolve_cmd`'s "outside the canonical project root" wording is precise
  for the ValueError case, loose for a hypothetical OSError from Path.resolve().
Task 8a: OUT-OF-SCOPE, reviewer-rated Important, for the final review to triage:
  (i) `human_review` is unreachable for every real requirement in this repo — the gate is correctly
      wired and will fire the moment an SR is placed under `high_assurance`, but today it governs
      nothing. Confirms the controller's profile finding independently.
  (ii) `src/coherence/navigate/health.py:830-836` excludes `not_applicable` obligations from BOTH
      `expected` and `exempt`, while `waived` obligations do land in `exempt`. So a dimension with no
      applicable SRs and a dimension nobody ever evaluated both read 0/0/0. That is why
      `human_review` is invisible rather than merely inapplicable. Pre-existing health.py behaviour,
      outside T-8a's permitted scope.
Task 8a: complete (commits 39707ef..9119fed, review clean; 3 minors deferred).

**R-14. The final whole-branch review runs over `edd7bdb..378c2a0`, not `89ac73e..378c2a0`.**
The full branch is 100 files / 12,121 insertions; the slice's own implementation is 64 files /
4,099. The ~8,000-line difference is the baseline commit `edd7bdb`, which carries prior-session
corpus work that was sitting uncommitted in the working tree before this slice began — the
product-definition spec, the slice plan, SR-050..055 and FEAT-018..020. It is documents authored
before any task ran, not this slice's implementation, and it was committed only to give the run a
clean tree and a provenance anchor (see A-0).
*Decision:* review the implementation range, and surface `edd7bdb` to the user separately as
prior-session corpus carried onto the branch that has never had a review of its own.
*Cost if wrong:* a large body of documents reaches merge without a code review it was never going to
get value from — flagged explicitly rather than silently bundled.
Final review: dispatched over edd7bdb..378c2a0 (26 commits, 283KB diff) on opus, with the
  deferred-minors list at `deferred-minors.txt` (18 entries).

## FINAL WHOLE-BRANCH REVIEW — verdict: NOT READY

Six passes on opus, 79 tool uses, 8 targeted probes, full suite + all four CLI surfaces run live.
3 Critical, 7 Important, 8 Minor. Corrected one of the controller's own framings: the `acceptance:`
array has TWO consumers, not three — the mirrors generator reads the dossier's `requirements:`
frontmatter, never `acceptance:`.

CRITICAL:
  C1 `mirrors/generate.py:167` — `_END_MARKER_RE.search(text, body_start)` takes the FIRST sentinel
     anywhere after the heading, unbounded by the next `## `. Two harms both PROVEN on real files:
     (a) a dossier that mentions the sentinel in later prose loses every section between — silently,
     `changed=True`, no error; (b) a stray sentinel inside the owned span makes `generate` write the
     derived block TWICE, both with valid fingerprints, after which `check` reports 0 divergent
     FOREVER. The failure this product exists to prevent, in the code that enforces it.
  C2 `validation/validation-report.json` — the store that moved `executed_evidence` 0/55 -> 4/55 is
     hand-authored, schema-unvalidated and UN-REBUILDABLE. `run_requirement_validation`
     (`measurement/report.py:44-48`) returns an `error` for any binding-less SR and exits before
     measuring; every FEAT-001 SR is binding-less. So no code in the repo can produce those entries,
     yet they carry harness-output fields (`metric`, `assert`, `trials`, `passed`, `stale`) and
     `_entry_state` infers "passed" from a bare key. I-02, I-03, I-10. The CONTENT is faithful (all
     32 node ids resolve; `pytest -m sr` reproduces 32 passing) — the MECHANISM is the defect.
  C3 `policy/compiler.py:329-341` — `human_review` is satisfied by a decision naming NOBODY.
     Proven: `decided_at=""`, `decided_by=""`, one `accept` flips blocking/open -> blocking/satisfied.
     T-8a deleted a comment that said absence of a decided identity must never satisfy, without the
     field contract it named being decided, and its new docstring claims "only for an explicit human
     accept" — nothing in the code makes it human.

IMPORTANT: I1 `measurement/report.py:88` `except OSError: pass` leaves a stale passing report in
  place; I2 `mirrors/generate.py:285-292` catches only MirrorFormatError so malformed YAML aborts
  mid-write, contradicting its own docstring; I3 `mirrors check` is wired into NO gate in
  `.factory/factory.yaml`; I4 `compile_health_dimensions` calls `load_register` 242 times per run
  (8.41s of 8.7s, ~13,000 frontmatter parses, quadratic in requirement count); I5
  `simulation/registry.py:41` skips manifests lacking a `"run"` key and T-6's uses `run_id`, so the
  repo's first evidence can never be reported stale; I6 an `sr:` reject has no consumer anywhere —
  a rejected requirement is system-wide indistinguishable from an accepted one; I7 `inbox.py:236`
  calls `load_register` unguarded so one malformed acceptance block takes down the whole inbox.

THE PROFILE ANSWER, sharper than the controller's: the reviewer applied `profile: high_assurance`
  to FEAT-001 byte-preserving and re-ran. `executed_evidence` **4/55 -> 0/55**; `human_review`
  **0/0 -> 0/8**. The branch's headline evidence number and its declared assurance level are
  MUTUALLY EXCLUSIVE as the code stands — the 4/55 exists *because* the profile is prototype, since
  `_verification_result_obligation`'s harness check runs only under high_assurance and rejects every
  binding-less SR. Verdict: ship the profile gap (found, recorded, correctly diagnosed, one-line
  fix available), but the reference run MUST record that 4/55 is profile-contingent, and the plan's
  T-8b premise ("FEAT-001 is high_assurance, so human_review compiles as blocking") must be struck.

HERMES COMMITS: read as full separate diffs. **No defect found.** Highest-density defensive work on
  the branch: `type(schema) is not int` catching `schema: true` via `bool.__eq__`; `decisions: 0`
  and `null` now raising instead of collapsing to empty; `_is_iso` gaining calendar semantics;
  `_parse_instant` fixing a latent naive/aware TypeError; `_resolve_acceptance_ref` rejecting
  POSIX and Windows anchors and walking components for reparse points.

TEST QUALITY: strong; neither prior bad habit survived. `test_health_dimensions.py:310-337` singled
  out as the best test on the branch — written against a hypothesis, not the implementation.
Final review: ONE fix wave dispatched on opus (per the skill — no per-finding fixers) covering
  C1, C2, C3, I1, I2, I3, I5, I7, M1, M5, M8.
Final review: Ruling R-15 — four findings deferred out of the fix wave with reasons:
  I4 (load_register called 242x per health run, 8.41s of 8.7s, quadratic in requirement count) — a
    real defect, but the fix is a caching/structural change needing its own design and review. Fixing
    it inside a fix wave would be the largest unreviewed change on the branch.
  I6 (an `sr:` reject has no consumer; a rejected requirement is system-wide indistinguishable from
    an accepted one) — a genuine design gap, but it needs a DECISION about what a rejection should
    do, which is the user's to make, not a fixer's.
  M2 (two `ref` path-safety policies — `health.py:646` normalises `..` away, `compiler.py:401`
    rejects it lexically) — divergence runs fail-safe (dimension green, obligation open), so it
    misreports nothing today; unifying two consumers' path policy deserves its own review.
  M3, M4, M6, M7 — polish.
  Cost if wrong: four known issues ship recorded rather than fixed; none can produce a false green.
Final review: the reference-run correction the reviewer required is the CONTROLLER's to make under
  ruling R-4, and is done (commit ee096a4). The record now states at the S-6 headline and again in
  the plan-defects section that `executed_evidence 4/55` holds only under `prototype` and inverts to
  0/55 under the `high_assurance` the specification declares — so the number can never be quoted
  bare. M8 (the plan file's own false T-8b premise) went to the fixer, since the plan is not the
  controller's artifact.
Final fix wave: 8 commits landed (ee096a4..9b3d53a), 29 files, +1334/-82, report written (33.5K).
  All eleven in-scope findings covered: C1 911b265, C3 2e76e98, C2 5c7c4d3, I1 d87e951,
  I5 03a423f, I7 399668f, I3 570ac4e, M8 9b3d53a; I2, M1 and M5 landed inside those commits.
  The wave hit an account session limit on its final verification run, so the CONTROLLER ran that
  verification itself rather than dispatching another agent round:
    full unit suite      1 failed, 2988 passed, 13 skipped (513s)
    ruff check .         All checks passed
    mirrors check        20 dossiers, 0 divergent
    register check       51 pending, 4 measured-passing, 0 measured-failing (unchanged, as required)
    navigate health      requirement_quality 8/55, executed_evidence 4/55, human_review 0/0,
                         **evidence_freshness 0/0 -> 0/1** (I5 landed: the manifest is now visible to
                         the freshness universe and honestly reported as NOT fresh)
  The single remaining failure is the known pre-existing `test_remediation.py::
  test_every_shell_command_names_a_real_subparser`, and the controller confirmed its REASON is
  unchanged — a missing `add_parser("run")` in a deprecated `coherence.measurement.cli` shim,
  unrelated to the mirrors gate command this wave added. Verified rather than assumed, because the
  wave edited `.factory/factory.yaml` and that test checks gate commands against subparsers.
Final fix wave: ONE scoped re-review dispatched (ee096a4..9b3d53a). There is no second fix wave;
  residual findings will be adjudicated by the controller and surfaced to the user.

### CONTROLLER FINDING on the fix wave — false human attribution in the provenance block

The provenance block added to `validation/validation-report.json` is well-built in every other
respect (`recorded_by: "hand"`, command, run_id, commit, `evidence_manifest` cross-link). Its `note`
says: **"A human ran the command above, read its output, and transcribed the per-SR results here;
the metric/assert/trials/declared_trials/stale fields are that human's transcription."**

**No human ran it.** The T-6 implementer — an agent this controller dispatched — ran
`rtk proxy uv run pytest -m sr -v -o addopts=""`, read the output and transcribed the results. No
person was involved at any point. Both human gates on this branch (T-4b, T-8b) are still open
precisely because no human has acted.

This is worse than having no provenance at all, and it is CREATED by the fix wave, not pre-existing:
  - the block's whole purpose is to state honestly who produced the data, so misattributing the
    actor defeats its reason for existing;
  - it asserts human involvement in an assurance artifact where none occurred — the exact signal
    I-01 exists to protect, in the canonical evidence location, in a file both user-facing surfaces
    read;
  - under I-03 human authorship here was not merely unrecorded, it was INVENTED;
  - the same wave's C3 fix reached the opposite conclusion and stated it correctly — its docstring
    now says the substrate cannot distinguish an agent-written decision from a human one. The
    provenance note contradicts its own wave.
Sent to the running re-reviewer for an independent verdict rather than adjudicated unilaterally,
along with three follow-up checks: whether the same phrasing propagated elsewhere in the diff,
whether the schema constrains `note` or restricts `recorded_by` to a vocabulary that cannot express
"agent", and confirmation the per-SR values were only labelled and not altered.
Controller finding SHARPENED into a schema-design finding: `validation_report.schema.json:30-33`
  constrains `recorded_by` to `enum: ["hand", "harness"]`, and its own description defines `hand` as
  "**a human** transcribed them from a run's output". So the vocabulary has NO value for what
  actually happened — an agent ran the command and transcribed the results. `harness` is false (no
  code can produce the entries, which is why the block exists) and `hand` is false by the schema's
  own definition. The file was forced into the option that manufactures human attribution.
  This matters beyond one file: Coherence is a substrate FOR AGENTIC engineering, so
  agent-ran-and-transcribed is the COMMON provenance, and the FEAT-017 bootstrap this reference run
  exists to specify will produce it on every registration. A vocabulary that cannot name it will make
  every future automated run mislabel itself, in the direction that overstates human involvement.
  Two dispositions put to the reviewer: (1) add a third value (`agent`) or split actor from
  transcription — the fix that scales to bootstrap; (2) keep the enum and redefine `hand` as
  "transcribed rather than harness-emitted", correcting the description. Either must preserve the
  schema's good `if/then` requiring run_id/evidence_manifest/commit/note when `recorded_by` is hand.
  Also flagged: `evidence_record.schema.json:31` has `recorded_by` as free-text `pattern: "\S"` —
  two schemas in one repo now use the same field name with incompatible vocabularies.

## Fix-wave re-review: 10 of 11 ADDRESSED, C2 OPEN

C1 ADDRESSED — reviewer independently reproduced BOTH harms in temp dirs: the silent-deletion shape
  now returns changed=False with the file byte-identical and a reported error naming it; the
  stray-sentinel shape fails check before and after and is never rewritten into a hidden second
  block. It also found the shape the fix does NOT handle: `_section_end` is a lexical `^## ` scan
  with no fenced-code awareness, so a fenced markdown example containing a `## ` line truncates the
  section — but that degrades to a FALSE-POSITIVE REFUSAL (changed=False, file untouched), never a
  silent rewrite. No real dossier has that shape.
C3, I1, I2, I3, I5, I7, M1, M5, M8 all ADDRESSED with real regression tests. Highlights: I7's fix
  correctly extended BEYOND the brief's named site to `_stale_binding_items`, which runs first, and
  reports failure as a visible `register:unreadable` inbox item rather than swallowing it; I3's gate
  wiring is what stales the T-6 manifest (evidence_freshness 0/0 -> 0/1) because the manifest
  fingerprints `.factory/factory.yaml` — an honest consequence, reported.
Scope creep: NONE. Every one of the 29 files maps to a listed finding. I4, I6, M2-M7 and the
  `verification_strategy` tautology all untouched. No `profile:` field added, no acceptance block or
  marker modified, no DecisionFile outside tmp_path, reference-run record untouched.

C2 NOT ADDRESSED. The MECHANISM is right — schema, load-time validation, fail-closed to {},
  navigator degradation, per-SR values byte-identical. The CONTENT is false, and the reviewer found
  the false claim in THREE places, not one:
    `validation/validation-report.json:9`                      the note
    `src/substrate/schemas/validation_report.schema.json:32`   the enum description
    `src/substrate/schemas/validation_report.schema.json:5`    the top-level description
  and PINNED BY A PASSING TEST:
    `tests/unit/validation/test_validation_report_schema.py:68-75`
      `test_the_repositorys_validation_report_says_it_was_recorded_by_hand`
  The reviewer agreed with the controller's severity "without reservation", rated it Critical, and
  called it breakage the WAVE INTRODUCED — there was no provenance block, true or false, before it.
  It endorsed Option 1 over Option 2: add a value the vocabulary can use honestly, because narrowing
  "hand" to "transcribed, actor unspecified" "just re-hides the same fact one layer down".
  It confirmed the cross-schema inconsistency is real: `evidence_record.schema.json:31` has
  `recorded_by` as free text, which is what `factory/evidence/records.py:160` actually populates with
  an agent/session identity — the established idiom the new closed enum broke.

**R-16. C2 gets one targeted correction rather than being surfaced unfixed.**
The process says there is no second fix wave and residual findings surface to the user. I am ruling
against that here, deliberately. This is not churn on a contestable point: a file in the canonical
evidence location falsely claims a human attested to evidence no human has seen, the claim is
pinned by a passing test, and it is the file FEAT-017's bootstrap will read as its template for
what evidence looks like. In a product whose entire premise is that "an AI said it's done" must
never pass as a human judgement, shipping that would be indefensible when the correction is a
schema value, three description strings and one test name.
*Scope:* the provenance vocabulary only — add an honest value for agent-transcribed evidence,
correct all three descriptions, retarget the test. Nothing else reopens.
*Cost if wrong:* one more small review cycle on a 20-line change. The alternative cost is shipping
a manufactured human attestation.
Task 9: reference run updated for the provenance failure (commit b9d7142) — A-17, A-18, a standalone
  account of the failure headed "The failure that came closest to defeating the whole exercise", and
  a FIFTH rule added to §6's step list: a provenance vocabulary for an agentic system must be able to
  name an agent as an actor, because if it cannot, every automated run mislabels itself in the
  direction that manufactures human attestation. It is the only rule in the record that the run
  violated WHILE FIXING another finding, and that is stated.
  The record now carries 8 steps, 18 ambiguities, 8 plan defects, a 19-step procedure and 5 rules.

## C2 correction — CLOSED (commit 0318400)

Controller-verified directly, item by item, rather than by dispatching a further review round:
  `recorded_by` is now **`agent`** — a value added to the enum, per the reviewer's endorsement of
    Option 1 over a wording-only fix.
  The note now reads "Recorded by an agent, not emitted by a harness and **not attested by a human**
    ... not values any code computed and **not values any human has reviewed**. No human has acted on
    this branch: the `authoring_consent` and `human_review` gates for these requirements are both
    still open, and the evidence manifest this note cites records no `reviews` and no `decisions`."
    It keeps the accurate substance — why no code can produce the entries, the manifest cross-link,
    and the reproduction command.
  The schema enum description names all three values honestly, including "`agent` means a non-human
    (AI) actor ran the command ... no human has attested to them."
  The `if/then` conditional is GENERALISED to `recorded_by: {"not": {"const": "harness"}}`, so an
    agent-recorded report carries the same run_id/evidence_manifest/commit/note citation burden as a
    hand-recorded one.
  The test is retargeted and renamed to `test_the_repositorys_validation_report_says_it_was_recorded_by_an_agent`.
  Every remaining occurrence of "human" in both files is a TRUE statement (checked each).
  `executed_evidence` still **4/55** — the correction was to attribution, and the number did not move.
  `evidence/runs/T-6-*.json` byte-identical (empty diff over `evidence/`).
  Per-SR values unchanged.
C2: minor (deferred, cosmetic): `tests/unit/validation/test_validation_report_schema.py:123` is named
  `test_a_report_whose_recorded_by_is_not_hand_or_harness_is_rejected` but now that `agent` is valid
  the name is imprecise; its assertion (rejecting `"magic"`) is correct. A one-word rename, noted
  rather than dispatched, since the process allows one scoped re-review of a fix wave and it is spent.

## Final verification (controller-run, on the tree being offered for merge)

HEAD 0318400, tree clean, 38 commits off main (89ac73e), 119 files, +13484/-154.
  `rtk proxy uv run pytest tests/unit/ -q` -> **1 failed, 2988 passed, 13 skipped** (1019s).
    The single failure is the known pre-existing `test_remediation.py::
    test_every_shell_command_names_a_real_subparser`; its reason was verified unchanged (a missing
    `add_parser("run")` in a deprecated `coherence.measurement.cli` shim). Not caused by this branch.
  `ruff check .` clean · `mirrors check` 20/0 divergent · `register check` 51 pending / 4 passing
  `navigate health`: requirement_quality 8/55, executed_evidence 4/55, evidence_freshness 0/1,
    human_review 0/0.
All 9 tasks complete and reviewed. Final review's 11 findings: 10 closed by the fix wave, C2 closed
by the targeted correction under ruling R-16. Awaiting the user's integration decision; workspace
retained until then.
