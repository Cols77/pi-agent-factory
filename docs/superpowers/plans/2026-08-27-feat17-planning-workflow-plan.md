---
id: PLAN-FEAT-017-MATURE-PLANNING-WORKFLOW
title: "FEAT-017 Mature Planning Workflow Implementation Plan"
status: draft
spec_ref: docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md
---

# FEAT-017 Mature Planning Workflow Implementation Plan

> **For Hermes:** Use subagent-driven-development to implement this plan task-by-task. This
> document is a roadmap, not permission to execute, commit, push, merge, adopt SRs, or start
> downstream work.

**Goal:** Implement a host-neutral FEAT-017 planning compiler that captures exact intent, authors
and verifies a real provisional specification, derives and reviews one run-local candidate SR set,
authors and verifies an implementation plan, materializes typed tasks, closes bidirectional
traceability, enforces explicit human boundaries, optionally transports the planning lifecycle over
Hermes Kanban, and emits a validated hash-bound handoff with `starts_automatically: false`.

**Architecture:** Coherence/substrate remains authoritative for canonical artifacts, schemas,
producers' read-back and hashes, provenance, traceability, decisions, and fail-closed gates. Hermes
Kanban is an optional durable transport projection for the planning stages; it owns lifecycle state,
dependencies, attempts, workspaces, and reclaim, but is not a second execution scheduler. Pi and
Hermes adapters provide conversation, backend/model capabilities, human prompts, and handoff
presentation without duplicating planning policy. FEAT-018, FEAT-019, and FEAT-020 remain distinct
capability boundaries.

**Tech Stack:** Python 3.11, dataclasses, pathlib, strict JSON/YAML/frontmatter parsing, SHA-256,
argparse, pytest, Ruff, Pyright, TypeScript/Vitest for the host adapter, the existing
`AgentBackend` seam, existing Coherence trace/register/gate machinery, filesystem-first artifacts,
and the existing `plan_to_tasks` parser/writer. Do not add a runtime dependency without a reviewed
need and a focused test.

---

## 1. Scope, ownership, and current baseline

### 1.1 Contract frozen by the authority spec

The canonical contract is
`docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md`. It fixes this
lifecycle and no implementation may reorder it:

```text
intent capture
  -> real provisional-spec authoring, read-back, and hash
  -> spec-alignment review
  -> one run-local candidate SR derivation and adversarial review
  -> real implementation-plan authoring, read-back, and hash
  -> task materialization
  -> cross-artifact and bidirectional traceability gates
  -> human boundaries, warning disposition, consent, and canonical adoption
  -> final gates, including the FEAT-018 capability check
  -> validated handoff
```

The three semantic checkpoints are therefore:

1. `PLANNING_ALIGNMENT` / `spec_alignment`, immediately after the real spec producer;
2. `CANDIDATE_SR_ALIGNMENT` / `candidate_sr_alignment`, after the single candidate derivation and
   before plan authoring;
3. `CROSS_ARTIFACT_ALIGNMENT` / `cross_artifact_alignment`, after plan authoring and task
   materialization.

Any previous text that put SR derivation after the plan, or treated a late SR pass as the source of
truth, is superseded. Do not preserve that order in code, tasks, graph nodes, or tests. Do not add a
second independent candidate-SR derivation. Do not create a separate hand-authored verification
plan; implementation and verification tasks live in this plan and a derived coverage report may
summarize them.

### 1.2 Ownership boundaries

- FEAT-017 owns planning compilation and may create an optional planning-stage Hermes Kanban graph.
- Coherence owns canonical artifacts, provenance, hashes, semantic reports, trace/register/gate
  decisions, warning disposition, consent validation, and final truth.
- Hermes Kanban owns durable transport state only: root/stage cards, dependencies, assignment,
  workspace claims, attempts, heartbeats, retry/reclaim, and `needs_input` transport.
- FEAT-018 owns validation of the governed execution proposal/expected execution graph before
  implementation. This plan adds only an honest capability seam/check.
- FEAT-019 owns cross-host conformance.
- FEAT-020 may optimize only a graph already validated by FEAT-018.
- Pi/Hermes adapters own conversation, native model catalog validation, user choice, presentation,
  and new-session creation. They do not own gates or consent.

This feature has no nested subfeatures. A split boundary stops for a human choice of scope and
sequential workflow/worktree handling. The implementation must never silently create or overwrite a
canonical `FEAT-*` file or supplied FEAT baseline.

### 1.3 Current baseline and explicit non-claims

Implementation must begin by recording the baseline, not by treating existing artifacts as proof:

- `src/coherence/planning/bootstrap.py` and `coherence plan bootstrap --decompose` consume supplied
  intent/spec/plan paths and can call the existing decomposer. They do not yet constitute the real
  provisional-spec and plan producers required here.
- `src/substrate/ledger/plans.py` parses `### Task N:` sections and writes basic task records. It
  does not yet guarantee source-spec/SR links, typed relationships, exact test commands, or
  implementation evidence obligations.
- `src/coherence/planning/workflow.py` and `src/coherence/planning/semantic.py` currently expose
  an older stage vocabulary/order. The implementation must move them to the three checkpoints in
  section 1.1; current behavior is not silently accepted as the final contract.
- `tests/integration/coherence/test_planning_dogfood.py` currently builds a consumer fixture by
  copying pre-existing spec and plan artifacts. That proves consumer validation only. The final
  dogfood must invoke the real producers and observe their writes/read-backs.
- `PlanningWorkflow.accept_warning` currently permits arbitrary in-memory acceptance state. It is
  not a human decision mechanism and must be replaced or made incapable of bypassing validated
  warning gates.
- The existing `.factory/planning/feat17-finalized-planning` consent/evidence hashes are stale for
  this final contract. Treat that as a fail-closed finding requiring clean re-derivation and fresh
  exact human consent. Do not edit the old snapshot to manufacture success.
- No FEAT-018/019/020 capability is assumed to exist because this plan names it.

Known repository-wide register, trace, type, or test debt must be reported separately from new
FEAT-017 failures. A fixture or current dirty artifact is not human consent or implementation
evidence.

## 2. Inputs, artifacts, and target contracts

### 2.1 Run inputs and evidence paths

Every run has a safe `run_id`, a selected project root, and an input manifest. The initial
implementation retains these paths:

```text
.intent/intent.json
.factory/planning/<run-id>/capture/events.jsonl
.factory/planning/<run-id>/state.json
.factory/planning/<run-id>/resolution-events.jsonl
```

The run may use schema-one intent input, but the canonical internal representation and new
materialization must preserve schema-two provenance fields: exact prompt, question/source/sequence,
structured brief, capture status, redactions, challenges, challenge responses, unresolved questions,
and decision provenance. Every review packet, producer record, task record, and final handoff binds
its input paths and hashes.

Planned run evidence includes:

```text
.factory/planning/<run-id>/spec-authoring.json
.factory/planning/<run-id>/candidate-sr-derivation.json
.factory/planning/<run-id>/reviews/<checkpoint>/<attempt>.json
.factory/planning/<run-id>/plan-authoring.json
.factory/planning/<run-id>/task-materialization.json
.factory/planning/<run-id>/traceability.json
.factory/planning/<run-id>/warning-decisions.json
.factory/planning/<run-id>/sr-consent.json
.factory/planning/<run-id>/feature-boundary-decision.json
.factory/planning/<run-id>/final-gates.json
.factory/planning/<run-id>/handoff.json
.factory/planning/<run-id>/handoff.md
.factory/planning/<run-id>/kanban-run.json       # only when optional transport is requested
```

Run-local evidence is derived and immutable by attempt. It never silently replaces canonical
source artifacts or human decisions.

### 2.2 Real producer interface

The mature path must expose typed host-neutral operations, implemented behind the existing
`AgentBackend` protocol or a compatible injected seam. The exact Python names may be selected
when import boundaries are verified, but the behavior is mandatory. The planned operations are:

```python
produce_provisional_spec(
    *, project_root, run_id, intent_path, repository_facts,
    output_path, backend, role, input_hashes
) -> ProducedArtifact

produce_implementation_plan(
    *, project_root, run_id, intent_path, spec_path,
    candidate_sr_path, repository_facts, output_path,
    backend, role, input_hashes
) -> ProducedArtifact
```

A `ProducedArtifact` records output path, output SHA-256, input hashes, producer role/session,
attempt, and read-back validation. The producer invokes the injected backend, validates structured
output, writes atomically within the approved path, reads the exact file back, parses it strictly,
and only then returns success. A prompt, a caller-supplied existing path, or a copied fixture is
not a producer.

### 2.3 Spec, candidate SR, plan, and task contracts

The provisional spec is the canonical semantic authority for the run. It has strict frontmatter
(`id`, `title`, `status`), stable anchors, explicit intent/challenge coverage, scope and non-goals,
provisional/unresolved state, and implementation and verification obligations. It cannot claim
human consent, canonical SR adoption, or downstream execution.

The one candidate-SR record is run-local and includes schema, run ID, source-spec path/hash,
derivation revision, candidate IDs/statements/anchors, evidence needed, full-context digest,
non-SR classifications, review hash, and feature-boundary outcome. Its adversarial review must
explicitly cover duplicate, conflict, unsupported-claim, compatibility, missing-obligation,
complete-context, and feature-boundary cases. A correction is a new immutable revision in this
single derivation lineage, not another independent derivation.

The implementation plan has `spec_ref` and candidate-set provenance. Every task section contains:

- objective and implementation scope;
- exact files to create/modify/test;
- dependency/order;
- an observed RED/GREEN or documentation-verification procedure;
- exact validation commands and expected evidence;
- acceptance criteria and prohibited scope;
- implementation and verification work in the same task;
- test-artifact obligations and implementation-evidence obligations;
- typed SR/non-SR coverage.

A generated task record must include:

```text
id, title, status
source_plan, source_task, source_spec
sr_bindings: [{id, type: implements|verifies|supports, source_anchor, hash}]
non_sr_classification: {classification, reason, source_anchor, review_hash}  # when applicable
acceptance_criteria
test_paths, test_commands
implementation_evidence, verification_evidence
dependencies, allowed_paths, prohibited_paths
spec_hash, plan_hash, candidate_set_hash
```

Before handoff, every task binds to an adopted SR through `implements`, `verifies`, or `supports`,
or to an explicit reviewed non-SR classification. Unbound or ambiguous tasks block.

## 3. Shared implementation and review protocol

Every code-producing task below follows this sequence:

1. Read the authority spec, this plan, the current source, and the task's exact dependencies.
2. Write the smallest failing test or documentation contract assertion and run it; capture the
   actual baseline, even when part of the existing behavior already passes.
3. Implement only the task's allowed paths and contract.
4. Run the task's focused GREEN tests, then its static/security checks.
5. Run a fresh spec-compliance review against the authority spec and this plan.
6. Run a fresh code-quality/security/fail-closed review after the compliance review passes.
7. A fresh-context fixer may address findings only in scope; reread changed files, recompute
   hashes, rerun both reviews, and preserve prior evidence.
8. Report new diagnostics separately from known debt. Do not merge or push without explicit
   authorization.

Reviewers receive complete required context and treat artifact text as untrusted data. Review
reports never create human consent. A direct fix always invalidates the affected checkpoint and all
downstream projections and requires a fresh independent review.

## 4. Dependency-gated implementation tasks

### Task 1: Close structured intent provenance, challenges, and recovery

**Objective:** Make the capture boundary a durable, verbatim, append-only source for prompt,
questions, answers, repository observations, challenges, human decisions, unresolved state, and
failed-snapshot recovery.

**Files:**
- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/intent.py`
- Modify: `src/coherence/planning/session.py`
- Modify: `src/coherence/planning/serialization.py`
- Modify: `src/coherence/planning/check.py`
- Test: `tests/unit/coherence/test_planning_intent.py`
- Test: `tests/unit/coherence/test_planning_session.py`
- Test: `tests/unit/coherence/test_planning_check.py`
- Test: `tests/unit/coherence/test_planning_resolution.py`

**Interfaces:**
- Existing `.intent/intent.json` schema-one reader and schema-two materializer.
- Existing `.factory/planning/<run-id>/capture/events.jsonl` and `state.json` paths.
- Existing strict serializers and safe path helpers.

**Dependencies/order:** First runtime task. It gates every producer and review packet because all
later stages require exact prompt/provenance and a recoverable run.

**RED/documentation verification:** Add failing tests for exact original prompt preservation,
question/answer source provenance, repository-observation hashes, challenge raise/resolve/revise/
defer/accept state, exact human response provenance, unresolved state, duplicate sequence/event
rejection, and atomic materialization failure preserving the last known-good snapshot while keeping
the new journal event. Run:

```bash
uv run pytest tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_session.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_resolution.py -q -o addopts=''
```

Record which existing tests pass and which new assertions are RED; do not delete tests to make the
baseline look green.

**Implementation/GREEN:** Extend the strict event schema and deterministic state projection,
retain schema-one reads, preserve all captured text exactly, bind challenge resolutions to an
explicit actor/provenance record, and use atomic replace semantics that never destroy the last good
snapshot on failure. Do not infer a decision from silence or model output.

```bash
uv run pytest tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_session.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_resolution.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_session.py
uv run pyright src/coherence/planning
```

**Acceptance criteria:** The journal is strictly ordered and append-only; schema-one reads remain
compatible; every challenge/decision/unresolved value is queryable with exact provenance; unsafe,
malformed, duplicate-key, non-finite, non-UTF-8, or secret-shaped data fails closed; a failed
snapshot replacement preserves the prior bytes; and state/hash evidence names the journal and
intent sources.

**Prohibited scope:** Do not author a specification or plan, allocate/adopt SRs, write consent or
warning decisions, alter FEAT files, create Kanban cards, invoke downstream work, or modify the two
canonical documents except for a separately authorized verified-fact update.

### Task 2: Implement and test the real provisional-spec producer

**Objective:** Replace prompt-only or supplied-path assumptions with a concrete injected-backend
producer that authors a provisional authority spec, reads it back, validates it, and records its
hash.

**Files:**
- Create: `src/coherence/planning/producers.py`
- Modify: `src/coherence/planning/bootstrap.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/cli.py`
- Modify: `src/factory/orchestrator/backends.py` only if a non-breaking typed producer seam is required
- Test: `tests/unit/coherence/test_planning_producers.py`
- Modify: `tests/unit/coherence/test_planning_bootstrap.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`

**Interfaces:**
- Existing `AgentBackend`/`AgentResult` seam in `src/factory/orchestrator/backends.py` and
  `src/substrate/agents/model.py`.
- Existing strict frontmatter/hash/path helpers in `src/coherence/planning/`.
- Canonical spec target under `docs/superpowers/specs/<approved-name>.md`.

**Dependencies/order:** Depends on Task 1. Must complete before spec alignment and candidate-SR
derivation. The mature entry point may accept an output name, but it must not treat an existing
spec file as successful authoring.

**RED/documentation verification:** Add tests that invoke a fake backend through the producer and
assert it writes a real spec; that a missing backend result, malformed frontmatter, unsupported
claim, output-path escape, stale input hash, or write/read-back mismatch blocks; and that a test
with only a caller-supplied spec path is rejected as not having run the producer. Run:

```bash
uv run pytest tests/unit/coherence/test_planning_producers.py tests/unit/coherence/test_planning_bootstrap.py -q -o addopts=''
```

**Implementation/GREEN:** Validate a structured producer result, restrict the role to the exact
spec output and run evidence paths, atomically write the output, read it back, validate frontmatter
and stable anchors, compute SHA-256, and persist `spec-authoring.json`. Expose a stable status
result to the host. Keep agent invocation behind the injected backend; the Python writer must not
launch a shell or provider itself.

```bash
uv run pytest tests/unit/coherence/test_planning_producers.py tests/unit/coherence/test_planning_bootstrap.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning src/factory/orchestrator tests/unit/coherence/test_planning_producers.py
uv run pyright src/coherence/planning src/factory/orchestrator
```

**Acceptance criteria:** A fake producer invocation creates the spec from captured intent, returns
and persists exact input/output hashes, succeeds only after read-back/strict validation, preserves
provisional and unresolved state honestly, and cannot write outside its scope or fabricate approval.
A consumer of a pre-created spec is covered separately and never counted as producer coverage.

**Prohibited scope:** Do not derive SRs, author the implementation plan, materialize tasks, write
canonical FEAT/SR/bundle files, write consent/warning decisions, or dispatch Kanban/downstream work.

### Task 3: Derive one run-local candidate SR set and review it adversarially before planning

**Objective:** Add one deterministic candidate-SR derivation lineage and an adversarial review that
runs before plan authoring with complete current SR context.

**Files:**
- Create: `src/coherence/planning/candidate_sr.py`
- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/semantic.py`
- Modify: `src/coherence/planning/workflow.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/navigate/requirements_context.py`
- Test: `tests/unit/coherence/test_planning_candidate_sr.py`
- Modify: `tests/unit/coherence/test_planning_semantic.py`
- Modify: `tests/unit/coherence/test_planning_workflow.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`

**Interfaces:**
- Reviewed provisional spec and `spec-authoring.json` from Task 2.
- Existing read-only Coherence trace/navigation context.
- Existing immutable semantic packet/report and resolution journal machinery.

**Dependencies/order:** Depends on Tasks 1 and 2. It must run after `spec_alignment` and before any
implementation-plan producer. Update `REVIEW_STAGES` and workflow state to
`spec_alignment`, `candidate_sr_alignment`, and `cross_artifact_alignment`. Do not preserve the
old late-derivation stage as an alias that can run after the plan.

**RED/documentation verification:** Add tests proving candidate derivation cannot run without a
hash-matching reviewed spec, produces exactly one run-local candidate set, and provides every
non-deleted SR with status/source/trace context. Add adversarial cases for duplicate and
near-duplicate obligations, contradictory statements/status/ownership, unsupported claims,
schema/register compatibility, missing independently governable obligations, explanatory prose,
complete-context digest, feature splits, and supplied FEAT baseline preservation. Assert that a
second independent derivation request is rejected or treated as a revision of the same lineage.

```bash
uv run pytest tests/unit/coherence/test_planning_candidate_sr.py tests/unit/coherence/test_planning_semantic.py tests/unit/coherence/test_planning_workflow.py -q -o addopts=''
```

**Implementation/GREEN:** Write the candidate record only under the run directory, bind it to the
reviewed spec and full-context digest, make candidate IDs/anchors/relations deterministic, and
persist adversarial findings. Allow only scoped revision attempts within this one derivation
lineage; every revision invalidates its review and downstream artifacts. Keep canonical SR
registration/adoption for the later human boundary.

```bash
uv run pytest tests/unit/coherence/test_planning_candidate_sr.py tests/unit/coherence/test_planning_semantic.py tests/unit/coherence/test_planning_workflow.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning src/coherence/navigate tests/unit/coherence/test_planning_candidate_sr.py
uv run pyright src/coherence/planning src/coherence/navigate
```

**Acceptance criteria:** Candidate derivation is observable before plan authoring, one candidate set
and revision lineage is hash-bound, every required adversarial category is represented in the review
contract, all current non-deleted SR context is supplied, duplicates/conflicts are retained for
review rather than hidden, and no candidate becomes canonical without later exact human consent.

**Prohibited scope:** Do not author a plan or task, modify canonical requirements/FEAT/bundle
records, grant consent, accept warnings, create nested subfeatures, or invoke FEAT-018/019/020.

### Task 4: Implement and test the real implementation-plan producer

**Objective:** Author an implementation plan from the reviewed provisional spec and candidate SR
set, then read back, validate, and hash it before task materialization.

**Files:**
- Modify: `src/coherence/planning/producers.py`
- Modify: `src/coherence/planning/bootstrap.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/cli.py`
- Modify: `src/substrate/ledger/plans.py` only for shared parser validation needed by the producer
- Test: `tests/unit/coherence/test_planning_producers.py`
- Modify: `tests/unit/coherence/test_planning_check.py`
- Modify: `tests/unit/coherence/test_planning_workflow.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`

**Interfaces:**
- Task 2 producer seam and strict artifact writer.
- Reviewed candidate record and `candidate_sr_alignment` report from Task 3.
- Existing `parse_plan_tasks` grammar in `src/substrate/ledger/plans.py`.
- Canonical plan target under `docs/superpowers/plans/<approved-name>.md`.

**Dependencies/order:** Depends on Task 3. It must run only after candidate-SR review is clean or
has an explicit permitted human disposition. It must complete before task materialization.

**RED/documentation verification:** Add a fake-backend producer test that fails until the plan
contains both implementation and verification sections, explicit test-artifact obligations, exact
commands, acceptance criteria, prohibited scope, source-spec reference, candidate-set provenance,
and implementation-evidence obligations. Test malformed output, stale candidate hash, duplicate
task numbers, empty `Files:` blocks, and read-back mismatch.

```bash
uv run pytest tests/unit/coherence/test_planning_producers.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_workflow.py -q -o addopts=''
```

**Implementation/GREEN:** Require the reviewed candidate record as an input, invoke the injected
plan-authoring backend, atomically write the selected plan target, read it back, validate frontmatter
and every task section, compute the exact plan hash, and persist `plan-authoring.json`. Keep
implementation and verification obligations in one plan; a coverage report may be derived later.
Do not silently reuse a pre-existing plan as producer success.

```bash
uv run pytest tests/unit/coherence/test_planning_producers.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_workflow.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning src/substrate/ledger tests/unit/coherence/test_planning_producers.py
uv run pyright src/coherence/planning src/substrate/ledger
```

**Acceptance criteria:** A real producer invocation creates a hash-bound plan from the reviewed
candidate set; read-back and strict validation are mandatory; every plan task states implementation
and verification work together; exact test paths/commands and evidence obligations are present;
and an existing supplied plan or plan-shaped prompt cannot bypass authoring.

**Prohibited scope:** Do not materialize generated tasks, alter canonical SR/FEAT/bundle files,
write human decisions, create a second verification plan, or start implementation/downstream work.

### Task 5: Materialize typed tasks with complete source and evidence contracts

**Objective:** Make plan-to-task generation idempotently create task records that preserve source
spec/plan/SR links, typed relations or reviewed non-SR classification, acceptance criteria, exact
tests/commands, and evidence obligations.

**Files:**
- Create: `src/coherence/planning/task_materialization.py`
- Modify: `src/substrate/ledger/plans.py`
- Modify: `src/coherence/planning/check.py`
- Modify: `src/coherence/planning/bootstrap.py`
- Test: `tests/unit/coherence/test_planning_task_materialization.py`
- Modify: `tests/unit/test_plan_to_tasks.py`
- Modify: `tests/unit/coherence/test_planning_check.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`

**Interfaces:**
- Task 4's hash-bound plan and `parse_plan_tasks` parser.
- Existing filesystem-first task writer and selected-plan parity behavior.
- Candidate/adopted SR and reviewed non-SR binding schemas.

**Dependencies/order:** Depends on Task 4. It runs after plan read-back and before the
`cross_artifact_alignment` checkpoint. It must not pre-create spec, plan, SR, FEAT, or bundle
artifacts merely to satisfy a consumer check.

**RED/documentation verification:** Add tests that fail for missing source spec/plan links,
missing or ambiguous SR bindings, unreviewed non-SR classification, missing acceptance criteria,
missing exact test paths/commands, missing implementation/verification evidence, wrong hashes,
duplicate IDs/source numbers, foreign-plan records, and non-idempotent reruns.

```bash
uv run pytest tests/unit/coherence/test_planning_task_materialization.py tests/unit/test_plan_to_tasks.py tests/unit/coherence/test_planning_check.py -q -o addopts=''
```

**Implementation/GREEN:** Extend the existing writer or add the narrowest wrapper so each plan task
maps to exactly one generated record, with deterministic IDs and source fields. Validate typed
`implements`/`verifies`/`supports` relations against candidate IDs and source anchors, or require a
reviewed non-SR record. Persist `task-materialization.json` with plan/spec/candidate hashes. Reruns
return existing records for the same plan hash/source task and never duplicate them.

```bash
uv run pytest tests/unit/coherence/test_planning_task_materialization.py tests/unit/test_plan_to_tasks.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning src/substrate/ledger tests/unit/coherence/test_planning_task_materialization.py tests/unit/test_plan_to_tasks.py
uv run pyright src/coherence/planning src/substrate/ledger
```

**Acceptance criteria:** One and only one generated task exists per selected plan task; unrelated
plans remain distinguishable; every record has the complete target contract and exact hashes;
running materialization twice is idempotent; missing/ambiguous bindings block; and no task claims
human adoption before the later consent boundary.

**Prohibited scope:** Do not adopt SRs, write canonical requirements/FEAT/bundle files, accept
warnings, alter the execution scheduler, or launch task workers.

### Task 6: Add cross-artifact, bidirectional traceability, and coverage gates

**Objective:** Prove forward and reverse closure from intent through spec, candidate/adopted SR or
reviewed non-SR classification, plan task, generated task, and implementation/verification evidence.

**Files:**
- Create: `src/coherence/planning/traceability.py`
- Modify: `src/coherence/planning/check.py`
- Modify: `src/coherence/planning/gates.py`
- Modify: `src/coherence/planning/semantic.py`
- Modify: `src/coherence/planning/workflow.py`
- Modify: `src/coherence/planning/run.py`
- Test: `tests/unit/coherence/test_planning_traceability.py`
- Modify: `tests/unit/coherence/test_planning_trace_contract.py`
- Modify: `tests/unit/coherence/test_planning_workflow.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`

**Interfaces:**
- Tasks 1–5 canonical and run-local artifacts.
- Existing Coherence trace/register/navigate/gate APIs; no parallel register.
- Existing planning report/hash and semantic review packet contracts.

**Dependencies/order:** Depends on Tasks 1–5. This is the third semantic checkpoint and runs only
after the real plan and typed tasks exist. The resulting trace gate must precede human adoption.

**RED/documentation verification:** Add failing forward and reverse cases: omitted intent decision,
unsupported spec claim, candidate with no spec anchor, spec obligation with no candidate or reviewed
non-SR classification, candidate with no plan task, task with no generated record, generated task
with no exact test/evidence, reverse links to the wrong plan/spec, and stale hashes. Verify that a
derived coverage report does not replace canonical links.

```bash
uv run pytest tests/unit/coherence/test_planning_traceability.py tests/unit/coherence/test_planning_trace_contract.py tests/unit/coherence/test_planning_workflow.py -q -o addopts=''
uv run coherence trace check --project-root .
```

**Implementation/GREEN:** Materialize a deterministic trace report with forward and reverse edges,
source anchors, relationship types, test/evidence paths, and all relevant hashes. Make
`cross_artifact_alignment` consume this report and fail closed on any gap, contradiction, duplicate,
foreign source, or stale artifact. Keep known repository-wide debt as a separately labelled finding.

```bash
uv run pytest tests/unit/coherence/test_planning_traceability.py tests/unit/coherence/test_planning_trace_contract.py tests/unit/coherence/test_planning_workflow.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_traceability.py tests/unit/coherence/test_planning_trace_contract.py
uv run pyright src/coherence/planning
uv run coherence trace check --project-root .
```

**Acceptance criteria:** `cross_artifact_alignment` runs after task materialization; every
independently governable obligation is represented exactly once or has a reviewed non-SR reason;
every candidate/task points back to valid source authority; implementation and verification
artifacts close both directions; and a clean report is impossible with stale or incomplete links.

**Prohibited scope:** Do not write human consent, adopt SRs, disposition warnings, create nested
features, or use Kanban `done` as a substitute for the Coherence trace gate.

### Task 7: Enforce human warning, feature-boundary, consent, and adoption writers

**Objective:** Make every unresolved human boundary explicit and hash-bound, with all security and
operability warnings blocked until resolution or explicit human disposition.

**Files:**
- Modify: `src/coherence/planning/gates.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/cli.py`
- Modify: `src/coherence/gate/model.py` only for a compatible validated decision family
- Modify: `src/coherence/gate/store.py` only for compatible storage/path binding
- Modify: `src/coherence/gate/service.py` only for compatible resolution
- Create/modify: `pi-ext/factory-watch/src/plan-review-command.ts`
- Modify: `pi-ext/factory-watch/src/index.ts`
- Test: `tests/unit/coherence/test_planning_review_resolution.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`
- Test: `pi-ext/factory-watch/test/plan-review-command.test.ts`

**Interfaces:**
- Existing validated `DecisionFile` machinery and read-only planning reports.
- Task 3 candidate-set hash and review hash.
- Task 6 clean cross-artifact/traceability report.
- Human-facing host escalation and consent prompt boundary.

**Dependencies/order:** Depends on Task 6. It runs after cross-artifact gates and before canonical
adoption/final gates. A feature split must stop before any canonical FEAT write.

**RED/documentation verification:** Add tests proving unresolved challenges, feature splits, stale
baselines, security warnings, and operability warnings remain blocked; only a validated human
DecisionFile can disposition a warning; `accept_warning` cannot alter blocking state; semantic
cleanliness, agent/model output, silence, fixture data, and free-text escalation answers cannot
create consent; exact SR consent binds candidate IDs, derivation-review hash, artifact hashes, run
ID, actor, phrase, reason, and timestamp; replayed/tampered/stale decisions fail; and failed current
consent/evidence snapshots require fresh re-derivation and fresh consent.

```bash
uv run pytest tests/unit/coherence/test_planning_review_resolution.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
npm test --prefix pi-ext/factory-watch -- --run test/plan-review-command.test.ts
```

**Implementation/GREEN:** Use existing gate writers rather than a second warning store. Replace
arbitrary in-memory warning acceptance with validation of an exact human decision bound to warning
IDs and current hashes. Add explicit feature-boundary decision writing that preserves supplied
FEAT/SR/bundle bytes until a human authorizes replacement. Add the exact SR consent phrase and
canonical adoption writer only after the candidate review and cross-artifact gate are current.

```bash
uv run pytest tests/unit/coherence/test_planning_review_resolution.py tests/unit/coherence/test_planning_integration.py tests/unit/coherence/test_planning_handoff.py -q -o addopts=''
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run test/plan-review-command.test.ts
uv run ruff check src/coherence/planning src/coherence/gate tests/unit/coherence/test_planning_review_resolution.py
uv run pyright src/coherence/planning src/coherence/gate
```

**Acceptance criteria:** Every security/operability warning blocks until fixed or explicitly human-
dispositioned; no agent state bypasses it; feature boundaries require human selection and sequential
workflow/worktree decisions; supplied baselines are never silently overwritten; canonical adoption
requires fresh exact human consent; and stale consent/evidence is a fail-closed state, not plan
success.

**Prohibited scope:** Do not infer approval, edit old snapshots in place, create nested subfeatures,
start implementation, or dispatch FEAT-018/019/020.

### Task 8: Materialize and reconcile the optional Hermes Kanban planning graph

**Objective:** Add an optional planning-stage Kanban transport projection with durable root/stage
cards, strict dependencies, idempotency, serialized workspaces, retry/reclaim/recovery, and no
silent downstream execution.

**Files:**
- Create: `src/coherence/planning/kanban.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/workflow.py`
- Modify: `src/coherence/planning/cli.py`
- Create: `pi-ext/factory-watch/src/planning-kanban.ts` only if the host has no existing Kanban adapter
- Test: `tests/unit/coherence/test_planning_kanban.py`
- Modify: `tests/unit/coherence/test_planning_workflow.py`
- Test: `pi-ext/factory-watch/test/planning-kanban.test.ts` if a host adapter is added
- Modify: `tests/integration/coherence/test_planning_dogfood.py`

**Interfaces:**
- Hermes Kanban API/adapter, discovered and documented before implementation.
- Coherence run/artifact/gate state from Tasks 1–7.
- Host-neutral stage dispatch seam; no new execution scheduler.

**Dependencies/order:** Depends on Tasks 1–7. Graph materialization is optional and must be
reconciled before the first worker when requested. It may transport the lifecycle but cannot change
its order or authorize downstream work.

**RED/documentation verification:** Add tests for the exact graph:

```text
planning-run -> capture -> provisional-spec-authoring -> spec-alignment
  -> candidate-sr-derivation -> candidate-sr-alignment
  -> implementation-plan-authoring -> task-materialization
  -> cross-artifact-alignment -> human-boundaries-and-adoption
  -> final-gates -> handoff
```

Test persisted root and stage IDs, parent links, contract hash, missing/incomplete-parent blocking,
idempotency-key replay, duplicate-card rejection, serialized shared `dir` workspaces, isolated
worktree reconciliation, timeout/heartbeat/retry/reclaim, interruption resume, `needs_input`
pause/resume, unauthorized path rejection, graph mismatch, and proof that no child or downstream
workflow runs from prose or a Kanban `done` state alone.

```bash
uv run pytest tests/unit/coherence/test_planning_kanban.py tests/unit/coherence/test_planning_workflow.py -q -o addopts=''
```

**Implementation/GREEN:** Persist `.factory/planning/<run-id>/kanban-run.json` with exact stage
contracts: inputs/outputs and hashes, role/assignee, allowed/prohibited paths, workspace mode,
parents, stable idempotency key, attempt/reclaim metadata, blocking reason, completion evidence,
and required Coherence gate. Reconcile actual root/cards/edges against the intended graph before
dispatch and before handoff. Reclaim the same key, append evidence, and never duplicate artifacts
or cards. If the optional capability is unavailable, report a capability block rather than silently
falling back to prose or an execution scheduler.

```bash
uv run pytest tests/unit/coherence/test_planning_kanban.py tests/unit/coherence/test_planning_workflow.py tests/integration/coherence/test_planning_dogfood.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_kanban.py
uv run pyright src/coherence/planning
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run test/planning-kanban.test.ts
```

**Acceptance criteria:** The optional graph has observable root/stage cards and strict edges in the
correct order; materialization is idempotent; writers serialize workspaces; retry/reclaim resumes
without duplicates; human blocks remain `needs_input`; all child dispatch is dependency- and gate-
gated; graph/artifact hashes are reconciled; and the graph never schedules implementation,
FEAT-018 execution, FEAT-019 conformance, FEAT-020 optimization, or health recovery.

**Prohibited scope:** Do not implement a second scheduler, alter Hermes Kanban lifecycle ownership,
use prose as a card, execute downstream work, or mark a Coherence gate green from Kanban state.

### Task 9: Add the FEAT-018 capability seam and honest block behavior

**Objective:** Check whether FEAT-018 can validate the governed execution proposal/expected graph,
block honestly when that capability is unavailable, and keep FEAT-018/019/020 ownership separate.

**Files:**
- Create: `src/coherence/planning/capabilities.py`
- Modify: `src/coherence/planning/gates.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/workflow.py`
- Modify: `src/coherence/planning/handoff.py`
- Test: `tests/unit/coherence/test_planning_capabilities.py`
- Modify: `tests/unit/coherence/test_planning_handoff.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`

**Interfaces:**
- A narrow capability-provider protocol supplied by the host or FEAT-018 integration.
- Final-gate and handoff validation from existing planning modules.
- No assumption that FEAT-018 artifacts are present in this repository.

**Dependencies/order:** Depends on Task 6 and Task 7; it is checked during final gates after human
boundaries and before handoff. Task 8 may include its result in the optional transport record but
cannot implement FEAT-018.

**RED/documentation verification:** Add tests for capability present and validating the expected
governed graph, capability absent, provider error, stale/invalid proposal, and provider that tries
to run implementation. Assert absent/error returns an explicit blocked result and cannot be reported
as FEAT-018 validation or handoff readiness.

```bash
uv run pytest tests/unit/coherence/test_planning_capabilities.py tests/unit/coherence/test_planning_handoff.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
```

**Implementation/GREEN:** Define a read-only capability check with provider/version/contract hash,
proposal/expected-graph hash, and result. Require a current positive FEAT-018 result for handoff
when the governed execution proposal is requested; otherwise surface a named block. Never invoke
execution or let FEAT-020 optimize an unvalidated graph.

```bash
uv run pytest tests/unit/coherence/test_planning_capabilities.py tests/unit/coherence/test_planning_handoff.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_capabilities.py
uv run pyright src/coherence/planning
```

**Acceptance criteria:** FEAT-018 availability and result are explicit and hash-bound; absence or
failure blocks without a false success; FEAT-017 does not claim FEAT-018/019/020 implementation;
FEAT-020 is never called from planning; and the handoff records the capability result.

**Prohibited scope:** Do not implement the governed execution proposal, cross-host conformance,
optimization, an execution scheduler, or any downstream worker.

### Task 10: Replace consumer-only dogfood with producer-path behavior coverage

**Objective:** Prove the full FEAT-017 path on a clean labelled consumer fixture and a self-hosting
case by invoking real producer seams instead of copying canonical spec/plan/task artifacts.

**Files:**
- Modify: `tests/integration/coherence/test_planning_dogfood.py`
- Modify/create: `tests/fixtures/planning-dogfood/README.md`
- Modify/create: `tests/fixtures/planning-dogfood/clean/README.md`
- Modify/create: `tests/fixtures/planning-dogfood/self-hosting/README.md`
- Create: `tests/fixtures/planning-dogfood/fake-producers.py` only if the fixture needs a reusable injected backend
- Modify: `tests/unit/coherence/test_planning_integration.py`

**Interfaces:**
- Real spec and plan producer operations from Tasks 2 and 4.
- Candidate review, typed task materialization, cross-artifact gates, human decision writers,
  optional Kanban graph, FEAT-018 seam, and handoff from Tasks 3 and 5–9.
- Labelled fixture values that are explicitly `test-data-not-approval`.

**Dependencies/order:** Depends on Tasks 1–9. This task is the first end-to-end proof and must not
be used to weaken production gates or to certify the stale current consent snapshot.

**RED/documentation verification:** Start each fixture with only the exact prompt, captured answers,
repository facts, and an empty approved output location. Invoke the real producers. Add tests for:

- provisional spec write/read-back/hash and spec alignment;
- one candidate derivation/review before plan authoring, including duplicate/conflict/missing-
  obligation context;
- plan write/read-back/hash with implementation and verification tasks;
- typed task materialization and idempotent rerun;
- bidirectional trace closure and a deliberate missing-edge failure;
- one agentic scoped fix followed by fresh review;
- human challenge escalation and next-loop answer provenance;
- every security/operability warning blocking until a labelled human decision;
- feature split stopping for human selection without overwriting a supplied baseline;
- interrupted/resumed capture and failed snapshot replacement preservation;
- Kanban materialization/reconciliation/reclaim when the optional capability is injected;
- FEAT-018 absent capability blocking;
- fresh exact consent, final gates, menu, and `starts_automatically: false` handoff.

```bash
uv run pytest tests/integration/coherence/test_planning_dogfood.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
```

**Implementation/GREEN:** Replace the current `_consumer` copy-only setup with producer invocation
through the same production seams used by the host. Keep any fixture source records clearly
labelled and use them only as inputs/context. Assert outputs were created by the producer, then
read them back and compare recorded hashes. Preserve a self-hosting test that reports existing
repository debt instead of claiming it is fixed.

```bash
uv run pytest tests/integration/coherence/test_planning_dogfood.py tests/unit/coherence -q -o addopts=''
uv run ruff check src tests
uv run pyright src/coherence/planning src/coherence/navigate src/factory/orchestrator src/substrate/agents
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run
```

**Acceptance criteria:** The dogfood fails if a spec/plan/task is pre-created instead of produced;
all corrected lifecycle stages are observed in order; producer hashes/read-backs, challenges,
reviews, warning decisions, consent, trace closure, recovery, capability block, and handoff are
verified; fixtures never count as human approval; and unrelated debt is reported separately.

**Prohibited scope:** Do not edit production canonical FEAT/SR/bundle records from a fixture, use
fixture values as consent, bypass a gate, launch downstream work, or change the authority documents
without verified facts and explicit authorization.

### Task 11: Holistic acceptance, fresh reviews, and known-debt separation

**Objective:** Exercise the complete contract after all fixes, perform independent compliance and
quality/security reviews, and publish an honest implementation/review result without merging.

**Files:**
- Create/modify: `tests/integration/coherence/test_planning_holistic.py`
- Modify: `tests/unit/coherence/test_planning_trace_contract.py` only for final contract assertions
- Modify: `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md` only with verified implementation facts
- Modify: `docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md` only with verified completion/debt facts
- Create/modify: `.factory/planning/<run-id>/final-gates.json` only through the validated writer

**Interfaces:**
- All prior task outputs and exact authority/plan contract.
- Existing unit, integration, Coherence, extension, and repository gate commands.
- Fresh spec-compliance and code-quality/security reviewers with no self-certification.

**Dependencies/order:** Final task; depends on Tasks 1–10. It must be rerun after every implementation
or fix cycle that changes a relevant artifact. No merge, push, canonical adoption, or downstream
workflow is allowed without explicit authorization.

**RED/documentation verification:** Add holistic assertions that the run cannot hand off when any
producer is skipped, any checkpoint is out of order, candidate review is late or duplicated, a task
is unbound, trace closure is one-way, a warning lacks human disposition, feature scope is unresolved,
FEAT-018 is unavailable when required, a snapshot/hash/consent is stale, a Kanban edge is missing,
or `starts_automatically` is true. Verify the final docs contain no contradictory normative order
and explicitly mark implementation, consent, and adoption as pending until proved.

```bash
uv run pytest tests/integration/coherence/test_planning_holistic.py tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
```

**Implementation/GREEN:** Run the complete independent review protocol. First perform a fresh
spec-compliance review against every acceptance row in the authority spec, then a fresh
code-quality/security review covering path safety, prompt injection, secret redaction, stale-hash
rejection, atomic writes, role scope, workspace serialization, retry/reclaim, and no auto-execution.
Use fresh-context fixers for findings, append all resolution events, reread changed artifacts,
recompute hashes, and repeat both reviews. Produce a derived coverage report if useful, but retain
canonical evidence and known-debt separation.

```bash
uv run pytest tests/integration/coherence/test_planning_holistic.py tests/integration/coherence/test_planning_dogfood.py -q -o addopts=''
uv run pytest tests/unit -q -o addopts=''
npm run typecheck --prefix pi-ext/scope-guard
npm test --prefix pi-ext/scope-guard -- --run
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run
uv run ruff check src tests
uv run pyright src
uv run coherence navigate health --repo-root . --json
uv run coherence register check --project-root .
uv run coherence trace check --project-root .
python scripts/gates/ext.py
python scripts/gates/watch_ext.py
```

Record command output and classify failures as new FEAT-017 regressions, known pre-existing debt, or
unavailable optional capabilities. Do not conceal failures by changing fixtures, accepting warnings,
or editing stale evidence.

**Acceptance criteria:** Every authority-spec acceptance criterion has fresh implementation and
verification evidence; final gates are hash-current and fail closed on stale consent/evidence; the
optional Kanban graph is reconciled when requested; FEAT-018 behavior is honestly present or blocked;
all security/operability warnings have resolution or explicit human disposition; handoff is validated
with `starts_automatically: false`; the final summary distinguishes known debt and unavailable
capabilities; and there is no claim of merge or plan acceptance without explicit authorization.

**Prohibited scope:** Do not merge, push, mutate Kanban outside the requested optional planning graph,
start implementation/downstream workflows, fabricate human consent, or rewrite history.

## 5. Final acceptance matrix

| Area | Required proof |
|---|---|
| Intent provenance | Exact prompt/question/answer text, source, sequence, observations, challenges, decisions, and unresolved state are durable and hash-bound |
| Snapshot recovery | Append-only journal survives interruption; failed materialization preserves the last known-good snapshot |
| Spec producer | Real backend-injected producer writes, reads back, validates, and hashes the provisional spec |
| Spec checkpoint | `PLANNING_ALIGNMENT` runs after the producer and before candidate derivation |
| Candidate SR | Exactly one run-local derivation lineage occurs before plan authoring; adversarial duplicate/conflict/unsupported/compatibility/missing-obligation/full-context review is explicit |
| Plan producer | Real backend-injected producer writes, reads back, validates, and hashes a plan containing implementation and verification work together |
| Task contract | Generated tasks bind source spec/plan/SR or reviewed non-SR, acceptance, exact tests/commands, and implementation/verification evidence |
| Cross-artifact gate | `CROSS_ARTIFACT_ALIGNMENT` runs after tasks and proves bidirectional closure |
| Human boundaries | Feature splits stop for human sequential workflow/worktree choice; supplied FEAT baseline is never silently overwritten |
| Warnings | Every security/operability warning blocks until fixed or explicitly dispositioned by a human; no `accept_warning` bypass |
| Consent/adoption | Fresh exact human SR consent binds candidate set, review, artifacts, and run; canonical adoption is distinct from review cleanliness |
| Kanban | Optional root/stage cards, dependencies, idempotency, workspace serialization, retry/reclaim, recovery, reconciliation, and no silent downstream execution are tested |
| FEAT boundary | FEAT-018 capability is checked/blocked honestly; FEAT-019 conformance and FEAT-020 optimization remain separate |
| Freshness | Any relevant input, output, context, model, decision, or policy change invalidates affected evidence and handoff |
| Handoff | JSON/Markdown handoff is current, validated, hash-bound, and `starts_automatically: false` |
| Known debt | Existing repository debt and unavailable capabilities are reported separately, never converted into false success |
| Authorization | No merge, push, canonical adoption, or downstream launch without explicit authorization |

## 6. Execution and review handoff

When implementation is explicitly authorized, work only in the designated repository/worktree and
keep unrelated dirty changes untouched. Before each task, verify prerequisites and exact paths. Stage
only the files belonging to that task. After each implementation/fix cycle, run both fresh reviews
and the task's focused checks; do not accept a subagent self-report without inspecting files and
real output.

The final handoff is a planning result, not an execution trigger. A new session must validate the
run ID, current source hashes, review hashes, warning/consent decisions, trace closure, optional
Kanban reconciliation, FEAT-018 capability result, and `starts_automatically: false` before it can
choose any separate downstream workflow. The plan itself never claims that acceptance, consent,
canonical adoption, or implementation has happened.

**Canonical authority:** `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md`

**Canonical plan:** `docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md`

**Execution policy:** No merge or push without explicit authorization. Do not modify Kanban state or
claim plan acceptance merely because these documents are written.
