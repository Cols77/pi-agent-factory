# T-3 report — acceptance criteria for the eight FEAT-001 SRs

**Status:** DONE_WITH_CONCERNS
**Branch:** `feat/feat001-slice` (worktree `C:/coding/pi-agent-factory-wt/feat001-slice`)
**Files changed:** `requirements/SR-001.md`, `SR-002.md`, `SR-003.md`, `SR-004.md`, `SR-005.md`,
`SR-006.md`, `SR-007.md`, `SR-050.md`. Nothing else. No test written or modified, no file under
`src/` touched, no `@pytest.mark.sr` decorator added, no gate `DecisionFile` authored.

`requirement_quality` moved **0/55 → 8/55**. All eight SRs count.

---

## 1. Criteria authored, with the source sentence each derives from

> **Superseded in part by §10 (review round 1 fixes).** Seven criteria were reworded and
> one was added after review. Where §1 and §10 differ, §10 carries the committed text.

### SR-001 — Explicit lifecycle traceability
Source: `docs/superpowers/plans/engineering-context/00-high-level-requirements.md#HLR-02`

HLR-02 makes four separable demands. I derived one criterion from each of three of them; the
fourth ("MUST NOT invent semantic trace edges from LLM inference and present them as
authoritative") is folded into AC-1's second clause rather than given its own criterion.

**AC-1** — *"Navigating from a feature anchor returns the connected system requirements, design
decisions, implementation task and its run, metric ids, evidence and current per-requirement
validation state, and reports no artifact that is not declared or recorded."*
→ `test_marker` → `tests/unit/system/test_feature.py`

Source sentence: *"At minimum, where the corresponding artifacts exist, the system SHALL support
navigation across: business intent → system requirement → feature / architecture / design decision
→ implementation → validation definition → experiment / simulation run → metric → evidence →
current validation state"*, plus *"The factory MUST NOT invent semantic trace edges from LLM
inference and present them as authoritative."*

**AC-2** — *"A requirement with no linked validation test, a requirement with no linked
implementation, and an implementation with no traceable requirement each surface as a named
engineering gap rather than being omitted."*
→ `test_marker` → `tests/unit/system/test_vcycle_health.py`

Source sentence: *"Missing links SHALL be surfaced as engineering gaps rather than hidden."*

**AC-3** — *"Every lifecycle relation declared in a requirement's typed fields is mirrored as an
Obsidian wikilink in that requirement's Markdown body, and no wikilink in the body names a relation
the typed fields do not declare."*
→ `manual`, reason names the exact human check.

Derived from the SR statement's *"mirrored as Obsidian wikilinks"*. **Not in HLR-02** — see
finding F-1.

### SR-002 — Requirement register closure
Source: `docs/superpowers/specs/2026-08-18-coherence-toolset-design.md#4.2`

The §4.2 anchor is a package-map table. The whole of its content for this SR is one table row:
*"| `coherence.register` | `factory.requirements` | the register and its closure model |"*. See
finding F-2 on anchor thinness. Its two nouns — *the register*, *its closure model* — plus the
register's `index` verb named in the same design's §5 CLI surface give three criteria.

**AC-1** — *"Requirements are parsed from their authoritative Markdown files into a register
ordered by requirement id, and a lookup for an id the register does not hold returns nothing rather
than a fabricated entry."*
→ `test_marker` → `tests/unit/requirements/test_register.py`

**AC-2** — *"The register emits an index naming every requirement with its checksum, and a
requirement carrying no binding is indexed as proposed with a null checksum and its file left
byte-identical."*
→ `test_marker` → `tests/unit/requirements/test_cli.py`

**AC-3** — *"The closure model assigns each requirement exactly one state, and a requirement that no
measurement, linked task or deferral accounts for is reported as pending with a gate-failing
severity rather than passing silently."*
→ `test_marker` → `tests/unit/requirements/test_closure.py`

### SR-003 — Spec frontmatter as spec nodes
Source: `…toolset-design.md#10`, the **Specs (TN-05)** bullet:
*"Specs (TN-05) gain `id`/`title`/`status` frontmatter and a `spec:` node kind, so `plan_no_spec`
stops depending on a regex over a literal path and a spec becomes answerable to 'do requirements
cover this'."*

**AC-1** — *"A spec carrying id, title and status frontmatter is loaded as a canonical spec node
addressed by its declared id."* (from *"gain `id`/`title`/`status` frontmatter and a `spec:` node
kind"*)
**AC-2** — *"A plan's reference to a spec resolves to that spec's canonical frontmatter id and never
to an id derived from the spec's file name, whether the reference is a frontmatter field or a
literal path in the body."* (from *"stops depending on a regex over a literal path"*)
**AC-3** — *"Two specs declaring the same id with differing content raise a deterministic load error
instead of one silently winning."* (from the SR statement, **not** from §10 — finding F-3)

All three → `test_marker` → `tests/unit/coherence/test_artifact_families.py`

### SR-004 — Single code map with import edges
Source: `…toolset-design.md#9.1`

**AC-1** — *"The import-edge layer persists its edges beside the fingerprinted code index and
requirement coverage computes overlap from that single map, with the former private import walker
reduced to a re-export shim."*
→ `test_marker` → `tests/unit/substrate/test_codemap_imports.py`
Source: *"The merged module keeps the index's engine and fingerprint and adds an import-edge layer;
`coherence.audit` computes overlap from it"*, against *"`factory.coverage.imports` … a second
parser, Python-only, with no freshness model."*

**AC-2** — *"A selection naming a missing or renamed binding test is reported as a distinct
unresolved outcome, never as a resolved selection that happens to overlap nothing."*
→ `test_marker` → `tests/unit/substrate/test_codemap_imports.py`
Source: *"a missing or renamed binding test becomes a distinct finding instead of being
indistinguishable from 'this test genuinely touches nothing' — the failure mode `compute_overlap`
has today."*

**AC-3** — *"Requirement coverage computes import overlap for every language the code index parses,
not for Python alone."*
→ `manual`
Source: *"the audit gains whatever languages the index parses"*. **This is currently unmet** — see
finding F-4. I authored it deliberately as a criterion the system fails today rather than omitting
it, because omitting a source-required property because the code does not do it is precisely the
"criteria describe what was built" defect this slice removes.

### SR-005 — Course traceability check
Source: `…toolset-design.md#10`, the **Courses (TN-04, TN-12)** bullet.

**AC-1** — *"A course note declaring an id the trace graph does not hold fails the check, whether
the id appears in the traceability frontmatter block or as a wikilink in the note body."*
Source: *"A coherence check resolves every id a note declares — both the `traceability:`
frontmatter block and any `[[wikilink]]` in the body — against the trace graph, failing on an
unknown id"*.

**AC-2** — *"The check reports every requirement and spec node that no course note reaches, and
reports failure when that set is non-empty."*
Source: *"the check also reports requirements and specs that no course note reaches, which is the
graph view the notes exist to give."*

**AC-3** — *"The drift snapshot is emitted as command output, exiting non-zero when a declared id is
unknown and zero with an empty unreached list when every declared id resolves and every node is
reached."*
Source: *"emits the drift snapshot as command output rather than a hand-edited file beside the
notes."*

All three → `test_marker` → `tests/unit/coherence/test_course.py`

### SR-006 — Test-to-requirement markers
Source: `…toolset-design.md#10`, the **Tests (TN-07)** bullet:
*"Tests (TN-07) gain `@pytest.mark.sr(\"SR-032\")`, collected into the register, with a gate that
fails when a bound SR's `experiment` names a file carrying no matching marker."*
Reinforced by §11's Increment 8 gate row: *"a bound SR with an unmarked test fails the gate"*.

**AC-1** — *"SR markers are collected from a test file by exact requirement-id string, without
importing the module and without normalising case, and unrelated decorators are ignored."*
**AC-2** — *"A bound requirement whose experiment names an existing Python test file carrying no
matching SR marker produces a closure finding whose severity fails the gate."*

Both → `test_marker` → `tests/unit/coherence/test_register_markers.py`. AC-2 is only *partly* met —
finding F-5.

### SR-007 — Knowledge base signature retrieval
Source: `…toolset-design.md#9.2`, defects TN-14 and TN-15.

**AC-1** — *"A knowledge-base entry scoped only by error signature is selected and reaches the agent
prompt when a real gate failure produces a matching signature, and is not selected when the failure
signature does not match or no gate failed."*
→ `test_marker` → `tests/unit/orchestrator/test_runner.py`
Source (TN-14): *"`select_entries` implements `sig_hit` against an entry's
`scope.error_signatures`; its only caller passes an empty list, so selection is file-glob-only in
practice. The fix is a caller change plus a signature source: gate output and node failure snippets
already contain the strings."* The SR's own *"so failure records built for retrieval actually
fire"* is what forced binding to the **caller** rather than to the matcher.

**AC-2** — *"A knowledge-base entry scoped only by a qualified symbol is selected when the changed
files reach that symbol through import edges, with no file-glob match, and a stale or missing code
map yields a diagnostic rather than a silent file-glob fallback."*
→ `test_marker` → `tests/unit/test_kb_retrieval.py`
Source (TN-15): *"an entry's scope can name a symbol or module and fire when the changed files
actually *reach* it, instead of matching a path pattern."*

### SR-050 — Per-requirement implementation traceability review
Source: `docs/superpowers/specs/2026-08-31-sr-code-validation-traceability-design.md#canonical-relations`

All three criteria are `manual`. Nothing in this SR is implemented — see finding F-6.

**AC-1** — *"Each requirement an implementation slice changes carries typed implementation and
validation references whose repository-relative paths resolve inside the project and whose symbol or
pytest node identifiers resolve to real definitions, with no line number used as identity."*
Source (Canonical relation model, rules 1–3 and the Decision summary): *"1. `path` is
repository-relative and must resolve inside the project. 2. `symbol` identifies a production
definition where symbol indexing supports it. 3. `test` is an optional pytest node ID"*; *"It does
not use line numbers as identity."*

**AC-2** — *"The per-requirement review reports structural coverage, evidence integrity and semantic
fidelity findings as separate categories, naming missing, dangling, weak and overstated links
distinctly rather than merging them into one verdict."*
Source (Review agents): the three named reviewers, and the Fidelity reviewer's list *"overstated
links; links to incidental helpers rather than behavior owners; tests that cover only a weaker
subset…"*. **Outside the cited anchor** — finding F-7.

**AC-3** — *"An agent's relation-review verdict does not close a requirement until the required gate
records a human decision covering that requirement."*
Source (Out of scope): *"allowing an LLM to silently approve an unresolved fidelity finding"*, and
(Workflow placement): *"A task cannot be marked complete merely because tests pass."* **Outside the
cited anchor** — finding F-7.

---

## 2. Findings — where source, statement and code disagree

**F-1 (SR-001, statement beyond source).** SR-001's statement requires relations *"mirrored as
Obsidian wikilinks"*. HLR-02 says nothing about wikilinks or about any rendering; it requires only
that traceability *"be based on explicit declared relations"*. The wikilink obligation is imported
from the 2026-08-31 design, which itself states (line 21) that SR-001 *"is clarified to include
explicit production and validation relations"*. The clarification is legitimate but the `source:`
anchor no longer covers the whole statement. Recorded, not reconciled: AC-3 states the wikilink
obligation and is honestly marked `manual`.

**F-2 (SR-002, anchor too thin).** §4.2 is a package-map table. Its entire content bearing on
SR-002 is the row *"the register and its closure model"*. It does not contain the words *proposed*,
*measured*, *accounted*, *index*, *deferral*, or *SR*/*BR node*. Every specific noun in SR-002's
statement comes from elsewhere in the same document (§5 CLI surface for `index`, §6.2 and §8 for
*proposed* and *deferral*) or from nowhere in it. A better anchor would be §5 plus §8, or the SR
should carry no anchor claim it cannot support.

**F-3 (SR-002, statement contradicts its own source document).** SR-002's statement says the
register is maintained *"over SR and BR nodes"*. §10 of the same design says the opposite:
*"Business requirements remain referenced (`upstream: [BR-002]`) and unmodelled. … a `BR-*` tier is
explicitly out of scope here."* The code agrees with §10 — `load_register` globs `SR-*.md` only
(`src/coherence/register/register.py`). **The statement is wrong, not the code.** I did not change
the statement (out of scope) and I did not write a criterion asserting BR nodes are registered,
because that would either fail permanently against an out-of-scope demand or, worse, invite a later
implementation of a feature the design explicitly excluded. Recommend a follow-up task to strike
*"and BR"* from SR-002's statement.

**F-4 (SR-003, statement beyond source).** SR-003's statement requires *"failing deterministically
on duplicate ids with differing content"*. That clause appears nowhere in §10, nor anywhere else in
the toolset design (I grepped the whole document for `duplicate`). The behaviour exists in the code
and is tested; the requirement for it does not come from the cited source. AC-3 is derived from the
statement and I say so above.

**F-5 (SR-004, source promise unmet by the code).** §9.1 promises *"the audit gains whatever
languages the index parses."* The signature index parses python, javascript, typescript, tsx and
rust (`src/substrate/codemap/sigs.py` `_TS_LANG_BY_EXT`), but the import-edge layer returns status
`unsupported` for any non-Python root, deliberately —
`tests/unit/substrate/test_codemap_imports.py::test_build_import_closure_non_python_root_is_unsupported`
asserts it with the comment *"a parser existing elsewhere in the codebase (tree-sitter, for
signatures) must not make this layer claim a transitive closure it never walked."* The code's
caution is right; the design's claim is unmet. SR-004's *"across the supported languages"* is
therefore aspirational today. Recorded as SR-004 AC-3, `manual`, currently **failing**.

**F-6 (SR-006, source demands unconditional gating; code gates only under one profile).** §10 says
*"a gate that fails when a bound SR's `experiment` names a file carrying no matching marker"*, and
§11 Increment 8 repeats *"a bound SR with an unmarked test fails the gate"* — both unconditional.
`verify_sr_marker` maps the compiled `test_marker` requiredness to a severity: `blocking` →
BLOCKING (gate-failing) only under the `high_assurance` profile; under the default `prototype`
profile the requiredness is `required` → WARNING, which
`tests/unit/coherence/test_register_markers.py::test_a_bound_sr_without_the_marker_is_required_under_the_default_profile`
explicitly asserts is **not** in `GATE_FAILING_SEVERITIES`. So on this repo's default profile an
unmarked bound SR does not fail the gate. SR-006 AC-2 states the source's demand; its binding
verifies only the `high_assurance` half. Stated here rather than reconciled.

**F-7 (SR-050, entirely unimplemented; anchor too narrow).** Two parts.
*Unimplemented:* typed `implemented_by` / `verified_by` references on a requirement do not exist
anywhere in `src/` (grep confirms; the existing `verified_by` edge kind in
`src/coherence/trace/model.py` links features and plans to tasks and runs, not requirements to
production symbols or test nodes). No structural, fidelity or evidence-reconciliation reviewer
exists under `src/coherence/`. And the gating half cannot presently succeed either: the compiled
`human_review` obligation hard-codes `reviewed = False` (`src/coherence/policy/compiler.py:235`),
so it can never reach satisfied however the review went, and its `requiredness` is
`not_applicable` outside the `high_assurance` profile (`compiler.py:236`), so nothing requires the
decision at all. All three criteria are therefore `manual`, and all three currently fail.

**Correction (review round 1).** An earlier version of this finding, and of SR-050 AC-3's `manual`
reason, claimed that `ITEM_ID_PREFIXES` in `src/coherence/gate/model.py` has no `sr:` prefix. **That
was false.** `model.py:41-48` contains `"sr:"`, and it was already present at this task's base
commit `2996613`. I carried the claim over from the reconnaissance file's §4 without checking it
against the file, which is exactly the failure the task's authoring rule is meant to prevent — and
it mattered more here than anywhere else in this diff, because a `manual` criterion's `reason` is
its entire evidence, so a false premise there is the cheapest possible route to a counted SR.
Corrected in `requirements/SR-050.md` and in §5 item 3 below; the two remaining claims
(`reviewed = False`, and `not_applicable` outside `high_assurance`) were each verified against the
source file this round.
*Anchor:* the `#canonical-relations` anchor covers only the typed-relation model (AC-1). The review
contract that gives SR-050 its title lives in `## Review agents`, `## Workflow placement` and
`## Out of scope`. The anchor understates the SR's own scope; it should name those sections too.

**F-8 (brief's binding table, three entries wrong).** See §4.

---

## 3. Judgement on the shared `#10` anchor (SR-003 / SR-005 / SR-006)

**§10 genuinely contains three separable requirements; the anchor grain is too coarse to
distinguish them.** Both halves matter.

§10 "Artifact families currently uncovered" is a list of four bullets, each naming a distinct
artifact family and its own tracking numbers: Specs (TN-05), Courses (TN-04, TN-12), Tests
(TN-07), and Business requirements (explicitly out of scope). SR-003 maps onto bullet 1, SR-005
onto bullet 2, SR-006 onto bullet 3 — one to one, with no overlap and no residue. The section is
not one requirement three SRs are slicing; it is four requirements in one section.

But `#10` as written points at all four. A reader given only `source: …#10` cannot tell which
bullet an SR derives from without reading the SR statement back into the source, which inverts the
direction of traceability the anchor exists to provide, and makes it impossible to detect that a
change to the Courses bullet should stale SR-005 and only SR-005. The section also silently
contains the sentence that contradicts SR-002 (finding F-3), so `#10` is simultaneously the source
of three SRs and the refutation of a fourth.

**Recommendation:** give §10 sub-anchors per family — the TN ids already exist and are stable, so
`#10-TN-05`, `#10-TN-04`, `#10-TN-07` cost nothing and are unambiguous. I did not make that change:
editing an SR's `source:` is out of scope for this task, and re-anchoring should change the design
document's headings and all citing SRs in one move.

---

## 4. Binding confirmations — every `ref` was read

| SR/AC | ref | Read? | Verifies the criterion? |
|---|---|---|---|
| SR-001/AC-1 | `tests/unit/system/test_feature.py` | yes | **Yes.** `test_feature_context_contains_only_connected_recorded_facts` asserts the returned dossier's `requirements`, `design_records` (ADR + plan + spec), `implementation` (task → run → changed_files), `verification` (per-SR state + stale), `goal_ids`, `metric_ids` and `latest_simulation_evidence` — HLR-02's chain minus *business intent*. The fixture plants a malformed `FEAT-BROKEN.md` that must not appear, which is the "no invented artifact" half. `test_feature_context_never_treats_missing_validation_as_a_pass` in the same file reinforces it. |
| SR-001/AC-2 | `tests/unit/system/test_vcycle_health.py` | yes | **Yes.** `test_requirement_without_test` → `REQ_NO_TEST`, `test_requirement_without_implementation` → `REQ_NO_IMPLEMENTATION`, `test_implementation_without_traceable_requirement` → `IMPL_NO_REQ`, each asserted as a named finding; `test_satisfied_and_validated_requirement_has_no_finding` is the negative control. |
| SR-001/AC-3 | — | n/a | `manual`; no automated coverage exists (F-1). |
| SR-002/AC-1 | `tests/unit/requirements/test_register.py` | yes | **Yes.** `test_load_register_and_get` asserts id-ordered load and that `get_requirement(reqs, "SR-999")` returns `None`. |
| SR-002/AC-2 | `tests/unit/requirements/test_cli.py` | yes | **Yes.** `test_index_stamps_checksums_and_writes_index` asserts the written `index.json` equals the returned result with a `sha256:` checksum; `test_index_leaves_a_proposed_requirement_untouched` asserts the file is byte-identical and the entry is `{"checksum": None, "proposed": True}`. |
| SR-002/AC-3 | `tests/unit/requirements/test_closure.py` | yes | **Yes.** `test_an_unbound_requirement_with_no_disposition_is_pending` asserts `PENDING` **and** `severity is FreshnessSeverity.BLOCKING`; `test_no_result_and_no_task_is_pending`, `test_a_deferral_wins_over_pending_but_not_over_a_real_result` and `test_healthy_states_carry_no_severity` cover the one-state-per-requirement partition. |
| SR-003/AC-1..3 | `tests/unit/coherence/test_artifact_families.py` | yes | **Yes, all three.** AC-1 → `test_frontmatter_spec_emits_the_canonical_spec_node` (+ `test_graph_emits_spec_node_for_frontmatter_spec`). AC-2 → `test_plan_edges_target_the_canonical_spec_id` and `test_a_plan_body_reference_resolves_to_the_canonical_spec_id`, the latter asserting `not any(dst == "spec:coherence.md" …)` — exactly the "never a filename-derived id" clause. AC-3 → `test_duplicate_spec_ids_with_differing_content_fail_deterministically`, which raises `SpecError` matching `duplicate`. |
| SR-004/AC-1 | `tests/unit/substrate/test_codemap_imports.py` | yes | **Yes.** `test_build_import_closure_persists_edges_beside_fingerprinted_index` asserts the `*.imports.json` sits in the same `.factory/code-index` dir as the fingerprinted index; the four `test_converted_codemap_overlap_matches_factory_coverage_imports_*` parity cases assert the single map returns the old walker's answers; `test_factory_coverage_imports_shim_warns_naming_substrate_codemap_imports` and `..._reexports_edge_and_overlap_types` assert the old walker is now a shim. |
| SR-004/AC-2 | `tests/unit/substrate/test_codemap_imports.py` | yes | **Yes.** `test_compute_overlap_distinguishes_selection_missing_from_no_overlap` asserts `missing.test_source is None` versus `no_overlap.test_source is not None` with `overlap == ()`; `test_build_import_closure_renamed_binding_fixture_is_unresolved` asserts `status == "unresolved"` with the renamed module named in the diagnostics. |
| SR-004/AC-3 | — | n/a | `manual`; currently **failing** (F-5). |
| SR-005/AC-1 | `tests/unit/coherence/test_course.py` | yes | **Yes.** `test_fails_on_unknown_frontmatter_id` asserts the error names `SR-9999` *and* `traceability`; `test_fails_on_unknown_body_token` asserts the error names `SR-9999` *and* `[[`. Both channels, as the source requires. |
| SR-005/AC-2 | `tests/unit/coherence/test_course.py` | yes | **Yes.** `test_reports_unreached_known_nodes` asserts `report.unreached >= {"SR-002", "spec:beta"}` with `report.ok is False` and no `unknown` error — i.e. unreached is reported independently of unknown-id failure. |
| SR-005/AC-3 | `tests/unit/coherence/test_course.py` | yes | **Yes.** `test_unknown_frontmatter_id_cli_exit_1` asserts exit 1 with JSON on stdout; `test_clean_cli_exits_zero_and_emits_empty_unreached` asserts exit 0, `ok is True`, `unreached == []`. Note: no test asserts the *absence* of a hand-edited file beside the notes, so I worded AC-3 as what is actually checked (output + exit code) rather than as the source's negative. |
| SR-006/AC-1 | `tests/unit/coherence/test_register_markers.py` | yes | **Yes.** `test_collect_markers_matches_the_sr_id_string_exactly` asserts `SR-0042` and `sr-0042` stay distinct; `test_collect_markers_ignores_unrelated_decorators`; the module is AST-parsed, never imported (`src/coherence/register/markers.py`). |
| SR-006/AC-2 | `tests/unit/coherence/test_register_markers.py` | **partly** | `test_a_bound_sr_without_the_marker_is_blocking_under_the_high_assurance_profile` asserts `finding.severity in GATE_FAILING_SEVERITIES` — that *is* the criterion, but only under `high_assurance`. The sibling default-profile test asserts the opposite outcome for `prototype`. Stated as F-6 rather than reconciled; the criterion keeps the source's wording so it can fail. |
| SR-007/AC-1 | `tests/unit/orchestrator/test_runner.py` | yes | **Yes.** A signature-only KB entry is planted; a real unit-gate failure emitting `ConnectionResetError: connection reset by peer` puts `kb-0002` and its body into the *second* dev prompt but not the first; `test_nonmatching_failure_signature_never_selects_the_entry` and `test_successful_gate_adds_no_signature_and_no_entry` are the two negative controls the criterion's second clause needs. |
| SR-007/AC-2 | `tests/unit/test_kb_retrieval.py` | yes | **Yes.** `test_select_entries_matches_moved_symbol_via_reachable_symbols` uses `_write_symbol_kb`, an entry scoped *purely* by `factory.module.function` with no `files` glob, and asserts it is selected when the edited `client.py` reaches that symbol; `test_select_entries_stale_codemap_diagnostic_and_no_file_glob_fallback` and `..._missing_codemap_diagnostic_and_no_symbol_hit` cover the diagnostic clause; `test_select_entries_symbol_match_is_exact_qualified_name` covers exactness. |
| SR-050/AC-1..3 | — | n/a | all `manual`; nothing exists to bind to (F-7). |

### Where I departed from the brief's indicative table, and why

- **SR-001 → `tests/unit/coherence/test_snapshot_navigation.py`: rejected.** I read it. Its four
  tests are about *navigation-snapshot freshness* for a scope ref (fresh vs stale, resolver_cmd,
  machine-readable stale report, and a no-`factory`-import architecture assertion). It never
  traverses a lifecycle relation. Binding SR-001 to it would have been exactly the stretched
  binding the brief warns against. I bound to `test_feature.py` and `test_vcycle_health.py`
  instead, both read and both genuinely verifying an HLR-02 sentence.
- **SR-007 → `tests/unit/substrate/test_kb_signatures.py` + `tests/unit/test_kb_index.py`:
  rejected.** `test_kb_signatures.py` tests `extract_signatures` — the signature *source*, i.e. one
  half of TN-14's fix, not selection; `test_kb_index.py` tests index building. Neither verifies
  *"entries be selected by error-signature"*. The selection behaviour lives in
  `tests/unit/test_kb_retrieval.py` (symbol scope) and, for the caller change that makes TN-14 real,
  `tests/unit/orchestrator/test_runner.py`. Both read, both bound.
- **SR-002 → `tests/unit/requirements/test_register.py` only: extended.** That file covers parsing
  and load, not the index or the closure model. Added `test_cli.py` and `test_closure.py`.
- **SR-003's suggested third criterion ("missing frontmatter degrades to filename node"): dropped.**
  §10 does not require a legacy-degrade path; it is an implementation courtesy. Writing it as an
  acceptance criterion would be deriving from the code.
- **SR-004 → `test_codemap_resolver.py`: not used.** That file is about code-map snapshot
  staleness/lineage, not about merging symbols with import edges. `test_codemap_imports.py` alone
  carries both criteria.

---

## 5. How SR-001 and SR-050 were handled, and what remains an honest gap

**SR-001.** The brief expected no adequate existing test. That is true of the *suggested* test, and
true of the wikilink clause. It is **not** true of two of HLR-02's four sentences: the lifecycle
chain is genuinely exercised by `test_feature.py`, and gap-surfacing by `test_vcycle_health.py`. I
read both in full before binding; neither is a stretch. The honest gap is AC-3, the wikilink
mirroring, which has no reader anywhere in `src/` and is recorded as `manual` with a precise human
check. SR-001 counts toward `requirement_quality` on AC-1 and AC-2, which resolve to real `.py`
files.

**SR-050.** Nothing in this SR is implemented (F-7). I bound none of it to a test. All three
criteria are `manual`, each with a reason that names what a human must check *and* why no automated
test can exist yet. SR-050 therefore counts toward `requirement_quality` on the strength of a
resolvable `manual` binding — which is correct: the dimension measures whether a requirement is
*well formed and checkable*, not whether it is *satisfied*. SR-050 remains, and should remain,
unsatisfied. Its honest gaps, in order of what would unblock them:
1. no typed `implemented_by` / `verified_by` relation model on requirements;
2. no structural / fidelity / evidence-reconciliation reviewer;
3. a hard-coded `reviewed = False` on the `human_review` obligation, plus `not_applicable`
   requiredness outside `high_assurance`, so even the gating half of the SR cannot presently
   succeed. (The gate decision model *does* accept an `sr:` item-id prefix — see the correction in
   F-7; an earlier version of this report claimed otherwise and was wrong.)

---

## 6. Verification output

**(1) All 55 SRs still load.** Run after each file and again at the end.

```
$ rtk proxy uv run python -c "... load_register(Path('requirements')) ..."
loaded 55
SR-001 ['AC-1:test_marker', 'AC-2:test_marker', 'AC-3:manual']
SR-002 ['AC-1:test_marker', 'AC-2:test_marker', 'AC-3:test_marker']
SR-003 ['AC-1:test_marker', 'AC-2:test_marker', 'AC-3:test_marker']
SR-004 ['AC-1:test_marker', 'AC-2:test_marker', 'AC-3:manual']
SR-005 ['AC-1:test_marker', 'AC-2:test_marker', 'AC-3:test_marker']
SR-006 ['AC-1:test_marker', 'AC-2:test_marker']
SR-007 ['AC-1:test_marker', 'AC-2:test_marker']
SR-050 ['AC-1:manual', 'AC-2:manual', 'AC-3:manual']
with acceptance: 8

$ rtk proxy uv run coherence register index | grep -c '"id"'
55
```

**(2) `requirements/index.json` unchanged.**

```
$ git diff --stat requirements/index.json
(no output)
```

`content_checksum` hashes only `statement` + the binding fields, so adding `acceptance:` perturbs
nothing. Confirmed empirically, not just by reading the code.

**(3) Test suites pass.**

```
$ rtk proxy uv run pytest tests/unit/requirements/ tests/unit/coherence/ -q
720 passed, 1 skipped, 27 warnings in 72.76s (0:01:12)
```

**(4) `requirement_quality`.**

Before:
```
$ rtk proxy uv run coherence navigate health --json | grep -A4 requirement_quality
      "name": "requirement_quality",
      "satisfied": 0,
      "expected": 55,
      "exempt": 0
```

After:
```
$ rtk proxy uv run coherence navigate health --json | grep -A4 requirement_quality
      "name": "requirement_quality",
      "satisfied": 8,
      "expected": 55,
      "exempt": 0
```

**0/55 → 8/55.** All eight SRs count, and the number matches exactly the number of SRs authored —
no SR failed to count. Each of the eight carries at least one criterion whose binding resolves
under `_has_resolvable_acceptance`: SR-002/003/004/005/006/007 and SR-001 via existing `.py` files
inside the project root; SR-050 via `manual`, which is resolvable as authored. The remaining 47 SRs
have no criteria and correctly do not count.

Worth stating plainly: **8 counting is not 8 satisfied.** SR-004/AC-3 and all three SR-050 criteria
describe behaviour the system does not have. That is the intended state — the requirements are now
able to fail, which they could not do yesterday.

---

## 7. Self-review

I re-read the whole diff asking, per criterion, *could this ever fail?*

- Every `test_marker` criterion names an outcome an implementation change could break: delete a
  gap code and SR-001/AC-2 fails; make duplicate spec ids last-write-wins and SR-003/AC-3 fails;
  let `compute_overlap` collapse missing-selection into empty-overlap and SR-004/AC-2 fails; pass
  an empty signature list from the runner again and SR-007/AC-1 fails. None is a restatement of
  "the code does what the code does".
- Every `manual` criterion is currently **unmet** (SR-001/AC-3 partially — the mirroring convention
  exists by hand in `docs/features/FEAT-001.md` but nothing enforces it; SR-004/AC-3 and all of
  SR-050 outright). A criterion that already fails cannot be a tautology.
- I read every file named in a `ref:`. Three of the brief's nine suggested paths did not verify the
  criterion and were replaced (§4). None of the replacements is a file I merely assumed the content
  of.
- Two wordings I softened to avoid over-claiming beyond what the bound test actually asserts:
  SR-005/AC-3 (states output + exit code, not the source's "rather than a hand-edited file", which
  no test checks) and SR-002/AC-3 (the "exactly one state" clause is verified by the partition of
  cases across `test_closure.py`, not by a single assertion).

## 8. Concerns

1. **F-3 is the one I would escalate.** SR-002's statement asserts a scope its own source document
   explicitly excludes. It is out of scope for me to fix, and it means SR-002 can never be fully
   satisfied as stated. A follow-up should strike *"and BR"*.
2. **SR-006/AC-2 is a partial binding by construction** (F-6). It is honest — the criterion states
   the source's demand and the test verifies one profile — but a reviewer should decide whether the
   right resolution is to tighten the code to gate under `prototype` too, or to amend §10 to say
   the gating is profile-dependent. Either way SR-006 is not currently satisfiable on this repo's
   default profile.
3. **`manual` criteria count toward `requirement_quality` unconditionally.** That is T-2's rule
   (R-8) and I relied on it for SR-050. It is defensible for a *quality* dimension, but it does
   mean an SR can reach 1/1 on requirement_quality with three criteria nothing can check. If the
   dimension is later read as a proxy for assurance rather than for well-formedness, SR-050 will
   look better than it is. Worth a note wherever the dimension is surfaced.
4. **I authored two criteria the system currently fails** (SR-004/AC-3, and effectively all of
   SR-050). If the project's convention is that acceptance criteria describe only agreed-and-built
   behaviour, these should be moved to a backlog instead. I judged the opposite — that a
   requirement which cannot fail is the defect — but the call is worth confirming.
5. The worktree also carries an unrelated pre-existing modification to
   `docs/superpowers/plans/2026-09-01-feat001-reference-run.md`. I did not touch it and did not
   include it in my commit.

---

## 9. Commit

`682cc8b feat(requirements): author acceptance criteria for the eight FEAT-001 SRs`
— the eight `requirements/SR-*.md` files only. This report is not in the commit:
`.superpowers/` is gitignored in this repo, so it lives in the worktree only.

---

# 10. Fix report — review round 1

Three Important findings plus two folded-in cleanups and an arithmetic correction. All addressed;
none disputed. Where a finding named a false claim of mine I verified the correction against the
source file this round rather than against the recon notes — that mis-step is what produced
Important 1 in the first place.

## Important 1 — SR-050/AC-3's `manual` reason contained a false claim

**Verified the finding first.** `src/coherence/gate/model.py:41-48` does contain `"sr:"`, and
`git show 2996613:src/coherence/gate/model.py` shows it was already there at my base commit. The
reviewer is right and my claim was wrong; I had carried it from recon §4 without checking the file.
The other two claims in the reason hold and I re-verified both:
`src/coherence/policy/compiler.py:235` is `reviewed = False`, and `:236` is
`requiredness = "blocking" if profile == "high_assurance" else "not_applicable"`.

`requirements/SR-050.md` AC-3 reason, final text:

> No automated coverage is possible today: the compiled human_review obligation hard-codes its
> reviewed field to false, so the obligation can never reach satisfied however the review went, and
> outside the high_assurance profile its requiredness is not_applicable, so nothing requires the
> decision at all. A human must confirm that any slice claiming a relation review for a requirement
> carries a corresponding gate decision authored by a person, and must refuse to treat the agent
> verdict alone as closure.

Also corrected in this report at §2 F-7 (with an explicit correction note naming what was wrong and
why it mattered) and at §5 item 3.

## Important 2 — SR-006/AC-2 booked a file-level green for a property the system lacks

Split, per the brief's stated order of preference. AC-2 now carries the profile scope its binding
actually verifies; the unconditional demand §10 and §11 make is stated as its own criterion, marked
`manual`, and currently fails.

`requirements/SR-006.md`, final text:

> **AC-2** — Under the high_assurance profile, a bound requirement whose experiment names an
> existing Python test file carrying no matching SR marker produces a closure finding whose severity
> fails the gate. → `test_marker` → `tests/unit/coherence/test_register_markers.py`
>
> **AC-3** — A bound requirement whose experiment names a file carrying no matching SR marker fails
> the gate under every profile, not only under high_assurance. → `manual`, reason: *No automated
> coverage, and the behaviour is absent under this repository's default profile. The compiled
> test_marker requiredness is blocking only under high_assurance; under the default prototype
> profile it is required, which maps to a WARNING severity that is not gate-failing, and the bound
> test file asserts exactly that non-gating outcome. Until the profile gap is closed, or the source
> design is amended to state that the gating is profile-dependent, a human must inspect every bound
> requirement whose experiment file carries no matching marker and decide it explicitly, because no
> gate will stop it.*

This is the right shape: F-6 is now expressed in the register itself as a failing criterion, not
only as prose in a report nobody's gate reads.

## Important 3 — three criteria carried clauses lifted from the bound test

All three clauses dropped. I did not attempt to re-derive any of them from a source sentence,
because in each case I checked and there is no such sentence — the reviewer's reading is correct.

| File | Was | Now |
|---|---|---|
| `SR-006.md` AC-1 | "SR markers are collected from a test file by exact requirement-id string, **without importing the module and without normalising case, and unrelated decorators are ignored**." | "A test carrying an SR marker is collected into the register under the requirement id that marker names." |
| `SR-002.md` AC-2 | "…indexed as proposed **with a null checksum and its file left byte-identical**." | "The register emits an index naming every requirement with its checksum, and a requirement carrying no binding is indexed as proposed rather than stamped with one." |
| `SR-007.md` AC-2 | "…with no file-glob match, **and a stale or missing code map yields a diagnostic rather than a silent file-glob fallback**." | "A knowledge-base entry scoped only by a qualified symbol is selected when the changed files reach that symbol through import edges, with no file-glob match." |

SR-006/AC-1 was the clearest instance and I agree with that assessment: §10 says only *"collected
into the register"*, and my three extra clauses were a transcription of
`test_register_markers.py:101`, `:116` and the AST implementation. The rewritten criterion states
what §10 requires and nothing more; it still fails if collection ever stops keying on the marker's
declared id.

## Folded-in cleanups

- **`SR-002.md` AC-3** — dropped the type-level tautology. `classify` returns one `ClosureFinding`
  with one `state` by construction, so "assigns each requirement exactly one state" cannot fail and
  no test asserts the partition. Final: *"A requirement that no measurement, linked task or deferral
  accounts for is reported as pending with a gate-failing severity rather than passing silently."*
  Still verified by `test_closure.py::test_an_unbound_requirement_with_no_disposition_is_pending`,
  which asserts `severity is FreshnessSeverity.BLOCKING`.
- **`SR-004.md` AC-1** — dropped the shim clause. Agreed that "the former private import walker
  reduced to a re-export shim" is a §4.3 migration artifact, not a property of SR-004, and cannot be
  verdicted separately from the rest of the id. Final: *"Requirement coverage computes import
  overlap from a single merged code map whose import edges are persisted beside the same
  fingerprinted symbol index, not from a second parser of its own."* — one claim, matching §9.1's
  *"The merged module keeps the index's engine and fingerprint and adds an import-edge layer;
  `coherence.audit` computes overlap from it"* and the SR statement's *"from a single parser"*.
  Verified by `test_build_import_closure_persists_edges_beside_fingerprinted_index` plus the four
  `test_converted_codemap_overlap_matches_factory_coverage_imports_*` parity cases.

## Arithmetic correction

My round-1 commit message and reply said "21 criteria (15 `test_marker`, 6 `manual`)". That was
wrong — the committed content was **22 (17 `test_marker`, 5 `manual`)**. I miscounted by hand
instead of counting the parsed register, which was available the whole time. Counted from
`load_register` this round, the **final** figures are:

| SR | criteria | test_marker | manual |
|---|---|---|---|
| SR-001 | 3 | 2 | 1 |
| SR-002 | 3 | 3 | 0 |
| SR-003 | 3 | 3 | 0 |
| SR-004 | 3 | 2 | 1 |
| SR-005 | 3 | 3 | 0 |
| SR-006 | 3 | 2 | 1 |
| SR-007 | 2 | 2 | 0 |
| SR-050 | 3 | 0 | 3 |
| **Total** | **23** | **17** | **6** |

23 criteria across 8 SRs — 17 `test_marker`, 6 `manual`, 0 `harness`. The one added criterion is
SR-006/AC-3; the change from 22 to 23 and from 5 to 6 `manual` is entirely that split.

## Verification (all four, `rtk proxy` prefixed)

**(1) All 55 SRs still load.**

```
$ rtk proxy uv run coherence register index | grep -c '"id"'
55

$ rtk proxy uv run python -c "... load_register(Path('requirements')) ..."
loaded 55
SR-001 3 ['test_marker', 'test_marker', 'manual']
SR-002 3 ['test_marker', 'test_marker', 'test_marker']
SR-003 3 ['test_marker', 'test_marker', 'test_marker']
SR-004 3 ['test_marker', 'test_marker', 'manual']
SR-005 3 ['test_marker', 'test_marker', 'test_marker']
SR-006 3 ['test_marker', 'test_marker', 'manual']
SR-007 2 ['test_marker', 'test_marker']
SR-050 3 ['manual', 'manual', 'manual']
TOTAL criteria 23 | test_marker 17 | manual 6 | harness 0
```

**(2) `requirements/index.json` unchanged.**

```
$ git diff --stat requirements/index.json
(no output)
```

**(3) Tests pass.**

```
$ rtk proxy uv run pytest tests/unit/requirements/ tests/unit/coherence/ -q
720 passed, 1 skipped, 27 warnings in 42.39s
```

**(4) `requirement_quality`.**

```
$ rtk proxy uv run coherence navigate health --json | grep -A4 requirement_quality
      "name": "requirement_quality",
      "satisfied": 8,
      "expected": 55,
      "exempt": 0
```

**Unchanged at 8/55, which is the expected result.** Splitting SR-006/AC-2 did not change its
count: `_has_resolvable_acceptance` short-circuits on the first resolvable binding, and SR-006 still
carries two `test_marker` criteria pointing at an existing in-root `.py` file. No SR stopped
counting. Nothing in this round removed a resolvable binding — the Important 3 edits shortened
criterion prose only, and the Important 2 edit *added* a criterion.

## Deferred minors — recorded, not fixed, per instruction

SR-001/AC-1 omitting *business intent* from HLR-02's chain (which should have been a numbered
finding rather than a table aside — noting it here so it is not lost); SR-005/AC-3 substituting an
exit-code contract for the source's *"rather than a hand-edited file beside the notes"* negative;
SR-050's `#canonical-relations` anchor not matching the actual heading `## Canonical relation
model`; the §10 sub-anchor recommendation from §3.

## Files changed this round

`requirements/SR-002.md`, `SR-004.md`, `SR-006.md`, `SR-007.md`, `SR-050.md`, and this report.
`SR-001.md`, `SR-003.md` and `SR-005.md` were not touched. No file under `src/` or `tests/` was
touched, no `@pytest.mark.sr` decorator added, no gate `DecisionFile` authored.

## Concerns after this round

The four concerns in §8 stand, with one amendment: **§8 concern 3 is now demonstrated rather than
hypothetical.** I wrote that a `manual` criterion's unconditional counting means an SR can reach
full `requirement_quality` on criteria nothing can check — and then produced exactly the failure it
predicts, by resting a `manual` reason on a premise I had not verified. The dimension counted
SR-050 at the time and would have kept counting it. Nothing in the tooling could have caught it;
only a human reading the reason did. That is worth carrying into FEAT-002: a `manual` binding is
only as good as the review of its `reason`, and there is currently no gate on that text at all.
