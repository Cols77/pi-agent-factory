# Coherence Increment 0 Baseline Enablement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the isolated Increment 0 workspace's existing unit baseline reproducible without changing application behaviour, then execute the approved evidence-register increment.

**Architecture:** Extension type checks obtain their pinned tools from their existing lockfiles; this changes only ignored workspace dependencies. The code-index tests classify tree-sitter as available only when `extract_signatures` actually uses that engine, preserving the documented stdlib fallback. The approved Increment 0 plan remains the implementation authority after these baseline repairs.

**Tech Stack:** npm/npm lockfiles, Python 3.12, pytest, tree-sitter optional extras, existing Coherence Increment 0 plan.

---

## File Structure

- `pi-ext/factory-watch/node_modules/` — ignored, lockfile-derived tools for the factory-watch extension.
- `pi-ext/scope-guard/node_modules/` — ignored, lockfile-derived tools for the scope-guard extension.
- `tests/unit/codeindex/test_codeindex.py` — test-only optional-accelerator probe; no production code changes.
- `docs/superpowers/plans/2026-08-20-coherence-increment-0-evidence-register.md` — the approved implementation plan that follows this enabling work.

### Task 1: Provision the locked extension toolchains

**Files:**
- Generated (ignored): `pi-ext/factory-watch/node_modules/`
- Generated (ignored): `pi-ext/scope-guard/node_modules/`

- [ ] **Step 1: Install the factory-watch lockfile dependencies.**

Run: `rtk proxy npm ci --prefix pi-ext/factory-watch`

Expected: npm installs the locked TypeScript compiler and test runner without changing `package-lock.json`.

- [ ] **Step 2: Install the scope-guard lockfile dependencies.**

Run: `rtk proxy npm ci --prefix pi-ext/scope-guard`

Expected: npm installs the locked TypeScript compiler and test runner without changing `package-lock.json`.

- [ ] **Step 3: Verify both previously failing extension gates.**

Run: `rtk proxy uv run python -m pytest tests/gates/test_ext_gate.py tests/gates/test_watch_ext_gate.py -q`

Expected: both tests pass because each gate can resolve its local `tsc` executable.

### Task 2: Make the tree-sitter availability probe reflect the selected engine

**Files:**
- Modify: `tests/unit/codeindex/test_codeindex.py:151-160`

- [ ] **Step 1: Preserve the observed failing test as the red evidence.**

Run: `rtk proxy uv run python -m pytest tests/unit/codeindex/test_codeindex.py::test_preferred_engine_reports_available_extractor -q`

Expected before this test-only correction: failure because `_tree_sitter_available()` returns true after the intended `stdlib-ast` fallback, so the assertion incorrectly requires `tree-sitter`.

- [ ] **Step 2: Narrow the test helper to the actual engine choice.**

Replace the helper body with:

```python
from pathlib import Path

def _tree_sitter_available(path: Path, source: str) -> bool:
    try:
        engine, _ = extract_signatures(path, source)
    except Exception:
        return False
    return engine == "tree-sitter"
```

Pass a language-specific path and valid source to each call: Python tests use a `.py` probe and
Python source; the TypeScript accelerator test uses a `.ts` probe and TypeScript source. This does
not change `factory.codeindex`; its optional fallback is already the specified production behaviour.

- [ ] **Step 3: Verify the accelerator-selection tests.**

Run: `rtk proxy uv run python -m pytest tests/unit/codeindex/test_codeindex.py -q`

Expected: core code-index tests pass; each grammar-specific accelerator test independently skips
when its own optional grammar is absent.

- [ ] **Step 4: Commit the test correction.**

```bash
git add tests/unit/codeindex/test_codeindex.py docs/superpowers/plans/2026-08-20-coherence-increment-0-baseline-enablement.md
git commit -m "test(codeindex): detect actual tree-sitter availability"
```

### Task 3: Re-establish the unit baseline and hand off Increment 0

**Files:**
- No source changes.

- [ ] **Step 1: Run the complete unit baseline.**

Run: `rtk proxy uv run python -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py`

Expected: the suite passes, with optional accelerator tests skipped when the grammars are unavailable.

- [ ] **Step 2: Begin Task 1 of the approved evidence-register plan.**

Dispatch an Increment 0 Task 1 implementer with the complete task text from `2026-08-20-coherence-increment-0-evidence-register.md`, including its required test-first contract and focused evidence regressions. Do not make Increment 0 production changes before that test has failed for the missing module.

## Plan Self-review

- The plan changes only ignored dependency installations and a test-only accelerator probe; it does not hide or relax production behaviour.
- Each baseline failure has a concrete owner: extension packages supply `tsc`; the test helper checks the selected extractor rather than any successful fallback.
- Increment 0 remains fully covered by its approved implementation plan and starts only after a clean baseline is demonstrated.
