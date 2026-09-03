# SR-010 human-consent review packet

FEAT-002 (progressive assurance), thin vertical slice. This packet exists so a human can give (or
withhold) authoring consent for SR-010 with the full trail in front of them. No decision is
recorded in this document or anywhere in this session -- see the closing line.

## 1. Source excerpt

`docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md`, section 4
("Progressive assurance model"):

> Compiled `Obligation`: ... requiredness is one of `not_applicable | advisory | required |
> blocking` [...] Minimal invariant kernel ... Rule 1 -- an execution error, missing executable or
> invalid result cannot become pass.

`docs/superpowers/specs/2026-09-01-coherence-product-definition.md` was checked as a possible
superseding source: it does not mention SR-010, "Requiredness", or the invariant kernel by name
anywhere, so it neither revisits nor supersedes this statement -- the 2026-08-22 design doc remains
the operative source.

## 2. Final statement -- CORRECTED

**Before** (recon's draft, quoting the source excerpt):

> The system shall treat requiredness in {not_applicable, advisory, required, blocking}, where the
> underlined invariant kernel blocks an execution error, missing executable, or invalid result
> from becoming pass on a task's justified SR.

**After** (what shipped, `requirements/SR-010.md` frontmatter, corrected during authoring
consent, then re-corrected once more during the independent review pass):

> The system shall treat requiredness in {not_applicable, advisory, required, blocking}, where the
> invariant kernel blocks an execution error, missing executable, or invalid result from becoming
> pass on a task's justified SR.

**Why it was corrected (in two passes):**

1. **Authoring pass:** "underlined invariant kernel" is nonsensical and almost certainly a typo --
   the source anchor's own §4 says "Minimal invariant kernel" (line 92), never "underlined". The
   authoring commit (`cdd64ae`) replaced it with "underlying invariant kernel" and a correction
   note claiming this tracked the source's own wording.
2. **Review pass:** the independent reviewer checked that claim by grepping
   `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` and found
   "underlying invariant kernel" appears **nowhere** in the source doc -- only "Minimal invariant
   kernel" (line 92) and "the invariant kernel" (line 204) exist. The authoring-pass fix was a
   defensible paraphrase and changed no scope or test-backed claim, but its own correction note
   overstated how directly it tracked the cited source text. The fix commit (`3a7e9f6`) reworded
   the statement to "the invariant kernel", matching line 204 verbatim, and adjusted the correction
   note to stop implying a closer source match than it had.

No content or scope change occurred at either step: the four-value Requiredness enum and kernel
rule 1's blocking behaviour (an execution error, missing executable, or invalid result cannot
become pass on a task's own justified SR) are unchanged throughout, and both are fully backed by
passing tests (`substrate/policy/obligation.py`'s `Requiredness` literal;
`coherence/measurement/pipeline.py`'s own-SR-vs-swept-SR distinction).

**Recon found no code gap.** Every clause of the statement was already implemented and exercised
by passing tests before this task began; the only thing missing was the acceptance-criteria block
itself (the file had statement-only frontmatter with no `acceptance:` key).

**Scope-fence note carried from recon, confirmed by the reviewer:** D16 scopes FEAT-002 to
prototype/high_assurance presets and, at design time, "three obligation kinds only." The compiler
today actually produces five kinds (`ci_verification`, `task_justification`, `verification_result`,
`human_review`, `test_marker`) -- the extra two were added by later increments referenced to other
SRs/plans, not to SR-010. None of SR-010's three ACs claims exploration/product-preset behavior or
states a specific kind count; AC-1 is a claim about the `Requiredness` type only, and the
requirement body explicitly says the kind count is out of scope for this SR's claim. The reviewer
confirmed this stays inside the fence and does not smuggle D16's stale "three kinds" figure past a
reader.

## 3. Final acceptance criteria, with verification refs

| AC | Criterion | Verification |
|----|-----------|---------------|
| AC-1 | The compiled Requiredness type accepts exactly four values -- `not_applicable`, `advisory`, `required`, `blocking` -- and every Obligation compiled for a project, `task:*`, or `sr:*` scope under the `prototype` or `high_assurance` preset carries one of them (never a fifth value or an untyped string). | `test_marker` -> `tests/unit/coherence/policy/test_compiler.py` |
| AC-2 | On a task's own justified SR, a failure to run validation (an execution error, an unbound/proposed requirement, or a missing declared harness -- each surfaces as an `"error"` report entry) blocks that task's `validate_task_requirements` from reporting `ok`, exactly like a ran-and-failed assertion; the identical failure on an SR the task did not justify (only swept in by `full_sweep`'s periodic cadence) leaves `ok` `True` as a warning, not a block. | `test_marker` -> `tests/unit/validation/test_pipeline.py` |
| AC-3 | Under the `high_assurance` preset, an SR's compiled `verification_result` obligation stays blocking/open both when no passing, non-stale validation result is recorded at all, and when a recorded result would otherwise pass but the requirement declares no `binding.harness` -- absence of harness-checked evidence is never reported as satisfied. | `test_marker` -> `tests/unit/coherence/policy/test_compiler.py` |

AC-3's "declares no `binding.harness`" clause covers the compiler's actual OR-condition
(`req.binding is None or req.binding.harness is None`), which has two distinct branches -- no
`binding:` block at all, versus a `binding:` block present but missing `harness` specifically. The
authoring pass proved only the first branch; the independent review pass (section 6, finding 2)
added a second test exercising the second branch directly.

Six tests carry `@pytest.mark.sr("SR-010")` across two files:

- `tests/unit/coherence/policy/test_compiler.py` (AC-1, AC-3):
  - `test_compile_obligations_requiredness_is_always_one_of_the_four_literal_values` (AC-1, new)
  - `test_compile_obligations_verification_result_high_assurance_no_validation_is_blocking_open`
    (AC-3, pre-existing)
  - `test_compile_obligations_verification_result_high_assurance_missing_harness_stays_open` (AC-3,
    pre-existing -- covers the no-`binding:`-block branch)
  - `test_compile_obligations_verification_result_high_assurance_binding_present_no_harness_stays_open`
    (AC-3, new in the fix commit -- covers the `binding:`-present-but-harness-omitted branch)
- `tests/unit/validation/test_pipeline.py` (AC-2, both pre-existing):
  - `test_missing_harness_on_own_sr_blocks`
  - `test_unrelated_periodic_sr_error_stays_a_warning`

A rejected candidate: recon considered
`test_compile_obligations_duplicate_profiles_are_ambiguous_and_blocking` for AC-1 and rejected it --
it shows every obligation kind pinned to `"blocking"` under one specific ambiguity condition, not
the closed-four-value-type claim AC-1 actually makes, so a new, purpose-built test was written
instead of stretching a loosely-related candidate.

## 4. Files changed and commit SHAs

Authoring (`cdd64aed942a77551499a54b542cc6f41a001e38` --
`feat(requirements): author FEAT-002/SR-010 acceptance criteria + binding`):

- `requirements/SR-010.md` (+39/-1) -- acceptance array (AC-1/AC-2/AC-3), statement correction pass
  1, authoring notes
- `tests/unit/coherence/policy/test_compiler.py` (+48) -- new AC-1 test
  (`test_compile_obligations_requiredness_is_always_one_of_the_four_literal_values`) plus SR-010
  markers on the AC-3-bound tests
- `tests/unit/validation/test_pipeline.py` (+2) -- SR-010 markers on the AC-2-bound tests

Fix (`3a7e9f6f72b49e6c44dcd2e022679f3ec69c659d` --
`fix(requirements): address independent review of FEAT-002/SR-010`):

- `requirements/SR-010.md` (+9/-4) -- statement correction pass 2 ("the invariant kernel," matching
  source line 204 verbatim), correction note reworded to stop overstating source match
- `tests/unit/coherence/policy/test_compiler.py` (+34) -- new AC-3 test covering the
  binding-present-but-harness-omitted branch

Evidence (`9baed8eee0e8a564c7f357d115c8249019ee9313` --
`chore(evidence): record FEAT-002/SR-010 evidence`):

- `evidence/runs/T-9010-evidence-execution-20260903T000239Z.json` (new, 115 lines) --
  agent-recorded run manifest for all six `@pytest.mark.sr("SR-010")` tests, mapped to AC-1..AC-3
- `validation/validation-report.json` (+29/-5) -- matching SR-010 entry; provenance block updated
  to `recorded_by: "agent"` citing this run's id/commit/evidence_manifest

All three commits are `recorded_by "agent"` throughout -- no `decided_by`/human-attestation field is
set anywhere in any of them. No `gate-decisions/*.json` file exists or was written for SR-010 by any
part of this pipeline.

An uncommitted, unrelated draft of this same work was found sitting in the worktree at the start of
the authoring pass (likely from a prior interrupted run of this task); it was independently
re-verified against the recon findings -- re-running the candidate tests plus the new AC-1 test,
checking the statement correction against the source anchor, running `ruff`/`pyright` on touched
files, and confirming marker collection wasn't broken via `test_register_markers.py` (15/15) --
rather than trusted and committed blindly. It matched the task instructions exactly and was
committed as the authoring commit above rather than rewritten from scratch.

## 5. Deterministic gate results

Run at fix commit `3a7e9f6` in `C:/coding/pi-agent-factory-wt/feat002-progressive-assurance`:

- **register_check_ok**: true -- `rtk proxy uv run coherence register check`: 56 requirements
  evaluated, 49 pending / 0 unmeasurable / 7 measured-passing / 0 measured-failing / 0 declined --
  SR-010 correctly appears in the pending/undecided list at this stage (expected: no gate decision
  has been recorded yet, and this task must not record one).
- **bound_tests_ok**: true -- `rtk proxy uv run pytest tests/unit/coherence/policy/test_compiler.py
  tests/unit/validation/test_pipeline.py -q`: **60 passed, 1 skipped, 0 failed**.
- **lint_ok**: true -- `rtk proxy uv run ruff check .`: all checks passed.
- **typecheck_ok**: true -- `rtk proxy uv run pyright`: 74 errors/21 warnings exist repo-wide, but
  none touch the SR-010-bound files (`test_compiler.py`, `coherence/measurement/pipeline.py`) --
  all pre-existing/unrelated (optional-dependency imports in `substrate/codemap/sigs.py`,
  `substrate/documents/adr.py`, `substrate/ledger/tasks.py`, plus benign `__all__`-shim warnings).
- **mirrors_clean**: true.
- **passed**: true overall; **escalate**: false at the gate stage.
- The fix commit `3a7e9f6` (`requirements/SR-010.md` + `tests/unit/coherence/policy/test_compiler.py`,
  39 lines added) matches the requested review fixes exactly: statement reworded to match the
  source doc verbatim, and a second AC-3 test case added covering the binding-present-but-harness-
  omitted branch.
- No `gate-decisions/` file was written and no consent/decision claim is made -- that remains for a
  human in a separate conversation.

After the evidence-recording commit, `coherence register check`'s measured-passing count moved from
7 to 8 and SR-010 no longer appears in the undecided-requirements list, with `recorded_by` staying
`"agent"` throughout -- no fabricated attestation.

One CLI foot-gun surfaced during evidence recording, consistent with the same issue noted on prior
SRs in this feature: `rtk proxy coherence measurement run --satisfies SR-010` returned an empty
requirements list (that runner only evaluates top-level `binding:` requirements, not
`kind:test_marker` acceptance criteria) and, as a destructive side effect, overwrote
`validation/validation-report.json` with an empty `requirements` array. This was caught immediately
and reverted with `git checkout -- validation/validation-report.json` before any evidence was
recorded, so no prior evidence (SR-001..SR-009/SR-050) was lost.

A pre-existing, unrelated test failure was noted but **not** touched:
`tests/unit/validation/test_validation_report_schema.py::test_the_repositorys_validation_report_cites_the_run_that_produced_it`
hardcodes `provenance.run_id` to an original `"T-6-..."` value and was already failing before any
of this task's edits (confirmed via `git stash`) -- it broke when SR-009's evidence was recorded,
prior to this task.

## 6. Independent review verdict and findings

**Verdict: `approved_with_reservations`**

The reviewer independently re-ran the full `test_compiler.py` + `test_pipeline.py` suites (59
passed, 1 skipped) plus `test_register_markers.py` (15/15) and `ruff` on the touched files, rather
than trusting the self-report. Each AC was checked 1:1 against the implementation
(`substrate/policy/obligation.py`, `coherence/measurement/pipeline.py`,
`coherence/policy/compiler.py`) and both spec docs, confirming:

- **AC-1**: the new test pins `typing.get_args(Requiredness)` to the exact four-value set and
  cross-checks a sampled compile across `project`/`task:*`/`sr:*` scopes and both presets. Every
  requiredness-assignment site in `compiler.py` (five obligation-producing functions plus the
  ambiguous-SR path) was read and confirmed to use one of the four literals only.
- **AC-2**: matches `validate_task_requirements`'s `own_errors = any("error" in e and
  e.get("id") in own_ids ...)` logic exactly; all three named failure modes uniformly surface as
  `"error"` entries, so the tested aggregation generalizes correctly to the two modes the bound
  tests don't directly exercise. Both bound tests are pre-existing test bodies (diff shows only
  `@pytest.mark.sr("SR-010")` decorators added, not new test logic) -- confirming the tests weren't
  written to order to fit the claim.
- **AC-3**: matches `_verification_result_obligation` exactly, including the `reason` string
  containing "harness." The rejected-candidate reasoning (duplicate-profiles test) was checked
  against the actual test body and found accurate, not fabricated.

Commit `cdd64aed942a77551499a54b542cc6f41a001e38` and its diff stat were verified via `git log`/
`git show` -- only `requirements/SR-010.md` and the two test files changed, consistent with the
"no code gap, only missing acceptance frontmatter" self-report claim.

Two low-severity findings surfaced, both fixed in the same review pass (commit `3a7e9f6`):

1. **Low severity, cheap fix -- FIXED.** The authoring-pass statement correction fixed a real
   problem ("underlined invariant kernel" is nonsensical) but its own justification was imprecise:
   it cited the source anchor's §4 wording ("Minimal invariant kernel") as proof that "underlined"
   was a typo, then substituted a third phrase, "underlying invariant kernel," which itself appears
   nowhere in `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md`
   (grepped: only "Minimal invariant kernel" at line 92 and "the invariant kernel" at line 204
   exist). The fix was a defensible paraphrase and changed no scope or test-backed claim, but the
   correction note overstated how directly it tracked the cited source text. **Fix:** reworded the
   statement to "the invariant kernel" (matching line 204 verbatim) and adjusted the correction note
   to stop implying a source match it didn't have.
2. **Low severity, cheap fix -- FIXED.** AC-3's second clause ("a recorded result would otherwise
   pass but the requirement declares no `binding.harness`") was proven by
   `test_compile_obligations_verification_result_high_assurance_missing_harness_stays_open` using
   an SR with no `binding:` block at all, not one with a `binding:` block that omits `harness`. The
   compiler's actual condition is `req.binding is None or req.binding.harness is None`
   (`src/coherence/policy/compiler.py:250`), so both sub-cases produce identical behavior today and
   the criterion itself was not misstated -- but only one of the two OR-branches was exercised, so a
   future regression breaking only the `binding-present-but-harness-None` branch specifically would
   not have been caught. **Fix:** added
   `test_compile_obligations_verification_result_high_assurance_binding_present_no_harness_stays_open`,
   a second case with a `binding:` block that has every field except `harness`.

No SR-001-style over-claim (wrong direction/scope) was found in any of the three ACs. Verification
refs are real, file-level, and match the established convention already used by SR-001/SR-008/
SR-009; every named test function exists and passes with the expected marker.

Verified via the fix commit's own test run: `test_compiler.py`: 52 passed, 1 skipped;
`test_compiler.py`+`test_pipeline.py`+`test_register_markers.py`: 75 passed, 1 skipped. `ruff check`
clean on both touched files.

---

Awaiting human accept/reject/defer -- no decision has been recorded.
