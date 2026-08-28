---
id: PLAN-FEAT-017-MATURE-PLANNING-WORKFLOW
title: "FEAT-017 Mature Planning Workflow Implementation Plan"
status: draft
spec_ref: docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md
---

# FEAT-017 Mature Planning Workflow Implementation Plan

> **For Hermes:** Use subagent-driven-development to implement this plan task-by-task. This document is the implementation plan; it is not itself permission to execute, commit, push, or merge.

**Goal:** Mature FEAT-017 from the existing deterministic planning/bootstrap slice into a resumable, host-portable planning workflow that conducts adaptive intent discovery, authors a provisional authority specification, runs three bounded semantic-review checkpoints with fresh verification after every fix, preserves human escalation and explicit SR consent, and emits a verified handoff for a separately started downstream workflow.

**Architecture:** Keep the Python Coherence/substrate layer authoritative for canonical artifacts, schemas, state transitions, hashes, path safety, registration, traceability, and fail-closed gates. Add host-neutral planning-review contracts and dedicated agent roles, but obtain agent execution and model catalog information from the host through the existing `AgentBackend` seam. Pi and Hermes remain thin adapters: they conduct the conversational interaction, ask the user to select a reviewer model once per run, render the text summary, and create a new session from the validated handoff; they do not reimplement planning rules.

**Tech Stack:** Python 3.11, dataclasses, pathlib, strict JSON/YAML/frontmatter parsing, argparse, pytest, Ruff, Pyright, TypeScript, Pi/Hermes host APIs, existing agent subprocess/backend seams, filesystem-first artifacts, and the existing Coherence trace/navigate/gate substrate. No new runtime dependency unless a host’s native model-catalog API requires a reviewed adapter dependency.

---

## 1. Scope and approved design baseline

This plan supersedes the earlier maturation proposal. The following decisions were explicitly confirmed during design review and must not be silently changed during implementation.

### 1.0 Current planning materialization

The current repository state is materialized with the tools available today before the mature
implementation lands:

- `.intent/intent.json` uses the existing schema-one contract and preserves the latest planning
  request plus the approved decision answers;
- the current `coherence.planning` checker validates source presence, frontmatter, safe paths,
  intent-token coverage, FEAT-017 closure, source anchors, and plan/task parity;
- current Coherence trace, register, health, and gate commands provide the available evidence;
- no proposed SR is treated as human-consented, no approval is fabricated, and no downstream
  workflow is started;
- the stable intent identifiers are `host-neutral`, `adaptive-brainstorming`, `provisional-spec`,
  `three-checkpoints`, `complete-sr-context`, `selected-review-model`, `fresh-review-loop`,
  `append-only-journal`, `human-escalation`, `explicit-sr-consent`, `text-summary-handoff`,
  `deferred-browser`, `canonical-spec-authority`, `no-auto-execution`, and
  `current-tooling-boundary`.

This current materialization is evidence that the planning artifacts are coherent under today’s
contracts; it is not evidence that the future mature runtime behavior has already been implemented.

### 1.1 Host boundary

- Implement one host-neutral workflow over the existing Coherence/substrate and factory-orchestrator seams.
- Pi and Hermes provide thin adapters for conversation, model discovery/selection, agent backend injection, text rendering, and new-session handoff.
- Do not build a Hermes-only planning implementation or a second Pi-only planning implementation.
- Do not put provider discovery, credentials, shell execution, or model invocation into the Python planning CLI.

### 1.2 Brainstorming behavior

- Brainstorming is adaptive and conversational, inspired by the upstream Superpowers `brainstorming` skill and Matt Pocock-style `grill-me`/`grilling` interaction.
- The inspiration governs questioning style only: inspect repository facts when discoverable, ask focused questions, surface trade-offs, and avoid silently assuming unresolved design choices.
- The user’s initial request and answers are preserved verbatim.
- The agent may author a provisional authority spec from an incomplete/provisional conversation. There is no separate blanket approval of the intent summary before spec generation.
- Missing intent, infeasibility, contradictions, and unresolved decisions are semantic-review findings that can escalate to the user later.

### 1.3 Semantic-review checkpoints

Semantic review runs at all three lifecycle points:

```text
Pass 1: provisional intent -> authority specification
Pass 2: intent/specification -> implementation plan and generated tasks
Pass 3: specification/plan -> derived SRs, FEAT dossier, and bundle
```

The third pass is separate because SRs are thin, independently governable projections of the authority spec, not a mechanical copy of every paragraph.

### 1.4 Review and fix loops

For every checkpoint:

```text
deterministic preflight
-> use the reviewer model selected for this run
-> dedicated semantic reviewer
-> reviewer classifies each finding as resolve_in_loop or escalate_to_human
-> agent directly fixes only its permitted planning artifacts
-> append the resolution/fix evidence for this run
-> deterministic reread and gates
-> fresh dedicated reviewer invocation
-> repeat until every finding is fixed or escalated
```

- A reviewer may choose what it can resolve and what needs human input.
- A reviewer cannot self-certify its own edits. Every fix is followed by a fresh reviewer invocation and deterministic gates.
- Human escalation answers become prompts/inputs to the next agentic loop iteration.
- The workflow does not stop merely because an agent says it is done.
- The human loop ends only when all escalations are resolved and the next agentic loop reaches a clean result.
- Informational notes may remain; unresolved semantic findings and deterministic warnings may not.

### 1.5 Human review and consent

- Human review is primarily escalation-driven: the system presents specific unresolved questions and asks the user to resolve them.
- After a clean pass, the user may optionally inspect artifacts one by one using normal editor/tools. This is not a mandatory new artifact-review workbench.
- Browser-based `/system` planning projection is deferred to a later requirement; the first mature workflow presents a text summary and stable handoff.
- For SR derivation, semantic cleanliness is not consent. After the derivation escalation has been resolved, the workflow must request an explicit consent phrase before adopting the candidate SR set.
- A free-text answer alone does not grant SR consent.
- Existing consent and review artifacts remain hash-bound and fail closed; compatibility with existing `review-decision.json` runs must be preserved or explicitly migrated.

### 1.6 Requirement model

Keep both specifications and SRs:

```text
authority spec = canonical semantic/design authority
SR             = thin, human-consented, machine-addressable obligation projection
```

Only independently governable obligations become SRs. An SR is appropriate when it needs independent verification, ownership, task/code traceability, an obligation, evidence, lifecycle/consent, feature/bundle membership, or separate health state. Explanatory prose, alternatives, rationale, and non-binding context stay in the spec.

### 1.7 Current requirement context

Every semantic reviewer receives the full current project requirement context for the initial reliable implementation:

- every non-deleted SR;
- full requirement content;
- proposed, deferred, satisfied, and active lifecycle/status labels;
- source anchors and available trace context.

Where an SR lacks a source status field, the labels are derived from the current Coherence trace/register state rather than fabricated. This deliberately accepts scale and token cost so duplicate requirements and contradictions are not hidden. The context is supplied through a read-only Coherence context interface, not ad-hoc model-directed globbing. A better retrieval/indexing technique is a deferred requirement, not an unimplemented promise in this feature.

### 1.8 Model selection

One reviewer model is selected for the entire FEAT-017 run:

```text
configured inexpensive classifier
-> complexity estimate
-> concrete provider:model recommendations with cost/capability metadata
-> user chooses a reviewer model
-> selected model is reused for all three checkpoints and retries
```

- The classifier model is configured by the project policy file.
- The host validates configured models against its native model API.
- The user sees concrete `provider:model` choices with non-secret quality/capability tier, local/remote status, cost class, and free/low-cost marker.
- If the classifier, catalog, or configured model is unavailable, the workflow pauses and asks for an explicit configured choice. It never silently falls back.
- Model selection is FEAT-017-local for now. A later separate feature may generalize it across all workflows.

### 1.9 Persistence and handoff

All loop history is append-only within one workflow execution:

```text
.factory/planning/<run-id>/resolution-events.jsonl
```

Prior iterations must never be replaced. Derived current-state views may be regenerated from the journal.

After all three semantic passes and deterministic gates are clean:

```text
.factory/planning/<run-id>/handoff.json
.factory/planning/<run-id>/handoff.md
```

`handoff.json` is the schema-versioned, hash-bound source. `handoff.md` is a concise copyable prompt for a new session. The selected downstream workflow is never started automatically; the new session revalidates the handoff before acting.

---

## 2. Existing substrate and dependencies to reuse

The implementation must map each new capability to the existing machinery before introducing a new abstraction.

### Canonical planning/artifact machinery

- `src/coherence/planning/model.py`
- `src/coherence/planning/check.py`
- `src/coherence/planning/serialization.py`
- `src/coherence/planning/paths.py`
- `src/coherence/planning/run.py`
- `src/coherence/planning/bootstrap.py`
- `src/coherence/planning/gates.py`
- `src/coherence/planning/cli.py`
- `.intent/intent.json` as the existing intent source path
- `.factory/planning/<run-id>/report.json` as the existing planning evidence location
- `src/substrate/ledger/plans.py` for canonical plan parsing and collision-safe task creation

### Coherence context, trace, and gate machinery

- `src/coherence/trace/model.py` for canonical SR/node loading and declared relations
- `src/coherence/trace/graph.py` for graph-derived relationships
- `src/coherence/navigate/queries.py` for brief, matrix, traversal, and feature context
- `src/coherence/navigate/cli.py` for the stable navigator interface
- `src/coherence/navigate/obligations.py` for declared obligation context where applicable
- `src/coherence/gate/model.py` for validated `DecisionFile` decisions
- `src/coherence/gate/store.py` for atomic decision writes/reads
- `src/coherence/gate/service.py` for fail-closed gate resolution
- existing `trace` writers rather than hand-editing trace metadata

### Agent/orchestration machinery

- `src/factory/orchestrator/backends.py` `AgentBackend` protocol
- `src/factory/orchestrator/types.py` `AgentRole`
- `src/factory/orchestrator/roles.py` role scopes and prompts
- `src/factory/orchestrator/pi_backend.py` composition wrapper
- `src/substrate/agents/backend.py` bounded agent process execution
- `src/substrate/agents/model.py` neutral `AgentResult`
- `pi-ext/factory-watch/src/subagent-tool.ts` only where a shared bounded host invocation seam is required
- `pi-ext/factory-watch/src/cli-runner.ts` and existing argv builders for safe backend calls
- `pi-ext/factory-watch/src/session-transcript.ts` for host session provenance where useful
- `pi-ext/factory-watch/src/pi-types.ts` host model/UI/session types

### Host/project configuration

- New non-secret project policy: `.factory/planning/models.json`
- Native Pi/Hermes model APIs validate the project policy and provide the available configured catalog.
- No credentials or provider tokens may enter the policy, packet, report, journal, or handoff.

### Explicitly deferred dependencies

These are not hidden blockers; they remain visible as deferred scope:

- a better token-efficient SR retrieval/indexing strategy;
- a `/system`-style interactive planning/artifact review projection;
- repository-wide cross-workflow model-selection policy;
- full blank-directory `factory-init`/FEAT-16 composition if its ownership is not yet safely available;
- automatic FEAT-13 execution.

---

## 3. Target workflow

```text
host starts/resumes planning run
  |
  v
adaptive brainstorming
  -> .intent/intent.json (schema 2)
  -> .factory/planning/<run-id>/capture/events.jsonl
  -> .factory/planning/<run-id>/state.json
  |
  v
agent authors provisional authority spec
  |
  v
Pass 1: PLANNING_ALIGNMENT
  -> full SR context + intent/spec packet
  -> resolve/escalate loop until clean
  |
  v
agent authors implementation plan and generated tasks
  |
  v
Pass 2: PLANNING_PLAN_REVIEW
  -> full intent/spec/plan/task chain + full SR context
  -> resolve/escalate loop until clean
  |
  v
agent derives candidate thin SRs, FEAT dossier, bundle
  |
  v
Pass 3: PLANNING_DERIVATION
  -> spec/plan/candidate derivation + full current SR context
  -> resolve/escalate loop until clean
  -> explicit human consent phrase for candidate SR set
  |
  v
deterministic final gates
  -> exact syntax, anchors, IDs, links, hashes, registration, parity, freshness
  |
  v
text summary + explicit downstream menu
  -> standard development
  -> health recovery
  -> another feature-planning workflow
  |
  v
hash-bound handoff.json + rendered handoff.md
  -> new session revalidates before acting
```

At every boundary the run can stop and resume without losing source intent, review evidence, model selection, resolution history, or the reason it is blocked.

---

## 4. Task plan

Each implementation task must follow strict TDD: write the failing test, run it and observe RED, implement the smallest change, run GREEN, then perform focused static checks. Commits are task-scoped and must not include unrelated parent-worktree changes.

### Task 1: Freeze the approved contracts and trace the design decisions

**Objective:** Update the FEAT-017 authority/design documents so the approved three-pass, host-neutral, model-selected, escalation-driven workflow is the canonical scope.

**Files:**

- Modify: `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md`
- Modify: `docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md`
- Modify: `docs/features/FEAT-017.md`
- Modify: `bundles/FEAT-017.json`
- Test: `tests/unit/coherence/test_planning_trace_contract.py`

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing contract tests**

Add source-contract assertions for:

- adaptive brainstorming and provisional spec authoring;
- three semantic checkpoints and their exact artifact coverage;
- full non-deleted SR context for the first implementation;
- model classifier, one reviewer-model selection per run, and fail-closed catalog behavior;
- direct but role-scoped agent artifact edits followed by fresh review;
- append-only resolution history;
- explicit human consent phrase for candidate SR adoption;
- text-only first milestone and deferred `/system` planning projection;
- explicit downstream menu and hash-bound new-session handoff;
- deterministic gate ownership of exact syntax, paths, keywords, links, and hashes.

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
```

Expected: RED because the current design and trace anchors do not contain the approved mature contracts.

**Step 2: Update the source contracts**

Add the approved design sections and acceptance rows. Keep these distinctions explicit:

- implementation not yet present;
- agent review pending;
- human escalation pending;
- explicit SR consent pending;
- formal Coherence defer/waiver;
- deferred browser/retrieval/cross-workflow scope.

Do not mark a requirement satisfied because its contract was written.

**Step 3: Verify**

```bash
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
uv run coherence trace check --project-root .
```

Expected: the contract tests pass; any new SRs remain proposed/pending until the existing consent and registration paths are exercised.

**Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md \
  docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md \
  docs/features/FEAT-017.md bundles/FEAT-017.json \
  tests/unit/coherence/test_planning_trace_contract.py
git commit -m "docs: define mature host-neutral planning workflow"
```

Do not allocate or consent new SRs in this task. SR allocation remains a later explicit human boundary.

---

### Task 2: Add schema-versioned intent capture and append-only capture events

**Objective:** Extend the existing `.intent/intent.json` contract for durable, resumable, verbatim intent capture while preserving schema-1 reads.

**Files:**

- Modify: `src/coherence/planning/model.py`
- Create: `src/coherence/planning/intent.py`
- Modify: `src/coherence/planning/serialization.py`
- Modify: `src/coherence/planning/check.py`
- Modify: `src/coherence/planning/__init__.py`
- Test: `tests/unit/coherence/test_planning_intent.py`
- Modify: `tests/unit/coherence/test_planning_check.py`

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Contract:** Schema-2 intent remains at the existing caller-selected `.intent/intent.json` path and contains:

```json
{
  "schema": 2,
  "run_id": "run-001",
  "prompt": "<initial request exactly as received>",
  "answers": [
    {
      "id": "goal",
      "question": "<question asked>",
      "text": "<answer exactly as captured>",
      "source": "user",
      "sequence": 1
    }
  ],
  "brief": {
    "goal": ["goal"],
    "scope": [],
    "constraints": [],
    "non_goals": [],
    "done_when": [],
    "open_questions": []
  },
  "capture_status": "provisional|needs_user|cancelled",
  "redactions": []
}
```

The run-local capture journal is:

```text
.factory/planning/<run-id>/capture/events.jsonl
```

**Step 1: Write failing tests**

Cover:

- exact prompt and answer preservation;
- stable unique answer IDs and sequence numbers;
- adaptive questions rather than an imposed fixed-order questionnaire;
- schema-1 backward-compatible read and canonical internal normalization;
- incomplete/resumable capture;
- cancellation and explicit user-deferred questions;
- append-only journal behavior and duplicate sequence rejection;
- malformed events, invalid transitions, duplicate JSON keys, non-finite values, invalid UTF-8, unsafe paths, and secret-redaction diagnostics;
- state/hash records identify the intent and capture journal sources.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_check.py -q -o addopts=''
```

Expected: RED because schema-2 intent and event persistence do not exist.

**Step 3: Implement minimally**

Implement pure readers/validators and atomic append/materialization functions, for example:

```python
read_intent(path: Path, *, project_root: Path) -> IntentDocument
validate_intent(document: IntentDocument) -> tuple[PlanningFinding, ...]
append_capture_event(root: Path, run_id: str, event: CaptureEvent) -> Path
materialize_intent(root: Path, run_id: str, destination: Path) -> Path
```

Use strict serializers and `coherence.planning.paths`; do not invoke a model or subprocess. Preserve all source text exactly at the capture boundary.

**Step 4: Run GREEN and static checks**

```bash
uv run pytest tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_check.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_check.py
uv run pyright src/coherence/planning
```

**Step 5: Commit**

```bash
git add src/coherence/planning tests/unit/coherence/test_planning_intent.py \
  tests/unit/coherence/test_planning_check.py
git commit -m "feat: add durable versioned planning intent capture"
```

---

### Task 3: Add resumable planning state and deterministic brainstorming commands

**Objective:** Expose a host-neutral state machine for starting/resuming capture and progressing to provisional spec authoring without allowing invalid transitions.

The existing repository contains task records generated from many different plans. The selected-plan checker must enforce exact parity only for records whose `source_plan` equals the selected plan; unrelated task records must not become false FEAT-017 parity errors.

**Files:**

- Create: `src/coherence/planning/session.py`
- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/bootstrap.py`
- Modify: `src/coherence/planning/cli.py`
- Test: `tests/unit/coherence/test_planning_session.py`
- Modify: `tests/unit/coherence/test_planning_cli.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`

**State projection:**

```text
capture -> intent_provisional -> spec_pending ->
pass1_pending -> pass1_escalated | pass1_clean ->
plan_pending -> pass2_pending -> pass2_escalated | pass2_clean ->
 derivation_pending -> pass3_pending -> pass3_escalated | pass3_clean ->
consent_pending -> handoff_ready | blocked
```

The state file is:

```text
.factory/planning/<run-id>/state.json
```

It is a derived projection, never an authority source. Every state read recomputes or validates the state against canonical files and report/journal hashes.

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing tests**

Test:

- start/resume with a safe run ID;
- append arbitrary user text through a safe file/input boundary;
- interruption and restart at the first incomplete capture event;
- provisional completion without requiring blanket intent approval;
- cancellation and explicit unresolved state;
- stale or contradictory state rejection;
- mismatched run IDs, unsafe paths, and attempts to skip required semantic checkpoints;
- stable JSON output for every command.

Use symbolic command names only after checking the existing `coherence plan` parser. Do not add a new top-level CLI group.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_session.py tests/unit/coherence/test_planning_cli.py -q -o addopts=''
```

Expected: RED because the resumable session/state API is absent.

**Step 3: Implement**

Reuse `write_planning_run`, strict serialization, safe path helpers, and existing planning run IDs. Add only the smallest extension to the existing `coherence plan` command vocabulary required for start/resume/status/append/finalize behavior.

The backend writes capture/state evidence only. It does not ask questions, invoke a model, launch a process, or author human approval.

**Step 4: Verify**

```bash
uv run pytest tests/unit/coherence/test_planning_session.py tests/unit/coherence/test_planning_cli.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_session.py
uv run pyright src/coherence/planning
```

**Step 5: Commit**

```bash
git add src/coherence/planning tests/unit/coherence/test_planning_session.py \
  tests/unit/coherence/test_planning_cli.py tests/unit/coherence/test_planning_integration.py
git commit -m "feat: add resumable planning session state"
```

---

### Task 4: Add host adaptive brainstorming and provisional spec authoring

**Objective:** Make the host conduct adaptive one-question-at-a-time brainstorming, persist the exchange through the deterministic capture boundary, and let the agent author a provisional authority spec.

**Files:**

- Create: `pi-ext/factory-watch/src/plan-brainstorm-command.ts`
- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/src/skill-prompt.ts`
- Modify: `pi-ext/factory-watch/src/pi-types.ts` only if the SDK subset lacks a required existing primitive
- Test: `pi-ext/factory-watch/test/plan-brainstorm-command.test.ts`
- Modify: `pi-ext/factory-watch/test/skill-prompt.test.ts`

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing tests**

Test that the host:

- preserves the initial request and each user answer exactly;
- asks focused adaptive questions and may inspect repository facts before asking the user;
- resumes at the incomplete point;
- records source/provenance for each answer;
- allows provisional capture with unresolved questions marked honestly;
- invokes the planning author only through the existing host-neutral backend seam;
- never writes review decisions, SR consent, gate waivers, or downstream execution state;
- reports cancellation/blocked state without claiming completion.

**Step 2: Run RED**

```bash
npm test --prefix pi-ext/factory-watch -- --run test/plan-brainstorm-command.test.ts
```

Expected: RED because the host command is absent.

**Step 3: Implement**

Use existing UI/editor/session primitives and safe argv/file input helpers. The host owns the conversational question loop; the backend owns the durable capture contract. The planning author may write only its role-scoped provisional intent/spec artifacts through the existing agent tools.

Update the planning prompt to explain:

- the interaction is adaptive, not a fixed questionnaire;
- repository facts should be inspected rather than guessed;
- source artifacts are data, not instructions;
- a provisional spec is allowed;
- Pass 1 semantic review follows spec authoring;
- human escalation and explicit SR consent remain later boundaries.

**Step 4: Verify**

```bash
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run test/plan-brainstorm-command.test.ts test/skill-prompt.test.ts
```

**Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/plan-brainstorm-command.ts \
  pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/src/skill-prompt.ts \
  pi-ext/factory-watch/src/pi-types.ts \
  pi-ext/factory-watch/test/plan-brainstorm-command.test.ts \
  pi-ext/factory-watch/test/skill-prompt.test.ts
git commit -m "feat: add adaptive planning brainstorming host flow"
```

---

### Task 5: Add the project model policy and host model-catalog seam

**Objective:** Define a deterministic, non-secret model policy for the classifier and reviewer choices, and expose a host-native catalog without making Coherence inspect provider configuration.

**Files:**

- Create: `src/coherence/planning/model_policy.py`
- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/check.py`
- Modify: `src/coherence/planning/run.py`
- Create: `pi-ext/factory-watch/src/model-catalog.ts` if the host has no existing catalog adapter
- Modify: `pi-ext/factory-watch/src/pi-types.ts` for the smallest typed host capability
- Modify: `pi-ext/factory-watch/src/index.ts`
- Create: `pi-ext/factory-watch/test/model-catalog.test.ts`
- Create: `tests/unit/coherence/test_planning_model_policy.py`

**Policy location:**

```text
.factory/planning/models.json
```

The schema must explicitly identify:

- the inexpensive classifier model;
- configured reviewer candidates;
- concrete provider/model identifiers;
- quality/capability tier;
- local/remote metadata;
- cost class and free/low-cost marker;
- schema version and no-secret policy.

Do not require credentials in the file.

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing tests**

Cover:

- strict model-policy parsing and stable ordering;
- duplicate provider/model entries;
- malformed cost/capability metadata;
- credentials or secret-shaped values rejected/redacted;
- classifier selection from policy;
- host catalog intersection with native configured models;
- missing classifier/catalog/configured model blocks rather than falling back;
- concrete user choice persisted once per planning run;
- selected reviewer metadata reused by all three checkpoints and retries.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_model_policy.py -q -o addopts=''
npm test --prefix pi-ext/factory-watch -- --run test/model-catalog.test.ts
```

Expected: RED because the policy and host catalog seam do not exist.

**Step 3: Implement**

Keep policy parsing and validation in Python. The host supplies native catalog entries and validates that the policy’s concrete entries are actually configured. Persist only non-secret catalog/selection metadata under the run directory, for example:

```text
.factory/planning/<run-id>/model-selection.json
```

The classifier is run using the configured inexpensive classifier model. The user is asked once to choose the reviewer model for the whole run. A missing classifier/catalog requires an explicit user-selected configured model path; it never silently inherits the active session model.

**Step 4: Verify**

```bash
uv run pytest tests/unit/coherence/test_planning_model_policy.py -q -o addopts=''
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run test/model-catalog.test.ts
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_model_policy.py
uv run pyright src/coherence/planning
```

**Step 5: Commit**

```bash
git add src/coherence/planning pi-ext/factory-watch/src pi-ext/factory-watch/test \
  tests/unit/coherence/test_planning_model_policy.py
git commit -m "feat: add planning model policy and host catalog seam"
```

---

### Task 6: Add full project requirement context through Coherence

**Objective:** Give every semantic reviewer complete, status-labelled current SR context through a read-only Coherence interface so duplicate and contradictory requirements are visible.

**Files:**

- Create: `src/coherence/navigate/requirements_context.py` or the existing query module selected after import-boundary inspection
- Modify: `src/coherence/navigate/queries.py` only if needed to compose existing loaders
- Create/modify: `pi-ext/factory-watch/src/eng-context-tools.ts`
- Create/modify: `pi-ext/factory-watch/src/eng-context-tool-format.ts`
- Create/modify: `pi-ext/factory-watch/src/system-cli.ts` only if the host already uses it for Python navigator calls
- Test: `tests/unit/coherence/test_requirements_context.py`
- Test: `pi-ext/factory-watch/test/eng-context-tools.test.ts`

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Contract:** The read-only context operation must return every non-deleted SR with:

- exact SR ID and statement;
- lifecycle/status including proposed/deferred/satisfied/active;
- source anchor(s);
- declared upstream/downstream/feature/task relationships available from the graph;
- enough trace metadata to flag likely duplicates/contradictions;
- stable deterministic ordering;
- a context digest for packet binding.

The first version may include the full content of every SR. Do not add a second register or graph implementation. Reuse `coherence.trace.model`, `coherence.trace.graph`, and existing `coherence.navigate` query paths.

**Step 1: Write failing tests**

Test:

- all non-deleted SRs are included, including proposed/deferred/satisfied;
- deleted/missing/invalid SRs fail closed or are explicitly diagnosed;
- status and source anchors are preserved;
- output ordering and digest are deterministic;
- context reads are read-only and do not write state;
- duplicate and contradiction candidates are not silently omitted;
- host tool output has bounded encoding behavior but does not truncate the canonical persisted packet;
- tool never accepts an arbitrary file path or model-authored command.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_requirements_context.py -q -o addopts=''
npm test --prefix pi-ext/factory-watch -- --run test/eng-context-tools.test.ts
```

Expected: RED because the project-wide requirement-context operation is absent.

**Step 3: Implement**

Expose the operation through the existing read-only engineering context-tool pattern. For reliability, the semantic-review packet may materialize the complete context once per checkpoint, while the agent may use the tool for exact trace details. Record the context digest in every review packet.

Record the stronger token-efficient retrieval/indexing idea as a deferred requirement; do not claim it is implemented.

**Step 4: Verify**

```bash
uv run pytest tests/unit/coherence/test_requirements_context.py -q -o addopts=''
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run test/eng-context-tools.test.ts
uv run ruff check src/coherence/navigate tests/unit/coherence/test_requirements_context.py
uv run pyright src/coherence/navigate
```

**Step 5: Commit**

```bash
git add src/coherence/navigate pi-ext/factory-watch/src/eng-context-tools.ts \
  pi-ext/factory-watch/src/eng-context-tool-format.ts \
  tests/unit/coherence/test_requirements_context.py \
  pi-ext/factory-watch/test/eng-context-tools.test.ts
git commit -m "feat: expose full Coherence requirement context"
```

---

### Task 7: Add semantic-review packet, report, and append-only resolution contracts

**Objective:** Define strict, hash-bound semantic-review evidence for three stages and persist every agentic/human resolution without overwriting prior iterations.

**Files:**

- Create: `src/coherence/planning/semantic.py`
- Create: `src/coherence/planning/resolution.py`
- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/serialization.py`
- Modify: `src/coherence/planning/check.py`
- Modify: `src/coherence/planning/run.py`
- Test: `tests/unit/coherence/test_planning_semantic.py`
- Test: `tests/unit/coherence/test_planning_resolution.py`
- Modify: `tests/unit/coherence/test_planning_run.py`

**Review stages:**

```text
spec_alignment
plan_task_alignment
derivation_alignment
```

Each packet/report must include:

- schema and run ID;
- stage and iteration number;
- exact sorted artifact paths and SHA-256 hashes;
- intent/spec/plan/task/SR/FEAT/bundle context as applicable;
- full-SR-context digest;
- selected provider/model and non-secret configuration metadata;
- reviewer role and child session ID if available;
- findings with stable IDs, evidence, confidence, and disposition;
- questions/prompts for human escalation;
- informational notes;
- report verdict;
- no credentials or arbitrary source instructions treated as commands.

Each finding disposition is one of:

```text
resolve_in_loop
escalate_to_human
informational
```

Resolution events append to:

```text
.factory/planning/<run-id>/resolution-events.jsonl
```

Each event records stage, iteration, finding ID, disposition, exact prompt/answer or fix summary, pre/post artifact hashes, actor kind, and timestamp. A derived current view may be written, but prior events remain immutable history.

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing tests**

Cover:

- deterministic packet ordering and artifact hashes;
- all three stage contracts;
- full SR context binding;
- strict JSON-only report parsing;
- confidence and evidence requirements;
- valid/invalid dispositions;
- report freshness invalidation after any relevant artifact/context/model change;
- append-only event sequencing and no replacement of prior iterations;
- malformed JSON, duplicate keys, oversized fields, path traversal, forged reviewer identity, and secret redaction;
- a report never becomes human approval or SR consent.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_semantic.py \
  tests/unit/coherence/test_planning_resolution.py \
  tests/unit/coherence/test_planning_run.py -q -o addopts=''
```

Expected: RED because stage-specific semantic packets/reports and the resolution journal do not exist.

**Step 3: Implement**

Use strict serializers, existing SHA-256 helpers where available, safe-root checks, atomic file writes, and immutable report semantics. Do not call a model or subprocess in these modules.

Ensure that any changed artifact, requirement context, selected model, or review policy invalidates the affected report and downstream state.

**Step 4: Verify**

```bash
uv run pytest tests/unit/coherence/test_planning_semantic.py \
  tests/unit/coherence/test_planning_resolution.py \
  tests/unit/coherence/test_planning_run.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_semantic.py \
  tests/unit/coherence/test_planning_resolution.py
uv run pyright src/coherence/planning
```

**Step 5: Commit**

```bash
git add src/coherence/planning tests/unit/coherence/test_planning_semantic.py \
  tests/unit/coherence/test_planning_resolution.py \
  tests/unit/coherence/test_planning_run.py
git commit -m "feat: add hash-bound semantic review and resolution contracts"
```

---

### Task 8: Add dedicated planning agent roles and restricted direct-write scopes

**Objective:** Extend the existing host-neutral agent role catalogue with dedicated planning roles while preserving direct-write boundaries and fresh-review verification.

**Files:**

- Modify: `src/factory/orchestrator/types.py`
- Modify: `src/factory/orchestrator/roles.py`
- Modify: `src/factory/orchestrator/backends.py` only if the protocol needs a non-breaking typed extension
- Modify: `src/factory/orchestrator/pi_backend.py` only for role composition
- Modify: `src/substrate/agents/backend.py` only if role transport requires a neutral extension
- Modify: `pi-ext/factory-watch/src/subagent-tool.ts` only for generic bounded invocation support
- Create/modify: role prompt/skill fixtures under the existing role-skill locations
- Test: `tests/unit/factory/orchestrator/test_roles.py` or the existing role test module
- Test: `pi-ext/factory-watch/test/subagent-tool.test.ts`

**Roles:**

- `PLANNING_COMPLEXITY`: classifier only; read-only; emits strict complexity/recommendation JSON.
- `PLANNING_ALIGNMENT`: spec alignment review and scoped intent/spec revisions.
- `PLANNING_PLAN_REVIEW`: plan/task alignment review and scoped plan/task revisions.
- `PLANNING_DERIVATION`: SR/FEAT/bundle derivation review and scoped derived-artifact revisions.

The reviewer invocation and fixer invocation must be fresh runs even when the same role and model are reused.

Role scopes must be explicit and minimal:

- no arbitrary shell execution;
- no project config edits;
- no gate-decision or requirement-consent fabrication;
- no writes outside the current run’s approved planning paths and the role’s artifact class;
- derived SR/FEAT/bundle edits remain subject to the existing writers/gates and later explicit human consent.

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing tests**

Test:

- each role has a prompt and scope;
- classifier/review roles cannot recurse or invoke arbitrary shell commands;
- alignment role cannot modify requirements/bundles;
- plan role cannot modify requirements/consent files;
- derivation role cannot modify source intent/spec/plan;
- direct edits are followed by new invocation in the orchestrator contract;
- role output must be structured and validated;
- the existing roles retain their behavior.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/factory/orchestrator -q -o addopts=''
npm test --prefix pi-ext/factory-watch -- --run test/subagent-tool.test.ts
```

Expected: RED because the planning roles and scope rules do not exist.

**Step 3: Implement**

Add the roles to the shared enum/catalogue and compose them through the existing `ROLE_SCOPE` mechanism. Keep semantic reviewers read-only during the review invocation; the same dedicated role may perform a subsequent scoped revision invocation, but no invocation may self-certify without a fresh review.

Do not make Python planning code launch a process. Use the injected `AgentBackend`; Pi/Hermes remain responsible for providing the implementation.

**Step 4: Verify**

```bash
uv run pytest tests/unit/factory/orchestrator -q -o addopts=''
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run test/subagent-tool.test.ts
uv run pyright src/factory/orchestrator src/substrate/agents
```

**Step 5: Commit**

```bash
git add src/factory/orchestrator src/substrate/agents \
  pi-ext/factory-watch/src/subagent-tool.ts \
  pi-ext/factory-watch/test/subagent-tool.test.ts \
  tests/unit/factory/orchestrator
git commit -m "feat: add scoped planning semantic agent roles"
```

---

### Task 9: Implement the fresh-review agentic resolution loop

**Objective:** Orchestrate reviewer output, direct scoped fixes, append-only resolution evidence, deterministic rereads, and fresh reviewer invocations until all findings are fixed or escalated.

**Files:**

- Create: `src/coherence/planning/loop.py`
- Modify: `src/coherence/planning/semantic.py`
- Modify: `src/coherence/planning/resolution.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/check.py`
- Test: `tests/unit/coherence/test_planning_loop.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing tests**

Test the loop sequence:

1. deterministic preflight;
2. reviewer call using selected model;
3. strict report validation;
4. agent disposition per finding;
5. scoped direct artifact edit for `resolve_in_loop`;
6. append resolution event with pre/post hashes;
7. deterministic reread/gates;
8. fresh reviewer call;
9. escalation prompt emission for `escalate_to_human`;
10. repeat until clean or user escalation is required.

Also test:

- repeated findings;
- malformed reviewer output;
- stale writes and changed artifacts;
- timeout, provider error, output overflow, and interruption;
- iteration/budget limits;
- invalid direct writes;
- informational-only findings;
- no false clean result while a deterministic gate is red;
- no replacement of prior `resolution-events.jsonl` entries.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_loop.py \
  tests/unit/coherence/test_planning_integration.py -q -o addopts=''
```

Expected: RED because no fresh-review loop exists.

**Step 3: Implement**

Implement the loop as a host-neutral coordinator over `AgentBackend`, deterministic planning checks, and the resolution journal. The loop may direct the agent to edit its permitted artifacts, but it must read back the files and recompute hashes before accepting the iteration.

If the loop cannot verify a fix, it escalates instead of silently accepting it. If the same finding recurs or the budget is exhausted, append the escalation evidence and stop at the human boundary.

Human answers are stored as the next-loop prompt/input. They do not directly mutate canonical artifacts; the next scoped planning-agent invocation applies them.

**Step 4: Verify**

```bash
uv run pytest tests/unit/coherence/test_planning_loop.py \
  tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_loop.py
uv run pyright src/coherence/planning
```

**Step 5: Commit**

```bash
git add src/coherence/planning tests/unit/coherence/test_planning_loop.py \
  tests/unit/coherence/test_planning_integration.py
git commit -m "feat: add fresh semantic review resolution loop"
```

---

### Task 10: Wire the three semantic checkpoints into the planning lifecycle

**Objective:** Make spec, plan/task, and SR/FEAT/bundle derivation review occur in the approved order and prevent later stages from bypassing earlier clean results.

**Files:**

- Create: `src/coherence/planning/workflow.py`
- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/bootstrap.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/gates.py`
- Modify: `src/coherence/planning/cli.py`
- Test: `tests/unit/coherence/test_planning_workflow.py`
- Modify: `tests/unit/coherence/test_planning_bootstrap.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing tests**

Test:

- Pass 1 cannot be skipped before plan/task authoring;
- Pass 2 sees intent, spec, plan, generated tasks, and full current SR context;
- Pass 3 sees spec, plan, candidate SRs, FEAT dossier, bundle, and full current SR context;
- each pass uses the same selected reviewer model for the run;
- changed artifacts invalidate only the affected and downstream stages;
- a clean pass is based on fresh report hashes and green deterministic preflight/postflight;
- unresolved questions stop progression;
- informational notes do not block;
- deterministic warnings block unless explicitly accepted by a human decision;
- a semantic report cannot create human approval, SR consent, or downstream execution.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_workflow.py \
  tests/unit/coherence/test_planning_bootstrap.py \
  tests/unit/coherence/test_planning_integration.py -q -o addopts=''
```

Expected: RED because the lifecycle currently has only the deterministic bootstrap/check path.

**Step 3: Implement**

Compose the existing `bootstrap`, `check`, `run`, `gates`, and canonical plan parser rather than duplicating their rules. The workflow coordinator should expose stable stage/status JSON for hosts.

The second semantic pass runs after plan authoring and task decomposition. The third runs after candidate derived artifacts are written. Each stage’s packet and report is immutable evidence; a later artifact change creates a fresh required stage.

**Step 4: Verify**

```bash
uv run pytest tests/unit/coherence/test_planning_workflow.py \
  tests/unit/coherence/test_planning_bootstrap.py \
  tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_workflow.py
uv run pyright src/coherence/planning
```

**Step 5: Commit**

```bash
git add src/coherence/planning tests/unit/coherence/test_planning_workflow.py \
  tests/unit/coherence/test_planning_bootstrap.py \
  tests/unit/coherence/test_planning_integration.py
git commit -m "feat: compose three planning semantic checkpoints"
```

---

### Task 11: Integrate explicit human escalation, warnings, and SR consent

**Objective:** Route unresolved semantic decisions to the user, persist answers for the next loop, reuse shared gate decisions for deterministic warnings, and require an explicit consent phrase for candidate SR adoption.

**Files:**

- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/gates.py`
- Modify: `src/coherence/planning/cli.py`
- Modify: `src/coherence/gate/model.py` only if a `planning:` item family is required
- Modify: `src/coherence/gate/store.py` only if path binding needs a compatible extension
- Modify: `src/coherence/gate/service.py` only if resolution needs a compatible extension
- Create/modify: `pi-ext/factory-watch/src/plan-review-command.ts`
- Modify: `pi-ext/factory-watch/src/index.ts`
- Test: `tests/unit/coherence/test_planning_review_resolution.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`
- Test: `pi-ext/factory-watch/test/plan-review-command.test.ts`

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing tests**

Test these rules:

- an unresolved semantic escalation emits exact user prompts and blocks advancement;
- a human answer is persisted and supplied to the next loop iteration;
- no answer is inferred from silence, a model response, or a malformed file;
- an explicit consent phrase is required after clean derivation before candidate SR adoption;
- semantic cleanliness alone never grants SR consent;
- a free-text escalation answer alone never grants SR consent;
- explicit human consent binds to the exact candidate SR set, run ID, derivation report hash, and artifact hashes;
- deterministic warnings use the shared `DecisionFile` mechanism and require human reason/hash binding;
- malformed/replayed/stale decisions fail closed;
- old valid review/consent records remain readable where compatibility is promised.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_review_resolution.py \
  tests/unit/coherence/test_planning_integration.py -q -o addopts=''
npm test --prefix pi-ext/factory-watch -- --run test/plan-review-command.test.ts
```

Expected: RED because the current path has one human review decision model but no multi-stage escalation/resolution flow.

**Step 3: Implement**

Use the existing gate decision store for explicit accepted deterministic warnings. Add a planning item prefix only if the existing validated vocabulary requires it; do not create another warning/waiver store.

Keep semantic resolution events in the planning journal because they contain iteration prompts/fixes and are not interchangeable with a gate decision.

The host presents:

- stage and iteration;
- exact unresolved finding IDs;
- concise reason/evidence;
- the prompt requiring a human answer;
- what the next loop will receive;
- explicit SR-consent request when applicable;
- current artifact/report hashes;
- legal next actions.

**Step 4: Verify**

```bash
uv run pytest tests/unit/coherence/test_planning_review_resolution.py \
  tests/unit/coherence/test_planning_integration.py -q -o addopts=''
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run test/plan-review-command.test.ts
uv run pyright src/coherence/planning src/coherence/gate
```

**Step 5: Commit**

```bash
git add src/coherence/planning src/coherence/gate \
  pi-ext/factory-watch/src/plan-review-command.ts \
  pi-ext/factory-watch/src/index.ts \
  tests/unit/coherence/test_planning_review_resolution.py \
  tests/unit/coherence/test_planning_integration.py \
  pi-ext/factory-watch/test/plan-review-command.test.ts
git commit -m "feat: add explicit planning escalation and consent flow"
```

---

### Task 12: Add the text summary, downstream workflow menu, and validated handoff

**Objective:** Present the clean result without forcing a browser workbench, offer explicit downstream workflow choices, and emit a new-session handoff that is revalidated before execution.

**Files:**

- Create: `src/coherence/planning/handoff.py`
- Modify: `src/coherence/planning/run.py`
- Modify: `src/coherence/planning/cli.py`
- Modify: `src/coherence/planning/bootstrap.py`
- Modify: `pi-ext/factory-watch/src/plan-gate-command.ts`
- Modify: `pi-ext/factory-watch/src/skill-prompt.ts`
- Modify: `pi-ext/factory-watch/src/index.ts`
- Test: `tests/unit/coherence/test_planning_handoff.py`
- Modify: `tests/unit/coherence/test_planning_integration.py`
- Modify: `pi-ext/factory-watch/test/plan-gate-command.test.ts`

**Handoff contract:**

`handoff.json` must include:

- schema and run ID;
- selected downstream workflow identifier;
- exact canonical artifact paths and hashes;
- clean semantic-stage report hashes;
- resolution-journal digest;
- model-selection metadata without secrets;
- deterministic gate result summary;
- explicit `starts_automatically: false`;
- creation metadata.

`handoff.md` is a derived, concise prompt containing the run ID, selected workflow, validated artifact references, current status, and instruction to revalidate before acting.

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing tests**

Test:

- final text summary includes semantic notes, unresolved state, hashes, and gate state;
- clean result offers a stable explicit menu including standard development, health recovery, and another feature-planning workflow;
- no menu choice starts a process in the planning CLI;
- invalid workflow identifiers fail closed;
- handoff paths remain inside the run directory;
- changed artifacts invalidate the handoff;
- the rendered prompt matches the canonical JSON content;
- a new-session consumer must revalidate before acting;
- browser projection is not required for completion.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_handoff.py \
  tests/unit/coherence/test_planning_integration.py -q -o addopts=''
npm test --prefix pi-ext/factory-watch -- --run test/plan-gate-command.test.ts
```

Expected: RED because no durable handoff contract exists.

**Step 3: Implement**

Reuse existing host `newSession`/session APIs where available. The host may create a new session or present the copyable prompt, but the backend writes and validates the canonical handoff. Downstream workflows remain separately invoked; the handoff is a clean bridge, not an implicit process launcher.

**Step 4: Verify**

```bash
uv run pytest tests/unit/coherence/test_planning_handoff.py \
  tests/unit/coherence/test_planning_integration.py -q -o addopts=''
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run test/plan-gate-command.test.ts
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_handoff.py
uv run pyright src/coherence/planning
```

**Step 5: Commit**

```bash
git add src/coherence/planning pi-ext/factory-watch/src \
  tests/unit/coherence/test_planning_handoff.py \
  tests/unit/coherence/test_planning_integration.py \
  pi-ext/factory-watch/test/plan-gate-command.test.ts
git commit -m "feat: add explicit planning workflow handoff"
```

---

### Task 13: Register mature FEAT-017 requirements and prove semantic/trace coverage

**Objective:** Record the accepted mature design decisions as thin, human-consented SRs and prove that no independently governable obligation is missing or invented.

**Files:**

- Modify/create: `requirements/SR-<allocated>-*.md`
- Modify: `docs/features/FEAT-017.md`
- Modify: `bundles/FEAT-017.json`
- Modify: `tests/unit/coherence/test_planning_trace_contract.py`
- Modify: existing register/obligation/evidence records only through their writers

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing trace tests**

Enumerate every mature design decision and assert:

- obligations needing independent governance have exactly one SR;
- explanatory/non-binding prose does not become unnecessary SR duplication;
- each SR has an exact spec anchor;
- each SR has FEAT-017 ownership;
- each candidate SR has a deterministic derivation report reference;
- each adopted SR has explicit consent provenance;
- each SR has appropriate task/plan/feature/bundle relationships;
- the review context includes pre-existing SRs so duplicates/contradictions are visible;
- formal deferral is distinguishable from merely unimplemented work.

Include a completeness baseline: enumerate the revised spec decisions and verify that every independently governable obligation is represented or explicitly classified as non-SR prose/deferred scope.

**Step 2: Run RED**

```bash
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
uv run coherence register check --project-root .
uv run coherence trace check --project-root .
```

Expected: RED or pending output until the explicit human consent/allocation path is exercised.

**Step 3: Implement the registration path**

Use existing register/health-resolution writers. Do not hand-edit trace links when a command exists. Candidate SRs remain proposed until the derivation review is clean and the explicit consent phrase is recorded.

Do not use formal defer to hide missing implementation. Record deferred browser/retrieval/cross-workflow work only with the project’s normal explicit defer semantics.

**Step 4: Verify**

```bash
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
uv run coherence navigate health --repo-root . --json
uv run coherence register check --project-root .
uv run coherence trace check --project-root .
```

Record live repository-wide debt honestly; do not claim FEAT-017 has healed unrelated register/trace debt.

**Step 5: Commit**

```bash
git add requirements docs/features/FEAT-017.md bundles/FEAT-017.json \
  tests/unit/coherence/test_planning_trace_contract.py
git commit -m "feat: register mature planning workflow requirements"
```

Use the existing human allocation/consent surface; never fabricate consent in tests or in the agent loop.

---

### Task 14: Dogfood the complete workflow on a clean fixture and this repository

**Objective:** Demonstrate that the mature workflow works end to end rather than merely exposing isolated contracts.

**Files:**

- Create: `tests/fixtures/planning-dogfood/` or the repository’s established fixture location
- Create: `tests/integration/coherence/test_planning_dogfood.py`
- Modify: `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md` only with verified facts
- Modify: `docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md` only with verified completion/deferred scope

**Interfaces:**

- The shared Coherence/substrate contract and the host boundary described in this task.

**Step 1: Write failing dogfood tests**

Exercise the backend with deterministic fake agent backends and explicit test decision fixtures:

1. a clean initialized consumer fixture with a small planning request;
2. the repository’s own FEAT-017 planning artifacts as a self-hosting case.

Exercise:

```text
adaptive capture
-> provisional spec
-> Pass 1 review/fix/escalation loop
-> plan/task authoring
-> Pass 2 review/fix/escalation loop
-> candidate SR/FEAT/bundle derivation
-> Pass 3 review/fix/escalation loop
-> explicit consent fixture
-> deterministic final gates
-> downstream menu
-> handoff artifact
```

Test at least one agentic fix, one human escalation prompt/resolution, one repeated/stale finding, one duplicate/contradictory SR context case, one accepted deterministic warning, and one interrupted/resumed run.

Fixtures must be labelled test fixtures. They are not real human approval.

**Step 2: Run RED**

```bash
uv run pytest tests/integration/coherence/test_planning_dogfood.py -q -o addopts=''
```

Expected: RED until every mature state transition and gate dependency is connected.

**Step 3: Implement fixture harness only**

Do not weaken production gates. When real providers are unavailable in CI, inject `FakeAgentBackend`/fixture reports at the host/backend seam and separately test actual report validation and hash invalidation. Do not replace the real workflow with a test-only parallel implementation.

**Step 4: Verify all relevant gates**

```bash
uv run pytest tests/integration/coherence/test_planning_dogfood.py -q -o addopts=''
uv run pytest tests/unit/coherence -q -o addopts=''
uv run pytest tests/unit/factory/orchestrator -q -o addopts=''
uv run pytest tests/unit -q -o addopts=''
npm run typecheck --prefix pi-ext/scope-guard
npm test --prefix pi-ext/scope-guard -- --run
npm run typecheck --prefix pi-ext/factory-watch
npm test --prefix pi-ext/factory-watch -- --run
uv run ruff check src tests
uv run pyright src/coherence/planning src/coherence/navigate src/factory/orchestrator src/substrate/agents
uv run coherence navigate health --repo-root . --json
uv run coherence register check --project-root .
uv run coherence trace check --project-root .
python scripts/gates/ext.py
python scripts/gates/watch_ext.py
```

The full repository Pyright result must distinguish new diagnostics from known unrelated legacy diagnostics. Existing repository-wide register/trace debt must be reported rather than hidden.

**Step 5: Commit**

```bash
git add tests/ docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md \
  docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md
git commit -m "test: dogfood mature planning workflow"
```

---

## 5. Deterministic acceptance matrix

The implementation is not complete unless the following are exercised and verified.

| Area | Required result |
|---|---|
| Intent source | `.intent/intent.json` preserves the original request and verbatim answers; schema 1 reads remain compatible |
| Capture history | `.factory/planning/<run-id>/capture/events.jsonl` is append-only and resumable |
| Provisional spec | Agent may author it before all intent questions are resolved; unsupported/unclear content is caught by Pass 1 |
| Pass 1 | Dedicated `PLANNING_ALIGNMENT` review runs after spec authoring |
| Pass 2 | Dedicated `PLANNING_PLAN_REVIEW` review runs after plan/task authoring |
| Pass 3 | Dedicated `PLANNING_DERIVATION` review runs after SR/FEAT/bundle derivation |
| Requirement context | Every non-deleted SR is supplied with labelled lifecycle/status and trace context |
| Model selection | Classifier estimates complexity; user selects one concrete reviewer model for the run; no silent fallback |
| Model metadata | Provider/model/cost/capability metadata is recorded without secrets |
| Fix loop | Agent may directly fix only scoped artifacts; every fix gets a fresh review and deterministic reread |
| Resolution history | Every iteration is appended to the current run journal; previous execution history is never replaced |
| Human escalation | Specific unresolved prompts are shown; answers become next-loop inputs |
| SR consent | Only an explicit consent phrase after clean derivation can adopt candidate SRs |
| Warnings | Deterministic warnings are fixed or explicitly human-accepted through shared `DecisionFile` machinery |
| Freshness | Any relevant artifact/context/model/policy change invalidates affected reports and handoff |
| Syntax/links | Exact IDs, keywords, source anchors, paths, plan/task parity, registration, hashes, and trace links are deterministic gates |
| Presentation | First milestone presents text summary, escalation state, hashes, and legal next actions; no browser workbench required |
| Downstream | Explicit workflow menu; no planning command starts FEAT-13 or another workflow |
| Handoff | Hash-bound `handoff.json` plus rendered `handoff.md`; new session revalidates before acting |
| Dogfood | Clean consumer fixture and repository self-hosting case both exercise the complete backend path |

---

## 6. Execution/review protocol after this plan is accepted

When implementation is explicitly requested:

1. Work only in `C:/coding/pi-agent-factory-wt/feat17-planning` on `feat/coherence-feat17-planning`.
2. Do not touch unrelated parent-worktree design changes.
3. Use strict TDD for every code task: failing test, observed RED, minimal implementation, GREEN.
4. Keep the Python layer deterministic and host-neutral; all agent invocation remains behind injected host backends.
5. Use parallel development only for disjoint file sets after Task 1 contract freeze.
6. For each implementation task, run two independent reviews:
   - spec/contract-compliance and completeness;
   - code quality/security/fail-closed behavior.
7. Use fresh-context fixers for findings, then repeat both reviews until silent; verify the files themselves rather than trusting child status.
8. Perform a holistic integration review specifically checking:
   - `/plan` reaches adaptive capture and provisional spec authoring;
   - all three semantic passes are actually invoked;
   - full current SR context reaches every reviewer;
   - model classifier/catalog failures block honestly;
   - fresh review follows every direct agent fix;
   - resolution history is append-only;
   - human answers become next-loop prompts;
   - explicit SR consent is required and cannot be fabricated;
   - deterministic warnings cannot silently pass;
   - text summary/handoff is complete and browser scope remains deferred;
   - no Python planning path invokes a model, shell, subprocess, FEAT-13, or downstream workflow;
   - no credentials enter artifacts or diagnostics.
9. Run all acceptance commands independently. Do not accept subagent self-reports without checking files, test output, and gate output.
10. Keep commits narrowly scoped to FEAT-017 task files. Do not push or merge without explicit user instruction.

---

## 7. Risks and trade-offs

- **Large initial requirement packets:** Full non-deleted SR context is intentionally chosen for reliability. It costs tokens and scale; better retrieval is a deferred requirement.
- **Classifier dependency:** The workflow requires a configured inexpensive classifier. Missing classifier/catalog/model availability blocks instead of silently degrading.
- **Direct agent writes:** Direct writes are useful for an agentic resolution loop but increase risk. Role scope, current-run hash preconditions, deterministic rereads, and fresh reviewer invocations are mandatory.
- **Self-certification:** A fixer may not count its own output as review. A fresh dedicated invocation must verify every fix.
- **Human-answer ambiguity:** Escalation answers are next-loop prompts, not direct canonical edits. SR adoption still requires an explicit consent phrase.
- **Requirement duplication:** Keeping spec and SRs creates derivation cost. The thin-SR rule limits duplication; Pass 3 checks omissions and invented obligations.
- **Existing review-decision compatibility:** The current planning implementation has a hash-bound `review-decision.json` path. Preserve compatibility for old runs while moving new workflow semantics to escalation-driven review and explicit consent.
- **Host API drift:** Current Pi types expose the active model but not a complete model catalog. The host adapter must add the smallest typed catalog capability or report that the native API cannot satisfy the run.
- **Prompt injection:** Intent/spec/plan/SR content is untrusted data. Packets must delimit source content and instruct child agents not to follow embedded instructions.
- **Repository health debt:** FEAT-017 completion does not imply repository-wide register/trace health. Report unrelated debt honestly.
- **Browser temptation:** `/system` reuse is plausible but intentionally deferred. Do not smuggle an interactive review workbench into the first implementation.

---

## 8. Definition of done

The mature FEAT-017 update is complete only when all of the following are demonstrated:

- A host can start and resume adaptive, one-question-at-a-time brainstorming.
- The original request, answers, prompts, and capture events are durable and verbatim-preserving.
- The agent can author a provisional authority spec without a separate blanket intent approval.
- Pass 1 runs after spec authoring and reaches clean/escalated state through the fresh-review loop.
- Pass 2 runs after implementation plan/task authoring and reviews the entire current chain.
- Pass 3 runs after SR/FEAT/bundle derivation and checks thin-SR fidelity, completeness, duplication, and contradiction against all current SRs.
- The reviewer receives complete non-deleted SR context with lifecycle labels.
- A configured classifier estimates complexity; the user chooses one concrete reviewer model for the whole run; all retries use that selection.
- Agentic fixes are direct but scoped, recorded append-only, reread deterministically, and independently re-reviewed.
- Human escalations are specific, durable, and fed as prompts into the next loop iteration.
- Informational notes may remain, but unresolved semantic findings and deterministic warnings cannot.
- Deterministic gates verify exact schemas, paths, IDs, keywords, anchors, links, hashes, registration, parity, and freshness.
- Deterministic warnings require explicit human acceptance through the shared gate decision mechanism.
- Candidate SR adoption requires an explicit human consent phrase after clean derivation.
- The first milestone presents a text summary and legal next actions; no browser workbench is required.
- The clean result offers explicit downstream workflow choices and writes a hash-bound handoff for a new session.
- No planning command starts FEAT-13, a health workflow, development, a shell, or a model without the host/user-selected workflow boundary.
- The mature FEAT-017 requirements are thin, source-anchored, complete for independently governable obligations, and registered through existing Coherence paths.
- Dogfood passes on a clean consumer fixture and on the repository’s own FEAT-017 planning artifacts.
- Full available tests, lint, type checks, extension checks, and Coherence gates are run and reported honestly, including unrelated pre-existing debt.

**Canonical plan:** `docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md`

**Design provenance:** `.hermes/plans/2026-08-28_115844-feat17-mature-bootstrap.md`

**Execution:** Do not execute until explicitly requested. When requested, use the repository’s subagent-driven development and review protocol task-by-task; do not push or merge without explicit instruction.
