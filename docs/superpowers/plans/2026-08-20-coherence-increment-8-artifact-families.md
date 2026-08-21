# Coherence Increment 8: Artifact Families Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make specs, course notes, SR-marked tests, and symbol-scoped KB knowledge visible and verifiable through the coherence graph.

**Architecture:** Evolve trace nodes from filename-derived spec heuristics to frontmatter-authoritative spec nodes with legacy compatibility. Course Markdown remains authoritative and its checker emits a computed result rather than a new store. The register collects pytest SR markers only for test-file experiment bindings, reporting ambiguous command bindings as configuration findings. KB symbol scope uses the codemap reachability API and never falls back to glob matching while claiming a symbol match.

**Tech Stack:** Python 3.11+, frontmatter, regex/AST, pytest marker collection, substrate.codemap, pytest, Ruff, Pyright.

---

## Execution Coordination

- Prerequisites: Increment 2 trace/register and Increment 1C codemap. KB symbol reachability additionally follows Increment 4 codemap audit cutover.
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

- Covers TN-05 specs, TN-04/TN-12 courses, TN-07 SR test markers, and TN-15 symbol-scoped KB retrieval.
- Keeps Markdown and existing artifact stores authoritative; all added outputs are derived checks or indexes.

## Review Amendments

Course frontmatter grammar is traceability: [NODE_ID, ...]; body grammar is [[NODE_ID]], where NODE_ID matches SR-[0-9]+ or SPEC-[A-Za-z0-9._-]+. No-course returns exit 0 with empty notes/unreached arrays; unknown/malformed refs or unreached known SR/spec nodes return exit 1. ReachabilityResult has status resolved|stale|missing|unsupported, symbols, diagnostics, and snapshot_ref; stale/missing/unsupported symbol scope yields a KB diagnostic/no symbol hit, never a file-glob fallback.
