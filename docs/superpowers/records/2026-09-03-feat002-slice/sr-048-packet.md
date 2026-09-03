# SR-048 human-consent review packet

FEAT-002 (progressive assurance), thin vertical slice. This packet exists so a human can give (or
withhold) authoring consent for SR-048 with the full trail in front of them. No decision is
recorded in this document or anywhere in this session -- see the closing line.

## 1. Source excerpt

`docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md#D18`, cross-referenced
against section 7 ("CI"), section 11 ("Testing"), and the section 13 amendment row that corrects
D18's original day-one-blocking divergence. Recon also checked
`2026-09-01-coherence-product-definition.md`, which only cross-references SR-048 at its L4 row
(`ci_verification`, `no` on manual-only) -- no supersession of D18 was found on this topic.

The statement was drafted directly from D18/§7/§11/§13; no single verbatim quotable bullet exists
the way some other SRs' did, since D18 is a decision-and-rationale entry rather than a bulleted
feature list.

## 2. Final statement -- NOT corrected

Recon's `statement_needs_correction` was `false`, and the authoring pass re-checked this against
the actual implementation (`src/coherence/policy/ci.py`, `src/coherence/policy/compiler.py`,
`.github/workflows/ci.yml`) before agreeing. The independent reviewer separately re-checked the
same claim against the same files and against D18/§7/§11/§13 and the product-definition's L4 row,
and reached the same conclusion. The statement is unchanged from recon's draft and from what
shipped in `requirements/SR-048.md`'s frontmatter:

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
the workflow enumerates specific commands by name. The reviewer additionally ran
`required_ci_commands(Path('.'))` live against this repo and confirmed it resolved the real
`.factory/factory.yaml` gates plus the two structural checks correctly.

One nuance was noted for the human reviewer but judged not to affect the statement: spec section 11
says "CI's own workflow is tested by running it against a seeded repo state in a dry-run job before
it gates real PRs." There is no separate dry-run job inside `ci.yml` itself (it has one job,
`gates`); what exists instead is a pytest integration suite
(`tests/integration/test_ci_workflow_dry_run.py`) that parses `ci.yml` and runs its individual steps
via subprocess, partly against the real repo and partly (the gate-loop shell logic) against fake
seeded executables. Functionally similar intent, differently shaped than the spec's literal
wording -- doesn't touch what SR-048's statement says, since the statement is silent on how CI's own
workflow is tested. The independent reviewer confirmed this reading and found no other part of the
product-definition's L4 row (branch-protection enforcement, a separate GitHub-repo-settings claim)
narrows or contradicts SR-048's statement or ACs, since neither asserts branch-protection
enforcement.

## 3. Final acceptance criteria, with verification refs

Two of recon's four draft criteria were narrowed during authoring (dated note in
`requirements/SR-048.md`'s body, mirroring SR-001's AC-3 narrowing precedent). Both narrowings drop
a claim that no currently-passing test actually proves, even though the surrounding implementation
likely satisfies it by construction. The independent reviewer re-derived both narrowings
independently by direct code trace and agreed both were genuinely untestable through any real
compilation path, not just a convenient trim.

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
applied to other SRs' authoring consent in this feature slice.

Eight tests carry `@pytest.mark.sr("SR-048")` across three files (two of the `test_compiler.py`
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
platform, including this one. The independent reviewer re-ran the full three-file test suite plus
all 8 SR-048-marked tests specifically and confirmed all pass.

## 4. Files changed and commit SHAs

Two commits exist for SR-048 -- authoring, then evidence. No fix commit exists because the
independent review found no findings to fix (section 6).

**Authoring** (`9ce6ee1adbcf946f390c5e0632470a8dc07f37d3` --
`feat(requirements): author FEAT-002/SR-048 acceptance criteria + binding`):

- `requirements/SR-048.md` (+40) -- acceptance array (AC-1..AC-4), AC-2/AC-3 narrowing note, no
  statement correction
- `tests/unit/coherence/policy/test_ci.py` (+4) -- SR-048 markers on 4 existing tests
- `tests/unit/coherence/policy/test_compiler.py` (+2) -- SR-048 markers on 2 existing tests
  (already carrying SR-009; markers stack)
- `tests/integration/test_ci_workflow_dry_run.py` (+15) -- SR-048 marker on 1 existing test, plus 1
  new test (`test_resolve_step_reads_gates_directly_from_required_ci_commands`)

**Evidence** (`b5889a42b5621130f8f01ee7270ff00d119cf07a` --
`chore(evidence): record FEAT-002/SR-048 evidence`):

- `evidence/runs/T-9012-evidence-execution-20260903T014536Z.json` (new, 124 lines) --
  agent-recorded run manifest for all 8 `@pytest.mark.sr("SR-048")` tests, mapped to AC-1..AC-4
- `validation/validation-report.json` (+31/-5) -- matching SR-048 entry (`passed: true`, `value:
  1.0`); provenance note updated to describe SR-048's addition and its run chain

No production code changed in either commit -- only `requirements/SR-048.md`, test files, and
evidence/report files. Both commits are `recorded_by "agent"` throughout -- no `decided_by`/
human-attestation field is set anywhere in either of them, and no `gate-decisions/*.json` file
exists or was written for SR-048 by any part of this pipeline.

## 5. Deterministic gate results

Gate stage passed at the authoring commit (`9ce6ee1`):

- **bound_tests_ok**: true
- **lint_ok**: true
- **typecheck_ok**: true
- **mirrors_clean**: true
- **register_check_ok**: true -- the gate's own health note clarifies this as "true" in the sense
  that `coherence register check` parsed SR-048's frontmatter correctly (no schema/parse error);
  the command's overall process exit is non-zero repo-wide because 47 requirements across the
  project are still `sr_proposed`/undecided pending gate decisions, which is pre-existing,
  repo-wide state predating this SR, not something SR-048 caused. SR-048 itself shows up in that
  pending list in the same expected "binding not yet decided" state as every other undecided
  sibling SR.
- **passed**: true
- **escalate**: false at the gate stage
- `coherence navigate health` was not run (not required for a single-SR gate pass per instructions)

## 6. Independent review verdict and findings

**Verdict: `approved`** -- no findings.

The reviewer independently read `requirements/SR-048.md`, `src/coherence/policy/ci.py`,
`src/coherence/policy/compiler.py`, `.github/workflows/ci.yml`, all three bound test files, D18/
§7/§11/§13 of the 2026-08-22 design spec, and the L4 row of the 2026-09-01 product-definition spec.
All four ACs were checked against what their bound tests actually prove, no more and no less:

- AC-1's exact command list/order/`{python}`-substitution and structural-check suffix is pinned by
  `test_includes_every_declared_gate_command_in_order_with_python_substituted` +
  `test_structural_checks_are_always_appended`.
- AC-2's two raise-branches (empty `resolve_cmd` on no declared gates; a monkeypatched
  multi-obligation case with one missing `resolve_cmd`) are each proven by a dedicated test. The
  reviewer independently confirmed by code trace that `_ci_verification_obligation` always sets
  `requiredness == "blocking"` unconditionally and `compile_obligations` appends exactly one
  `ci_verification` obligation for project scope, so both narrowed-out clauses (an unreachable
  "zero obligations" raise branch, an untested "exactly one obligation" cardinality claim) really
  were untestable through any real compilation path -- matching the author's own narrowing
  rationale.
- AC-3's requiredness/order/duplicate-preservation claims are pinned by the two compiler tests,
  verified against the actual compiler code.
- AC-4's claim that the workflow step calls `required_ci_commands` directly (not a hand-maintained
  list) is pinned by both the text-parsing test and, by direct inspection of
  `.github/workflows/ci.yml`, is literally true (`python -c 'from coherence.policy.ci import
  required_ci_commands; ...'`).

Scope-fence check: the reviewer confirmed the work stays inside D16's thin-slice fence -- only
`prototype` (the resolved default in every seeded test, with no `.factory/policy.yaml` present) is
exercised, and the spec's own §13 amendment row explicitly states `ci_verification` is "not a new
obligation kind in the guide's sense" distinct from D16's three-kind count
(task_justification/verification_result/human_review), so this is not a fence violation.

Independently re-ran all 8 SR-048-marked tests plus the full `test_ci.py`/`test_compiler.py`/
`test_ci_workflow_dry_run.py` suites (59 passed, 7 skipped -- all pass), `ruff` and `pyright` clean
on every touched file, `coherence register`/`trace check` showing SR-048 correctly pending (not an
error), and reproduced the two pre-existing unit-test failures the author reported
(`test_remediation.py::test_every_shell_command_names_a_real_subparser`,
`test_validation_report_schema.py::test_the_repositorys_validation_report_cites_the_run_that_produced_it`)
to confirm they are unrelated to this SR's files. Verified commit `9ce6ee1adbcf946f390c5e0632470a8dc07f37d3`
exists and matches the self-report's description. Confirmed no `gate-decisions/*.json` file exists
for SR-048 and no `decided_by`/consent claim appears anywhere in the commit.

No defects found worth acting on -- no fix commit was needed.

## 7. Evidence recording

`rtk proxy uv run coherence measurement run --satisfies SR-048` was tried first per process and
returned an empty requirements list (that runner only evaluates top-level `binding:` requirements,
not `kind:test_marker` acceptance criteria, matching the SR-008/009/010/011 precedent). That command
overwrote `validation/validation-report.json` with an empty result; reverted via `git checkout --
validation/validation-report.json` before any real evidence was recorded.

Evidence was then recorded manually following the dual-store discipline: all 8 tests marked
`@pytest.mark.sr("SR-048")` across the three ref files named by AC-1..AC-4 were collected and run
directly (`rtk proxy uv run pytest`) -- all 8 passed, 0 failed.
`evidence/runs/T-9012-evidence-execution-20260903T014536Z.json` was written (schema_version 2,
per-AC test breakdown, provenance `recorded_by: "agent"`) and a matching SR-048 entry appended to
`validation/validation-report.json` (`passed: true`, `value: 1.0`), with the file-level provenance
note updated to describe SR-048's addition and its five-run chain (T-6, T-9008..T-9012). Both JSON
files were validated with a parse check.

`rtk proxy uv run coherence register check` confirmed SR-048 no longer appears in the "no
measurement, task, or deferral accounts for this requirement" warning list afterward (neighbors
SR-045/046/047/049/050/051 still do, confirming the check is discriminating, not silenced
globally).

`git status` before the evidence commit showed only the two evidence files touched -- no
`gate-decisions/*.json` written, no `decided_by` or human attestation fabricated anywhere.

---

Awaiting human accept/reject/defer -- no decision has been recorded.
