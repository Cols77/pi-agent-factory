# Coherence Increment 5: Status, Focus, Dispatcher, and TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a deterministic coherence status, session focus, explanation, Pi status widget, and honest intent-routing interface.

**Architecture:** Python owns concurrent read-only probes, precedence, focus storage, and vocabulary explanation. The extension renders structured JSON and a deterministic zero-argument menu. Argument classification has an explicit host-capability gate because the installed Pi API exposes newSession/sendUserMessage, not a direct enum-constrained completion.

**Tech Stack:** Python 3.11+, atomic JSON, argparse, TypeScript, Pi extension, pytest, npm test.

---

## Execution Coordination

- Prerequisites: Increments 3 and 4.
- Parallel after StatusLine is frozen: Python status/focus/explain; TypeScript widget/menu; factory-selfcheck compatibility alias.
- Serial: extension command registration has one owner; argument classifier wiring follows verified Pi API capability.

## File Structure

**Create:** src/coherence/status.py, src/coherence/focus.py, src/coherence/explain.py, .pi/skills/using-coherence/SKILL.md, pi-ext/factory-watch/src/coherence-command.ts, pi-ext/factory-watch/src/coherence-status.ts, tests/unit/coherence/test_status.py, tests/unit/coherence/test_focus.py, tests/unit/coherence/test_explain.py, pi-ext/factory-watch/test/coherence-command.test.ts, pi-ext/factory-watch/test/coherence-status.test.ts.

**Modify:** src/coherence/cli.py, pi-ext/factory-watch/src/index.ts, status-format.ts, mission-control-dashboard.ts, factory-skills.ts, factory-init-command.ts, and their existing tests.

### Task 1: Add a pure status contract

- [ ] **Step 1: Write failing precedence tests.**

Define StatusLine(source, outcome, summary, produced_by, resolve_cmd, observation_ref) and StatusSnapshot(lines, primary, exit_code). Use fake probe results to assert:

    interrupted_run > failing_gate > stale_audit > proposed_backlog > nothing_pending

Every line names the producer and resolver command. A stale snapshot must render stale with its resolver and never current.

- [ ] **Step 2: Implement concurrent probes.**

Implement status_snapshot(project_root) to concurrently run trace check, register check, current run checkpoint, newest audit age, and membership --gate. Each probe returns one StatusLine even on a tool error. Add coherence status and coherence status --json to the group dispatcher.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_status.py tests/unit/system/test_cli.py tests/unit/orchestrator/test_run_cli.py tests/unit/orchestrator/test_status.py -q
    git add src/coherence/status.py src/coherence/cli.py tests/unit/coherence/test_status.py
    git commit -m "feat(coherence): aggregate truthful status"

### Task 2: Add focus and explain

- [ ] **Step 1: Write failing atomic focus tests.**

Test set_focus(session_root, "feat:FEAT-NAV-017"), get_focus, and clear_focus. Invalid refs create no file. Assert the atomic JSON location is sessions/.coherence-focus.json and no repository-tracked file changes. Test explain delegates current vocabulary and rejects unknown values.

- [ ] **Step 2: Implement and wire CLI.**

Add coherence focus <scope-ref>, coherence focus --none, and coherence explain <term-or-id>. Explicit command scopes override session focus. The explain implementation reads the existing vocabulary data only.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_focus.py tests/unit/coherence/test_explain.py -q
    git add src/coherence/focus.py src/coherence/explain.py src/coherence/cli.py tests/unit/coherence
    git commit -m "feat(coherence): add session focus and explain"

### Task 3: Add deterministic extension status and menu

- [ ] **Step 1: Write TypeScript fixtures.**

Mock coherence status JSON and assert coherence-status renders primary and resolve command. Mock no-argument probes and assert coherence-command renders the ranked menu, offers “not that? pick from the menu”, and sends no model message.

- [ ] **Step 2: Implement the bridge.**

coherence-status.ts invokes coherence status --json. coherence-command.ts implements the zero-argument menu only. Register /using-coherence in index.ts, add the widget beside the factory widget, and write the skill routing table without write authority.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy npm test --prefix pi-ext/factory-watch -- coherence-command coherence-status status-format factory-skills skill-prompt
    git add .pi/skills/using-coherence pi-ext/factory-watch/src pi-ext/factory-watch/test
    git commit -m "feat(pi): add coherence status and deterministic menu"

### Task 4: Resolve the direct-classifier capability gate truthfully

- [ ] **Step 1: Verify host support.**

Add an extension test for a direct structured completion accepting the enum:

    UNDERSTAND, VERIFY_CLAIM, CLOSE_GAPS, AUTHOR_REQUIREMENTS,
    BUILD, RECOVER, TRIAGE, TEACH

The test must distinguish this capability from session creation. On the present API it demonstrates absence.

- [ ] **Step 2: Implement the only supported outcome.**

If the test finds a verified direct structured-completion API, implement classify_intent(text) returning intent and optional scope ref, print the classification and menu escape hatch, then dispatch.

If it does not, /using-coherence with an argument returns exit 2 and:

    argument routing requires a Pi structured-completion capability; use the no-argument menu

Do not create a session and describe it as one constrained classification call.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy npm test --prefix pi-ext/factory-watch -- coherence-command
    git add pi-ext/factory-watch/src pi-ext/factory-watch/test .pi/skills/using-coherence
    git commit -m "feat(pi): gate coherence intent classification on host capability"

### Task 5: Rename factory diagnostics and verify Increment 5

- [ ] **Step 1: Update alias tests.**

Test /factory-selfcheck performs current bootstrap diagnostics. Test /factory-doctor prints one deprecation line and forwards. Test factory.orchestrator.run_cli doctor remains run-recovery only.

- [ ] **Step 2: Implement aliases and run final checks.**

Rename the registration in factory-init-command.ts while retaining the old forwarder. Then run:

    rtk proxy uv run python -m pytest tests/unit/coherence tests/unit/system tests/unit/orchestrator -q
    rtk proxy npm test --prefix pi-ext/factory-watch
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: deterministic work lands regardless of classifier capability; classification is never falsely claimed.

## Plan Self-review

- Covers status, focus, explain, TUI, using-coherence, and doctor renaming.
- Records the current Pi capability limitation as a testable implementation gate rather than inventing an unavailable API.

## Review Amendments

Focus is stored atomically in .pi/factory/session-context.json under a coherence_focus key, matching the existing session-policy owner; tests assert it is ignored/untracked. The classifier capability probe is a version-pinned integration fixture against the real Pi SDK export, not the local structural pi-types.ts subset.

Until that fixture proves a direct schema-constrained one-response API, the original exact-one-intent acceptance criterion is externally blocked and Increment 5 cannot be marked complete. Deterministic no-argument routing, status, focus, explanation, and aliases remain independently shippable; argument routing returns the documented refusal.
