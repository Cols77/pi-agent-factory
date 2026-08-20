# Coherence Increment 1C: Codemap, Knowledge Base, and Gate Signatures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the durable code map and knowledge base to substrate, add a structured Python import-edge layer, and make a failed gate’s canonical error signatures select KB guidance on the next attempt.

**Architecture:** Preserve the current code-index fingerprint, storage, parser fallback, and Python overlap truth table while moving it to substrate.codemap behind one-release factory wrappers. Keep gate execution factory-owned, but extend it from an integer-only result to a structured GateRun that retains output for evidence and signature extraction. substrate.kb remains a pure reader/index; the factory runner supplies changed paths and signature history before each retry.

**Tech Stack:** Python 3.11+, ast, tree-sitter fallback already present, dataclasses, pathlib, pytest, Ruff, Pyright.

---

## Execution Coordination

- **Prerequisites:** Increment 1 foundation and Increment 1B.
- **Parallel:** codemap relocation can run alongside KB relocation after substrate validators exist. GateRun/signature work can begin after the KB public selector is frozen.
- **Serial:** import-edge representation follows codemap relocation; TN-14 runner wiring follows GateRun and KB signature APIs; compatibility/import-cycle/full gate verification is last.
- **Ownership:** factory.orchestrator.runner, gate-runner protocols, and NodeEvent are exclusively owned by the TN-14 task. Do not edit them from the codemap stream.

## File Structure

**Create:**

- src/substrate/codemap/{__init__,model,build,sigs,store,imports}.py
- src/substrate/kb/{__init__,index,retrieval,signatures}.py
- tests/unit/substrate/test_codemap_imports.py
- tests/unit/substrate/test_kb_signatures.py
- tests/unit/orchestrator/test_gate_run_detail.py

**Modify:**

- src/factory/codeindex/{__init__,model,build,sigs,store,cli}.py
- src/factory/coverage/imports.py
- src/factory/kb/{index,retrieval}.py
- src/factory/validation/kb_validator.py
- src/factory/orchestrator/{backends,nodes,runner,types}.py
- src/factory/orchestrator/context_packet.py
- tests/unit/codeindex/test_codeindex.py
- tests/unit/coverage/test_imports.py
- tests/unit/test_kb_{index,retrieval,validator}.py
- tests/unit/orchestrator/test_{runner,gates,nodes}.py

### Task 1: Relocate the code map and preserve old freshness semantics

- [ ] **Step 1: Write legacy/canonical parity tests.**

For each code-index fixture, compare substrate.codemap.ensure_fresh/load_latest/render_index_slice to factory.codeindex equivalents. Assert a source change rebuilds, parser-engine change rebuilds, matching fingerprint/engine reuses, and no-files returns the existing empty CodeIndex result. Capture exactly one DeprecationWarning for every old factory.codeindex module import.

- [ ] **Step 2: Run the new tests before the move.**

Run: rtk proxy uv run python -m pytest tests/unit/codeindex/test_codeindex.py tests/unit/substrate/test_codemap_imports.py -q

Expected: substrate.codemap import failure.

- [ ] **Step 3: Move canonical code and leave wrappers.**

Move CodeIndex/IndexFile/IndexSignature, builders, signature extraction, store/atomic persistence, CLI helpers, and public exports to substrate.codemap. Update the Increment 1 code-map resolver adapter so the canonical resolver is substrate.codemap and any factory composition remains outside substrate. Make each factory.codeindex module a warning/re-export shim. Retarget factory.orchestrator.context_packet to substrate.codemap.

- [ ] **Step 4: Verify the move.**

Run:

    rtk proxy uv run python -m pytest tests/unit/codeindex/test_codeindex.py tests/unit/substrate/test_codemap_imports.py -q
    rtk proxy uv run ruff check src/substrate/codemap src/factory/codeindex tests/unit/codeindex tests/unit/substrate

Expected: existing code navigation and persistent index behaviour are unchanged.

- [ ] **Step 5: Commit.**

    git add src/substrate/codemap src/factory/codeindex src/factory/orchestrator/context_packet.py tests/unit/codeindex tests/unit/substrate/test_codemap_imports.py
    git commit -m "refactor(substrate): move durable code map"

### Task 2: Add a structured import-edge layer without changing current overlap answers

- [ ] **Step 1: Create exact Python import-edge tests.**

Use the current coverage import fixtures. Assert:

    result = build_import_closure(repo, ["src/a.py"])
    assert result.status == "resolved"
    assert result.files == ("src/a.py", "src/b.py")

Add missing-import and renamed-binding fixtures requiring status unresolved and a diagnostic that distinguishes “selection missing” from “no overlap”. For every existing Python fixture assert the converted codemap overlap equals factory.coverage.imports.compute_overlap exactly.

- [ ] **Step 2: Implement the edge data and APIs.**

Define ImportEdge(source: str, target: str, kind: str) and ImportClosure(files, status, diagnostics). Implement substrate.codemap.imports using the existing ast import-resolution semantics first. Store edges beside the fingerprinted index data with a backward reader for old index files. Non-Python source types return structured unsupported status; they must not claim transitive coverage merely because a parser exists.

Expose:

    build_import_closure(repo_root, roots) -> ImportClosure
    compute_overlap(repo_root, binding_test, changed_files) -> OverlapResult

Keep factory.coverage.imports as a warning wrapper until Increment 4 consumes substrate.codemap directly.

- [ ] **Step 3: Run regression tests.**

Run: rtk proxy uv run python -m pytest tests/unit/coverage/test_imports.py tests/unit/substrate/test_codemap_imports.py -q

Expected: all historical Python overlap cases pass, with new unresolved/unsupported distinctions.

- [ ] **Step 4: Commit.**

    git add src/substrate/codemap src/factory/coverage/imports.py tests/unit/coverage/test_imports.py tests/unit/substrate/test_codemap_imports.py
    git commit -m "feat(codemap): index import edges for overlap"

### Task 3: Move KB readers and canonicalise failure signatures

- [ ] **Step 1: Write KB parity and signature tests.**

Compare old/new index and retrieval on path-glob fixtures. Add:

    signatures = canonical_failure_signatures(
        "E ConnectionResetError: connection reset by peer\\n1 failed in 0.2s"
    )
    assert "ConnectionResetError: connection reset by peer" in signatures

Assert whitespace is collapsed, output is deterministically deduplicated/capped, secret-like values are not persisted as a new fact, and empty/nonmatching output selects no signature-only entry.

- [ ] **Step 2: Move KB model/index/retrieval.**

Move factory.kb.index/retrieval to substrate.kb. Expose load_entries(kb_dir, ids=None), select_entries(kb_dir, touched_files, signatures), and canonical_failure_signatures(text). Update the canonical KB validator import to substrate.validators.kb; factory.kb modules warn/re-export. No KB module determines a gate outcome.

- [ ] **Step 3: Run KB tests.**

Run: rtk proxy uv run python -m pytest tests/unit/test_kb_validator.py tests/unit/test_kb_index.py tests/unit/test_kb_retrieval.py tests/unit/substrate/test_kb_signatures.py -q

Expected: file and signature selection are both deterministic.

- [ ] **Step 4: Commit.**

    git add src/substrate/kb src/factory/kb src/factory/validation/kb_validator.py tests/unit/test_kb_validator.py tests/unit/test_kb_index.py tests/unit/test_kb_retrieval.py tests/unit/substrate/test_kb_signatures.py
    git commit -m "refactor(substrate): move KB and canonical signatures"

### Task 4: Retain gate output and reselect KB guidance on failures

- [ ] **Step 1: Add failing structured gate tests.**

Introduce the expected factory execution result:

    GateRun(
        name="unit",
        returncode=1,
        output="E ConnectionResetError: connection reset by peer",
        applicable=True,
        commands=("python -m pytest -q",),
        log_path=None,
    )

Assert GateRunner.run(name) still returns its integer returncode. Assert run_detail(name) returns GateRun, captures stdout/stderr, writes the same log text when log_dir exists, and echoes captured output when no log is configured.

- [ ] **Step 2: Implement GateRun compatibility.**

Add GateRun and GateRunner.run_detail. ConfigGateRunner performs one subprocess execution and returns its detail; run delegates to detail.returncode. Fake gate runners accept scripted GateRun instances. Nodes retain GateRun.to_dict and canonical signatures in NodeEvent.extra; absent gates are applicable false rather than fabricated failures.

- [ ] **Step 3: Wire retry-time selection.**

Replace runner’s one-time select_entries(..., []) setup with an injected selector called before every DEV/review attempt:

    select_kb(current_changed_files, signature_history) -> list[dict]

After each failed unit/sim/full gate append canonical signatures from that GateRun, then reselect before the next attempt. The runner never executes a gate twice merely to obtain output.

Add the regression: a KB entry has only error_signatures for ConnectionResetError and no matching file glob; a failed unit gate produces that line; the next DEV prompt contains the entry. Also prove a nonmatching failure and a successful gate add no entry.

- [ ] **Step 4: Run focused and full Increment 1C checks.**

Run:

    rtk proxy uv run python -m pytest tests/unit/orchestrator/test_gate_run_detail.py tests/unit/orchestrator/test_runner.py tests/unit/coverage/test_imports.py tests/unit/codeindex/test_codeindex.py tests/unit/test_kb_retrieval.py tests/unit/substrate -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: signature-only guidance reaches the retry prompt; no substrate module imports factory/coherence.

- [ ] **Step 5: Commit.**

    git add src/factory/orchestrator src/substrate tests/unit/orchestrator tests/unit/substrate
    git commit -m "feat(factory): select KB guidance from gate signatures"

## Plan Self-review

- Completes the original Increment 1 codemap/KB/TN-14 obligations while retaining the architecture rule that gate execution is factory-owned.
- Parallel codemap and KB streams converge only at their explicit wrappers and final test suite.
- It does not promise cross-language import reachability until an extractor exists; unsupported language state is truthfully surfaced.

## Review Amendments

Move OverlapResult to substrate.codemap.imports and re-export it from factory.coverage.imports. GateRun, GateRunner, FakeGateRunner, ConfigGateRunner, GATE_NOT_APPLICABLE, subprocess capture, and log handling are edited only in factory.orchestrator.backends.py; nodes.py, runner.py, and types.py carry the typed result/history. Add tests/unit/orchestrator/test_backends.py to the Task 4 command and commit.
