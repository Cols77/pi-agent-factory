# Coherence Increment 4: Audit, Measurement, and Observation Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move coverage assurance and measurement harnesses to coherence, emit validated domain observations, parallelise independent SR reviews deterministically, and consume codemap import-edge overlap.

**Architecture:** Preserve the native HarnessResult/TrialResult and coverage report formats, adapting them to typed ObservationEnvelope payloads rather than flattening them into command text. Audit and measurement move in parallel after their input contracts land; a shared adapter/projection test validates their agreement. Per-SR review dispatch becomes bounded parallel work with the coordinator as the only report/status writer. Audit replaces its private import walker with substrate.codemap and reports missing/renamed test selection separately.

**Tech Stack:** Python 3.11+, concurrent.futures, dataclasses, existing validation harnesses, substrate observations/projections/codemap, pytest, Ruff, Pyright.

---

## Execution Coordination

- **Prerequisites:** Increment 1C codemap/KB APIs, Increment 2 trace/register, and Increment 3 simulation/navigation canonical paths.
- **Parallel:** audit transfer/codemap fixtures, measurement harness transfer, and simulation observation fixtures can run in separate worktrees.
- **Serial:** bounded SR concurrency follows audit runner transfer; shared adapter registry, coherence CLI dispatch, report compatibility, and final gate verification are one integration lane.
- **Shared file rule:** only the integration worker edits coherence.cli, adapter registration, pyproject entry points, and compatibility-test matrix.

## File Structure

**Create:**

- src/coherence/audit/ canonical coverage modules plus observations.py
- src/coherence/measurement/ canonical harness modules plus observations.py
- src/coherence/simulation/observations.py
- tests/unit/coherence/test_observation_adapters.py
- tests/unit/coherence/test_audit_parallel.py

**Modify:**

- src/factory/coverage/{scope,imports,audit,gate,report,runner,cli,__main__}.py
- src/factory/validation/{harness,sim_harness,playwright_harness,pipeline,report,scorer_registry,assertions,cli,__main__}.py
- src/coherence/{cli,__main__}.py
- tests/unit/coverage/* and tests/unit/validation/*

### Task 1: Move audit and cut over to codemap overlap

- [ ] **Step 1: Write old/new audit parity and selection tests.**

For existing feature fixtures compare audit JSON, consolidate states, gate outcome, and human report from factory.coverage and coherence.audit. Add a binding-test path that no longer exists and require:

    {"ok": false, "reason": "binding test selection missing", ...}

which is distinct from an existing test with zero overlap. Re-run every current Python import fixture and assert substrate.codemap.compute_overlap has the same truth values as the old private walker.

- [ ] **Step 2: Move audit modules and add a compatibility wrapper.**

Move coverage scope/audit/gate/report/runner/cli to coherence.audit. Replace factory.coverage with warning forwarding modules. In coherence.audit import OverlapResult/compute_overlap only from substrate.codemap; factory.coverage.imports remains a legacy shim but no audit code imports it.

- [ ] **Step 3: Verify codemap audit cutover.**

Run: rtk proxy uv run python -m pytest tests/unit/coverage/test_scope.py tests/unit/coverage/test_imports.py tests/unit/coverage/test_audit.py tests/unit/coverage/test_cli.py -q

Expected: unchanged existing results plus explicit missing-selection findings.

- [ ] **Step 4: Commit.**

    git add src/coherence/audit src/factory/coverage tests/unit/coverage
    git commit -m "refactor(coherence): migrate audit to codemap overlap"

### Task 2: Move measurement harnesses and add native observation payloads

- [ ] **Step 1: Write contract fixtures.**

For a passing, failing, interrupted, and invalid harness result assert:

    envelope = measurement_observation(result, inputs, artifacts)
    assert envelope.facts["schema"] == "measurement/v1"
    assert envelope.outcome == expected

Assert typed facts preserve metric_value, passed, trials, artifacts, and raw references without embedding raw output. Machine and agent_compact projections must have identical outcome, diagnostic codes, and artifact refs; invalid/unknown cannot project to pass.

- [ ] **Step 2: Move harness modules.**

Move harness, sim_harness, playwright_harness, pipeline, report, scorer_registry, assertions, cli, and __main__ to coherence.measurement. Retarget pipeline configuration to substrate.config and register calls to coherence.register. Keep factory.validation document validators in substrate/factory adapters from Increment 1B; do not move them again.

- [ ] **Step 3: Implement adapters.**

Implement coherence.measurement.observations and coherence.simulation.observations using the Increment 1 PayloadRegistry. Register named schemas measurement/v1 and simulation-run/v1. Persist or reference raw output through ArtifactRef only; adapters never decide policy from a compact projection.

- [ ] **Step 4: Verify harness and adapter suites.**

Run:

    rtk proxy uv run python -m pytest tests/unit/validation tests/unit/simulation tests/unit/coherence/test_observation_adapters.py -q
    rtk proxy uv run pyright

Expected: old/new harness results agree and every adapter validates its native facts.

- [ ] **Step 5: Commit.**

    git add src/coherence/measurement src/coherence/simulation/observations.py src/factory/validation tests/unit/validation tests/unit/coherence/test_observation_adapters.py
    git commit -m "refactor(coherence): migrate measurement observations"

### Task 3: Add audit observations and bounded deterministic per-SR review

- [ ] **Step 1: Write controlled concurrency tests.**

Use a fake backend with a barrier and active-worker counter. For three independent SRs assert max active workers is greater than one and no greater than --max-workers; require nonpositive values to fail argument validation. Assert pre-existing verdicts launch no worker, one worker failure yields the current degraded semantics, and two runs with differing completion order produce byte-identical sorted audit/report JSON.

- [ ] **Step 2: Implement serial coordinator plus bounded workers.**

Add --max-workers to coherence audit run, defaulting from an explicit configuration policy. Phase 0 scope/overlap, resume checks, consolidation, and gate remain serial. Submit only missing SR verdicts to a bounded executor; each worker constructs its own PiAgentBackend and atomically writes verdicts/<SR>.json. The coordinator collects futures, sorts SR IDs, appends deterministic tool failures, and is the sole writer of status/report artifacts.

- [ ] **Step 3: Emit audit observations.**

Adapt completed audit reports and per-SR verdicts to audit/v1 envelopes with feature/SR/snapshot refs, typed states, diagnostics, and report ArtifactRefs. A workflow failure produces fail/unknown according to the existing gate state, never a synthetic pass.

- [ ] **Step 4: Run audit suite.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coverage/test_runner.py tests/unit/coverage/test_gate.py tests/unit/coverage/test_cli.py tests/unit/coherence/test_audit_parallel.py tests/unit/coherence/test_observation_adapters.py -q

Expected: concurrency is bounded, resume works, and report ordering is deterministic.

- [ ] **Step 5: Commit.**

    git add src/coherence/audit tests/unit/coverage tests/unit/coherence/test_audit_parallel.py tests/unit/coherence/test_observation_adapters.py
    git commit -m "feat(audit): parallelise deterministic SR review"

### Task 4: Expose canonical coherence groups and verify envelopes

- [ ] **Step 1: Add console group tests.**

Add audit and measurement to coherence.cli GROUPS. Test python -m coherence audit audit FEAT-001 and python -m coherence measurement check with fixture argv, plus old factory module invocations warning and forwarding.

- [ ] **Step 2: Run full Increment 4 verification.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coverage tests/unit/validation tests/unit/simulation tests/unit/coherence -q
    rtk proxy uv run python -m pytest -m unit -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: audit/measurement behaviour is compatible; envelope and compact projection facts agree; complete unit suite passes.

- [ ] **Step 3: Commit.**

    git add src/coherence src/factory tests
    git commit -m "feat(coherence): expose audit and measurement groups"

## Plan Self-review

- Covers TN-09 parallel SR auditing, TN-13 codemap overlap, and remaining audit naming while retaining test/simulation domain semantics.
- Limits parallel execution to independently owned workers and keeps all durable audit report assembly serial and deterministic.

## Review Amendments

Process execution stays factory-owned: factory validation gate runners execute pytest/Playwright and return native results; coherence.measurement owns HarnessResult/TrialResult schemas, readers, reports, and adapters only. Add test-run/v1, experiment/v1, and gate-run/v1 adapters beside measurement/v1, simulation-run/v1, and audit/v1; each content-hashes raw output artifacts.

The audit worker policy is config key audit.max_workers with default 4 and CLI --max-workers override. write_verdict_atomically(run_dir, sr_id, verdict) is the only worker write; coordinator alone writes audit.json, report.json, status transitions, and ordered tool_failures. The adapter registry and test_observation_adapters.py are integration-owned. Increment 4 production work follows Increment 3.
