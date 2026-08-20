# Coherence Increment 7: Unified Long-Run Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present factory runs, audits, measurements, simulations, and experiments through one status protocol and mission-control surface while preserving every native durable store and raw artifact reference.

**Architecture:** coherence.runs adapts existing checkpoint, journal, audit, simulation, and measurement records into a source-discriminated RunStatus pointing to ObservationEnvelope/artifact references. It never merges or overwrites source stores. coherence.status and the extension consume the same service. Notifications are extension-owned and deduplicated by immutable producer/run/terminal-observation identity, not timestamp.

**Tech Stack:** Python 3.11+, dataclasses, JSONL/JSON readers, substrate observations, TypeScript Pi extension, pytest, npm test.

---

## Execution Coordination

- Prerequisites: Increment 4 domain observation adapters and Increment 6 decision/inbox status.
- Parallel after RunStatus freezes: factory/audit/measurement/simulation adapter units; TypeScript renderer after the contract; source-specific fixtures can be built independently.
- Serial: runs service/status integration after all adapters; completion notification is last because it depends on stable terminal identities.

## File Structure

**Create:** src/coherence/runs/{__init__,model,store,service,factory_adapter,audit_adapter,measurement_adapter,simulation_adapter,experiment_adapter}.py, tests/unit/coherence/test_runs.py, tests/unit/coherence/test_run_adapters.py, pi-ext/factory-watch/test/coherence-mission-control.test.ts.

**Modify:** src/coherence/status.py, factory/orchestrator/{execution,journal,run_cli,run_state,status}.py readers only as needed, coherence/{audit,measurement,simulation} adapters, pi-ext/factory-watch/src/{mission-control-dashboard,status-format,index}.ts, related existing tests.

### Task 1: Freeze source-discriminated RunStatus

- [ ] **Step 1: Write model fixtures.**

Define:

    RunStatus(
      producer="factory" | "audit" | "measurement" | "simulation" | "experiment",
      run_id="...",
      state="running" | "interrupted" | "passed" | "failed" | "unknown",
      observation_ref="obs:...",
      artifacts=(ArtifactRef(...),),
      resume_cmd="...",
      updated_at="...",
    )

Reject missing producer/run_id/ref, state outside enum, duplicate artifact refs, and a terminal run lacking an observation reference. Assert sorting is producer/run-id deterministic.

- [ ] **Step 2: Implement model and pure store protocol.**

Create frozen RunStatus plus a RunSource Protocol returning status rows. No writer API is exposed. Add tests proving the model does not inspect mtimes or modify an artifact.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_runs.py -q
    git add src/coherence/runs tests/unit/coherence/test_runs.py
    git commit -m "feat(coherence): define unified run status"

### Task 2: Implement independent source adapters

- [ ] **Step 1: Write one fixture per durable source.**

Cover factory session checkpoint/JSONL, coverage report, measurement report, simulation registry run, and experiment observation. Each asserts native identifier/outcome/artifact refs/resume command are retained and malformed source produces unknown with diagnostic, not a pass.

- [ ] **Step 2: Implement adapters.**

Implement factory_run_status, audit_run_status, measurement_run_status, simulation_run_status, and experiment_run_status. Read only existing locations such as sessions/.factory-runs/by-session, coverage-reviews, validation reports, and simulation registry/evidence. Attach existing observation refs; do not synthesize raw artifacts or centralise data.

- [ ] **Step 3: Verify and commit adapter streams.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_run_adapters.py tests/unit/orchestrator/test_execution.py tests/unit/orchestrator/test_journal.py tests/unit/orchestrator/test_run_cli.py tests/unit/simulation/test_sim_registry.py tests/unit/validation/test_report.py tests/unit/coverage/test_cli.py -q
    git add src/coherence/runs tests/unit/coherence/test_run_adapters.py
    git commit -m "feat(coherence): adapt durable run sources"

### Task 3: Integrate status, dashboard, and deduplicated notification

- [ ] **Step 1: Write service and UI tests.**

Assert list_run_statuses aggregates/sorts sources, status displays the same primary condition, and the dashboard renders source-specific rows. Test terminal notification writes a session-local dedupe key:

    (producer, run_id, terminal_observation_id)

and fires once across polls even if source mtime changes; a later terminal observation may notify once.

- [ ] **Step 2: Implement service and extension integration.**

coherence.runs.service aggregates RunSource implementations. coherence.status reads it. Update mission-control dashboard/status-format/index to discriminate producers rather than assuming pipeline rows. Persist notification keys under sessions only; ctx.ui.notify is invoked only after a new immutable terminal tuple.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_runs.py tests/unit/coherence/test_run_adapters.py -q
    rtk proxy npm test --prefix pi-ext/factory-watch -- mission-control-dashboard status-format coherence-mission-control
    git add src/coherence/status.py src/coherence/runs pi-ext/factory-watch tests/unit/coherence
    git commit -m "feat(coherence): unify long-run mission control"

### Task 4: Verify Increment 7

- [ ] **Step 1: Run complete source and static checks.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence tests/unit/orchestrator tests/unit/simulation tests/unit/validation tests/unit/coverage -q
    rtk proxy npm test --prefix pi-ext/factory-watch
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: one status protocol and dashboard reach every source; raw artifacts remain reachable through refs.

## Plan Self-review

- Preserves existing stores and adds only projections/adapters, meeting the unified long-run requirement without a new event database.

## Review Amendments

RunStatus additionally has diagnostics: tuple[RunDiagnostic, ...] and terminal_observation_id: str | None; malformed source records return state unknown plus a diagnostic and no fabricated terminal identity. Per-producer adapters are the exact separate modules listed above and may run in parallel; service.py is the sole integration registry owner. coherence reads substrate/coherence artifacts only: factory exposes its checkpoint/journal data through the existing substrate-compatible read adapter introduced in Increment 1B, never through a coherence import of factory.
