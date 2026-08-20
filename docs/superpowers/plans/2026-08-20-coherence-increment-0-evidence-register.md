# Coherence Increment 0: Evidence-State Audit and Requirement Register Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make feature coverage audits distinguish missing provenance from recorded empty scope, let an authorised user add a narrowly verifiable historical evidence record, and bootstrap a non-empty repository requirement register without inventing a requirement-to-test binding.

**Architecture:** Keep normal factory run manifests canonical for automated runs. Add a separate, explicitly manual historical evidence-record contract; it refers to a real Git commit range and never pretends to be a run manifest, validation result, or patch capture. Resolve each task to one of three evidence states (missing, empty, present), propagate that state through audit JSON and the reviewer prompt, and preserve reconciliation's rule that missing provenance cannot be repaired automatically. Seed one traceability requirement copied from the canonical high-level requirements document as proposed, so tracing has a real register but does not falsely claim implementation satisfaction.

**Tech Stack:** Python 3.11+, dataclasses and enums, JSON Schema, pathlib/json, subprocess Git through the existing Git abstraction, pytest.

## Invariants

- A missing run manifest is not equivalent to a run manifest whose changed-files list is empty.
- A historical record is author-provided provenance: its commits must exist and its changed files must be derived from that range, never typed in or inferred by reconciliation.
- The new record format is deliberately not evidence/runs/*.json. It must not claim automated validation, a captured patch, agent identity, or a gate outcome.
- reconcile --repair remains unable to resolve missing evidence. Only an explicit evidence record command can make such a task auditable.
- Audit output remains deterministic and machine-readable; a human review prompt receives the same diagnostic state.
- The bootstrap SR is proposed and unbound. trace check may report its declared gap; the acceptance test is that it evaluates a non-empty register rather than silently treating this repository as requirement-free.

## File Structure

**Create:**

- src/factory/evidence/records.py — schema validation, Git-range derivation, atomic persistence, and listing of manual historical records.
- src/factory/schemas/evidence_record.schema.json — the separate v1 manual-record contract.
- tests/unit/evidence/test_records.py
- requirements/SR-001.md — a proposed requirement sourced from the repository's HLR-02.

**Modify:**

- src/factory/evidence/cli.py — add evidence record; leave reconcile repair policy unchanged.
- src/factory/evidence/reconcile.py — recognise a valid manual record as explicit evidence, while retaining missing-evidence diagnostics if none exists.
- src/factory/coverage/scope.py — expose typed per-task evidence state and record paths.
- src/factory/coverage/cli.py — emit evidence-state details and distinguish audit causes.
- src/factory/coverage/runner.py — give the semantic reviewer the same evidence-state explanation.
- tests/unit/evidence/test_cli.py
- tests/unit/evidence/test_reconcile.py
- tests/unit/coverage/test_scope.py
- tests/unit/coverage/test_cli.py
- tests/unit/coverage/test_audit.py
- tests/unit/coverage/test_runner.py
- tests/unit/trace/test_cli_check.py

## Task 1: Introduce a minimal, explicit historical evidence-record contract

**Files:**

- Create: src/factory/schemas/evidence_record.schema.json
- Create: src/factory/evidence/records.py
- Create: tests/unit/evidence/test_records.py

- [ ] **Step 1: Write contract tests before implementation.**

Add fixtures for a completed task T-058 and a real two-commit temporary Git repository. Cover these exact cases:

1. build_historical_record derives a sorted, unique changed_files list from start_commit..result_commit and writes evidence/records/manual-T-058-<result-prefix>.json atomically.
2. A non-existent commit, equal commits, reversed/no-diff range, invalid task ID, a missing task Markdown file, duplicate paths, absolute paths, and a non-SHA Git revision are rejected.
3. load_historical_record rejects malformed JSON, an unknown property, an invalid timestamp, a content hash with the wrong length, and a record whose changed_files no longer equal the declared Git range.
4. list_historical_records(evidence_dir, "T-058") returns valid records newest-first and ignores no malformed record silently: it raises an actionable ValueError naming the bad path.
5. The persisted record has no validation, outcome, patch, transcript, or inferred source fields.

The expected v1 fixture is:

    {
      "schema_version": 1,
      "record_id": "manual-T-058-bbbbbbbbbbbb",
      "task_id": "T-058",
      "recorded_at": "2026-08-20T09:00:00Z",
      "recorded_by": "human@example.invalid",
      "reason": "Recovered completed work from an interrupted session.",
      "start_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "result_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "changed_files": ["src/factory/example.py"],
      "task_sha256": "<64 lowercase hex characters>"
    }

- [ ] **Step 2: Run the focused test and confirm it fails for the absent module.**

Run: rtk proxy uv run python -m pytest tests/unit/evidence/test_records.py -q

Expected: import failure for factory.evidence.records.

- [ ] **Step 3: Add the strict schema and implementation.**

The schema must be Draft 2020-12 with additionalProperties false. Require schema_version 1, a safe record_id, task_id, UTC ISO-8601 recorded_at, nonblank recorded_by and reason, two forty-hex commit IDs, a non-empty changed_files array of unique repository-relative POSIX paths, and task_sha256. Do not include a free-form changed-files escape hatch.

Implement these public interfaces:

    HISTORICAL_RECORD_SCHEMA_VERSION = 1
    build_historical_record(repo_root, task_id, start_commit, result_commit, recorded_by, reason, now=None) -> dict
    write_historical_record(evidence_dir, record) -> Path
    load_historical_record(repo_root, path) -> dict
    list_historical_records(repo_root, evidence_dir, task_id=None) -> list[dict]

Use the repository's existing schema validator and Git execution convention. Resolve and verify both commits before invoking git diff --name-only start result. The writer creates evidence/records, writes a same-directory temporary JSON file, then replaces the final file. Before loading or listing, recompute the task Markdown SHA-256 and Git changed-file set; reject mismatches as stale/invalid provenance. The new module must not import coverage or orchestrator code.

- [ ] **Step 4: Run focused tests and adjacent evidence regressions.**

Run: rtk proxy uv run python -m pytest tests/unit/evidence/test_records.py tests/unit/evidence/test_manifests.py -q

Expected: pass.

- [ ] **Step 5: Commit the isolated contract.**

    git add src/factory/schemas/evidence_record.schema.json src/factory/evidence/records.py tests/unit/evidence/test_records.py
    git commit -m "feat(evidence): add explicit historical records"

## Task 2: Expose the explicit record command and preserve reconciliation authority

**Files:**

- Modify: src/factory/evidence/cli.py
- Modify: src/factory/evidence/reconcile.py
- Modify: tests/unit/evidence/test_cli.py
- Modify: tests/unit/evidence/test_reconcile.py

- [ ] **Step 1: Add failing CLI and reconciliation tests.**

Add a record subcommand test that runs:

    python -m factory.evidence record T-058 --repo <repo> --start <sha> --result <sha> --recorded-by human@example.invalid --reason "Recovered completed work." --json

Assert exit 0, stdout-only JSON containing record_id/task_id/changed_files, and the exact record file. Assert invalid input exits 2 with a concise stderr error and creates no file.

Extend the existing completed-task-without-manifest test into a three-state assertion:

1. A done task without manifest or manual record produces ReconcileKind.MISSING_EVIDENCE and repairable is false.
2. Calling repair_reconciliation does not create a record or manifest.
3. After a valid explicit historical record, reconcile no longer emits MISSING_EVIDENCE for that task; it also does not label the record as an automated run.

- [ ] **Step 2: Run to prove the command is absent.**

Run: rtk proxy uv run python -m pytest tests/unit/evidence/test_cli.py tests/unit/evidence/test_reconcile.py -q

Expected: failing record-command tests, with existing reconcile behavior still passing.

- [ ] **Step 3: Implement the command as an authorised writer.**

In cli.py add record arguments exactly as tested. It must call build_historical_record then write_historical_record; it may not call repair_reconciliation or mutate task status. JSON success includes path relative to repo root. Catch validation/Git/schema errors, print them to stderr, and return 2.

In reconcile.py import only the record-listing/query interface. A valid record makes the task evidence-present for missing-evidence detection; an invalid/stale record becomes a reconciliation diagnostic rather than silently becoming evidence. Do not change repair_reconciliation's handling of ReconcileKind.MISSING_EVIDENCE.

- [ ] **Step 4: Verify manual provenance has not weakened the gate.**

Run: rtk proxy uv run python -m pytest tests/unit/evidence/test_cli.py tests/unit/evidence/test_reconcile.py -q

Expected: all tests pass, including the pre-existing assertion that repair never infers provenance.

- [ ] **Step 5: Commit.**

    git add src/factory/evidence/cli.py src/factory/evidence/reconcile.py tests/unit/evidence/test_cli.py tests/unit/evidence/test_reconcile.py
    git commit -m "feat(evidence): record approved historical provenance"

## Task 3: Carry evidence state through feature-scope resolution

**Files:**

- Modify: src/factory/coverage/scope.py
- Modify: tests/unit/coverage/test_scope.py

- [ ] **Step 1: Add failing scope tests for all three states.**

Extend the coverage-demo helpers to create:

1. T-058 and T-067 with no manifest and no record: evidence_state is missing, changed_files is empty, and record_paths/manifests are empty.
2. A valid normal run manifest with implementation.changed_files: []: evidence_state is empty, and the manifest remains represented.
3. A valid explicit historical record with a changed file: evidence_state is present and the record path plus file appear.
4. Both a normal manifest and a manual record: changed_files is their stable union, evidence_state is present, and both source lists survive.

Assert no test encodes missing as an empty changed_files tuple alone.

- [ ] **Step 2: Run to establish the current conflation.**

Run: rtk proxy uv run python -m pytest tests/unit/coverage/test_scope.py -q

Expected: new tests fail because TaskScope only exposes changed_files and manifests.

- [ ] **Step 3: Add an explicit typed state.**

Define EvidenceState as a str Enum with exactly missing, empty, and present. Extend TaskScope with:

    evidence_state: EvidenceState
    record_paths: tuple[str, ...]

resolve_feature_scope loads normal manifests and valid historical records for each linked task. Its classification is:

- missing: no valid manifest and no valid historical record;
- empty: one or more valid sources exist, but their aggregate changed-files set is empty;
- present: one or more valid sources have at least one changed file.

Keep paths and changed files sorted deterministically. A stale or malformed record must raise the same actionable error as the evidence query; scope resolution must not quietly lose provenance.

- [ ] **Step 4: Run coverage scope and evidence regression tests.**

Run: rtk proxy uv run python -m pytest tests/unit/coverage/test_scope.py tests/unit/evidence -q

Expected: pass.

- [ ] **Step 5: Commit.**

    git add src/factory/coverage/scope.py tests/unit/coverage/test_scope.py
    git commit -m "feat(coverage): distinguish task evidence states"

## Task 4: Make audit diagnostics and reviewer input truthful

**Files:**

- Modify: src/factory/coverage/cli.py
- Modify: src/factory/coverage/runner.py
- Modify: tests/unit/coverage/test_cli.py
- Modify: tests/unit/coverage/test_audit.py
- Modify: tests/unit/coverage/test_runner.py or its existing equivalent

- [ ] **Step 1: Add failing audit JSON tests.**

Build FEAT-NAV-017 with linked done tasks T-058 and T-067 and no evidence. Assert audit JSON contains, per task, task_id, changed_files, manifests, record_paths, and evidence_state. For an SR linked only to them, assert:

    {
      "ok": false,
      "reason": "missing evidence for tasks",
      "missing_task_ids": ["T-058", "T-067"]
    }

Then add an approved record whose Git range changes src/factory/navigator.py. Assert the overlap calculation runs and returns the actual overlap outcome; it must no longer report "no changed files from tasks".

Add an empty-evidence fixture and require the separate reason "recorded evidence has no changed files" with empty_task_ids. It is a valid but non-actionable scope, not missing provenance.

- [ ] **Step 2: Add a failing reviewer-prompt assertion.**

For the missing-evidence feature, compose_audit_prompt must identify the task IDs and say evidence is missing. For present evidence, it must name source type (run manifest or historical record) and changed files. Do not include raw history reason or user identity in the prompt.

- [ ] **Step 3: Implement output changes without changing overlap semantics.**

In cmd_audit, branch on task evidence state before calling compute_overlap:

1. If any linked task is missing, return the missing-evidence diagnostic with its exact IDs.
2. Else if all aggregate files are empty, return the recorded-empty diagnostic.
3. Otherwise call the existing import/overlap computation unchanged.

Add the typed state and source-path fields to the serialised task scope. In runner.py render a compact Evidence section immediately after Changed files. Preserve existing requirements, SR ordering, reviewer instructions, and overlap analysis.

- [ ] **Step 4: Run the complete focused suite.**

Run: rtk proxy uv run python -m pytest tests/unit/coverage/test_scope.py tests/unit/coverage/test_cli.py tests/unit/coverage/test_audit.py tests/unit/coverage/test_runner.py -q

Expected: pass.

- [ ] **Step 5: Commit.**

    git add src/factory/coverage/scope.py src/factory/coverage/cli.py src/factory/coverage/runner.py tests/unit/coverage
    git commit -m "fix(coverage): report missing task evidence accurately"

## Task 5: Bootstrap a traceable, non-empty requirement register

**Files:**

- Create: requirements/SR-001.md
- Modify: tests/unit/trace/test_cli_check.py

- [ ] **Step 1: Add an integration-style trace fixture before changing the repository.**

Create a temporary project with a requirements/SR-001.md and run factory.trace check against it. Assert the rendered text includes SR-001 and does not report a zero-node/empty register. The test must allow the expected non-zero exit for the intentionally pending proposed SR; it validates the graph input and diagnostic, not premature gate success.

- [ ] **Step 2: Add the minimal proposed SR, copied from the canonical HLR.**

Create requirements/SR-001.md using the requirements parser's existing YAML/frontmatter format:

    ---
    id: SR-001
    title: "Explicit lifecycle traceability"
    statement: "Where corresponding artifacts exist, the factory shall support navigation across system requirement, feature/design decision, implementation, validation definition, experiment/simulation run, metric, evidence, and current validation state through explicit declared relations."
    domain: behavioral
    upstream: []
    source: "docs/superpowers/plans/engineering-context/00-high-level-requirements.md#HLR-02"
    ---

Use exactly this human-authored statement from docs/superpowers/plans/engineering-context/00-high-level-requirements.md HLR-02:

    Where corresponding artifacts exist, the factory shall support navigation across system requirement, feature/design decision, implementation, validation definition, experiment/simulation run, metric, evidence, and current validation state through explicit declared relations.

Do not add a binding block: its absence is the register's explicit proposed state. Do not add a fabricated task relation or implementation evidence. In the Markdown body, cite the source document and HLR-02 for humans; do not create a trace edge to HLR-02 because trace does not model HLR nodes.

- [ ] **Step 3: Verify the real register and report its initially open gap.**

Run:

    rtk proxy uv run python -m factory.requirements status --requirements-dir requirements
    rtk proxy uv run python -m factory.trace check --project-root .

Expected: requirements status identifies SR-001; trace check describes SR-001's real pending/proposed status and must not treat the register as empty. The second command can return 1 because the requirement has deliberately not been implemented and bound.

- [ ] **Step 4: Run regression checks.**

Run: rtk proxy uv run python -m pytest tests/unit/requirements tests/unit/trace/test_cli_check.py -q

Expected: pass.

- [ ] **Step 5: Commit.**

    git add requirements/SR-001.md tests/unit/trace/test_cli_check.py tests/unit/requirements
    git commit -m "docs(requirements): bootstrap repository trace register"

## Final Verification and Acceptance

- [ ] **Step 1: Run the increment test suite and static checks.**

Run:

    rtk proxy uv run python -m pytest tests/unit/evidence tests/unit/coverage tests/unit/requirements tests/unit/trace -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright
    rtk proxy uv run python -m factory.coverage audit FEAT-NAV-017 --project-root .
    rtk proxy uv run python -m factory.trace check --project-root .

Expected: unit/lint/type checks pass; audit identifies missing evidence for T-058/T-067 before an explicit record and calculates overlap after one; trace runs against SR-001 and honestly reports any unresolved proposed link.

- [ ] **Step 2: Inspect the diff and commits.**

Run:

    rtk git diff --check HEAD~5..HEAD
    rtk git status --short

Expected: no whitespace errors and no staged or unintended files.

## Plan Self-review

- This implements original increment 0 unchanged in intent: evidence-first audit, an explicit recovery path, and a repository requirement-register bootstrap.
- The only design addition is the manual record's narrow authority boundary. It avoids abusing the rich run-manifest schema to manufacture historical test or validation provenance.
- It deliberately does not auto-resolve stale or missing historical evidence; that remains provenance-blocked under the later freshness architecture.
