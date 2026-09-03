# SR-048 human-consent review packet

FEAT-002 (progressive assurance), thin vertical slice. This packet exists so a human can give (or
withhold) authoring consent for SR-048 with the full trail in front of them. No decision is
recorded in this document or anywhere in this session -- see the closing line.

**This packet is incomplete by pipeline design, not by omission.** The deterministic gate stage
crashed and returned nothing after authoring, so the independent review, fix, and evidence stages
that normally follow never ran. Section 5 records that failure plainly; section 7 explains exactly
what that leaves open for a human to decide.

## 1. Source excerpt

`docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md#D18`, cross-referenced
against section 7 ("CI"), section 11 ("Testing"), and the section 13 amendment row that corrects
D18's original day-one-blocking divergence. Recon also checked
`2026-09-01-coherence-product-definition.md`, which only cross-references SR-048 at its L4 row
(`ci_verification`, `no` on manual-only) -- no supersession of D18 was found on this topic.

The statement was drafted directly from D18/§7/§11/§13; no single verbatim quotable bullet exists
the way SR-011's did, since D18 is a decision-and-rationale entry rather than a bulleted feature
list.

## 2. Final statement -- NOT corrected

Recon's `statement_needs_correction` was `false`, and the authoring pass re-checked this against
the actual implementation (`src/coherence/policy/ci.py`, `src/coherence/policy/compiler.py`,
`.github/workflows/ci.yml`) before agreeing. The statement is unchanged from recon's draft and from
what shipped in `requirements/SR-048.md`'s frontmatter:

> The system shall make CI enforcement itself a compiled blocking obligation that runs every check
> backing the repo's blocking obligations, extending automatically when a later increment compiles
> a new blocking obligation, so CI, status, gates, and the obligation model agree by construction.

**Why no correction was needed:** `required_ci_commands()` (`src/coherence/policy/ci.py`) reads the
compiled `ci_verification` obligation via `compile_obligations`, which itself
(`src/coherence/policy/compiler.py::_ci_verification_obligation`) builds `resolve_cmd`
unconditionally as `blocking` from every gate command declared in `.factory/factory.yaml`, reusing
the task orchestrator's own `{python}` substitution helpers. `.github/workflows/ci.yml`'s "Resolve
required CI gates" step calls this function directly and runs each returned command in a loop --
confirmed by reading the workflow file itself, not just the spec's claim. "Extends automatically
when a later increment compiles a new blocking obligation" was checked generically: the unit tests
seed an arbitrary gate list and assert every entry flows through untouched, so nothing in `ci.py` or
the workflow enumerates specific commands by name.

One nuance was noted for the human reviewer but judged not to affect the statement: spec section 11
says "CI's own workflow is tested by running it against a seeded repo state in a dry-run job before
it gates real PRs." There is no separate dry-run job inside `ci.yml` itself (it has one job,
`gates`); what exists instead is a pytest integration suite
(`tests/integration/test_ci_workflow_dry_run.py`) that parses `ci.yml` and runs its individual steps
via subprocess, partly against the real repo and partly (the gate-loop shell logic) against fake
seeded executables. Functionally similar intent, differently shaped than the spec's literal
wording -- doesn't touch what SR-048's statement says, since the statement is silent on how CI's own
workflow is tested.

## 3. Final acceptance criteria, with verification refs

Two of recon's four draft criteria were narrowed during authoring (dated note in
`requirements/SR-048.md`'s body, mirroring SR-001's AC-3 narrowing precedent). Both narrowings drop
a claim that no currently-passing test actually proves, even though the surrounding implementation
likely satisfies it by construction.

| AC | Criterion | Verification |
|----|-----------|---------------|
| AC-1 | For a project whose `.factory/factory.yaml` declares gate commands, `required_ci_commands()` returns exactly those commands in their declared order, each with `{python}` substituted by the same substitution rule the task orchestrator itself uses (`factory.orchestrator.backends`'s `_target_python`/`_quote_for_shell`), followed by the two fixed structural checks `coherence trace check` and `coherence register check`. | `test_marker` -> `tests/unit/coherence/policy/test_ci.py` |
| AC-2 | `required_ci_commands()` raises `NoBlockingObligationError` when the project declares no gates at all (the compiled `ci_verification` obligation's `resolve_cmd` is empty), and also when, among several compiled `ci_verification` obligations, at least one carries no `resolve_cmd` -- CI can never silently run against only a partial subset of the gates it compiled. | `test_marker` -> `tests/unit/coherence/policy/test_ci.py` |
| AC-3 | The project-scope compiled obligation set includes a `ci_verification` obligation with `requiredness == "blocking"`, whose `resolve_cmd` is built by substituting the real interpreter into every gate command declared in `.factory/factory.yaml`, in the order those gates are declared, including duplicates -- the command list CI runs is read from the compiled obligation model, not maintained by hand. | `test_marker` -> `tests/unit/coherence/policy/test_compiler.py` |
| AC-4 | `.github/workflows/ci.yml`'s "Resolve required CI gates" step calls `required_ci_commands` directly against the repo it runs in (not a hand-maintained command list embedded in the workflow), so the command list CI actually executes is reproducible outside the workflow by calling that same function. | `test_marker` -> `tests/integration/test_ci_workflow_dry_run.py` |

**AC-2 narrowing:** dropped the clause "raises when the project compiles no blocking
`ci_verification` obligation at all." `compile_obligations` unconditionally appends exactly one
`ci_verification` obligation for every scope, so that branch of `required_ci_commands`'s
`if not selected: raise ...` guard is unreachable through any real compilation path, and neither
candidate error test exercises it -- both hit the "`resolve_cmd` missing" branch instead.

**AC-3 narrowing:** dropped an "exactly one `ci_verification` obligation" cardinality claim. Both
candidate tests resolve the obligation via `next(o for o in obligations if o.kind ==
"ci_verification")`, which would still pass even if a duplicate existed, so no test actually pins
that count. True by construction (the compiler only ever appends one), not tested -- removed from
the criterion per the same "match what the bound test actually proves, no more, no less" rule
applied to SR-011's AC-1/AC-2 by its own reviewer.

Eight tests carry `@pytest.mark.sr("SR-048")` across two files (two of the `test_compiler.py`
markers already carried `SR-009`; markers stack, both survive), plus one new cross-platform test
added to close a platform gap in AC-4's original candidate coverage:

- `tests/unit/coherence/policy/test_ci.py` (AC-1/AC-2, 4 tests):
  `test_includes_every_declared_gate_command_in_order_with_python_substituted`,
  `test_structural_checks_are_always_appended`,
  `test_no_declared_gates_raises_no_blocking_obligation_error`,
  `test_commandless_blocking_obligation_rejects_partial_results`
- `tests/unit/coherence/policy/test_compiler.py` (AC-3, 2 tests):
  `test_compile_obligations_ci_verification_substitutes_python_like_backends_does`,
  `test_compile_obligations_preserves_configured_order_and_duplicates`
- `tests/integration/test_ci_workflow_dry_run.py` (AC-4, 2 tests):
  `test_required_ci_commands_resolves_a_well_formed_list_against_this_repo` (pre-existing, passes on
  every platform), `test_resolve_step_reads_gates_directly_from_required_ci_commands` (new in the
  authoring commit -- see below)

Recon's third AC-4 candidate, `test_workflow_resolves_required_gates_against_the_real_repo`, is
skip-if'd on Windows/no-bash and was confirmed SKIPPED (not passing) in this dev environment,
matching recon's `currently_passes: false` for it. Per instructions it was not marked. Instead a new
test, `test_resolve_step_reads_gates_directly_from_required_ci_commands`, was added: it parses the
"Resolve required CI gates" step's `run` text directly and asserts it imports and calls
`required_ci_commands` -- proving the same AC-4 claim without a subprocess, so it passes on every
platform, including this one.

## 4. Files changed and commit SHAs

Only one commit exists for SR-048 -- the authoring commit. No fix or evidence commit exists because
the gate stage that would normally trigger review/fix/evidence crashed (section 5).

Authoring (`9ce6ee1adbcf946f390c5e0632470a8dc07f37d3` --
`feat(requirements): author FEAT-002/SR-048 acceptance criteria + binding`):

- `requirements/SR-048.md` (+40) -- acceptance array (AC-1..AC-4), AC-2/AC-3 narrowing note, no
  statement correction
- `tests/unit/coherence/policy/test_ci.py` (+4) -- SR-048 markers on 4 existing tests
- `tests/unit/coherence/policy/test_compiler.py` (+2) -- SR-048 markers on 2 existing tests
  (already carrying SR-009; markers stack)
- `tests/integration/test_ci_workflow_dry_run.py` (+15) -- SR-048 marker on 1 existing test, plus 1
  new test (`test_resolve_step_reads_gates_directly_from_required_ci_commands`)

No production code changed -- only `requirements/SR-048.md` and test files. The commit is
`recorded_by "agent"` throughout -- no `decided_by`/human-attestation field is set anywhere in it,
and no `gate-decisions/*.json` file exists or was written for SR-048 by any part of this pipeline.

## 5. Deterministic gate results

**The gate stage did not produce a result.** The gate agent crashed or returned nothing when run
against the authoring commit (`9ce6ee1`), and no deterministic pass/fail evidence exists for
SR-048's bound tests, lint, typecheck, `mirrors check`, or `register check` at this stage of the
pipeline -- unlike SR-011's packet (section 5 there), there is no rerun to cite here.

The author's own self-report (section "notes" of the authoring output, not an independently-run
gate) states that before marking any test, the tests were re-run directly against the worktree's
venv (`.venv/Scripts/python.exe -m pytest`): all unit candidates passed, and of the integration
candidates, the two flagged `currently_passes: true` in recon passed while the one flagged `false`
was confirmed SKIPPED, not passing, matching recon. The author also reports `ruff check` and
`pyright` clean on every touched file, and the full unit suite at 2930 passed / 2 failed (both
pre-existing and unrelated, confirmed via `git stash`) / 12 skipped / 120 deselected, plus
`coherence register check` and `coherence trace check` both parsing SR-048's new frontmatter without
a schema error. **This is author self-report, not a gate run** -- it has not been independently
re-executed by this packet, and it is explicitly not a substitute for the deterministic gate stage
that was supposed to run next and did not.

- **bound_tests_ok**: unknown (gate did not run)
- **lint_ok**: unknown (gate did not run)
- **typecheck_ok**: unknown (gate did not run)
- **mirrors_clean**: unknown (gate did not run)
- **register_check_ok**: `false` per the gate input -- consistent with SR-048 sitting undecided/
  pending in the register, the same status most other pending SRs in this repo hold at this stage
  (matching what SR-011's own gate run separately confirmed for `register_check_ok=false` being
  expected pre-decision, not a defect)
- **passed**: `false`
- **escalate**: `true`
- **escalate_reason**: "gate agent failed/returned nothing"

## 6. Independent review verdict and findings

**No independent review ran.** Because the gate stage crashed, the review stage that consumes a
passing gate result never started -- `review: null` in this pipeline's state. There is no reviewer
verdict, no findings list, and nothing that was "addressed" by a fix commit, because no fix commit
exists (section 4). Any claim in this packet about test results, lint, or typecheck is the author's
self-report from section 5, not an independently verified review.

## 7. NEEDS HUMAN INPUT BEFORE CONSENT

This SR is flagged `escalate: true`. The open question here is procedural, not a design or scope
judgment call the way SR-011's was -- it is about what to do with an authoring result that never got
an independent gate/review pass:

1. **The gate agent crashed after authoring, before any independent review ran.** SR-048's
   requirement statement, acceptance criteria, and test bindings exist and were authored following
   the same narrowing discipline used on SR-001/SR-011 (dropping unreachable/untested clauses rather
   than leaving them overclaimed). But nothing past the author's own self-report has independently
   re-run the bound tests, lint, or typecheck against this commit, and no independent reviewer has
   checked the authored ACs and statement-correction reasoning against the implementing code the
   way SR-011's reviewer did (section 6 there). **The open question for you:** do you want the gate
   and review stages re-run against commit `9ce6ee1adbcf946f390c5e0632470a8dc07f37d3` before
   authoring consent is considered at all, or are you willing to evaluate consent on the authoring
   record and the author's self-report alone, treating the crashed gate as a pipeline-infrastructure
   problem to fix separately rather than a blocker on this SR's content? Either way, no gate,
   review, fix, or evidence has actually happened yet for SR-048, and this packet cannot substitute
   for that.

This turns on how much weight to give an authoring-only record with no independent verification
behind it -- exactly what authoring consent exists to catch before anything is treated as settled.

---

Awaiting human accept/reject/defer -- no decision has been recorded.
