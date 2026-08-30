---
id: SPEC-FEAT-017-PLANNING-BOOTSTRAP
title: "FEAT-017 Planning Bootstrap Design"
status: draft
---

# FEAT-017 — Planning Bootstrap

_Status: design authority, final contract revision 2026-08-30._

This document is the canonical design contract for FEAT-017. It specifies a host-neutral planning
compiler that turns an exact user intent into reviewable, hash-bound planning artifacts and a
separately consumable handoff. It does not claim that the workflow, its producers, its graph
transport, or its human decisions are implemented or accepted today.

The current repository contains a deterministic checker, a path-safe capture substrate, review
record types, and a consumer-oriented bootstrap. Those are useful baseline capabilities, not proof
that FEAT-017's producer path is complete. In particular, the current bootstrap consumes supplied
specification and plan paths; this contract requires real producers that author and read back those
artifacts.

## 1. Ownership and feature boundaries

### 1.1 FEAT-017 ownership

FEAT-017 owns **planning compilation**:

- capture and preservation of the exact original request and conversational provenance;
- provisional authority-spec authoring;
- one run-local candidate SR derivation and its adversarial review;
- implementation-plan authoring;
- task materialization and bidirectional traceability gates;
- explicit human boundaries for unresolved decisions, warnings, SR adoption, and feature scope;
- final validation and a hash-bound handoff;
- optionally, materialization of a planning-stage Hermes Kanban transport graph.

FEAT-017 is not an execution engine. It never silently launches implementation, a shell, a model,
health recovery, or another workflow.

### 1.2 Split ownership

The layers have distinct sources of truth:

| Concern | Owner | Contract |
|---|---|---|
| Canonical intent, spec, candidate/adopted SR evidence, plan, task links, trace gates, decisions, and hashes | Coherence/substrate | Filesystem-first, schema-validated, hash-bound, fail closed |
| Durable card lifecycle, assignment, dependency state, attempts, heartbeats, workspace claims, retry/reclaim, and `needs_input` transport | Hermes Kanban | Durable transport state only; a Kanban state never substitutes for a Coherence gate |
| Conversation, native model catalog, user selection, rendering, and new-session creation | Thin Pi/Hermes adapters | Adapters call the shared workflow; they do not reimplement policy |
| Governed execution proposal and expected execution graph validation before implementation | FEAT-018 | FEAT-017 may check that the FEAT-018 capability is available; it does not own the execution proposal or graph |
| Cross-host conformance | FEAT-019 | Not part of FEAT-017 planning compilation |
| Optimization of a validated governed execution graph | FEAT-020 | May optimize only the graph validated by FEAT-018; it may not optimize an unvalidated FEAT-017 plan |

A planning-stage Kanban graph is a transport projection of the FEAT-017 lifecycle, not a second
scheduler. Hermes Kanban owns lifecycle state; Coherence owns artifact meaning and gate truth.

### 1.3 Feature-boundary decisions

There are no nested subfeatures in FEAT-017. If the captured intent yields multiple coherent
feature boundaries, the workflow stops at `needs_input` and asks a human to choose the boundary.
The answer must also state whether the selected features are handled sequentially and which
workflow/worktree is used for each. The agent must not silently create nested feature records,
allocate additional canonical FEAT files, or overwrite a supplied FEAT baseline.

A supplied `docs/features/FEAT-017.md`, bundle, or requirement set is an input snapshot. It is never
silently replaced by a newly derived baseline. Adoption or replacement requires a separately
recorded human decision with exact pre/post hashes. A planning run may produce candidate records
under its run directory while the canonical FEAT/SR records remain unchanged until adoption.

## 2. Inputs, outputs, and provenance

### 2.1 Required inputs

A run has a safe `run_id`, a selected project root, and:

1. the original user prompt, preserved byte-for-byte at the capture boundary;
2. each question and answer, including source, sequence, and exact text;
3. repository facts actually inspected, with path and hash provenance;
4. the current complete non-deleted SR context, including proposed, deferred, satisfied, and active
   records, source anchors, status provenance, and available trace relations;
5. the project policy and host-validated model catalog, without credentials;
6. any supplied canonical FEAT/SR/bundle baseline, preserved as a read-only snapshot until a human
   decision authorizes adoption or replacement;
7. an explicit request for a planning-stage Kanban graph, when that optional transport is desired.

Missing, stale, unsafe, contradictory, or unverified input blocks the dependent stage.

### 2.2 Canonical and derived outputs

The run produces or references these artifacts:

```text
.intent/intent.json
.factory/planning/<run-id>/capture/events.jsonl
.factory/planning/<run-id>/state.json
.factory/planning/<run-id>/spec-authoring.json
.factory/planning/<run-id>/candidate-sr-derivation.json
.factory/planning/<run-id>/reviews/<checkpoint>/<attempt>.json
.factory/planning/<run-id>/plan-authoring.json
.factory/planning/<run-id>/task-materialization.json
.factory/planning/<run-id>/traceability.json
.factory/planning/<run-id>/resolution-events.jsonl
.factory/planning/<run-id>/warning-decisions.json
.factory/planning/<run-id>/sr-consent.json
.factory/planning/<run-id>/feature-boundary-decision.json
.factory/planning/<run-id>/final-gates.json
.factory/planning/<run-id>/handoff.json
.factory/planning/<run-id>/handoff.md
.factory/planning/<run-id>/kanban-run.json              # optional transport
```

In the review path above, `<checkpoint>` is exactly one of `spec_alignment`,
`candidate_sr_alignment`, or `cross_artifact_alignment`, and `<attempt>` is a positive decimal
attempt number. The versioned `.factory/planning/<run-id>/candidate-sr-derivation.json` record is
the single run-local candidate-SR derivation artifact: it contains the candidate SR set and the
candidate feature/bundle projection together with their derivation and source hashes. If the
projection is stored separately, that record must name and hash the separate artifact. Neither form
is canonical FEAT/SR/bundle adoption; adoption remains later, explicit, and consent-gated.

The selected canonical source paths remain the repository's normal paths, for example:

```text
docs/superpowers/specs/<approved-name>.md
docs/superpowers/plans/<approved-name>.md
tasks/T-<digits>-<slug>.md
```

The run records the exact relative path and SHA-256 hash of every source and derived artifact it
uses. Run-local candidate SR records are not canonical adopted SRs.

### 2.3 Exact original prompt and challenge provenance

Intent provenance is normative, not a supplemental note. The capture journal and materialized
intent must preserve:

- the exact original prompt and the capture source;
- every question asked and answer received verbatim, in sequence;
- repository observations with path, observer/source, and hash where applicable;
- challenges raised against unsupported claims, contradictions, exclusivity, feasibility, security,
  or operability;
- the claim, rationale, evidence requested, originating answer/event, current status, exact human
  response when present, response provenance, and decision timestamp for every challenge;
- unresolved questions, deferred questions, and explicit cancellations;
- decisions and their actor kind, exact text, and input/output hashes.

Silence, a model response, a fixture value, or a missing event is not a human decision. Challenge
resolution is append-only. A response may resolve, revise, defer, or accept a challenge only when
its actor and provenance are explicit; unresolved or deferred challenges remain visible and block
any stage that requires their disposition.

The existing schema-one `.intent/intent.json` remains readable. A schema-two materialization may
add `run_id`, question/source/sequence metadata, a structured brief, capture status, redactions,
and challenge records without changing captured text. A failed snapshot replacement
snapshot must leave the last known-good snapshot untouched while retaining the new journal event
for recovery.

## 3. Workflow state and lifecycle

### 3a. Planning pipeline ownership and lifecycle

The corrected planning pipeline is intent capture -> real provisional-spec authoring/read-back/hash
-> `PLANNING_ALIGNMENT` -> one run-local candidate SR derivation and
`CANDIDATE_SR_ALIGNMENT` -> real implementation-plan authoring/read-back/hash -> task
materialization -> `CROSS_ARTIFACT_ALIGNMENT` and trace gates -> human boundaries/consent and
canonical adoption -> final gates -> handoff. Candidate SR alignment is before plan authoring;
there is no post-plan SR derivation.

#### 3a.1 Adaptive clarify and align

`adaptive-brainstorming` means focused, repository-aware questions with verbatim prompt/question/
answer preservation, not a fixed questionnaire. `provisional-spec` is intentional: the producer
may author it before every question is answered, while unresolved challenges remain explicit and
block the stages that require a decision.

### 3b. Ordering and ownership

Coherence owns canonical artifacts, hashes, provenance, semantic gates, traceability, warning
records, consent validation, and canonical adoption. Hermes Kanban, when requested, owns only
planning-stage transport state. Pi and Hermes remain thin adapters. FEAT-018 owns governed execution
proposal/expected-graph validation; FEAT-019 owns cross-host conformance; FEAT-020 may optimize
only a graph already validated by FEAT-018. No feature split creates nested subfeatures or silently
overwrites a supplied FEAT baseline.

### 3c. Semantic checkpoints

The three checkpoints are retained in this corrected order:

1. `PLANNING_ALIGNMENT` / `spec_alignment` runs after the real provisional-spec producer and
   compares the spec with complete intent/provenance and full current SR context.
2. `CANDIDATE_SR_ALIGNMENT` / `candidate_sr_alignment` runs after the one run-local candidate SR
   derivation and before plan authoring; it checks duplicates, conflicts, unsupported claims,
   compatibility, missing obligations, complete context, and feature boundaries.
3. `CROSS_ARTIFACT_ALIGNMENT` / `cross_artifact_alignment` runs after implementation-plan
   authoring and task materialization; it checks the intent/spec/candidate/task chain and
   bidirectional trace closure.

The old late-SR checkpoint names and order are superseded. They are not additional stages and must
not be implemented as a second independent derivation.

### 3d. Deterministic contract and available gates

Every producer and checkpoint uses strict parsing, safe relative paths, deterministic ordering,
read-back, exact SHA-256 hashes, and current input hashes. Existing Coherence gate, decision, trace,
register, and filesystem machinery is reused rather than replaced. Missing, malformed, stale,
unsafe, or contradictory input fails closed. Every security/operability warning blocks until fixed
or explicitly dispositioned by a human through a validated decision writer. Every downstream gate
requires its predecessor's current artifact/input hashes and, when that predecessor is a
review/resolution stage, a current clean review report plus deterministic gate evidence. A non-clean
report, escalation record, human response, or Kanban `done` state never satisfies that requirement.

### 3e. Review, resolution, escalation, and consent

Every checkpoint receives the complete non-deleted SR context, including proposed, deferred,
satisfied, and active records with source anchors and available trace context. The selected reviewer
model is fixed for the run. A scoped fix is followed by deterministic reread and a fresh independent
review; resolution history is append-only. An unresolved finding is recorded as an escalation and
leaves the review/resolution stage blocked in `needs_input`; an escalation record is never a
completion record. The stage may leave that blocked state only after a validated human answer or
decision is written through the specified `DecisionFile` writer, with the exact finding scope and
current artifact/input hashes. That record queues a fresh independent review on the same
stage/revision lineage; the human response alone never releases a child. The stage completes only
when that fresh report is clean, current, hash-bound, and its deterministic gate passes. A clean
review never grants consent: canonical SR adoption requires exact, fresh, hash-bound human consent.

### 3f. Summary, downstream menu, and handoff

The first presentation is a text summary with review status, challenges, warnings, hashes, and
legal next actions. A richer browser workbench is deferred. A clean run exposes an explicit
menu and writes a hash-bound handoff with `starts_automatically: false`; a new session revalidates
it before acting and no planning stage starts downstream work.

### 3g. State machine and invariants

### 3.1 States

The durable state projection is:

```text
capture
  -> intent_provisional
  -> spec_authoring
  -> spec_written
  -> spec_alignment
  -> candidate_sr_derivation
  -> candidate_sr_alignment
  -> plan_authoring
  -> plan_written
  -> task_materialization
  -> cross_artifact_alignment
  -> human_boundaries
  -> canonical_adoption
  -> final_gates
  -> handoff_ready
```

Any state may become `needs_input` or `blocked`. Resumption uses the journal, immutable review
records, and current hashes. A state file is a derived projection; it cannot advance itself or
override a failed gate.

Globally, `escalated`, `needs_input`, `blocked`, and `human response recorded` are non-terminal
states, never completion states. A recorded human response is only an input to the next validated
review/resolution attempt; it cannot release a child by itself.

### 3.2 State invariants

- A stage cannot run until every predecessor has a durable, hash-matching completion record; a
  review/resolution predecessor additionally requires its current clean review report and
  deterministic gate evidence.
- A producer completion requires write, read-back, strict parse, and a recorded SHA-256 hash.
- A source change invalidates that stage and every downstream projection; old evidence remains
  immutable history.
- A review finding is either resolved by a permitted scoped fix followed by a fresh independent
  review, or recorded as an escalation that leaves the stage blocked in `needs_input`; it cannot be
  silently dropped or treated as completion.
- A blocked review/resolution stage resumes only after the validated `DecisionFile` writer records a
  human answer/decision with actor, exact finding scope, reason, timestamp, and current
  artifact/input hashes, and then queues a fresh independent review on the same stage/revision
  lineage. Agents cannot mint consent or warning disposition, and a human response alone cannot
  release a child.
- A scoped fix invalidates the affected review/resolution stage and every descendant, even when old
  cards or reports say `done`; all downstream gates must use the new current clean evidence.
- Reclaim and retry reuse the run/stage idempotency key and append attempt evidence; they do not
  duplicate canonical artifacts, task records, cards, or decisions.
- A terminal `handoff_ready` state always has `starts_automatically: false`.

## 4. Required lifecycle order

This is the only normative FEAT-017 order. Any older description that placed SR derivation after
plan authoring or treated a late SR pass as authoritative is superseded and must not be implemented.

### Step 1 — Intent capture

The host captures the exact prompt and conducts adaptive, repository-aware clarification. Questions
are focused on goal, scope, non-goals, constraints, completion, risks, and trade-offs; they are not a
fixed questionnaire. The host persists events and challenges through the capture boundary and may
leave the intent provisional or `needs_user`.

### Step 2 — Real provisional-spec authoring, read-back, and hash

A concrete producer, invoked through the host-neutral agent/backend seam, authors the provisional
authority specification from the captured intent and inspected facts. Supplying an already-written
spec path is not a substitute for this producer. The producer writes only its approved spec target,
reads it back, validates frontmatter and anchors, and records the exact hash. The spec may be
provisional; it must not claim unresolved decisions are settled.

### Step 3 — Semantic checkpoint 1: spec alignment

`PLANNING_ALIGNMENT` reviews the real provisional spec against the complete intent/provenance
record, challenges, repository facts, and full current SR context. It checks omission, unsupported
claims, contradictions, feasibility, security/operability concerns, and unresolved boundaries.
Scoped fixes invalidate this checkpoint and every descendant, then require a fresh independent review.
An unresolved finding leaves this checkpoint blocked in `needs_input`; after a validated human
answer/decision is recorded with exact finding scope and current artifact/input hashes, the same
stage/revision lineage queues a fresh review. Only a current, hash-bound clean report whose
deterministic gate passes can feed candidate derivation; it is not human approval.

### Step 4 — One run-local candidate SR derivation and adversarial review

Exactly one derivation operation creates the run-local candidate SR set from the reviewed provisional
authority specification. It occurs before plan authoring. The candidate set is a versioned,
hash-bound run artifact; it is not yet canonical SR adoption.

The `CANDIDATE_SR_ALIGNMENT` reviewer receives the full current non-deleted SR context and must
explicitly review:

- duplicate and near-duplicate obligations;
- conflicts with existing SR statements, status, ownership, or anchors;
- unsupported or over-broad claims;
- compatibility with current schemas, register, feature, and bundle conventions;
- missing independently governable obligations;
- obligations that are explanatory/non-SR prose and why;
- complete-context coverage and exact source anchors;
- feature-boundary splits and any supplied FEAT baseline that must remain untouched.

A correction is a scoped revision of this one run-local candidate set and its derivation evidence;
it is not a redundant second independent SR derivation. There is no second derivation after plan
authoring. The reviewed candidate set and its hash are inputs to the plan producer.

### Step 5 — Real implementation-plan authoring, read-back, and hash

A concrete plan producer authors the implementation plan from the reviewed spec and candidate SR
set. Supplying an existing plan path is not enough. The producer writes the approved plan target,
reads it back, validates its task grammar and frontmatter, and records the exact hash.

The plan contains implementation and verification work together. Every task has explicit
implementation evidence and verification evidence, test-artifact obligations, exact likely test
paths, and exact validation commands. A separate hand-authored verification plan is prohibited; a
derived coverage report is allowed.

### Step 6 — Task materialization

The plan-to-task producer materializes one task record per plan task. Materialization is idempotent
and does not pre-create artifacts merely to make a consumer test pass. Each generated task carries
the target contract in its metadata/body:

- source plan link and source spec link;
- the candidate/adopted SR links, each typed `implements`, `verifies`, or `supports`, or an explicit
  reviewed `non-SR` classification and reason;
- acceptance criteria;
- exact test paths and commands;
- implementation evidence obligations and expected evidence paths;
- task identity, source task number, dependencies, allowed/prohibited paths, and current-run hash.

Before handoff, every task must bind to an adopted SR through a typed relationship or to an
explicitly reviewed non-SR classification. Unbound tasks block.

### Step 7 — Semantic checkpoint 3: cross-artifact and traceability alignment

`CROSS_ARTIFACT_ALIGNMENT` runs after plan authoring and task materialization. It reviews the
intent/spec/candidate-SR/plan/task chain, bidirectional links, task coverage, implementation and
verification evidence obligations, exact commands, feature boundary, and current hashes. It also
runs the deterministic trace gates. It must prove closure in both directions:

```text
intent decision/challenge
  <-> spec anchor
  <-> candidate/adopted SR or reviewed non-SR classification
  <-> plan task
  <-> generated task record
  <-> implementation evidence and verification test
```

A derived coverage report may summarize this closure but cannot replace the canonical links or
producer-path tests.

### Step 8 — Human boundaries, consent, and canonical adoption

The workflow stops for explicit human decisions where required:

- unresolved challenge, feasibility, contradiction, warning, or feature-boundary choice;
- selection of sequential workflows/worktrees when boundaries split;
- exact candidate SR adoption;
- whether any supplied canonical FEAT/SR/bundle baseline may be changed.

Only a validated human consent writer may adopt the exact candidate SR set. Consent binds the run,
candidate-set hash, derivation-review hash, source artifact hashes, exact candidate IDs, actor,
phrase, reason, and time. Semantic cleanliness, an escalation answer, `accept_warning`, model
output, fixture data, or silence is not consent.

Every security or operability warning blocks until it is either fixed or explicitly dispositioned by
a human through the validated warning/decision writer. `accept_warning` must not be an arbitrary
agent-controlled set or an in-memory bypass.

### Step 9 — Final gates

Final gates re-read all current sources and verify schemas, paths, hashes, freshness, provenance,
challenge state, candidate/adopted SR bindings, task parity, bidirectional trace closure, warning
and consent decisions, feature-boundary decisions, optional Kanban reconciliation, and the FEAT-018
capability seam. A missing FEAT-018 capability is an honest `blocked` result, not a claim that
execution validation occurred.

The current repository's consent/evidence snapshots are stale for this contract. That is a
fail-closed finding requiring clean re-derivation and fresh exact human consent; it is not plan
success and must not be repaired by editing the old snapshot in place.

### Step 10 — Handoff

Only a green final-gate result produces a handoff. The handoff is hash-bound, records all legal
next actions, and sets `starts_automatically: false`. A new session must revalidate the exact
handoff and all current hashes before it acts. Handoff never silently launches implementation,
FEAT-018, FEAT-019, FEAT-020, health recovery, or any downstream work.

## 5. Review protocol and human boundary

### 5.1 The three semantic checkpoints

The three semantic review checkpoints are retained, but their corrected order is fixed:

| Checkpoint | Runs after | Primary evidence |
|---|---|---|
| `PLANNING_ALIGNMENT` / `spec_alignment` | real provisional-spec authoring and read-back | intent, provenance/challenges, spec, repository facts, full SR context |
| `CANDIDATE_SR_ALIGNMENT` / `candidate_sr_alignment` | the one run-local candidate SR derivation, before plan authoring | provisional spec, candidate set, derivation evidence, full SR context, compatibility/duplicate/conflict/missing-obligation findings |
| `CROSS_ARTIFACT_ALIGNMENT` / `cross_artifact_alignment` | real plan authoring and task materialization | intent, spec, candidate/adopted SR bindings, plan, tasks, feature boundary, trace and test evidence |

The prior late-SR ordering is superseded. Do not add a redundant post-plan SR derivation or require a
separate hand-authored verification plan.

### 5.2 Fresh review loop

Each checkpoint follows:

```text
deterministic preflight
  -> fresh reviewer invocation with complete required context
  -> strict report validation
  -> clean current report + deterministic gate -> stage complete
  -> scoped fix -> append revision/evidence, invalidate stage + descendants
     -> deterministic read-back, hashes, and fresh independent review
  -> escalation record -> append evidence -> stage blocked `needs_input`
     -> validated human answer/decision through the `DecisionFile` writer
        with exact finding scope and current artifact/input hashes
     -> deterministic read-back, hashes, and fresh independent review
        on the same stage/revision lineage
  -> repeat within a bounded budget, or remain blocked
```

The selected reviewer model is fixed for the run after host catalog validation; retries reuse it.
A reviewer/fixer cannot self-certify. A scoped fix invalidates the affected checkpoint and all
downstream projections before the fresh review. An escalation record, `needs_input` state, or human
response is never completion evidence and never releases a child. Provider errors, malformed output,
stale packets, exhausted budgets, and missing capabilities block or escalate into this same loop.

Review packets delimit source artifacts as untrusted data. Embedded instructions in intent, spec,
SR, plan, task, or fixture content cannot change the reviewer's role, permissions, or acceptance
rules.

### 5.3 Human decisions

Human answers are captured verbatim as next-loop inputs with provenance. They do not silently edit
canonical artifacts; a permitted producer/fixer applies them and the next review rereads the result.
An objection, deferral, or unresolved response is not consent.

No model response, agent state, test fixture, file presence, Kanban `done`, or empty warning list
counts as human authorization. The human decision boundary must be observable in the persisted
record.

## 6. Artifact, hash, and trace contracts

### 6.1 Producer contract

Every real producer must expose a typed host-neutral operation with:

- an explicit input manifest and approved output path;
- a backend capability, role, and allowed/prohibited path scope;
- strict structured result validation;
- atomic write behavior;
- read-back of the exact output;
- strict parse/semantic validation;
- SHA-256 of output and input manifest;
- append-only attempt and error evidence;
- no approval, consent, warning disposition, or downstream launch authority.

A producer test must invoke the producer and observe the output. A test that copies a prebuilt spec,
plan, task, or FEAT artifact into place tests only a consumer and does not satisfy FEAT-017.

### 6.2 Intent and challenge contract

The existing paths are retained:

```text
.intent/intent.json
.factory/planning/<run-id>/capture/events.jsonl
.factory/planning/<run-id>/state.json
```

Schema-one reads remain compatible. Schema-two fields must include the run identity, exact prompt,
answers with question/source/sequence, structured brief, capture status, redactions, challenges,
challenge responses, and provenance. Journal events are strictly ordered and append-only. Atomic
snapshot replacement failures preserve the last known-good `.intent/intent.json` while leaving the
journal as the recovery source.

### 6.3 Provisional authority spec

The spec is the canonical semantic authority for this run. It must have strict frontmatter with
`id`, `title`, and `status`, stable non-fenced anchors, explicit intent/challenge coverage,
assumptions, non-goals, feature boundary, implementation/verification obligations, and visible
unresolved/provisional status. It must not claim SR adoption, implementation completion, human
consent, or downstream execution.

### 6.4 Candidate SR contract

The run-local candidate record contains at least:

```json
{
  "schema": 1,
  "run_id": "<safe-id>",
  "source_spec": {"path": "<relative>", "sha256": "<sha256>"},
  "derivation_revision": 1,
  "candidate_srs": [
    {
      "id": "SR-candidate-1",
      "statement": "<one independently governable obligation>",
      "source_anchor": "<stable spec anchor>",
      "classification": "sr",
      "evidence_needed": ["<path or command>"],
      "relationships": {"implements": [], "verifies": [], "supports": []}
    }
  ],
  "non_sr_classifications": [],
  "full_context_sha256": "<sha256>",
  "review_hash": "<sha256>"
}
```

IDs, anchors, status, compatibility, and relation targets are checked deterministically. Existing
SR records remain visible, including duplicates and contradictions; the derivation cannot hide or
discard them. Candidate records do not become canonical requirements until exact human consent and
canonical adoption have passed.

### 6.5 Implementation-plan contract

The plan frontmatter binds to this spec with `spec_ref` and records candidate-set provenance. Each
plan task includes:

- objective and implementation scope;
- exact files to create/modify/test;
- dependency/order;
- RED/GREEN or documentation-verification procedure;
- exact validation commands and expected evidence;
- acceptance criteria;
- prohibited scope;
- implementation and verification obligations in the same task;
- typed candidate/adopted SR or reviewed non-SR classification.

The plan is not an execution authorization. Its task sections are the source for materialization.

### 6.6 Generated-task contract

A materialized task must preserve the plan/spec/SR links and source task number. Its canonical
metadata/body must include `id`, `title`, `status`, `source_plan`, `source_task`, `source_spec`,
`sr_bindings`, `acceptance_criteria`, `test_paths`, `test_commands`, `implementation_evidence`,
`verification_evidence`, dependencies, allowed/prohibited paths, and the exact plan/spec/candidate
hashes used. Each SR binding has one of `implements`, `verifies`, or `supports`. A reviewed non-SR
record has classification, reason, reviewer/report hash, and source anchor. Missing or ambiguous
bindings block handoff.

### 6.7 Bidirectional trace closure

The trace gate must prove both forward and reverse coverage. It must enumerate every intent decision,
challenge, and independently governable spec obligation, then resolve it to exactly one candidate SR
or reviewed non-SR classification, plan task, generated task, and verification evidence. It must also
start from every candidate/adopted SR and task and resolve back to a valid spec anchor and intent or
reviewed rationale. Explanatory prose is not silently promoted to SRs; omitted obligations are not
silently accepted.

### 6.8 Handoff contract

`handoff.json` and `handoff.md` are written under the run directory only. The JSON binds:

- run and contract schema/version;
- exact prompt/intent, spec, candidate/adopted SR, plan, task, FEAT/bundle baseline, and evidence
  hashes;
- all three current clean review report hashes, each bound to the current artifact/input hashes and
  deterministic checkpoint-gate evidence, plus the resolution-journal digest; a non-clean or
  escalation report hash, `needs_input` record, or human-response hash cannot satisfy this field;
- human challenge, feature-boundary, warning, and consent decision hashes;
- FEAT-018 capability result;
- selected downstream workflow and legal menu;
- `starts_automatically: false`.

The markdown rendering is derived from the JSON. A consumer validates path safety, exact hashes,
clean final gates, and `starts_automatically` before it can do anything else.

## 7. Failure, recovery, and security semantics

### 7.1 Fail closed

The workflow blocks on missing or malformed artifacts, unsafe paths, stale hashes, incomplete
provenance, unresolved challenges, duplicate/conflicting/unsupported/missing obligations, unbound
tasks, invalid trace closure, missing capability, invalid human decisions, or graph mismatch.

All security and operability warnings block until resolution or explicit human disposition. There is
no warning category that can be ignored because it is inconvenient or because an agent says it is
acceptable. `accept_warning` is not a consent mechanism and cannot mutate a bypass set.

### 7.2 Recovery

Every attempt, review, fix, escalation, human answer, challenge decision, and hash transition is
append-only. Reclaim after interruption, timeout, crash, or lost heartbeat resumes from the last
verified predecessor. It does not replace prior events or reuse a stale snapshot as if it were
current. If a materialization write fails, the previous good snapshot is retained and the journal
remains authoritative for retry.

A retry is allowed only when its input hashes still match. Otherwise the stage is invalidated and
must begin a fresh attempt. Repeated findings or exhausted retry budgets remain blocked and require
human action.

### 7.3 Untrusted content and secrets

Intent, repository text, spec, SR, plan, task, reviewer output, and fixture content are data, not
instructions. Packets must delimit them and enforce role scopes. No credential, token, password,
secret, or provider configuration is written to canonical artifacts, packets, reports, journals,
Kanban metadata, or diagnostics; secret-shaped values are rejected or rendered as `[REDACTED]`.
Paths must stay below the selected project root and reject traversal, symlink/reparse escapes,
absolute machine-specific persistence, malformed JSON/YAML/frontmatter, duplicate keys, and
non-finite values.

## 8. Optional Hermes Kanban planning graph

When requested and supported, FEAT-017 materializes one planning transport graph. If the capability
is unavailable, the run reports an explicit capability block; it must not emulate Kanban with prose
or silently dispatch work without the graph.

The intended graph is:

```text
planning-run
  -> capture
  -> provisional-spec-authoring
  -> spec-alignment
  -> candidate-sr-derivation
  -> candidate-sr-alignment
  -> implementation-plan-authoring
  -> task-materialization
  -> cross-artifact-alignment
  -> human-boundaries-and-adoption
  -> final-gates
  -> handoff
```

Each edge is a strict dependency. The root and all stage cards are materialized and reconciled
before any worker is dispatched. Each card includes run/stage/version, parent IDs, exact input and
output paths/hashes, role/assignee, allowed/prohibited paths, workspace mode, idempotency key,
attempt/retry/timeout/heartbeat/reclaim state, blocking reason, completion evidence, and the
Coherence downstream gate.

Writing stages use one serialized shared `dir` workspace rooted at the selected project, or an
isolated worktree whose outputs are explicitly reconciled before the child runs. Two writers may not
share a directory. Review and gate stages are read-only. A child cannot run when any parent is
missing, incomplete, stale, or merely represented by prose. A Kanban `done` card cannot bypass a
Coherence gate. Re-running an idempotency key returns the existing card and does not duplicate
children or artifacts. Recovery tests must prove interruption, retry/reclaim, workspace
serialization, graph reconciliation, `needs_input` pause/resume, and no silent downstream
execution.

This graph transports planning lifecycle only. It does not schedule FEAT-018 execution, FEAT-019
conformance, FEAT-020 optimization, implementation, or health recovery.

### 8.1 Stage-card contract

The following table is normative for the root and every stage card. “Review/resolution” is one
durable stage with append-only review attempts; a scoped fix invalidates that stage and all downstream
cards and requires a fresh independent review. It is not a second SR derivation or a hidden scheduler.

All paths in this table are repository-relative and use the artifact naming contract in §2.2. In a
review path, `<checkpoint>` is `spec_alignment`, `candidate_sr_alignment`, or
`cross_artifact_alignment`, and `<attempt>` is a positive decimal attempt number. Each card's stable
idempotency key is `feat17/<run-id>/<stage-id>/v1`, where `<stage-id>` is the exact lowercase,
hyphenated graph node name in the table and `v1` is the stage-card contract version. Revision and
attempt are separate card fields: retries/reclaims keep the same key and append attempt evidence;
a scoped fix creates a new revision in the same durable stage lineage and invalidates its descendants.

| Stage | Inputs -> outputs | Role and paths | Workspace, key, retry/block/completion | Downstream gate |
|---|---|---|---|---|
| `planning-run` (root) | request/policy/catalog -> `.factory/planning/<run-id>/state.json` and optional `.factory/planning/<run-id>/kanban-run.json` | coordinator; run directory only; no canonical writes | coordinator workspace; key `feat17/<run-id>/planning-run/v1`; reclaim resumes the same run; block on unsafe/missing inputs; complete only after graph reconciliation | all stage cards exist with exact edges and contract hash |
| `capture` | prompt, questions, repository observations -> `.intent/intent.json` and `.factory/planning/<run-id>/capture/events.jsonl` | capture agent; `.intent/` and run capture paths only | serialized project `dir`; key `feat17/<run-id>/capture/v1`; append attempt evidence on retry/reclaim; block on incomplete/unsafe capture; complete on durable verbatim read-back/hash | current intent/provenance gate |
| `provisional-spec-authoring` | captured intent, facts, SR context -> `docs/superpowers/specs/<approved-name>.md` and `.factory/planning/<run-id>/spec-authoring.json` | spec producer; approved spec target plus run evidence only | serialized writer workspace; key `feat17/<run-id>/provisional-spec-authoring/v1`; retry same target/key, never overwrite silently; block on producer/read-back/schema failure; complete on strict parse and hash | current spec-alignment preflight |
| `spec-alignment` (Pass 1 review/resolution) | spec, intent, challenges, full SR context -> `.factory/planning/<run-id>/reviews/spec_alignment/<attempt>.json` | fresh semantic reviewer; read-only review path, `.factory/planning/<run-id>/resolution-events.jsonl`, and approved fixer target only | read-only review workspace; key `feat17/<run-id>/spec-alignment/v1`; unresolved findings/warnings or missing context leave the card `blocked`/`needs_input`; an escalation record never completes it; a validated human answer/decision through the `DecisionFile` writer, with exact finding scope and current artifact/input hashes, queues a fresh independent review on the same stage/revision lineage; complete only when the fresh report is current, hash-bound, clean, its deterministic gate passes for spec alignment | current candidate-derivation gate requires this clean report/gate evidence |
| `candidate-sr-derivation` | reviewed spec -> `.factory/planning/<run-id>/candidate-sr-derivation.json` containing the one run-local candidate SR/feature/bundle projection and derivation record | candidate derivation agent; run directory only, canonical records read-only | serialized run writer; key `feat17/<run-id>/candidate-sr-derivation/v1`; retry/reclaim resumes one lineage and never duplicates; block on stale spec or unsafe/ambiguous boundaries; complete on deterministic candidate set/projection and source hashes | current candidate-SR alignment preflight |
| `candidate-sr-alignment` (Pass 2 review/resolution) | candidate set, spec, full SR context -> `.factory/planning/<run-id>/reviews/candidate_sr_alignment/<attempt>.json` | fresh SR reviewer; read-only review path plus `.factory/planning/<run-id>/resolution-events.jsonl` | read-only review workspace; key `feat17/<run-id>/candidate-sr-alignment/v1`; duplicate/conflict/unsupported/missing-obligation/security findings leave the card `blocked`/`needs_input`; an escalation record never completes it; a validated human answer/decision through the `DecisionFile` writer, with exact finding scope and current artifact/input hashes, queues a fresh independent review on the same stage/revision lineage; complete only when the fresh report is current, hash-bound, clean, its deterministic gate passes for candidate-SR alignment | current plan-authoring gate requires this clean report/gate evidence |
| `implementation-plan-authoring` | reviewed spec and candidate SR set -> `docs/superpowers/plans/<approved-name>.md` and `.factory/planning/<run-id>/plan-authoring.json` | plan producer; approved plan target plus run evidence only | serialized writer workspace; key `feat17/<run-id>/implementation-plan-authoring/v1`; retry same key/read-back, no supplied-path shortcut; block on stale inputs or invalid task grammar; complete on strict parse/hash with implementation and verification obligations together | current task-materialization preflight |
| `task-materialization` | reviewed plan -> `tasks/T-<digits>-<slug>.md` records and `.factory/planning/<run-id>/task-materialization.json` | plan-to-task producer; approved task targets plus run evidence only | serialized task writer or isolated worktree reconciled before child; key `feat17/<run-id>/task-materialization/v1`; idempotent replay; block on parity/unbound task/path violation; complete when every task has required links/evidence | current cross-artifact review/trace preflight |
| `cross-artifact-alignment` (Pass 3 review/resolution) | intent/spec/candidate SR/plan/tasks/trace evidence -> `.factory/planning/<run-id>/reviews/cross_artifact_alignment/<attempt>.json` and `.factory/planning/<run-id>/traceability.json` | fresh independent reviewer plus deterministic trace gate; read-only review/gate paths | read-only review workspace; key `feat17/<run-id>/cross-artifact-alignment/v1`; one-way/missing trace, stale hash, or warning leaves the card `blocked`/`needs_input`; an escalation record never completes it; a validated human answer/decision through the `DecisionFile` writer, with exact finding scope and current artifact/input hashes, queues a fresh independent review on the same stage/revision lineage; complete only when the fresh report is current, hash-bound, clean, its deterministic gate passes, and bidirectional trace evidence is current | current human-boundaries preflight requires this clean report/gate evidence |
| `human-boundaries-and-adoption` | clean reviews, candidate set, warnings, boundary choices -> `.factory/planning/<run-id>/warning-decisions.json`, `.factory/planning/<run-id>/sr-consent.json`, `.factory/planning/<run-id>/feature-boundary-decision.json`, and only after consent canonical SR/FEAT/bundle records | validated human-decision writer; run decision paths plus approved canonical writer paths; supplied baselines read-only until explicit replacement | serialized decision/canonical writer workspace; key `feat17/<run-id>/human-boundaries-and-adoption/v1`; reclaim preserves pending `needs_input`; block on any unresolved warning/challenge, missing consent, or scope choice; complete only on validated hash-bound decisions and exact adoption | current final-gates preflight |
| `final-gates` | all current artifacts, decisions, optional graph, FEAT-018 capability -> `.factory/planning/<run-id>/final-gates.json` | deterministic gate runner; run evidence only, read-only canonical inputs | read-only gate workspace; key `feat17/<run-id>/final-gates/v1`; retry recomputes current hashes; block on stale consent/evidence, unavailable required capability, or graph mismatch; complete only on green current report | current handoff preflight |
| `handoff` | green final gates -> `.factory/planning/<run-id>/handoff.json` and `.factory/planning/<run-id>/handoff.md` plus explicit next-action menu | handoff writer/presenter; run handoff paths only; never dispatches | read-only inputs, atomic run write; key `feat17/<run-id>/handoff/v1`; idempotent by final-gate hash; block on any hash change; complete with validated `starts_automatically: false` | no automatic downstream execution |

No card may be marked complete from prose, a model assertion, fixture data, or Kanban `done` alone.
The coordinator must reconcile each card’s recorded inputs, outputs, role, paths, workspace claim,
attempt history, and required Coherence gate before releasing its children. Every downstream gate
must require the predecessor's current artifact/input hashes and, for a review/resolution predecessor,
the fresh clean report and deterministic gate evidence described in that row. A missing stage, edge,
hash, clean report, or completion record leaves the child unrunnable and visible as `blocked` rather
than being silently skipped. A non-clean escalation hash or a human-response hash can never satisfy
the handoff's three-clean-review requirement.

## 9. Baseline limitations and explicit deferrals

The current repository baseline must be reported honestly:

- `src/coherence/planning/bootstrap.py` and `coherence plan bootstrap --decompose` consume supplied
  intent/spec/plan paths; they are not the required real spec and plan producers.
- `src/substrate/ledger/plans.py` performs basic plan parsing/task creation; the richer typed task
  contract and evidence bindings are future implementation work.
- `src/coherence/planning/workflow.py` and `semantic.py` contain an older stage vocabulary/order;
  the corrected three-checkpoint order in this document supersedes it.
- The current dogfood consumer fixture copies prebuilt spec/plan/task/FEAT artifacts; it does not
  prove producer-path behavior and must be replaced or complemented by producer invocation tests.
- Existing warning acceptance and consent paths must be hardened so agent state cannot stand in for
  validated human decisions.
- Existing `.factory/planning/feat17-finalized-planning` consent/evidence hashes are stale for this
  final contract. They are a fail-closed baseline finding, not evidence of plan acceptance.
- FEAT-018/019/020 artifacts or capabilities are not assumed to exist merely because FEAT-017
  names their boundary.

Deferred from FEAT-017 are an interactive browser planning workbench, token-optimized SR retrieval,
general cross-workflow model policy, cross-host conformance, execution-graph optimization, and
automatic downstream execution. Deferral is not completion and may not be used to hide a missing
obligation or warning disposition.

## 10. Acceptance criteria

FEAT-017 is implementation-review ready only when its implementation and verification evidence
prove all of the following:

1. Exact prompt, questions, answers, repository observations, challenges, decisions, unresolved
   state, and provenance are durable, verbatim where required, append-only, and recoverable.
2. A real provisional-spec producer is invoked, writes the approved target, reads it back, validates
   it, and records its hash; a prompt or supplied path alone does not satisfy this criterion.
3. `PLANNING_ALIGNMENT` runs after that spec producer and before candidate derivation.
4. Exactly one run-local candidate SR derivation occurs before plan authoring, and its adversarial
   review checks duplicates, conflicts, unsupported claims, compatibility, missing obligations,
   complete context, and feature boundaries without requiring a redundant second derivation.
5. A real implementation-plan producer is invoked, writes and reads back a plan containing both
   implementation and verification tasks, explicit test-artifact obligations, commands, criteria,
   and hashes.
6. Tasks are materialized only from that plan and carry source spec/plan/SR links, typed relations
   or reviewed non-SR classification, acceptance criteria, exact test paths/commands, evidence
   obligations, and dependency metadata.
7. `CROSS_ARTIFACT_ALIGNMENT` runs after plan and task materialization and proves bidirectional
   trace closure through producer-path behavior tests.
8. Human boundaries are explicit: feature splits stop for selection and sequential
   workflow/worktree decisions; supplied FEAT baselines are not silently overwritten; warnings,
   unresolved challenges, consent, and canonical adoption require validated human records.
9. Every security/operability warning blocks until fixed or explicitly human-dispositioned; no
   `accept_warning`, model response, silence, or fixture data bypasses that gate.
10. Optional Kanban materialization proves the root/stage graph, dependencies, idempotency,
    serialized workspace, retry/reclaim, recovery, reconciliation, and no silent downstream
    execution. Hermes Kanban is transport state, not a second scheduler.
11. FEAT-018 capability is checked honestly and blocks when unavailable; FEAT-017 does not claim
    FEAT-018, FEAT-019, or FEAT-020 behavior.
12. Final gates reject stale consent/evidence and require clean re-derivation plus fresh exact human
    consent. Handoff is current, hash-bound, validated, and explicitly
    `starts_automatically: false`.
13. Review/fix cycles use fresh independent review, deterministic read-back, append-only evidence,
    known-debt separation, and no merge without explicit authorization.

This document is a design authority only. It does not certify implementation, consent, canonical
adoption, repository health, or plan acceptance.
