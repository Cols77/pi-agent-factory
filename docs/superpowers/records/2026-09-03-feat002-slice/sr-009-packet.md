# SR-009 human-consent review packet

FEAT-002 (progressive assurance), thin vertical slice. This packet exists so a human can give (or
withhold) authoring consent for SR-009 with the full trail in front of them. No decision is
recorded in this document or anywhere in this session -- see the closing line.

## 1. Source excerpt

`docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md`, section 4
("Progressive assurance model"):

> Compiled `Obligation`: `{id, scope_ref, kind, requiredness, reason, source_policy, state,
> resolve_cmd}` [...] Status, health, inbox, navigator and gates consume this contract; none
> reinterpret the profile independently.

`docs/superpowers/specs/2026-09-01-coherence-product-definition.md` was checked as a possible
superseding source: it mentions "obligations" only in passing (the assurance-spine summary, the
gate-finalize pseudocode, and the `human_review` description) and never revisits or supersedes the
design doc's consumer list -- so the 2026-08-22 design doc remains the operative source for this
statement.

## 2. Final statement -- CORRECTED

**Before** (recon's draft, quoting the source excerpt verbatim):

> The system shall expose each compiled obligation with id, scope ref, kind, requiredness, reason,
> source policy, state, and a fully-substituted resolve command, consumed by status, health,
> inbox, navigator, and gates without reinterpreting the profile.

**After** (what shipped, `requirements/SR-009.md` frontmatter, corrected during authoring
consent):

> The system shall expose each compiled obligation with id, scope ref, kind, requiredness, reason,
> source policy, state, and a fully-substituted resolve command, consumed by health, navigator,
> and gates without reinterpreting the profile.

**Why it was corrected:** the draft claimed five consumers -- status, health, inbox, navigator,
gates -- quoting the design doc's §4 directly. Grepping `src/coherence` for
`compile_obligations`/`Obligation` usage confirms only three of the five actually exist in code:

- `coherence.navigate.health` (`src/coherence/navigate/health.py`) -- calls `compile_obligations`
  per SR to build health dimensions 4/5 (verification strategy / executed evidence) and
  dimension 11 (`human_review`).
- the navigator (`src/coherence/navigate/obligations.py`, wired into
  `src/coherence/navigate/cli.py`'s `cmd_obligations`/`cmd_sim_run`/`cmd_goal_show`/`cmd_present`)
  -- composes `compile_obligations`/`resolve_profile` directly; its own module docstring says it
  "never recomputes that logic itself."
- gates (`src/coherence/policy/ci.py`'s `required_ci_commands`) -- builds CI's command list solely
  from compiled, blocking `ci_verification` obligations.

The other two do not exist in the current code: `status_snapshot` (`src/coherence/status.py`,
whose six probes are `trace_check`, `register_check`, `run_checkpoint`, `audit_age`,
`membership_gate`, `inbox`) and `coherence register status` (`src/coherence/register/cli.py`) have
zero references to `compile_obligations`, `Obligation`, or `coherence.policy.compiler`/
`coherence.navigate.obligations` anywhere in either file; `list_items`
(`src/coherence/inbox.py`) likewise never consumes a compiled obligation. This mirrors the same
over-claim pattern already corrected in SR-001's AC-3 and SR-002's statement (both narrowed during
their own authoring-consent passes) -- a design doc claiming more consumers than a bound test could
ever honestly prove today.

`compile_obligations` also has two further real consumers not named by the source statement at
all: `src/coherence/register/closure.py` (requiredness for the marker-closure `CHECK`) and
`src/coherence/runs/service.py`/`src/coherence/audit/runner.py` (run-blocking). Neither is
"status" or "inbox" as the statement claims, so they don't rescue the dropped clauses -- they're
additional real consumers the statement doesn't credit, left uncounted rather than folded in,
since adding them wasn't necessary to prove any AC.

Wiring `status.py`'s probes and `inbox.py`'s `list_items` to the compiled obligation set is a real
design decision (which obligations belong in a status line vs. an inbox item, at what
requiredness threshold, for which scope) that no increment in the design doc's own integration map
(§10) assigns -- Increment 2C covers only CI/gates, 3B only the navigator, 5 only the health
vector. That remains open follow-on work for a future SR, not something this authoring pass closes
by drafting an acceptance criterion no test could honestly back today.

## 3. Final acceptance criteria, with verification refs

| AC | Criterion | Verification |
|----|-----------|---------------|
| AC-1 | A compiled `Obligation` exposes exactly the documented fields (`id`, `scope_ref`, `kind`, `requiredness`, `reason`, `source_policy`, `state`, `resolve_cmd`), with requiredness constrained to `not_applicable \| advisory \| required \| blocking`. | `test_marker` -> `tests/unit/substrate/policy/test_obligation.py` |
| AC-2 | A compiled `ci_verification` obligation's `resolve_cmd` is fully substituted -- no literal `{python}` placeholder survives -- and the gate order and duplicates of the source config are preserved verbatim. | `test_marker` -> `tests/unit/coherence/policy/test_compiler.py` |
| AC-3 | `coherence.navigate.health` computes its obligation-backed health dimensions (verification strategy / executed evidence) from the compiled obligation set returned by `compile_obligations` for each SR scope, never by re-deriving profile logic itself. | `test_marker` -> `tests/unit/coherence/test_health_dimensions.py` |
| AC-4 | The navigator's effective-profile/obligation view (`coherence.navigate.obligations`) presents the same compiled obligation set `compile_obligations` returns for a scope, without recomputing profile resolution independently. | `test_marker` -> `tests/unit/coherence/test_navigate_obligations.py` |
| AC-5 | CI's required command list (`coherence.policy.ci`) draws its gate commands only from compiled obligations of kind `ci_verification` with requiredness `blocking`, sourced from the same compiler every other consumer uses -- never a hand-maintained gate step list -- with two fixed structural checks (`coherence trace check`, `coherence register check`) appended after them, unconditionally, not obligation-derived. | `test_marker` -> `tests/unit/coherence/policy/test_ci.py` |

AC-5 was narrowed during the independent review pass (see section 6, finding 1) from an earlier
wording that claimed CI's command list is built "only" from compiled obligations and is "never a
hand-maintained step list," full stop -- the code and the bound test both prove a narrower claim:
gate commands are exclusively obligation-derived, but two structural checks are a separate,
unconditional, non-obligation-derived tail appended after them. AC-1's bound test was also
strengthened in the same review pass with a `dataclasses.fields()` introspection assertion that
pins the exact field-name set, closing a gap where the original test only constructed an
`Obligation` and read back two of its eight fields (see section 6, finding 2).

Six tests carry `@pytest.mark.sr("SR-009")` across five files, one per AC except AC-2 (two):

- `tests/unit/substrate/policy/test_obligation.py`: `test_obligation_is_the_documented_contract`
- `tests/unit/coherence/policy/test_compiler.py`:
  `test_compile_obligations_ci_verification_substitutes_python_like_backends_does`,
  `test_compile_obligations_preserves_configured_order_and_duplicates`
- `tests/unit/coherence/test_health_dimensions.py`:
  `test_verification_strategy_and_executed_evidence_share_the_active_obligation_denominator`
- `tests/unit/coherence/test_navigate_obligations.py`: `test_effective_profile_view_project_scope`
- `tests/unit/coherence/policy/test_ci.py`:
  `test_includes_every_declared_gate_command_in_order_with_python_substituted`

A seventh candidate test flagged by recon as `currently_passes: false`
(`tests/unit/coherence/runs/test_service.py::test_blocking_open_test_marker_gates_the_run`) was
never bound to any SR-009 AC and, on re-verification through the correct venv interpreter, in fact
passes -- the recon-time failure was a collection-error false negative from an unqualified `pytest`
invocation in an environment where bare `pytest` can't resolve the `coherence`/`substrate`
packages. This doesn't affect SR-009's acceptance array either way.

## 4. Files changed and commit SHAs

Authoring (`dfeda5da998c4818b15f6240127815ae4ba32552` --
`feat(requirements): author FEAT-002/SR-009 acceptance criteria + binding`):

- `requirements/SR-009.md` (+48/-1) -- corrected statement, five ACs, dated authoring notes
- `tests/unit/coherence/policy/test_ci.py` (+1) -- SR-009 marker
- `tests/unit/coherence/policy/test_compiler.py` (+2) -- SR-009 markers
- `tests/unit/coherence/test_health_dimensions.py` (+1) -- SR-009 marker
- `tests/unit/coherence/test_navigate_obligations.py` (+1) -- SR-009 marker
- `tests/unit/substrate/policy/test_obligation.py` (+1) -- SR-009 marker

Fix (`acfd3a4f4e0e92b32c5ca376d50397b2a73ccbba` --
`fix(requirements): narrow SR-009/AC-5 overclaim + strengthen AC-1 proof`):

- `requirements/SR-009.md` (+16/-1) -- AC-5 narrowed to what code/test actually prove, AC-1 body
  note added
- `src/substrate/policy/obligation.py` (+4/-2) -- module docstring corrected to drop the stale
  "status, health, inbox, navigator and gates" claim, now reads "Health, navigator and gates
  consume this shape (SR-009)"
- `tests/unit/substrate/policy/test_obligation.py` (+16) -- added `dataclasses.fields()`
  introspection assertion strengthening AC-1's field-exactness proof

Evidence (`36bf0c4d898110a44fc1485fbd0cfa84e707daa0` --
`chore(evidence): record FEAT-002/SR-009 evidence`):

- `evidence/runs/T-9009-evidence-execution-20260902T233750Z.json` (new, 125 lines) -- agent-recorded
  run manifest for all six `@pytest.mark.sr("SR-009")` tests, mapped to AC-1..AC-5
- `validation/validation-report.json` (+29/-5) -- matching SR-009 entry feeding
  `executed_evidence`; provenance note extended

All three commits are `recorded_by "agent"` throughout -- no `decided_by`/human-attestation field
is set anywhere in any of them. No `gate-decisions/*.json` file exists or was written for SR-009 by
any part of this pipeline.

A separate, unrelated, still-uncommitted SR-010 draft (`requirements/SR-010.md`, plus hunks inside
`tests/unit/coherence/policy/test_compiler.py` and `tests/unit/validation/test_pipeline.py`) is
present in this worktree from a different task; it was deliberately left untouched and out of
scope throughout SR-009's authoring, fix, and evidence commits (confirmed via
`git diff --stat` on each commit above -- none touches `SR-010.md` or `test_pipeline.py`).

## 5. Deterministic gate results

- **register_check_ok**: true -- `rtk proxy .venv/Scripts/python.exe -m coherence.cli register
  check` exits 0 with no output (clean) after the fix commit `acfd3a4`.
- **bound_tests_ok**: true -- all five AC-bound test files run together: **94 passed, 2 skipped**.
- **lint_ok**: true -- `rtk proxy .venv/Scripts/python.exe -m ruff check src tests` -> all checks
  passed.
- **typecheck_ok**: true -- `rtk proxy .venv/Scripts/python.exe -m pyright` on the SR-009-relevant
  modules (`compiler.py`, `ci.py`, `navigate/obligations.py`, `navigate/health.py`,
  `substrate/policy/obligation.py`) -> 0 errors/warnings.
- **mirrors_clean**: true.
- **passed**: true overall; **escalate**: false at the gate stage (the pipeline-level `escalate:
  true` recorded for this SR comes from the unresolved-gap flag carried since recon/authoring, not
  from any gate failure -- see section 7).
- Full unit suite (`tests/unit`, 2922 passed / 2 failed / 12 skipped / 71 deselected): the 2
  failures (`tests/unit/system/test_remediation.py::test_every_shell_command_names_a_real_subparser`,
  `tests/unit/validation/test_validation_report_schema.py::test_the_repositorys_validation_report_cites_the_run_that_produced_it`)
  are pre-existing and unrelated to the fix commit `acfd3a4`, which touches only
  `requirements/SR-009.md`, `src/substrate/policy/obligation.py`, and
  `tests/unit/substrate/policy/test_obligation.py` (confirmed via
  `git diff acfd3a4~1 acfd3a4 --stat`); those two failing files were last modified by an unrelated
  commit `0318400`.
- No `gate-decisions/` file was written and no consent/decision claim is made -- that remains for a
  human in a separate conversation.

After the evidence-recording commit, `coherence.register check`'s measured-passing count moved
from 6 to 7 and SR-009 no longer appears in the undecided-requirements list; `coherence navigate
health --json`'s `executed_evidence` dimension moved from 6/56 to 7/56 satisfied. `authoring_consent`
and `human_review` gates for SR-009 remain open -- neither is touched by this packet or by anything
committed so far.

One CLI foot-gun surfaced during evidence recording, worth flagging upstream but not blocking
this SR: `rtk proxy uv run coherence measurement run --satisfies SR-009` returned an empty
requirements list (that runner only evaluates top-level `binding:` requirements, not
`kind:test_marker` acceptance criteria) and, as a destructive side effect, overwrote
`validation/validation-report.json` in place, wiping the prior 8-SR history. This was caught via
`git diff --stat` before any further work and the file was restored with
`git checkout -- validation/validation-report.json` prior to the evidence commit above.

## 6. Independent review verdict and findings

**Verdict: `approved_with_reservations`**

The reviewer verified each of the five ACs 1:1 against its bound test(s) and the implementation,
confirmed the statement's authoring-time correction (dropping "status" and "inbox") is itself
accurate -- grep confirms `status.py` and `inbox.py` have zero `compile_obligations`/`Obligation`
references, while `health.py`, `navigate/obligations.py`, and `policy/ci.py` all genuinely call
`compile_obligations` rather than re-deriving profile logic -- and confirmed SR-009 stays inside
D16's thin-slice fence (AC-2/AC-5's references to the `ci_verification` obligation kind are
sanctioned by the design doc's own D18 decision, a documented exception scoped to CI/Increment 2C,
not the thin-slice demo itself; no AC references exploration/product presets).

Three findings, all fixed in this review pass (commit `acfd3a4`, stacked on the original
`dfeda5d`):

1. **Medium severity, cheap fix -- FIXED.** AC-5 as originally authored over-claimed: CI's
   required command list "is built only from compiled obligations of kind `ci_verification` with
   requiredness `blocking` ... never a hand-maintained step list." `src/coherence/policy/ci.py`'s
   `required_ci_commands` contradicts this as literally written -- it unconditionally appends two
   hardcoded strings (`"coherence trace check"`, `"coherence register check"`) after the compiled
   gate commands, inside the very function the AC and its bound test target. The bound test
   already works around this by slicing `commands[:-2]` before asserting the compiled portion, and
   a second, unmarked test in the same file (`test_structural_checks_are_always_appended`) shows
   the tail is unconditional -- the test authors evidently already knew the "never a hand-maintained
   step list" claim didn't cover the whole function's output. This directly undercuts the design
   doc's own stated rationale for D18 ("CI reads the compiled obligation set rather than
   maintaining its own list, so the two cannot silently diverge") -- the AC as written declared
   exactly the failure mode the design exists to prevent to be impossible, when it demonstrably
   still exists for two commands. **Fix:** narrowed AC-5 to claim only what the code and the
   existing bound test actually prove -- gate commands are exclusively obligation-derived, never
   hand-maintained; the two structural checks are a separate, unconditional, non-obligation-derived
   tail. No test changed, only the criterion wording plus a body addendum.
2. **Low severity, cheap fix -- FIXED.** AC-1 ("A compiled Obligation exposes exactly the
   documented fields ..., with requiredness constrained to ...") was under-proven by its
   originally bound test: `test_obligation_is_the_documented_contract` only constructed an
   `Obligation` with the eight kwargs and read back two of them -- it would not have caught an
   additive field-set drift (an extra optional field with a default would still pass silently),
   and the "requiredness constrained to ..." clause was checked only via a trivial `in (...)`
   membership test on a value the test itself chose to be valid, proving nothing about exclusion of
   invalid values. A stronger, purpose-built test for the closed-type claim already exists in
   `test_compiler.py`
   (`test_compile_obligations_requiredness_is_always_one_of_the_four_literal_values`) but is marked
   `@pytest.mark.sr("SR-010")`, not SR-009 -- a legitimate cross-SR overlap, not a contradiction,
   but it meant SR-009's own AC-1 rested on weaker proof than was readily available. **Fix:** added
   a `dataclasses.fields()` introspection assertion to `test_obligation_is_the_documented_contract`
   that pins the exact field-name set, closing the "exactly the documented fields" gap directly.
   Left the requiredness-closed-type sub-claim as-is (already well covered cross-SR by SR-010's
   dedicated test); did not add `__post_init__` runtime validation to the dataclass since that
   would be a behavior change outside this review's remit.
3. **Cosmetic -- FIXED.** `src/substrate/policy/obligation.py`'s module docstring still read
   "Status, health, inbox, navigator and gates consume this shape" -- the exact overclaim the
   SR-009 statement itself was already corrected (in the same authoring commit, `dfeda5d`) to drop,
   after grep confirmed `status.py` and `inbox.py` have zero references to
   `compile_obligations`/`Obligation`. Leaving the stale docstring meant the source-of-truth code
   comment still asserted something the requirement it implements had already disavowed. **Fix:**
   docstring now reads "Health, navigator and gates consume this shape (SR-009)," matching the
   corrected statement.

All 6 SR-009-bound tests plus the two new/touched files pass `ruff` and `pyright` clean after the
fixes.

## 7. NEEDS HUMAN INPUT BEFORE CONSENT

This SR is flagged `escalate: true`. One open question needs a human decision before consent can
be recorded:

1. **The unresolved status/inbox consumer gap.** Recon's central finding is real but was judged
   not small/well-defined enough to implement in this pass: the source design doc's §4 names
   "status" and "inbox" among the compiled-Obligation contract's consumers, but neither exists in
   the current code -- `status_snapshot`/`cmd_status` and `inbox.py`'s `list_items` have zero
   references to `compile_obligations` or `Obligation`. Wiring those two modules to the compiled
   obligation set requires new design decisions (which obligations surface at a status line vs. an
   inbox item, at what requiredness threshold, for which scope) that no increment in the design
   doc's §10 integration map assigns (2C = CI/gates only, 3B = navigator only, 5 = health vector
   only). Rather than draft an acceptance criterion no test could honestly back today, the
   statement was narrowed to the three proven consumers (health, navigator, gates) and the gap left
   as open follow-on work. **The open question for you:** do you accept the narrowed statement as
   the correct scope for SR-009 -- deferring status/inbox obligation-consumption to a future,
   explicitly-scoped SR -- or does this gap mean SR-009 should not be consented as authored, e.g.
   because the status/inbox claim was load-bearing for some other part of the design (such as the
   assurance-spine summary in the 2026-09-01 product-definition doc) and needs its own SR/decision
   before this one can be accepted as complete?

This turns on a judgment call about scope and intent that this pipeline is not positioned to make
on its own -- exactly what authoring consent exists to catch.

---

Awaiting human accept/reject/defer -- no decision has been recorded.
