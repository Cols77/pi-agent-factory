# Coherence Increment 8: Artifact Families Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make specs, course notes, SR-marked tests, and symbol-scoped KB knowledge visible and verifiable through the coherence graph.

**Architecture:** Evolve trace nodes from filename-derived spec heuristics to frontmatter-authoritative spec nodes with legacy compatibility. Course Markdown remains authoritative and its checker emits a computed result rather than a new store. The register collects pytest SR markers only for test-file experiment bindings, reporting ambiguous command bindings as configuration findings. KB symbol scope uses the codemap reachability API and never falls back to glob matching while claiming a symbol match.

**Tech Stack:** Python 3.11+, frontmatter, regex/AST, pytest marker collection, substrate.codemap, pytest, Ruff, Pyright.

---

## Execution Coordination

- Prerequisites: Increment 2 trace/register and Increment 1C codemap. Progressive-assurance Task 6 additionally consumes this plan's Task 3 marker-closure contract, Increment 2B's compiler base, Increment 4's `verification_result` compiler addendum, and Increment 6's `human_review` compiler addendum; all four are prerequisites, not Task 6 deliverables. KB symbol reachability additionally follows Increment 4 codemap audit cutover.
- Parallel after graph/codemap contracts freeze: spec-node/course work, test-marker collector, and KB schema/retrieval fixtures.
- Serial: trace graph API before course reachability; codemap reachable_symbols before KB symbol selection; final trace/register/course/KB gate last.

## File Structure

**Create:** src/coherence/course/{__init__,parser,check,cli}.py, src/coherence/register/markers.py, tests/unit/coherence/{test_course,test_artifact_families,test_register_markers}.py, course/spec/codemap fixture directories.

**Modify:** src/coherence/trace/{model,graph,gaps,cli,write}.py, src/coherence/register/{register,closure,cli}.py, src/substrate/kb/{index,retrieval}.py, src/substrate/codemap/imports.py, src/substrate/schemas/kb_entry.schema.json, pyproject.toml, factory compatibility wrappers, current trace/register/KB tests.

### Task 1: Make specs frontmatter-authoritative trace nodes

- [ ] **Step 1: Write graph compatibility tests.**

Add specs with:

    ---
    id: SPEC-COHERENCE-001
    title: "Coherence"
    status: accepted
    ---

Assert graph emits spec:SPEC-COHERENCE-001 and plan/spec edges target it. Existing filename-only specs remain readable as legacy nodes with a diagnostic/migration hint. Assert duplicate IDs, missing required fields in a frontmatter spec, and a relation to unknown spec fail deterministically.

- [ ] **Step 2: Implement spec parsing and node migration.**

Extend coherence.trace model/graph/gaps to parse id/title/status, use canonical frontmatter spec refs, and retain filename-derived compatibility only for legacy files. Replace literal-path regex checks with node/edge checks. Keep link/unlink writers from rewriting an unrelated spec document.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/trace/test_model_nodes.py tests/unit/trace/test_model_edges.py tests/unit/trace/test_gaps.py tests/unit/coherence/test_artifact_families.py -q
    git add src/coherence/trace tests/unit/trace tests/unit/coherence/test_artifact_families.py
    git commit -m "feat(trace): model frontmatter spec nodes"

### Task 2: Add a Markdown-native course checker

- [ ] **Step 1: Write course parser/check tests.**

Create course fixture notes under docs/course with traceability frontmatter and body links. Assert coherence course check --json:

1. fails unknown frontmatter ID;
2. fails unknown [[ID]] token;
3. reports known SR/spec nodes unreached by every course note;
4. accepts multiple notes that jointly cover graph nodes;
5. reports malformed traceability input;
6. succeeds with a no-course empty-state report.

Use node IDs only inside wikilinks; titles/paths are rejected as ambiguous.

- [ ] **Step 2: Implement pure parse/check/CLI.**

Parser returns CourseNote(path, refs). check_course(root) builds the coherence trace graph, validates refs, computes unreached known SR/spec nodes, and returns a report without writing beside the notes. Add coherence course check --json to the group dispatcher. Do not build an HTML/classroom exporter.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_course.py tests/unit/trace -q
    git add src/coherence/course src/coherence/cli.py tests/unit/coherence/test_course.py tests/fixtures
    git commit -m "feat(coherence): check Markdown course traceability"

### Task 3: Require SR markers for path-bound experiments

- [ ] **Step 1: Write marker collector tests.**

Use test modules containing:

    @pytest.mark.sr("SR-032")
    def test_example(): ...

Assert multiple markers and duplicate marker text reduce to a set per file. A bound SR whose experiment resolves to a .py test file with no matching marker is a blocking finding. An experiment that is a command/non-file creates an explicit configuration finding, not a guessed marker result.

- [ ] **Step 2: Implement collector and closure integration.**

Create coherence.register.markers.collect_markers(path) using AST or pytest collection without executing tests. Extend closure/check to verify only resolvable test-file experiment paths. Add the sr marker declaration to pyproject.toml. Preserve proposed/unbound requirement behaviour.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/requirements/test_register.py tests/unit/requirements/test_closure.py tests/unit/requirements/test_cli.py tests/unit/coherence/test_register_markers.py -q
    git add src/coherence/register pyproject.toml tests/unit/requirements tests/unit/coherence/test_register_markers.py
    git commit -m "feat(register): verify SR test markers"

### Task 4: Select KB entries by reachable symbols

- [ ] **Step 1: Write symbol-scope tests.**

Add a KB entry with:

    scope:
      symbols: ["factory.module.function"]

Move that symbol to another file in a codemap fixture while an edited file reaches it through imports. Assert select_entries finds the entry via reachable_symbols. Assert unknown/missing/stale codemap returns a staleness diagnostic and does not claim a symbol hit; legacy files/signatures still work.

- [ ] **Step 2: Extend schema and retrieval.**

Add scope.symbols to the KB schema and index payload. Expose:

    reachable_symbols(repo_root, changed_files) -> ReachabilityResult
    select_entries(kb_dir, touched_files, signatures, reachable_symbols=())

Match canonical qualified symbols only. Factory legacy callers keep files/signatures and pass reachable symbols when supplied. Do not silently convert symbol scope to a glob fallback.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/test_kb_index.py tests/unit/test_kb_retrieval.py tests/unit/substrate/test_codemap_imports.py tests/unit/coherence/test_artifact_families.py -q
    git add src/substrate/kb src/substrate/codemap tests/unit tests/fixtures
    git commit -m "feat(kb): match scope by reachable symbols"

### Task 5: Final Increment 8 gate

- [ ] **Step 1: Run integrated checks.**

Run:

    rtk proxy uv run python -m coherence course check --json
    rtk proxy uv run python -m coherence trace check --project-root .
    rtk proxy uv run python -m coherence register check --project-root .
    rtk proxy uv run python -m pytest tests/unit/coherence tests/unit/trace tests/unit/requirements tests/unit/substrate -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: unknown IDs/links and unmarked bound test files fail their owning checks; legacy source forms remain readable during the shim release.

## Plan Self-review

- Covers the local TN-05 specs, TN-04/TN-12 course checks, TN-07 SR test-marker closure, and TN-15 symbol-scoped KB retrieval. It does not claim shared progressive-assurance taxonomy coverage for `test_marker` or course-trace obligations.
- Keeps Markdown and existing artifact stores authoritative; all added outputs are derived checks or indexes.

## Review Amendments

Course frontmatter grammar is traceability: [NODE_ID, ...]; body grammar is [[NODE_ID]], where NODE_ID matches SR-[0-9]+ or SPEC-[A-Za-z0-9._-]+. No-course returns exit 0 with empty notes/unreached arrays; unknown/malformed refs or unreached known SR/spec nodes return exit 1. ReachabilityResult has status resolved|stale|missing|unsupported, symbols, diagnostics, and snapshot_ref; stale/missing/unsupported symbol scope yields a KB diagnostic/no symbol hit, never a file-glob fallback.

## Addendum (2026-08-22): progressive assurance — profile-aware test markers

See `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` (section 10 disposition row for Increment 8). Requires this plan's Task 3 and Increment 2B merged first (`coherence.policy.compiler.compile_obligations`/`resolve_profile`), plus Increment 4's `verification_result` and Increment 6's `human_review` compiler addenda. Task 6 extends that same compiled SR-obligation list and therefore consumes all four prerequisites; it does not provide them. Task 3 above currently treats a missing `@pytest.mark.sr("SR-...")` marker on a path-bound experiment as an unconditional blocking finding; this addendum makes that requiredness profile-aware through a local obligation projection, instead of hard-coding the closure check.

**Scope note (minor):** spec §10 row 8 covers "test markers AND course trace obligations ...
classroom generation." This addendum only does local marker closure (Task 3's own deliverable).
Course-trace obligations and classroom projections (this plan's Task 2, "course check") remain
out of scope here. The `test_marker` label below is an Increment 8-local projection label; whether
it, or course-trace obligations, belongs in the shared progressive-assurance taxonomy is unresolved
and is not decided by this plan.

### Task 6: Profile-aware test-marker closure (shared taxonomy ownership unresolved)

- [ ] **Step 1: Write the failing test.**

Add to `tests/unit/coherence/test_register_markers.py` (created by Task 3): seed two SRs with
path-bound experiments and no matching marker, one under the project default `prototype` profile
and one with a `profile: high_assurance` frontmatter override. Assert the `prototype` SR's missing-
marker finding reports `required` (the decided severity for this addendum -- a missing marker
under `prototype` must still show up as a real, trackable gap, just not one that fails a gate)
while the `high_assurance` SR's finding reports `blocking`, exactly as Task 3's finding did
unconditionally before this addendum. Both assertions read the finding's severity off the SAME
compiled `test_marker` `Obligation`'s `requiredness` (Step 2 below), not a value the closure check
re-derives independently.

**This addendum changes two of Task 3's own tests, not just adds new ones.** Task 3 Step 1 seeds
"a bound SR whose experiment resolves to a `.py` test file with no matching marker is a blocking
finding" with no `profile:` override -- meaning that SR resolves to the project default,
`prototype`. Once this addendum lands, that specific case is `required`, not `blocking`: update
that existing assertion (wherever it lands in `tests/unit/coherence/test_register_markers.py`) to
expect `required`, and add a new, separate case that reseeds the same fixture with a
`profile: high_assurance` frontmatter override to preserve the original `blocking` assertion under
that specific profile. Every OTHER Task 3 test not exercising this specific missing-marker-severity
path (marker collection itself, duplicate-marker reduction, the command/non-file configuration
finding) is unaffected and needs no change.

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_register_markers.py -k profile -v

Expected: FAIL (both SRs currently report the same, unconditional severity; `test_marker` is not
yet a compiled obligation kind).

- [ ] **Step 2: Implement the local test-marker obligation projection.**

In `src/coherence/policy/compiler.py` (Increment 2B), extend the existing `elif
scope_ref.startswith("sr:")` branch (already appending `_verification_result_obligation` and
`_human_review_obligation`, Increment 4's and Increment 6's addenda) to also append the local
`_test_marker_obligation(root, scope_ref, profile)` projection. Reuse the existing `Obligation`
shape for this plan's closure check; the `kind="test_marker"` label below is not a decision to
promote that label into the shared progressive-assurance taxonomy.

```python
def _test_marker_obligation(root: Path, scope_ref: str, profile: str) -> Obligation:
    """test_marker: a bound SR's experiment, when it resolves to a .py test
    file (Task 3's own resolvable-test-file check -- an experiment that is a
    command/non-file is a separate configuration finding, not this
    obligation's concern, and this kind is not_applicable for it), must carry
    a matching @pytest.mark.sr(sr_id) marker. The marker-closure CHECK (Task 3)
    consumes THIS compiled obligation's requiredness rather than re-deriving
    severity from a raw profile string -- one source of truth, like every
    other obligation-backed check in this design.
    """
    from coherence.register import register as register_module
    from coherence.register.markers import collect_markers

    sr_id = scope_ref.partition(":")[2]
    register = {r.id: r for r in register_module.load_register(root / "requirements")}
    req = register.get(sr_id)
    requiredness = "blocking" if profile == "high_assurance" else "required"
    if req is None or req.binding is None:
        return Obligation(
            id=f"ob:test_marker:{scope_ref}", scope_ref=scope_ref, kind="test_marker",
            requiredness="not_applicable", reason=f"{sr_id} has no binding to check a marker for",
            source_policy=profile, state="satisfied", resolve_cmd=None,
        )
    experiment_path = root / req.binding.experiment
    if not (experiment_path.suffix == ".py" and experiment_path.is_file()):
        # Command/non-file experiment: Task 3's own configuration-finding path
        # owns this case, not a guessed marker result.
        return Obligation(
            id=f"ob:test_marker:{scope_ref}", scope_ref=scope_ref, kind="test_marker",
            requiredness="not_applicable",
            reason=f"{sr_id}'s experiment does not resolve to a test file",
            source_policy=profile, state="satisfied", resolve_cmd=None,
        )
    markers = collect_markers(experiment_path)
    present = sr_id in markers
    return Obligation(
        id=f"ob:test_marker:{scope_ref}",
        scope_ref=scope_ref,
        kind="test_marker",
        requiredness=requiredness,
        reason=f'{profile} requires @pytest.mark.sr("{sr_id}") on {sr_id}\'s bound experiment test file',
        source_policy=profile,
        state="satisfied" if present else "open",
        resolve_cmd=f'add @pytest.mark.sr("{sr_id}") to {experiment_path.name}',
    )
```

`coherence.register.markers.collect_markers(path) -> set[str]` is Task 3's own collector
(unchanged, reused directly -- this addendum does not reimplement marker collection).

Wire the marker-closure CHECK (Task 3's own closure/check integration in
`coherence.register.markers`) to read the `test_marker` obligation's `requiredness` for the
scope it is checking, instead of hard-coding `blocking` or independently comparing a raw profile
string. On `UncompiledPresetError` (Increment 2B, e.g. an `exploration`/`product`-profiled scope)
the check does **not** silently fall back to the project default -- the spec's "never silently
fall back" rule (§9.3: "Invalid profile: configuration error, not fallback... Missing evidence:
unknown/blocked, never pass") applies here exactly as it does everywhere else in this design.
Instead, mirror Increment 5's addendum's `degraded.append(...)` pattern: if the marker-closure
check's own output has a degrade channel (a `degraded`/`errors` list on its report, matching this
repo's established degrade-not-crash convention), append a clear message there and skip emitting a
`test_marker` finding for that SR (never fabricate a severity for a profile the compiler could not
resolve); if the check's output has no such channel yet, this addendum requires Task 3's own
report shape to gain one (a bare `list[str]`, named consistently with the other degrade lists this
codebase already has) rather than swallowing the error silently.

- [ ] **Step 3: Run the tests.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_register_markers.py tests/unit/coherence/policy/test_compiler.py tests/unit/requirements -q

Expected: PASS; every Task 3 test not covering the missing-marker-severity path keeps its original
expectation; the two updated/added cases from Step 1 assert `required` (default profile) and
`blocking` (`high_assurance` override) respectively, both read off the compiled `test_marker`
obligation.

- [ ] **Step 4: Commit.**

    git add src/coherence/policy/compiler.py src/coherence/register/markers.py tests/unit/coherence/test_register_markers.py tests/unit/coherence/policy/test_compiler.py
    git commit -m "feat(register): compiled test_marker obligation, profile-aware requiredness for missing SR test markers"

### Approval-dependent decisions left open

This addendum intentionally leaves these cross-increment decisions for approval:

- whether `test_marker` belongs in the shared progressive-assurance taxonomy;
- whether the course-trace check becomes a shared `course_trace` obligation, and whether
  classroom-generation projections are added later;
- whether a future status contract should add a `reviewer` field, including its owner and
  serialization;
- whether `Obligation.resolve_cmd` is portable enough to display or execute across shells and
  platforms. Increment 8 only carries the existing structured command value and does not execute
  it.

No choice about those fields, taxonomy labels, or policies is made by Increment 8.
