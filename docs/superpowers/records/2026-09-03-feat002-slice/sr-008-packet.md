# SR-008 human-consent review packet

FEAT-002 (progressive assurance), thin vertical slice. This packet exists so a human can give (or
withhold) authoring consent for SR-008 with the full trail in front of them. No decision is
recorded in this document or anywhere in this session -- see the closing line.

## 1. Source excerpt

`docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md`, section 4
("Progressive assurance model"), the "Profile vocabulary" bullet:

> - **Profile vocabulary**: seven dimensions (`maturity`, `consequence`, `reversibility`,
>   `volatility`, `verification_cost`, `exposure`, `collaboration`), each a fixed enum, compiled
>   with explicit scope precedence (artifact/requirement > feature/bundle > path/component >
>   project default), equal-specificity conflicts rejected rather than silently ordered.

Same document, decision D16 (line 83), which scopes FEAT-002's thin vertical slice:

> D16 | Progressive assurance is scoped to the thin vertical slice (guide §11) first: `prototype`
> and `high_assurance` presets only, three obligation kinds only | `exploration`/`product`/
> `high_assurance`'s remaining obligation kinds are declared in the schema but not compiled or
> tested until a real use case needs them -- matches the toolset design's own YAGNI instinct (§2
> non-goals)

A companion doc independently confirms the gap this packet is about is real and known, not an
oversight of this recon:
[[docs/superpowers/specs/2026-08-22-system-traceability-course-overhaul-design#L214|system
traceability course overhaul design]], line 214, teaching the seven-dimension profile as
**"designed, not shipped"**:

> 0. **Progressive assurance: obligations, profiles, nonconformances (roadmap)** -- added at the
>    learner's request after the second-wave amendment. Teaches the vocabulary as **designed, not
>    shipped**: the seven-dimension profile (`maturity`, `consequence`, `reversibility`,
>    `volatility`, `verification_cost`, `exposure`, `collaboration`) [...]

The 2026-09-01 product-definition doc's own feature map (section 5) uses "Profile" purely as a
single-value column (`prototype`/`high_assurance`), consistent with what actually ships, and does
not mention or restore the seven-dimension model.

## 2. Final statement -- CORRECTED

**Before** (recon's draft, taken from the source excerpt's surface reading):

> The system shall compile obligations from a seven-dimension profile with fixed enums and
> explicit scope precedence (artifact/requirement > feature/bundle > path/component > project
> default), rejecting equal-specificity conflicts.

**After** (what shipped, `requirements/SR-008.md` frontmatter, corrected during authoring
consent):

> The system shall resolve a project's, or an artifact's, effective assurance preset from a fixed
> enum (exploration/prototype/product/high_assurance) through explicit scope precedence
> (artifact/requirement > feature/bundle > path/component > project default), rejecting
> equal-specificity conflicts, and shall compile obligations only for presets it actually supports
> (prototype and high_assurance, per D16), failing closed on any other preset name or value.

**Why it was corrected:** the draft claimed the system compiles obligations "from a
seven-dimension profile with fixed enums" -- the design doc's per-dimension vocabulary
(`maturity`, `consequence`, `reversibility`, `volatility`, `verification_cost`, `exposure`,
`collaboration`). That per-dimension model does not exist in the shipped code: `DIMENSIONS` in
`src/substrate/policy/vocabulary.py` is declared but never consumed anywhere -- no schema,
resolver, or obligation compiler constrains or compiles a value for any of the seven named
dimensions (grep-confirmed zero references outside its own declaration). What is actually
implemented and tested is scope-precedence resolution over a single flat preset name (one of
`exploration`/`prototype`/`product`/`high_assurance`, itself a fixed enum in
`profile.schema.json`), with equal-specificity path-override conflicts rejected and obligations
compiled only for the two presets D16 authorizes for the thin slice. Collapsing seven independent
per-dimension enums down to one of four presets (or replacing the preset model with a genuine
multi-dimension one) would be a materially new design surface -- not a small mechanical
addition -- and D16 does not authorize it here. So the statement was narrowed to describe only
what is real, rather than the code being stretched to match the broader draft claim.

The seven-dimension vocabulary (`DIMENSIONS` in `vocabulary.py`) remains in the codebase as an
unused, documented-only constant, unless and until a future SR explicitly scopes compiling it.

## 3. Final acceptance criteria, with verification refs

| AC | Criterion | Verification |
|----|-----------|---------------|
| AC-1 | Resolving `project` scope returns the project's own configured preset when `.factory/factory.yaml` declares one, and the fixed `prototype` default when it does not. | `test_marker` -> `tests/unit/coherence/policy/test_compiler.py` |
| AC-2 | A requirement/artifact carrying its own `profile:` frontmatter override resolves to that preset directly -- taking precedence over any feature/bundle-level override on the same artifact -- and an SR belonging to a feature/bundle that declares a `profile:` override, while the SR itself declares none, inherits that feature-level preset. | `test_marker` -> `tests/unit/coherence/policy/test_compiler.py` |
| AC-3 | Among two or more path/component overrides in `.factory/profile.yaml` matching the same path, the most-specific glob (by segment count) wins; when the equally-most-specific matches disagree on the resolved preset, resolution raises `ProfileConflictError` rather than picking one arbitrarily. | `test_marker` -> `tests/unit/substrate/policy/test_vocabulary.py` |
| AC-4 | A profile string naming a preset outside the four known preset names (`exploration`/`prototype`/`product`/`high_assurance`) is rejected as `InvalidProfileError`, a distinct exception type from `UncompiledPresetError` (neither is a subclass of the other). | `test_marker` -> `tests/unit/substrate/policy/test_vocabulary.py` |
| AC-5 | A resolved profile naming a real, known preset name that is not yet in `COMPILED_PRESETS` (`exploration` or `product`) is rejected as `UncompiledPresetError` rather than silently substituting a default. | `test_marker` -> `tests/unit/coherence/policy/test_compiler.py` |

AC-4 was split out of the recon draft's single combined criterion (which asserted both the
unknown-preset-name path and the known-but-uncompiled-preset path as one claim against one ref)
into AC-4/AC-5, because the two error paths are proven by tests in two different files
(`InvalidProfileError` in `test_vocabulary.py`, `UncompiledPresetError`'s raise site in
`test_compiler.py`). This mirrors how SR-001's own AC-3 was narrowed during its authoring consent
(`ca3162c`).

Ten tests carry `@pytest.mark.sr("SR-008")` across the two files, two per AC, including one new
test written during authoring (no candidate test proved, at the `resolve_profile` level, that an
SR's own override wins over its feature's -- only that it inherits when it has none):

- `tests/unit/coherence/policy/test_compiler.py`: `test_resolve_profile_project_default`,
  `test_resolve_profile_project_scope_uses_project_default_explicitly`,
  `test_resolve_profile_honors_preloaded_nodes_and_edges`,
  `test_resolve_profile_artifact_own_override_wins_over_feature_inheritance` (new),
  `test_resolve_profile_rejects_uncompiled_preset`,
  `test_resolve_profile_rejects_uncompiled_preset_product`
- `tests/unit/substrate/policy/test_vocabulary.py`: `test_path_override_most_specific_wins`,
  `test_path_override_equal_specificity_conflict_raises`,
  `test_unknown_preset_name_raises_invalid_profile_error`,
  `test_invalid_profile_error_is_not_an_uncompiled_preset_error`

## 4. Files changed and commit SHAs

Authoring (`1ec7dfc6fd7de05a5d6b9735e6ae80bf17ac2871` --
`feat(requirements): author FEAT-002/SR-008 acceptance criteria + binding`):

- `requirements/SR-008.md` (+57/-1) -- corrected statement, five ACs, dated authoring notes
- `tests/unit/coherence/policy/test_compiler.py` (+24) -- SR-008 markers, one new test
- `tests/unit/substrate/policy/test_vocabulary.py` (+4) -- SR-008 markers

No production code changed in this commit -- only test markers, one new test, and the requirement
document.

Evidence (`6a2a8fa3d150b7da33b2e510697dd3abdfa4d932` --
`chore(evidence): record FEAT-002/SR-008 evidence`):

- `evidence/runs/T-9008-evidence-execution-20260902T223423Z.json` (new, 133 lines) -- agent-recorded
  run manifest for all ten `@pytest.mark.sr("SR-008")` tests, mapped to AC-1..AC-5
- `validation/validation-report.json` (+35/-6) -- matching SR-008 entry feeding
  `executed_evidence`; provenance note extended to cite both the pre-existing FEAT-001 T-6 run and
  this new T-9008 run

Both commits are `recorded_by "agent"` throughout -- no `decided_by`/human-attestation field is
set anywhere in either commit.

## 5. Deterministic gate results

- **register_check_ok**: true -- `coherence.register check` (via `.venv/Scripts/python.exe -m`,
  since bare `coherence`/`ruff` are not on PATH here) shows the whole-repo closure with 51/56
  requirements pending, including SR-008 pre-evidence; this is the pre-existing repo-wide baseline
  (matches already-consented SR-001), not something this work introduced. `coherence.register show
  SR-008` and the raw frontmatter parse cleanly: 5 ACs (AC-1..AC-5), all `kind: test_marker`,
  correct refs.
- **bound_tests_ok**: true -- both touched test files run together: **57 passed, 1 skipped**
  (a pre-existing Windows-only junction test in `test_vocabulary.py`, unrelated to SR-008,
  confirmed pre-existing by name). Six `@pytest.mark.sr("SR-008")` markers confirmed present in
  `test_compiler.py`.
- **lint_ok**: true -- `ruff check` on the three touched files: all checks passed.
- **typecheck_ok**: true -- `pyright` on the two touched test files: 0 errors/warnings/informations.
- **mirrors_clean**: true -- `coherence.mirrors generate`: 20 feature dossiers processed, no drift
  ("no changes -- every mirror already matched its derivation").
- **passed**: true overall.
- No `gate-decisions/` file exists or was written for SR-008 by any part of this pipeline,
  consistent with instructions.
- Health notes corroborate the author's self-report: statement narrowing, the AC-4/AC-5 split, and
  the unresolved-gap rationale all match what's actually in `requirements/SR-008.md` and the code.

After the evidence-recording commit, `coherence.register check` moved SR-008 out of "undecided
requirements" with measured-passing count 5 -> 6, and `coherence navigate health --json`'s
`executed_evidence` dimension moved satisfied 5 -> 6 of 56. `authoring_consent` and `human_review`
gates for SR-008 remain open -- neither is touched by this packet or by anything committed so far.

## 6. Independent review verdict and findings

**Verdict: `approved_with_reservations`**

The reviewer verified each of the five ACs 1:1 against its bound test(s) and the implementation
(`src/coherence/policy/compiler.py`'s `resolve_profile`/`compile_obligations`,
`src/substrate/policy/vocabulary.py`, `src/substrate/schemas/profile.schema.json`), confirmed the
exact precedence order (own override -> owning-feature override via a `contains` edge -> path
override -> project default), confirmed `DIMENSIONS` is grep-dead (zero references outside its own
declaration), confirmed the companion-doc citation ("designed, not shipped") is exact at line 214,
confirmed D16's thin-slice preset fence is honored by every AC, confirmed the git diff for the
authoring commit touches only the three claimed files with the exact self-reported hunks, and
re-ran both bound test files directly (57 passed, 1 pre-existing unrelated skip).

Two findings:

1. **Low severity, cheap fix available -- not yet addressed.** AC-2's criterion text says an SR
   "belonging to a feature/bundle" inherits that container's profile, but the trace model
   (`coherence/trace/model.py` `NodeKind`) has no `bundle` node kind at all -- only `feat` is ever
   consulted for inheritance in `resolve_profile` (via the `contains` edge lookup gated on
   `node.kind == 'sr'`). The bound test only exercises the FEAT case; no scope named `bundle`
   exists to test. This phrasing is inherited verbatim from the design doc's own precedence phrase
   and from SR-008's pre-existing statement text, so it is not a new over-claim invented during
   this authoring pass -- but as written, an AC meant to say only what its bound test proves,
   "feature/bundle" reads as claiming two distinct, both-tested precedence rungs when only one
   (feature) is implemented or provable.
2. **Informational, not a defect in SR-008.** D16 says progressive assurance is scoped to "three
   obligation kinds only," but the shipped compiler already compiles at least five kinds
   (`ci_verification`, `verification_result`, `human_review`, `test_marker`,
   `task_justification`) across the test suite -- a real drift from D16's own fence. SR-008's
   statement and all five ACs make no claim about obligation-kind count, so this isn't a defect in
   SR-008's own authored criteria; flagged only as context in case a sibling SR's ACs need the same
   scrutiny.

**How addressed:** neither finding has been acted on. Finding 1 is cheap to fix (narrow AC-2's
wording to "feature" alone, or add a genuine `bundle` scope and a test for it) but was left open
rather than edited unilaterally after the review; finding 2 names a real drift that belongs to
whichever SR(s) actually bind those other obligation kinds, not to SR-008, and is carried forward
only as context.

## 7. NEEDS HUMAN INPUT BEFORE CONSENT

This SR is flagged `escalate: true`. Two open questions need a human decision before consent can
be recorded:

1. **AC-2's "feature/bundle" wording.** Should AC-2 be edited now to say only "feature" (matching
   what `resolve_profile` and its bound test actually implement and prove), or left as-is on the
   grounds that it mirrors the design doc's and the pre-existing statement's own phrasing, with
   the gap simply noted? This is the reviewer's one actionable (cheap-fix) finding, and it was
   deliberately left unedited pending your call rather than resolved unilaterally after review.
2. **The seven-dimension profile gap itself.** Recon's central finding stands unresolved by
   design, not by oversight: SR-008's original statement claimed the system compiles obligations
   "from a seven-dimension profile with fixed enums," but only a single flat preset enum is
   actually resolved/compiled anywhere in the codebase (`DIMENSIONS` is declared, unused). The
   statement was narrowed to match what ships rather than the gap being filled, on the grounds
   that filling it (collapsing seven per-dimension enums into a preset, or replacing the preset
   model outright) is a materially new design surface that D16 does not authorize for FEAT-002's
   thin slice. **The open question for you:** do you accept the narrowed statement as the correct
   scope for SR-008 (deferring the seven-dimension model to a future, explicitly-scoped SR), or
   does this gap mean SR-008 should not be consented as authored -- e.g. because the seven-dimension
   claim was load-bearing for some other part of the design and needs its own SR/decision before
   this one can be accepted as complete?

Both questions turn on judgment calls about scope and intent that this pipeline is not positioned
to make on its own -- they are exactly what authoring consent exists to catch.

---

Awaiting human accept/reject/defer -- no decision has been recorded.
