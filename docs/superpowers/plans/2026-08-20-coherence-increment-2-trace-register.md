# Coherence Increment 2: Trace, Register, and Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move traceability and the requirement register into coherence with behaviour-preserving factory shims, add safe relation unlinking, and expose the coherence console entry point.

**Architecture:** coherence.trace and coherence.register depend only on substrate. Before moving trace, replace its current factory.system ADR and factory.goals type dependencies with a substrate document parser and structural protocol so the architecture remains one-way. Move trace and register as separate parallel streams, then integrate their group dispatch through coherence.cli; old Python modules remain warning re-exports for one release.

**Tech Stack:** Python 3.11+, argparse, frontmatter, dataclasses, Protocol, pytest, Ruff, Pyright.

---

## Execution Coordination

- **Prerequisite:** Increment 1C is merged, including substrate ledger/evidence/freshness/configuration and a shared ADR/document parser.
- **Parallel:** trace transfer plus unlink tests and register transfer plus closure tests may run in separate worktrees.
- **Serial:** eliminate trace’s factory imports before any coherence.trace import; coherence CLI dispatcher and factory shims follow both transfers; full behavioural equivalence is the final merge lane.
- **Parallel successor:** Increment 3 may prepare its goals/simulation move only after this plan’s canonical public APIs land.

## File Structure

**Create:**

- src/coherence/{__init__,__main__,cli}.py
- src/coherence/trace/{__init__,model,graph,gaps,health,propose,validation_status,write,cli}.py
- src/coherence/register/{__init__,register,closure,write,cli}.py
- src/coherence/doctor/{__init__,context,write,cli}.py
- tests/unit/coherence/test_cli.py
- tests/unit/coherence/test_trace_unlink.py
- tests/unit/coherence/test_legacy_shims.py

**Modify:**

- src/substrate/documents/adr.py
- src/factory/trace/{__init__,__main__,model,graph,gaps,health,propose,validation_status,write,cli,explainers}.py
- src/factory/requirements/{__init__,__main__,register,closure,write,cli}.py
- src/factory/doctor/{__init__,__main__,context,write,cli}.py
- pyproject.toml
- tests/unit/trace/* and tests/unit/requirements/*

### Task 1: Break trace’s factory-only dependencies without changing graph answers

- [ ] **Step 1: Write a dependency and behaviour regression.**

Add an AST test requiring all coherence.trace modules to avoid factory/coherence imports outside their own package. For the current trace fixture, compare graph_to_dict and cmd_check output/exit before and after a proposed shared ADR parser. Add a test where validation_status accepts a structural object with state rather than importing factory.goals.schema.Goal.

- [ ] **Step 2: Extract the shared structural seam.**

Place the existing ADR/document parsing needed by trace in substrate. Define:

    class HasState(Protocol):
        state: str

Make validation_status use HasState. Retarget trace graph document parsing to substrate rather than factory.system.adr. Do not move system navigation here.

- [ ] **Step 3: Verify the seam.**

Run: rtk proxy uv run python -m pytest tests/unit/trace/test_model_nodes.py tests/unit/trace/test_cli_check.py tests/unit/coherence/test_legacy_shims.py -q

Expected: identical old graph/check output and no planned coherence->factory import.

- [ ] **Step 4: Commit.**

    git add src/substrate src/factory/trace tests/unit/trace tests/unit/coherence/test_legacy_shims.py
    git commit -m "refactor(trace): remove execution-layer dependencies"

### Task 2: Move trace and add destructive-safe unlink

- [ ] **Step 1: Add unlink API/CLI failures.**

Test:

    unlink_relation(root, "T-001", satisfies="SR-001")
    unlink_relation(root, "SR-001", upstream="BR-002")

The arguments are mutually exclusive. Assert only the chosen frontmatter relation changes; remaining list values preserve order; a scalar becomes absent when removed; body bytes stay unchanged. A missing node/relation returns error code 2 and leaves the source bytes unchanged.

- [ ] **Step 2: Move trace as the canonical implementation.**

Move all factory.trace modules to coherence.trace and replace old modules, including __main__, with warning/re-export or forwarding main shims. Implement unlink_relation using frontmatter load/write only after relation validation. The CLI adds:

    coherence trace unlink NODE_ID --satisfies SR-###
    coherence trace unlink NODE_ID --upstream BR-###

It rejects both/neither flags through argparse and prints a deterministic result.

- [ ] **Step 3: Verify trace parity and unlink.**

Run:

    rtk proxy uv run python -m pytest tests/unit/trace tests/unit/coherence/test_trace_unlink.py -q
    rtk proxy uv run python -m coherence.trace check --project-root .
    rtk proxy uv run python -m factory.trace check --project-root .

Expected: old/new commands have equal output and exit code on the same fixture; unlink never deletes a file.

- [ ] **Step 4: Commit.**

    git add src/coherence/trace src/factory/trace tests/unit/trace tests/unit/coherence/test_trace_unlink.py
    git commit -m "refactor(coherence): migrate trace and add unlink"

### Task 3: Move the requirement register

- [ ] **Step 1: Add old/new closure parity tests.**

For proposed, bound-current, stale, deferred, measured-passing, and measured-failing fixtures, compare every register command’s stdout/exit:

    new, index, status, show, bind, defer, check, next

between factory.requirements and coherence.register. Assert coherence.register imports substrate ledger/evidence/freshness, not factory.

- [ ] **Step 2: Move canonical modules and shims.**

Move register.py, closure.py, write.py, cli.py, and __main__ to coherence.register; retarget their neutral imports to substrate. Replace factory.requirements modules with warning/re-export shims. Preserve the absence-of-binding means proposed rule, existing checksum semantics, and explicit-only bind/reaffirm writers.

- [ ] **Step 3: Run register regression suite.**

Run: rtk proxy uv run python -m pytest tests/unit/requirements tests/unit/coherence/test_legacy_shims.py -q

Expected: exact behaviour parity and one-release old import warnings.

- [ ] **Step 4: Commit.**

    git add src/coherence/register src/factory/requirements tests/unit/requirements tests/unit/coherence/test_legacy_shims.py
    git commit -m "refactor(coherence): migrate requirement register"

### Task 4: Move the requirements doctor into coherence

- [ ] **Step 1: Write doctor old/new parity tests.**

For context, mint, promote, and task fixtures, compare factory.doctor and coherence.doctor stdout, exit code, proposed requirement content, and explicit writer effects. Assert coherence.doctor imports coherence.register/substrate only and does not take ownership of factory bootstrap diagnostics or run recovery.

- [ ] **Step 2: Move canonical doctor modules.**

Move factory.doctor context.py, write.py, cli.py, and __main__ to coherence.doctor. Retarget requirement writes to coherence.register's explicit writer interfaces. Replace factory.doctor with warning/re-export shims. Keep the names context, mint, promote, and task unchanged.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/doctor tests/unit/coherence/test_legacy_shims.py -q
    git add src/coherence/doctor src/factory/doctor tests/unit/doctor tests/unit/coherence/test_legacy_shims.py
    git commit -m "refactor(coherence): migrate requirements doctor"

### Task 5: Add the coherence console group dispatcher

- [ ] **Step 1: Write dispatcher tests.**

Test python -m coherence trace check and python -m coherence register status --requirements-dir <fixture>; assert missing/unknown group exits 2 and lists valid groups. Assert each group receives argv unchanged after the group name.

- [ ] **Step 2: Implement console entry.**

Define an explicit registry:

    GROUPS = {
      "trace": coherence.trace.cli.main,
      "register": coherence.register.cli.main,
      "doctor": coherence.doctor.cli.main,
    }

coherence.cli dispatches the first argv token without parser rewriting. coherence.__main__ calls it. Add:

    [project.scripts]
    coherence = "coherence.cli:main"

to pyproject.toml if no existing scripts table exists; otherwise add that single mapping without altering other entries.

- [ ] **Step 3: Run final Increment 2 checks.**

Run:

    rtk proxy uv run python -m pytest tests/unit/trace tests/unit/requirements tests/unit/coherence -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright
    rtk rg -n "^(from|import) factory" src/coherence

Expected: tests/static checks pass and the final search finds no factory import in coherence.

- [ ] **Step 4: Commit.**

    git add src/coherence pyproject.toml tests/unit/coherence
    git commit -m "feat(coherence): add trace and register console groups"

## Plan Self-review

- Covers Increment 2’s trace/register/requirements-doctor moves, console contract, and TN-03 unlink.
- Keeps original commands compatible and does not let trace pull navigation or goals prematurely across the boundary.

## Review Amendments

Task 1 imports substrate.documents.adr.parse_adr exactly; its test is tests/unit/substrate/test_adr.py and checks factory.trace.graph output parity. Move factory.trace.explainers to coherence.trace.explainers and retarget its fingerprint import to substrate.freshness.fingerprint; retain a warning wrapper at the old path.
