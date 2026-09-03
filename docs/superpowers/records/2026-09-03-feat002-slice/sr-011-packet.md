# SR-011 human-consent review packet

FEAT-002 (progressive assurance), thin vertical slice. This packet exists so a human can give (or
withhold) authoring consent for SR-011 with the full trail in front of them. No decision is
recorded in this document or anywhere in this session -- see the closing line.

## 1. Source excerpt

`docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md`, section 4, the
"Typed task justification" and "Typed lifecycle relationships" bullets, scoped by D16 (section 3
decisions table) to the thin vertical slice:

> Typed task justification (satisfies/corrects/mitigates/implements/maintains/explores) [...]
> Typed lifecycle relationships (derives/decomposes/refines/allocates/implements/verifies/
> validates/evidences/corrects/impacts/supersedes), rejecting an unsupported kind at load.

D16 frames the wider relationship vocabulary as schema-only, deliberately deferred until a real
use case needs it -- not something FEAT-002's thin slice compiles or tests.

## 2. Final statement -- CORRECTED

**Before** (recon's draft, quoting the source excerpt verbatim):

> The system shall accept typed task justification (satisfies/corrects/mitigates/implements/
> maintains/explores) and typed lifecycle relationships (derives/decomposes/refines/allocates/
> implements/verifies/validates/evidences/corrects/impacts/supersedes), rejecting an unsupported
> kind at load.

**After** (what shipped, `requirements/SR-011.md` frontmatter, corrected during authoring
consent):

> The system shall accept typed task justification (satisfies/corrects/mitigates/implements/
> maintains/explores) on task nodes, with legacy bare satisfies: frontmatter read as shorthand for
> a satisfies justification entry, rejecting an unsupported justification kind or malformed entry
> at load.

**Why it was corrected:** the draft statement's second half -- "typed lifecycle relationships
(derives/decomposes/refines/allocates/implements/verifies/validates/evidences/corrects/impacts/
supersedes), rejecting an unsupported kind at load" -- is not implemented for anything beyond task
justification. `coherence.trace.model.EdgeKind` (a `Literal[...]`) lists all twelve
lifecycle-relationship kind names (see correction below on the count), but that is only a
type-level enumeration used so the shared `Edge` dataclass can represent a justification edge
whose kind happens to be `corrects`/`implements`/etc. There is no frontmatter field (a
`relationships:` list or similar) on any non-task node kind (sr/br/feature/decision/...) that is
parsed into these edges, and no load-time rejection path for an unsupported relationship kind
analogous to `_justification_scope_error`/`InvalidJustificationError`. Grepping the codebase for
derives/decomposes/refines/allocates/verifies(edge)/validates(edge)/evidences/impacts turns up
zero occurrences outside that one `Literal` declaration (`supersedes` is used elsewhere, but in
`substrate/artifacts.py` for evidence-record supersession -- an unrelated mechanism, not the
trace/lifecycle-relationship graph SR-011's draft described). The statement now describes exactly
what is implemented and tested: typed task justification on task nodes, with the legacy
`satisfies:` shorthand preserved, rejecting an unsupported kind or malformed entry at load. This
mirrors how [[SR-004]]'s AC-3 and [[SR-008]]'s AC-4/AC-5 were narrowed to what is automatable today
during their own authoring consent.

**A second, smaller correction landed during the independent review pass.** The authoring
commit's own correction note claimed `EdgeKind` "lists all eleven lifecycle-relationship kind
names" and enumerated eleven (omitting `mitigates`). Reading `src/coherence/trace/model.py`
lines 303-315, the contiguous `Literal` block actually contains twelve entries -- derives,
decomposes, refines, allocates, implements, verifies, validates, mitigates, evidences, corrects,
impacts, supersedes -- with `mitigates` sitting in that same block, doing double duty as both a
lifecycle-relationship kind and a task-justification kind. The fix commit (`dcac485`) corrected
the note to say twelve and include `mitigates`. This was documentation-only: it didn't touch any
acceptance criterion, test binding, or verification ref.

**The gap this correction carves out is real and unresolved** -- see section 7.

## 3. Final acceptance criteria, with verification refs

| AC | Criterion | Verification |
|----|-----------|---------------|
| AC-1 | A task's `justification:` list, with an entry for any of the six supported kinds (satisfies/corrects/mitigates/implements/maintains/explores), produces a correspondingly-typed edge from the task to the named target id in the trace graph, and a bare legacy `satisfies:` frontmatter field (list or scalar) with no `justification:` key produces the identical satisfies edge it always has, with no migration required. | `test_marker` -> `tests/unit/trace/test_model_edges.py` |
| AC-2 | A task's `justification:` list frontmatter parses into typed `Justification(kind, target_id)` entries at the substrate ledger layer for any of the six supported kinds, mixed within a single list, and a bare legacy `satisfies:` frontmatter field with no `justification:` key parses as an implicit satisfies-kind entry, populating `Task.satisfies` identically to before. | `test_marker` -> `tests/unit/substrate/ledger/test_tasks_justification.py` |
| AC-3 | A task justification entry that is malformed -- naming a kind outside the six supported kinds, or packing more than one `{kind: target_id}` pair into a single list entry -- degrades to a `scope_error` recorded on the task's trace node naming the offending content, rather than producing a valid edge or being silently dropped; a well-formed justification list leaves `scope_error` unset. | `test_marker` -> `tests/unit/trace/test_model_nodes.py` |
| AC-4 | The same two malformed-justification cases -- an unsupported kind, or more than one `{kind: target_id}` pair in one entry -- raise `substrate.ledger.tasks.InvalidJustificationError` at the ledger layer. | `test_marker` -> `tests/unit/substrate/ledger/test_tasks_justification.py` |

AC-1 and AC-2 each claim coverage of all six justification kinds. As first authored, the bound
tests exercised only three (satisfies/corrects/mitigates) -- a real criterion/test-coverage gap
the independent review caught (section 6, finding 1) and the fix commit closed by extending the
mixed-kinds tests to assert `implements`/`maintains`/`explores` edges as well.

Twelve tests carry `@pytest.mark.sr("SR-011")` across three files, all currently passing:

- `tests/unit/trace/test_model_edges.py` (AC-1, 4 tests): `test_task_declares_source_plan_and_satisfies`,
  `test_scalar_satisfies_is_accepted_as_single_edge`,
  `test_task_justification_corrects_produces_a_typed_edge`,
  `test_task_justification_mixed_kinds_produce_their_own_edges` (extended in the fix commit to
  cover all six kinds)
- `tests/unit/substrate/ledger/test_tasks_justification.py` (AC-2/AC-4, 5 tests):
  `test_legacy_satisfies_becomes_typed_justification`, `test_explicit_justification_corrects`,
  `test_justification_mixed_kinds` (extended in the fix commit to cover all six kinds),
  `test_unknown_justification_kind_raises`, `test_multi_key_justification_entry_raises`
- `tests/unit/trace/test_model_nodes.py` (AC-3, 3 tests):
  `test_task_with_unsupported_justification_kind_degrades_to_a_scope_error`,
  `test_task_with_well_formed_justification_has_no_scope_error`,
  `test_task_with_multi_key_justification_entry_degrades_to_a_scope_error` (new in the authoring
  commit -- proves already-implemented behavior in `_justification_scope_error`'s
  `len(entry) != 1` check; no production code changed for this AC)

## 4. Files changed and commit SHAs

Authoring (`a939bd40233b8bcbaeb7b078b2f814a44a04271e` --
`feat(requirements): author FEAT-002/SR-011 acceptance criteria + binding`):

- `requirements/SR-011.md` (+58/-1) -- acceptance array (AC-1..AC-4), statement correction, AC
  split, authoring notes
- `tests/unit/substrate/ledger/test_tasks_justification.py` (+5) -- SR-011 markers
- `tests/unit/trace/test_model_edges.py` (+4) -- SR-011 markers
- `tests/unit/trace/test_model_nodes.py` (+14) -- SR-011 markers plus one new test
  (`test_task_with_multi_key_justification_entry_degrades_to_a_scope_error`)

Fix (`dcac485bfde60fd7c65e48587a29d503513291f4` --
`fix(requirements): address independent review of FEAT-002/SR-011`):

- `requirements/SR-011.md` (+4/-2) -- correction note fixed to say twelve `EdgeKind` names and
  include `mitigates`
- `tests/unit/substrate/ledger/test_tasks_justification.py` (+5/-1) -- `test_justification_mixed_kinds`
  extended to all six kinds
- `tests/unit/trace/test_model_edges.py` (+5/-1) -- `test_task_justification_mixed_kinds_produce_their_own_edges`
  extended to all six kinds

Evidence (`c4e0b184b8393e2cf6cab505b575950a49c81fed` --
`chore(evidence): record FEAT-002/SR-011 evidence`):

- `evidence/runs/T-9011-evidence-execution-20260903T003052Z.json` (new, 132 lines) --
  agent-recorded run manifest for all twelve `@pytest.mark.sr("SR-011")` tests, mapped to AC-1..AC-4
- `validation/validation-report.json` (+30/-5) -- matching SR-011 entry; provenance block updated
  to `recorded_by: "agent"` citing this run's id/commit/evidence_manifest

No production code changed in any of these three commits -- only `requirements/SR-011.md`, test
files, and evidence/report files. All three commits are `recorded_by "agent"` throughout -- no
`decided_by`/human-attestation field is set anywhere in any of them, and no `gate-decisions/*.json`
file exists or was written for SR-011 by any part of this pipeline.

## 5. Deterministic gate results

Run at commit `dcac485` in `C:/coding/pi-agent-factory-wt/feat002-progressive-assurance`
(all invocations via `rtk proxy`, using venv binaries since bare `rtk proxy coherence`/`pytest`
resolve to the wrong Python/PATH on this box):

- **bound_tests_ok**: true -- `rtk proxy .venv/Scripts/python.exe -m pytest
  tests/unit/trace/test_model_edges.py tests/unit/substrate/ledger/test_tasks_justification.py
  tests/unit/trace/test_model_nodes.py -q` -> 38 passed, 0 failed (4 unrelated DeprecationWarnings
  about `factory.*` shim modules).
- **lint_ok**: true -- `rtk proxy .venv/Scripts/ruff.exe check src tests requirements` -> "All
  checks passed!".
- **typecheck_ok**: true -- `rtk proxy .venv/Scripts/pyright.exe` -> 74 errors / 21 warnings
  repo-wide, but none in files touched by this fix commit (only `requirements/SR-011.md` and the
  three bound test files changed; no production code changed). Confirmed via
  `git diff a939bd4^..dcac485 --stat`. The 74 errors are pre-existing baseline noise unrelated to
  SR-011.
- **mirrors_clean**: true -- `rtk proxy .venv/Scripts/coherence.exe mirrors check` -> "20 feature
  dossier(s) checked, 0 divergent".
- **register_check_ok**: false -- `rtk proxy .venv/Scripts/coherence.exe register check` ->
  requirements closure: 56 evaluated, 48 pending/undecided including SR-011 ("no measurement,
  task, or deferral accounts for this requirement"), 8 measured-passing, 0 measured-failing.
  `register show SR-011` confirmed binding was "(proposed -- not yet measurable)" at this stage.
  This was the same undecided status the SR held before the fix -- the fix commit only corrected
  the requirement statement/AC wording and test coverage, it did not add register-level
  measurement/task/deferral wiring, matching most of the other pending SRs in this repo at that
  point in the sequence.
- **passed**: true overall (the SR-level gate treats `register_check_ok=false` as expected/
  pre-existing at this stage, consistent with how SR-009/SR-010 were gated); **escalate**: false at
  the gate stage.

A stray `git stash`/`pop` cycle used to inspect a pre-fix commit round-tripped cleanly (nothing was
lost); it left `validation/validation-report.json` modified (auto-regenerated by the coherence
commands run), reverted with `git checkout -- validation/validation-report.json`. Working tree was
clean afterward other than that revert.

After the evidence-recording commit (`c4e0b18`), `coherence register check`'s measured-passing
count moved from 8 to 9 and SR-011 no longer appeared in the undecided-requirements list, with
`recorded_by` staying `"agent"` throughout. `rtk proxy coherence measurement run --satisfies
SR-011` was tried first per process and returned an empty requirements list (that runner only
evaluates top-level `binding:` requirements, not `kind:test_marker` acceptance criteria), and as a
destructive side effect overwrote `validation/validation-report.json` with an empty array -- caught
immediately and reverted before any evidence was recorded, confirming no prior SR-001..SR-010/
SR-050 evidence was lost. A pre-existing, unrelated failure was noted but not touched:
`tests/unit/validation/test_validation_report_schema.py::test_the_repositorys_validation_report_cites_the_run_that_produced_it`
hardcodes an old `run_id` and has been failing since SR-009's evidence was recorded, before this
task.

## 6. Independent review verdict and findings

**Verdict: `approved_with_reservations`**

The reviewer checked SR-011's statement, AC-1..AC-4, and the statement-correction/AC-split
authoring note against `requirements/SR-011.md` as it stood at the authoring commit, the three
bound test files, the implementing code in `src/coherence/trace/model.py` and
`src/substrate/ledger/tasks.py`, and design-doc section 4 / D16. All four ACs bind to real,
precise, single-file `test_marker` refs; all 38 tests in the three files passed (`rtk proxy uv run
pytest`), `ruff` was clean on the touched files, and `git show` on `a939bd4` confirmed the commit
touched only `requirements/SR-011.md` and test-marker/one-new-test additions -- no production code,
matching the self-report. AC-2/AC-4's ledger-layer implementation
(`substrate/ledger/tasks.py`'s `_parse_justification`/`InvalidJustificationError`) and AC-1/AC-3's
trace-layer implementation (`coherence/trace/model.py`'s `_edges_from_justification`/
`_justification_scope_error`) each precisely matched what their bound tests asserted, including
the legacy bare-satisfies shorthand and both malformed-entry shapes. The statement correction was
found well-founded: `EdgeKind`'s wider lifecycle-relationship vocabulary is genuinely schema-only
with zero parsing/rejection code anywhere in `src/` (verified by grep), matching D16's explicit
thin-slice fence, and the AC split follows the repo's established one-file-per-criterion
convention.

Two findings surfaced, both cheap fixes, both addressed in the fix commit (`dcac485`):

1. **Medium severity, cheap fix -- FIXED.** AC-1's criterion text claimed edge production for "any
   of the six supported kinds," and AC-2 made the identical claim for ledger-layer parsing "mixed
   within a single list." But the bound tests, as first authored, only exercised three of the six
   (satisfies/corrects/mitigates) -- grepping both files for "maintains" or "explores" or a
   justification-position "implements:" turned up zero hits. The implementation is genuinely
   kind-agnostic (a single membership check against a 6-tuple in both
   `coherence.trace.model._edges_from_justification` and
   `substrate.ledger.tasks._parse_justification`, no per-kind branching), so this was judged very
   unlikely to be a real behavioral gap, but per the letter of "match what the bound test actually
   proves, no more, no less," the criteria over-claimed coverage of three of the six named kinds --
   the same shape of problem SR-001's original AC-3 had with the reverse wikilink direction.
   **Fix:** extended `test_task_justification_mixed_kinds_produce_their_own_edges`
   (`tests/unit/trace/test_model_edges.py`) and `test_justification_mixed_kinds`
   (`tests/unit/substrate/ledger/test_tasks_justification.py`) to assert `implements`/`maintains`/
   `explores` edges in addition to `satisfies`/`mitigates`, so all six kinds are now exercised.
2. **Low severity, cheap fix -- FIXED.** SR-011.md's own authoring-consent note (and the commit
   message that introduced it) asserted `coherence.trace.model.EdgeKind` "lists all eleven
   lifecycle-relationship kind names" and enumerated eleven (omitting `mitigates`). Reading
   `src/coherence/trace/model.py` lines 303-315, the contiguous block under the "# Typed lifecycle
   relationships (spec section 4)" comment actually contains twelve entries, with `mitigates`
   sitting in that same code block, not off to the side. The note's central technical claim (no
   frontmatter field on any non-task node kind is parsed into these edges) was correct and the
   statement correction otherwise sound, but this specific count/enumeration was off by one and
   silently dropped `mitigates` from the list it was counting. Documentation-only -- doesn't touch
   any acceptance criterion, test binding, or verification ref. **Fix:** corrected the note to say
   twelve and include `mitigates`, noting it does double duty as both a lifecycle-relationship kind
   and a task-justification kind.

Verified via the fix commit's own re-run: 20 tests passed across the two touched files, `ruff
check` clean.

## 7. NEEDS HUMAN INPUT BEFORE CONSENT

This SR is flagged `escalate: true`. One open question needs a human decision before consent can
be recorded:

1. **The unresolved "typed lifecycle relationships" gap.** The draft statement's second half --
   "typed lifecycle relationships (derives/decomposes/refines/allocates/verifies/validates/
   evidences/impacts/supersedes), applied to non-task node kinds" -- has no implementation to fix
   mechanically. `coherence.trace.model.EdgeKind` only declares these names as a type-level
   `Literal` for the shared `Edge` dataclass; there is no frontmatter field on any node kind
   (sr/br/feature/decision/...) parsed into such edges, and no load-time rejection path for an
   unsupported relationship kind. Building this would mean designing and adding new frontmatter
   parsing + validation across every node kind -- a real feature, not a small mechanical fix -- and
   design-doc D16 explicitly frames this wider vocabulary as schema-only and deliberately deferred
   until a real use case needs it. Per instructions, this was not attempted; the statement was
   corrected to drop this claim and the acceptance criteria narrowed to only the typed-task-
   justification behavior that is actually implemented and tested. **The open question for you:**
   do you accept the narrowed statement as the correct scope for SR-011 -- deferring the general
   lifecycle-relationship-edge feature (beyond task justification) to a future, explicitly-scoped
   SR once a real use case drives it -- or does this gap mean SR-011 should instead be split now
   into a justification-only SR (this one) plus a separate placeholder SR that formally tracks the
   deferred lifecycle-relationship vocabulary, so the design doc's broader claim isn't quietly
   dropped with nothing tracking it going forward?

This turns on a judgment call about scope and intent that this pipeline is not positioned to make
on its own -- exactly what authoring consent exists to catch.

---

Awaiting human accept/reject/defer -- no decision has been recorded.
