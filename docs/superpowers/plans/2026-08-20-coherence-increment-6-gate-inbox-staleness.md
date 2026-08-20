# Coherence Increment 6: Gate Protocol, Inbox, and Staleness Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every assurance gate require an explicit durable decision, compute a single non-authoring inbox, preserve/expire deferrals, and route unresolved freshness safely.

**Architecture:** coherence.gate owns a versioned DecisionFile and atomic store; existing coverage and human-review flows adapt to it without conflating code review annotations with gate decisions. coherence.inbox derives items from source artifacts on read and calls no writer itself. Deferrals accept legacy strings and structured data; expiration creates an inbox item but never mutates authored intent. Freshness routes authoritative/provenance-blocked items to their owner command or blocker.

**Tech Stack:** Python 3.11+, dataclasses, JSON Schema, atomic files, datetime, pytest, TypeScript renderer tests.

---

## Execution Coordination

- Prerequisites: Increment 1 freshness recipes, Increment 4 producer observations, Increment 5 status contract.
- Parallel after DecisionFile schema freezes: pure gate model/store, backward-compatible deferral reader, inbox collectors, and TypeScript renderer.
- Serial: gate store then coverage runner adoption; final inbox/status integration after owner-writer adapters exist.
- HumanReviewGate wire format is not changed until its adapter regressions pass.

## File Structure

**Create:** src/coherence/gate/{__init__,model,store,service}.py, src/coherence/inbox.py, src/coherence/deferrals.py, src/coherence/staleness.py, tests/unit/coherence/{test_gate,test_inbox,test_deferrals,test_staleness_routing}.py.

**Modify:** src/coherence/audit/runner.py, src/factory/orchestrator/human_review.py, src/coherence/{trace,register}/write.py and readers, src/coherence/status.py, relevant Pi review renderer, tests/unit/{coverage,requirements,trace,orchestrator}.

### Task 1: Define and persist explicit decisions

- [ ] **Step 1: Write failing DecisionFile tests.**

Use:

    DecisionFile(
      gate_id="coverage:FEAT-001",
      artifact_ref="artifact:coverage-reviews/FEAT-001/report.json",
      decisions=(Decision("SR-001", "accept"),),
      decided_at="2026-08-20T00:00:00Z",
      decided_by="human@example.invalid",
    )

Reject an empty decision set, unknown decision, reject/defer without nonblank reason, defer without ISO review_after, duplicate item IDs, and non-atomic/corrupt reload. Existing valid file must short-circuit re-prompt.

- [ ] **Step 2: Implement model/store/service.**

Implement frozen Decision, DecisionFile, load_decision, write_decision, and resolve_gate. Writes use same-directory temporary replace. resolve_gate returns blocked when no decision and unattended mode is true; --no-gates is the sole explicit opt-out.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_gate.py -q
    git add src/coherence/gate tests/unit/coherence/test_gate.py
    git commit -m "feat(coherence): persist explicit gate decisions"

### Task 2: Adapt coverage gates without changing annotation review

- [ ] **Step 1: Write failing coverage gate tests.**

Assert the former 300-second timeout no longer produces a human-reviewed report without a DecisionFile. An unattended run without decision exits nonzero; an existing valid decision resumes without a prompt; --no-gates remains explicit. Assert orchestrator human-review decision JSON stays byte-compatible.

- [ ] **Step 2: Implement adapters.**

Replace coherence.audit runner timeout logic with coherence.gate.resolve_gate and map per-SR verdict items to DecisionFile entries. Keep factory/orchestrator HumanReviewGate separate; add an adapter only where its result is represented as a gate item.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coverage/test_runner.py tests/unit/coverage/test_gate.py tests/unit/orchestrator/test_human_review.py tests/unit/coherence/test_gate.py -q
    git add src/coherence/audit src/factory/orchestrator/human_review.py tests/unit
    git commit -m "feat(gate): require decisions for coverage finalisation"

### Task 3: Migrate deferrals compatibly

- [ ] **Step 1: Write legacy/structured read tests.**

Require the reader to accept:

    trace_deferred: "reason"

and:

    trace_deferred:
      reason: "reason"
      review_after: "2026-09-01T00:00:00Z"
      decided_at: "2026-08-20T00:00:00Z"
      decided_by: "human@example.invalid"

Assert both render the same present deferral; only structured due deferrals appear expired. Unknown shapes are rejected, not treated current.

- [ ] **Step 2: Implement reader-first migration.**

Add a shared parse_deferral value object. Retarget trace/register/coverage readers before writers. Extend defer CLI with --review-after; old calls still write/read legacy-compatible values. Expiration never clears frontmatter.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/requirements/test_write.py tests/unit/requirements/test_cli.py tests/unit/trace/test_write.py tests/unit/trace/test_model_nodes.py tests/unit/trace/test_gaps.py tests/unit/coverage/test_scope.py tests/unit/coherence/test_deferrals.py -q
    git add src/coherence tests/unit
    git commit -m "feat(coherence): support expiring deferrals"

### Task 4: Compute inbox and route blocked freshness

- [ ] **Step 1: Write source collector tests.**

Build fixtures for coverage reports, session review suggestions, KB candidates, expired deferrals, and stale register bindings. Assert InboxItem(id, source, kind, ref, summary, evidence, resolve_cmd, review_after) is stable-sorted, has no duplicate ID, and creates no new file. Assert authoritative_gate staleness maps to owning resolve_cmd and provenance_blocked maps to a blocker without resolver execution.

- [ ] **Step 2: Implement pure collectors.**

Implement coherence.inbox.list_items(root, now) reading all named sources and coherence.staleness.route(result). Inbox does not call doctor, trace, register, or KB writers; resolve_cmd is informational.

- [ ] **Step 3: Integrate status and renderer.**

Add inbox triage and status counts from the pure items. The Pi renderer consumes DecisionFile/InboxItem JSON only. Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_inbox.py tests/unit/coherence/test_staleness_routing.py tests/unit/coherence/test_deferrals.py -q
    rtk proxy npm test --prefix pi-ext/factory-watch -- review-protocol review-model coverage-run-command

- [ ] **Step 4: Commit.**

    git add src/coherence/inbox.py src/coherence/staleness.py src/coherence/status.py pi-ext/factory-watch tests/unit/coherence
    git commit -m "feat(coherence): compute triage inbox and stale routing"

### Task 5: Verify Increment 6

- [ ] **Step 1: Run gates and checks.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence tests/unit/coverage tests/unit/requirements tests/unit/trace tests/unit/orchestrator -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: no finalisation without a decision; every input source appears in inbox; blocked freshness names ownership.

## Plan Self-review

- Covers the original unified gate, inbox, expiring deferral, and unresolved-staleness requirements without making inbox an author or resolver.

## Review Amendments

DecisionFile has schema=1 and is stored as <run_dir>/gate-decisions/<gate_id>.json; load_decision(path) returns a typed corrupt-file diagnostic, write_decision(run_dir, file) validates then atomically replaces. The Pi renderer writes this file through the same validated service. Item IDs are coverage:<run>:proposal:<id>, coverage:<run>:warning:<id>, doctor:<id>, trace:<id>, or review:<id>; accept/reject/defer never author a requirement/trace change, and owning writers apply any follow-up action.

Adopt the DecisionFile adapter for coverage, doctor proposals, trace-gap review, and HumanReviewGate. Human review maps approve to accept and reject to reject while retaining review-decision.json compatibility. Inbox collectors start only after the deferral parser and staleness source are final. unresolved_staleness(root) performs the documented guarded-read/status sweep and exposes recorded StalenessObservation/ResolutionBlocker items; inbox reads that sweep, never executes a resolver.
