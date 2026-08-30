---
id: SPEC-FEAT-017-PLANNING-BOOTSTRAP
title: "FEAT-017 Planning Bootstrap Design"
document_state: draft
---

# FEAT-017 — Planning Bootstrap

_Authority: design authority, final contract revision 2026-08-30._

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

- capture and preservation of the exact post-redaction original request (all non-secret text remains
  verbatim) and conversational provenance;
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

1. the original user prompt, preserved exactly for all non-secret text at the capture boundary;
2. each question and answer, including source, sequence, and exact non-secret text;
3. repository facts actually inspected, with path and hash provenance;
4. the current complete non-deleted SR context, including every record and its source anchors,
   disposition provenance, and available trace relations;
5. the project policy and host-validated model catalog, without credentials;
6. any supplied canonical FEAT/SR/bundle baseline, preserved as a read-only snapshot until a human
   decision authorizes adoption or replacement;
7. an explicit request for a planning-stage Kanban graph, when that optional transport is desired.

The versioned secret detector and redaction happen before any prompt, question, answer, observation, response, or
policy value enters a persisted event or artifact. Non-secret user text remains exact and verbatim;
secret-shaped values are replaced at ingress with `[REDACTED]`. The raw secret is never persisted,
hashed for provenance, echoed in an error, or included in a summary/diagnostic. A structured redaction
record names only the field path, detector/reason, and replacement; it contains no raw or reversible
secret value. Security redaction takes precedence over byte-for-byte preservation when the two conflict.
Missing, stale, unsafe, contradictory, or unverified input blocks the dependent stage.

### 2.2 Canonical and derived outputs

The run produces or references these artifacts. Run-local evidence is never overwritten in place:

```text
.intent/intent.json
.factory/planning/<run-id>/state.json                         # derived run projection
.factory/planning/<run-id>/revision-index.jsonl                # append-only lineage index
.factory/planning/<run-id>/current/<stage-id>.json              # derived current pointer
.factory/planning/<run-id>/stages/<stage-id>/r<revision>/a<attempt>/stage-manifest.json
.factory/planning/<run-id>/stages/capture/r<revision>/a<attempt>/events.jsonl
.factory/planning/<run-id>/stages/provisional-spec-authoring/r<revision>/a<attempt>/spec-authoring.json
.factory/planning/<run-id>/stages/spec-alignment/r<revision>/a<attempt>/review-report.json
.factory/planning/<run-id>/stages/spec-alignment/r<revision>/a<attempt>/checkpoint-gate.json
.factory/planning/<run-id>/stages/candidate-sr-derivation/r<revision>/a<attempt>/candidate-sr-derivation.json
.factory/planning/<run-id>/stages/candidate-sr-alignment/r<revision>/a<attempt>/review-report.json
.factory/planning/<run-id>/stages/candidate-sr-alignment/r<revision>/a<attempt>/checkpoint-gate.json
.factory/planning/<run-id>/stages/implementation-plan-authoring/r<revision>/a<attempt>/plan-authoring.json
.factory/planning/<run-id>/stages/task-materialization/r<revision>/a<attempt>/task-materialization.json
.factory/planning/<run-id>/stages/cross-artifact-alignment/r<revision>/a<attempt>/review-report.json
.factory/planning/<run-id>/stages/cross-artifact-alignment/r<revision>/a<attempt>/checkpoint-gate.json
.factory/planning/<run-id>/stages/cross-artifact-alignment/r<revision>/a<attempt>/traceability.json
.factory/planning/<run-id>/decisions/<decision-kind>/r<revision>/a<attempt>/decision-<decision-id>.json
.factory/planning/<run-id>/resolution-events.jsonl               # append-only
.factory/planning/<run-id>/stages/human-boundaries-and-adoption/r<revision>/a<attempt>/warning-decisions.json
.factory/planning/<run-id>/stages/human-boundaries-and-adoption/r<revision>/a<attempt>/sr-consent.json
.factory/planning/<run-id>/stages/human-boundaries-and-adoption/r<revision>/a<attempt>/feature-boundary-decision.json
.factory/planning/<run-id>/stages/human-boundaries-and-adoption/r<revision>/a<attempt>/canonical-adoption.json
.factory/planning/<run-id>/stages/final-gates/r<revision>/a<attempt>/final-gates.json
.factory/planning/<run-id>/stages/handoff/r<revision>/a<attempt>/handoff.json
.factory/planning/<run-id>/stages/handoff/r<revision>/a<attempt>/handoff.md
.factory/planning/<run-id>/stages/planning-run/r<revision>/a<attempt>/kanban-run.json # optional
```

`<stage-id>` is the exact lowercase, hyphenated graph node name. `<revision>` and `<attempt>` are
positive decimal identities, rendered as `r1`, `a1`, and so on. A revision starts at 1 for a stage
lineage and increments for a scoped source/fix change; an attempt increments for each new invocation
within that revision. A crash reclaim resumes the same attempt identity and appends journal evidence;
a retry that starts a new invocation uses the next attempt and never reuses the old output path. The
append-only `revision-index.jsonl` records lineage, predecessor revision, invalidation reason, and the
current pointer. Each `current/<stage-id>.json` pointer records the current revision/attempt, artifact
paths/hashes, report/gate paths/hashes when applicable, and invalidation status. A pointer is derived
and replaceable; the evidence it names is immutable. No candidate revision, review attempt, task or
trace projection, resolution event, or handoff may be overwritten ambiguously.

The candidate-SR derivation path above is the single run-local candidate artifact. It contains the
candidate SR set and the candidate feature/bundle projection in the same JSON document; separate
projection files are forbidden. Its immutable content hash is recorded in its stage manifest,
review inputs, and downstream manifests, while the candidate document has no back-reference to any
review. Neither the candidate artifact nor its projection is canonical FEAT/SR/bundle adoption;
adoption remains later, explicit, and consent-gated.

The selected canonical source paths remain the repository's normal paths, for example:

```text
docs/superpowers/specs/<approved-name>.md
docs/superpowers/plans/<approved-name>.md
tasks/T-<digits>-<slug>.md
```

Canonical targets are recorded as exact repository-relative paths and pre/post SHA-256 values in the
versioned stage manifest. The run records the exact relative path and SHA-256 hash of every source,
projection, decision, review, gate, and derived artifact it uses. Run-local candidate SR records are
not canonical adopted SRs.

### 2.3 Exact original prompt and challenge provenance

Intent provenance is normative, not a supplemental note. After ingress redaction, the capture journal
and materialized intent must preserve:

- every non-secret byte of the original prompt and the capture source;
- every non-secret byte of every question asked and answer received verbatim, in sequence;
- repository observations with path, observer/source, and hash where applicable;
- challenges raised against unsupported claims, contradictions, exclusivity, feasibility, security,
  or operability;
- the claim, rationale, evidence requested, originating answer/event, current disposition, exact human
  response when present, response provenance, and decision timestamp for every challenge;
- unresolved questions, deferred questions, and explicit cancellations;
- decisions and their actor kind, exact non-secret text, and input/output hashes;
- structured redaction records containing `field_path`, `reason`, `replacement` (`[REDACTED]`),
  and detector/version, but never the raw secret or a hash that could disclose it.

The raw ingress buffer is transient and is never written to disk, logs, packets, hashes, summaries, or
diagnostics. Security redaction has precedence over exact-text preservation: non-secret text is exact,
but every secret-shaped value is replaced at ingress before persistence. Silence, a model response, a
fixture value, or a missing event is not a human decision. Challenge resolution is append-only. A
response may resolve, revise, defer, or accept a challenge only when its actor and provenance are
explicit; unresolved or deferred challenges remain visible and block any stage that requires their
disposition.

The existing schema-one `.intent/intent.json` remains readable. A schema-two materialization may
add `run_id`, question/source/sequence metadata, a structured brief, capture state, redactions,
and challenge records without changing captured non-secret text. A failed snapshot replacement
must leave the last known-good snapshot untouched while retaining the new journal event for recovery.

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

### 3e.1 Decision writer prerequisite and no bypass

The common DecisionFile contract in §6.9, including authenticated-human provenance, exact finding /
boundary coverage, current input/artifact hashes, response and decision hashes, replay binding, and
append-only `resolution-events.jsonl` mapping, must be implemented and validated before Task 4 is
eligible to run. Task 4 must not depend on Task 7's later adoption logic. If a review has an
unresolved finding, escalation, `needs_input` state, or recorded human response in its current
lineage, the next stage remains unrunnable until a fresh current clean report and matching
checkpoint-gate evidence are produced. No `human disposition`, `accept_warning`, card state, model
assertion, or DecisionFile status can substitute for that tuple.

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

The host captures the exact post-redaction prompt (all non-secret text remains verbatim) and conducts
adaptive, repository-aware clarification. Questions
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
immutable candidate-artifact hash, candidate-SR review-report hash, source artifact hashes, exact candidate IDs, actor,
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

### 6.0 Closed status vocabulary and deterministic evidence schemas

#### 6.0.1 Closed status vocabulary

The JSON member named `status` has one closed vocabulary. A record MUST NOT invent a synonym,
combine values, use a transport state as a status, or use an unlisted value. Review records use
`clean|findings|escalated|invalid`; deterministic gate records use `pass|fail|invalid`. A
`decision_file` uses the enum selected by its `decision_kind`:

| Decision kind | Closed `status` enum |
|---|---|
| `challenge-resolution` | `resolved|revised|deferred|unresolved|invalid` |
| `warning-disposition` | `fixed|accepted_risk|rejected|deferred|invalid` |
| `feature-boundary` | `selected|split_sequential|withheld|deferred|invalid` |
| `sr-consent` | `consent_granted|consent_withheld|deferred|invalid` |
| `canonical-adoption` | `adopted|withheld|deferred|invalid` |

Only review, gate, and decision records carry `status`. Other records use explicitly named
`lifecycle_state`, `state`, `pointer_state`, or `lease_state` fields and those fields are not
semantic status fields. The lifecycle state vocabulary is the state machine in §3.1; the transport
state and lease vocabulary are defined in §8. The authority-spec frontmatter and generated-task
metadata therefore use `lifecycle_state`, never an open-ended `status`.

`fixed` and `accepted_risk` are not self-certifying outcomes. Each requires a fresh, current,
independent review record that re-evaluates the exact warning scope and binds the current input and
artifact hashes. Neither status erases the warning or any historical/current finding: the finding,
decision, review, and hash transitions remain append-only. A current review may be `clean` only when
that fresh evidence proves that no unresolved blocking finding remains; an accepted risk remains
visible in the decision and audit history. Every `unresolved`, `deferred`, `withheld`, `rejected`,
or `invalid` decision state blocks the dependent stage. A review status of `findings` or `escalated`
and a gate status of `fail` or `invalid` also block; only a current `clean` review paired with a
current `pass` gate can release a child.

#### 6.0.2 EvidenceRecordSchema

`EvidenceRecordSchema` is the normative envelope for every persisted JSON or JSONL evidence record.
The record type is closed to exactly:

```text
stage_manifest
revision_index_entry
current_pointer
input_manifest
capture_event
spec_authoring
candidate_sr_derivation
checkpoint_review
checkpoint_gate
plan_authoring
task_materialization
traceability
decision_file
resolution_event
final_gates
kanban_graph_manifest
kanban_run
planning_handoff
state_projection
```

Every member below is mandatory unless the record-specific schema explicitly says that it is an
embedded object rather than a top-level record. The exact top-level identity fields are:

```text
schema                 positive integer schema version
record_type            one value from the closed list above
record_id              safe, unique ID within the run and record family
run_id                 safe run identity
stage_id               exact lowercase hyphenated graph node name
lineage_id             immutable stage lineage identity
revision               positive decimal revision within the lineage
attempt                positive decimal invocation attempt within the revision
sequence               positive monotonic sequence within the append-only record family
previous_record_hash   prior record-family terminal hash, or null only for sequence 1
created_at             UTC RFC-3339 timestamp with seconds and offset Z
provenance             producer/actor, invocation, source, and authentication provenance
input_manifest_ref     exact repository-relative path and SHA-256 of the input manifest
terminal_hash          the record-specific terminal hash named by its schema
```

`terminal_hash` is a schema concept, not an additional JSON member. The concrete terminal member is
`record_hash` unless a record schema below names `manifest_sha256`, `pointer_hash`, `report_hash`,
`gate_hash`, `decision_hash`, `graph_hash`, or `handoff_hash`; exactly one such terminal member is
permitted. `provenance` MUST include `actor_kind`, `producer_role`, `producer_identity`,
`invocation_id`, `source_record_ids`, and `source_paths`; human decisions additionally require the
authenticated actor fields in §6.9. All source paths and output paths in provenance are exact
repository-relative UTF-8 paths.

The record's `terminal_hash` is SHA-256 over its canonical strict-JSON bytes with only that terminal
hash member omitted. It is not a hash of a pretty-printed rendering, a status projection, a database
row, or a path alone. Referenced artifact hashes are SHA-256 over the exact persisted bytes after
ingress redaction. The hash of an `InputManifest` is SHA-256 over its canonical JSON with only
`manifest_sha256` omitted; its enclosing record terminal hash additionally covers the complete
manifest object. Hashes are lowercase hexadecimal and are never computed over raw secrets.

#### Immutable input snapshots and read-hash binding

Every stage receives an immutable input snapshot before producer or reviewer invocation. The
`InputManifestSchema` records the exact repository-relative path, byte length, SHA-256, source record
ID, and observation time for every input, plus the repository commit/tree identity or explicit
`uncommitted` marker. The manifest and every referenced source snapshot are read-only for that
attempt. A producer binds the manifest hash into its output evidence, reads the published output
back, recomputes the read hash from the exact bytes, and records that read-hash binding; a reviewer
and every downstream consumer must recompute and match the same binding. Any input mutation,
missing snapshot, hash mismatch, or changed repository identity invalidates the current pointer and
requires the transition in §6.0.4. A path name, file timestamp, or successful open is not an input
snapshot and cannot satisfy read-hash binding.

Canonical strict JSON is UTF-8 without a BOM, RFC-8259 JSON with finite numbers only, no duplicate
object keys, no insignificant whitespace, lexicographically sorted object keys, and arrays in the
schema-declared order. Implementations MUST use one RFC-8785/JCS-equivalent serialization and MUST
reject NaN, Infinity, duplicate keys, invalid UTF-8, non-canonical number forms, and a different
array order. JSONL has one complete canonical JSON record per line and no blank lines.

Writers reject an omitted required field, an extra/unknown field, a duplicate field, a wrong type,
an invalid enum, an unsafe path, a non-positive identity, a sequence gap, a mismatched previous hash,
or a null where null is not explicitly allowed. They do not silently default, coerce, truncate, or
drop a field. A rejected candidate is retained as an immutable `invalid` evidence record when it can
be safely recorded; otherwise the writer records the failure in the append-only journal without
persisting untrusted content. No schema has an extension bag, so unknown fields are never accepted.

All evidence paths are exact and repository-relative. For a stage record they MUST be below
`.factory/planning/<run-id>/stages/<stage-id>/r<revision>/a<attempt>/`; the revision index is exactly
`.factory/planning/<run-id>/revision-index.jsonl`; a current pointer is exactly
`.factory/planning/<run-id>/current/<stage-id>.json`; the resolution journal is exactly
`.factory/planning/<run-id>/resolution-events.jsonl`. The path encoded in a record MUST equal its
actual path byte-for-byte after repository-root validation. Absolute, drive, UNC, NUL, traversal,
alternate-data-stream, alias, symlink, junction, mount-point, and reparse-point paths are rejected
as specified in §7.4.

Evidence is immutable. A writer creates a same-directory temporary file, writes canonical bytes,
durably flushes it, atomically publishes it once, and never replaces or compacts a published record.
The append-only writer takes the family lock, verifies `sequence` and `previous_record_hash`, flushes
the line, and releases the lock only after durable storage. A failed publish leaves the prior bytes
untouched and appends a failure/invalidation event rather than overwriting the prior record.

The current pointer is a derived, replaceable CAS object, not evidence. A pointer update MUST include
`expected_pointer_hash`, the newly selected record path/hash, the new input-manifest hash, and an
invalidation list; it succeeds only if the on-disk pointer hash equals the expected hash while the
pointer lock is held. A source/fix/decision/adoption/task change first appends an invalidation event,
sets the affected pointer and every descendant pointer to `pointer_state=invalidated`, and then
publishes a new pointer only after a new immutable record is complete. A pointer with
`pointer_state=invalidated` cannot release a child.

Crash recovery scans the durable record chain and journal, discards uncommitted temporary files,
retains the last valid pointer, and reconstructs a missing derived pointer only from a complete,
hash-valid chain. A lost lease or process crash reclaims the same `revision` and `attempt` and
appends recovery evidence; it does not create a duplicate artifact or silently promote an orphan.
If the last append is ambiguous, recovery fails closed and records an invalidation. A retry that is
a new invocation uses the next attempt and a new output path. Recovery never treats a transport
state, a model response, or a stale snapshot as evidence.

#### 6.0.3 Required record schemas

The following are complete required-field schemas. Every schema inherits the EvidenceRecordSchema
envelope, exact path rules, canonical serialization, immutable-write rules, and unknown-field
rejection above. Fields named `path` always carry a repository-relative path and its matching SHA-256.

**StageManifestSchema** (`record_type=stage_manifest`; exact path
`.factory/planning/<run-id>/stages/<stage-id>/r<revision>/a<attempt>/stage-manifest.json`) requires:

```text
run_id, stage_id, lineage_id, revision, attempt, sequence, previous_record_hash,
record_id, input_manifest_ref, predecessor_refs[], produced_artifacts[], producer,
workspace_claim, lifecycle_state, gate_result, started_at, finished_at, invalidation,
record_hash
```

`predecessor_refs[]` contains exact `stage_id`, `revision`, `attempt`, `path`, `sha256`, and
`record_hash`; `produced_artifacts[]` contains `ProducedArtifact` objects. `gate_result` is
`pass|fail|invalid` when the stage has a deterministic gate and is null only for a non-gate producer
stage. `invalidation` is `{event_id, reason, descendant_stage_ids[]}` or null. A completed stage
requires `lifecycle_state=handoff_ready` only for handoff; all other stage completion is represented
by the stage-specific gate/result and predecessor contract, not a new status value.

**RevisionIndexEntrySchema** (`record_type=revision_index_entry`; one line in the exact
`revision-index.jsonl`) requires:

```text
run_id, stage_id, lineage_id, revision, attempt, sequence, previous_record_hash,
record_id, transition, predecessor_revision, predecessor_attempt, input_manifest_ref,
artifact_refs[], invalidated_stage_ids[], current_pointer_ref, provenance, record_hash
```

`transition` is one of `new_invocation`, `crash_reclaim`, `retry`, `scoped_fix`, `human_decision`,
`canonical_adoption`, or `task_source_change`; null predecessor identities are allowed only for
`new_invocation`. The entry is append-only and records exactly why the revision/attempt changed.

**CurrentPointerSchema** (`record_type=current_pointer`; exact path
`.factory/planning/<run-id>/current/<stage-id>.json`) requires:

```text
run_id, stage_id, lineage_id, revision, attempt, sequence, previous_record_hash,
record_id, pointer_state, expected_pointer_hash, selected_record, input_manifest_ref,
descendant_pointer_refs[], invalidation_event_ref, cas, provenance, pointer_hash
```

`pointer_state` is `current|invalidated`; `selected_record` has the exact path, terminal hash, and
stage-manifest hash; for a decision-bearing stage, `selected_record` additionally has the exact
ordered `decision_refs[]` member, whose items are `{decision_id, decision_kind, decision_path,
decision_hash, event_id, event_hash}` and whose order is the canonical decision-path order. The
`decision_refs[]` member is required for a decision-bearing pointer and is absent for other pointers;
no other `selected_record` members are permitted. `cas` has `compare_hash`, `publish_sequence`, and
`fencing_token`.
`invalidation_event_ref` is required when the pointer is invalidated and null otherwise.

**InputManifestSchema** (`record_type=input_manifest`; exact path is the `input_manifest_ref.path`)
requires:

```text
run_id, stage_id, lineage_id, revision, attempt, sequence, previous_record_hash,
record_id, entries[], observed_at, source_snapshot, manifest_sha256, provenance
```

Each `entries[]` item requires `path`, `sha256`, `byte_length`, `role`, `source_record_id`, and
`observed_at`; entries are sorted by exact path, with no duplicate path. `source_snapshot` requires
the repository root identity and the source revision/commit or an explicit `uncommitted` marker.

**ProducedArtifact** is the required object used by every producer and stage manifest:

```text
artifact_id, kind, path, sha256, byte_length, canonical, redacted,
writer_role, writer_identity, source_refs[], input_manifest_sha256
```

`source_refs[]` contains exact path/hash or record-ID/hash pairs. `canonical` and `redacted` are
booleans; `redacted=true` is mandatory for user-originating material. An artifact path cannot be
outside the writer's approved scope. The object has no status field and cannot authorize adoption
or execution.

**SpecAuthoringSchema** (`record_type=spec_authoring`; exact path
`.factory/planning/<run-id>/stages/provisional-spec-authoring/r<revision>/a<attempt>/spec-authoring.json`)
requires:

```text
run_id, stage_id=provisional-spec-authoring, lineage_id, revision, attempt,
record_id, input_manifest_ref, source_intent_ref, source_fact_refs[], output: ProducedArtifact,
target_path, read_back, frontmatter, anchor_index[], challenge_refs[], lifecycle_state,
producer, record_hash
```

`read_back` requires `path`, `sha256`, `parsed`, and `semantic_validation`; `frontmatter` requires
`id`, `title`, and `lifecycle_state`; `anchor_index[]` is stable and non-fenced. The record is
invalid if the producer did not write the target itself, read it back, and bind its hash.

**PlanAuthoringSchema** (`record_type=plan_authoring`; exact path
`.factory/planning/<run-id>/stages/implementation-plan-authoring/r<revision>/a<attempt>/plan-authoring.json`)
requires:

```text
run_id, stage_id=implementation-plan-authoring, lineage_id, revision, attempt,
record_id, input_manifest_ref, spec_ref, spec_sha256, candidate_sr_ref, candidate_sr_sha256,
output: ProducedArtifact, target_path, read_back, task_index[], verification_obligations[],
producer, lifecycle_state, record_hash
```

`read_back` requires `path`, `sha256`, `parsed`, and `semantic_validation`; every `task_index[]`
item requires source task number, exact task anchor, dependencies, implementation evidence,
verification evidence, test paths, test commands, and acceptance criteria. The plan producer must
write and read back the plan; a supplied plan path alone is invalid.

**TaskMaterializationSchema** (`record_type=task_materialization`; exact path
`.factory/planning/<run-id>/stages/task-materialization/r<revision>/a<attempt>/task-materialization.json`)
requires:

```text
run_id, stage_id=task-materialization, lineage_id, revision, attempt, record_id,
input_manifest_ref, source_plan, source_plan_sha256, source_spec, source_spec_sha256,
candidate_sr_ref, candidate_sr_sha256, task_records[], parity, produced_artifacts[],
dependencies, allowed_paths, prohibited_paths, lifecycle_state, gate_result, producer, record_hash
```

Each `task_records[]` item requires `task_id`, `source_task_number`, exact task `path`, `sha256`,
`sr_bindings`, `acceptance_criteria`, `test_paths`, `test_commands`, `implementation_evidence`,
`verification_evidence`, `dependencies`, `allowed_paths`, `prohibited_paths`, and
`source_record_hashes`. `parity` requires plan-task count, materialized-task count, exact source
numbers, and `duplicates=[]`; parity failure or an unbound task makes `gate_result=fail` or
`invalid` and blocks handoff.

**TraceabilitySchema** (`record_type=traceability`; exact path
`.factory/planning/<run-id>/stages/cross-artifact-alignment/r<revision>/a<attempt>/traceability.json`)
requires:

```text
run_id, stage_id=cross-artifact-alignment, lineage_id, revision, attempt, record_id,
input_manifest_ref, source_hashes, forward_links[], reverse_links[], uncovered[],
ambiguous[], non_sr_classifications[], status, evidence, provenance, record_hash
```

Every forward and reverse link requires the exact source/target record IDs, paths, hashes, stable
anchors, and typed relationship (`implements|verifies|supports|non-SR`). `uncovered=[]` and
`ambiguous=[]` are required for `status=pass`; either nonempty list forces `status=fail` or
`invalid`. This record is a deterministic gate projection and uses only the gate enum.

**FinalGatesSchema** (`record_type=final_gates`; exact path
`.factory/planning/<run-id>/stages/final-gates/r<revision>/a<attempt>/final-gates.json`) requires:

```text
run_id, stage_id=final-gates, lineage_id, revision, attempt, record_id,
input_manifest_ref, current_pointer_refs[], current_clean_review_gate_tuples[],
artifact_hashes, decision_refs[], traceability_ref, graph_manifest_ref, feat018_capability,
warning_summary, consent_summary, adoption_summary, status, evidence, provenance, gate_hash
```

Each review/gate tuple requires checkpoint, report path/hash, gate path/hash, input-manifest hash,
revision, attempt, and current-pointer hash. `feat018_capability` requires `requested`, boolean
`available`, `result_hash`, and `gate_result` (`pass|fail|invalid`); an unrequested capability is
represented by `requested=false`, not a new status token. `status=pass` requires all three current
clean/pass tuples, current decisions, current traceability, an exact graph hash when requested,
and `starts_automatically=false` in the handoff. Missing FEAT-018 is an honest `fail` or `invalid`
block, never execution validation.

**KanbanRunSchema** (`record_type=kanban_run`; exact path
`.factory/planning/<run-id>/stages/planning-run/r<revision>/a<attempt>/kanban-run.json`) requires:

```text
run_id, stage_id=planning-run, lineage_id, revision, attempt, record_id,
input_manifest_ref, graph_manifest, graph_hash, root_card_id, card_refs[], edge_refs[],
reconciliation, state, lease, retry_policy, reclaim_policy, coherence_gate_refs[],
no_silent_execution, provenance, record_hash
```

`graph_manifest` MUST be the exact `KanbanGraphManifest` below and `graph_hash` MUST match it.
`card_refs[]` has one card reference for every graph node and exact card input/output hashes;
`reconciliation` requires `complete=true`, the graph hash, node count, ordered node IDs, and exact
edge count. `no_silent_execution=true` is mandatory. This record transports lifecycle only and has
no authority to approve, adopt, or execute.

#### 6.0.4 revision-vs-attempt transition table

Revision identifies a new semantic input/output lineage state; attempt identifies a new invocation
of the same revision. Every transition appends a `RevisionIndexEntrySchema` record before publishing
the new current pointer.

| Event | Revision | Attempt | Required transition and invalidation |
|---|---:|---:|---|
| New invocation | `1` for a new stage lineage | `1` | Create a new lineage, input manifest, stage manifest, and pointer; predecessor is null. A replay of the same idempotency key returns the existing lineage. |
| Crash reclaim | unchanged | unchanged | Reacquire the lease with a higher fencing token, append `crash_reclaim` evidence, and resume the same attempt/path. Do not duplicate output or increment attempt. |
| Retry | unchanged | `previous+1` | Only allowed when current input hashes still match. Create a new `a<attempt>` path; prior attempt remains immutable and cannot be selected by the pointer. |
| Scoped fix | `previous+1` | `1` | Append the fix and invalidation, recompute inputs, invalidate the affected stage and all descendants, and require fresh independent review/gates in the same lineage. |
| Human decision | unchanged for the reviewed stage | `previous+1` for the queued fresh review | Persist the authenticated DecisionFile at the current revision, append its resolution event, and queue a fresh independent review. The response/decision never releases a child by itself. |
| Canonical adoption | `previous+1` for the adoption output | `1` | Bind exact consent and feature-boundary decisions, target pre/post hashes, and candidate hash; invalidate final-gate/handoff descendants and publish a new adoption revision only through the validated writer. |
| Task/source change | `previous+1` for the affected stage | `1` | Recompute the input manifest, invalidate the affected stage and every descendant, and rebuild all dependent artifacts, traceability, reviews, gates, and handoff. |

An attempt number is never reused for a different invocation, and a revision number is never reused
after invalidation. A human decision that changes an artifact rather than merely answering a blocked
question is a `scoped_fix`, `canonical_adoption`, or `task_source_change` as applicable and follows
that row instead of being hidden as a retry.

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

The existing paths are retained with versioned run evidence:

```text
.intent/intent.json
.factory/planning/<run-id>/stages/capture/r<revision>/a<attempt>/events.jsonl
.factory/planning/<run-id>/state.json
```

Schema-one reads remain compatible. Schema-two fields must include the run identity, exact post-redaction prompt,
answers with question/source/sequence, structured brief, capture status, redactions, challenges,
challenge responses, and provenance. Journal events are strictly ordered and append-only. Atomic
snapshot replacement failures preserve the last known-good `.intent/intent.json` while leaving the
journal as the recovery source.

### 6.3 Provisional authority spec

The spec is the canonical semantic authority for this run. It must have strict frontmatter with
`id`, `title`, and `lifecycle_state`, stable non-fenced anchors, explicit intent/challenge coverage,
assumptions, non-goals, feature boundary, implementation/verification obligations, and visible
`lifecycle_state=provisional` with unresolved work explicit. It must not claim SR adoption, implementation completion, human
consent, or downstream execution.

### 6.4 Candidate SR and projection contract

The run-local candidate record is immutable after publication and contains the complete candidate SR,
feature, and bundle projections in one document. No projection sidecar or separately stored feature /
bundle candidate file is permitted. Separate projection files are forbidden. The immutable content hash is computed over the canonical UTF-8,
strict-JSON serialization of this document (sorted object keys, deterministic array order, no
whitespace variance) and is recorded by the stage manifest and every consumer. The candidate document
contains no review hash or any field written after review; in particular, no review is allowed to
mutate this artifact. The minimum contract is:

```json
{
  "schema": 2,
  "record_type": "candidate_sr_derivation",
  "run_id": "<safe-id>",
  "stage_id": "candidate-sr-derivation",
  "lineage_id": "feat17/<run-id>/candidate-sr-derivation/v1",
  "revision": 1,
  "attempt": 1,
  "source_spec": {"path": "<relative>", "sha256": "<sha256>"},
  "full_context_sha256": "<sha256>",
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
  "candidate_feature_projection": {
    "id": "FEAT-candidate-<safe-id>",
    "title": "<candidate feature title>",
    "scope": ["<explicit in-scope statement>"],
    "non_goals": ["<explicit non-goal>"],
    "source_anchors": ["<stable spec anchor>"],
    "candidate_sr_ids": ["SR-candidate-1"],
    "boundary_state": "single_feature|split_requires_human"
  },
  "candidate_bundle_projection": {
    "id": "BUNDLE-candidate-<safe-id>",
    "title": "<candidate bundle title>",
    "feature_id": "FEAT-candidate-<safe-id>",
    "candidate_sr_ids": ["SR-candidate-1"],
    "source_anchors": ["<stable spec anchor>"],
    "baseline_ref": {"path": "<relative-or-null>", "sha256": "<sha256-or-null>"}
  }
}
```

`candidate_feature_projection` and `candidate_bundle_projection` are projections only: their IDs,
scope, source anchors, SR membership, boundary state, and baseline reference are deterministic and
must be internally consistent with `candidate_srs` and the reviewed spec. `baseline_ref` is a
read-only input snapshot, not permission to modify a canonical FEAT/SR/bundle file. Existing SR
records remain visible, including duplicates and contradictions; derivation cannot hide or discard
them. Candidate records do not become canonical requirements until exact human consent and canonical
adoption have passed.

### 6.5 Review-report and checkpoint-gate contracts

Each semantic checkpoint has an immutable review report and a separately immutable deterministic gate
record. The report path is exactly
`.factory/planning/<run-id>/stages/<stage-id>/r<revision>/a<attempt>/review-report.json`, where the
checkpoint/stage mapping is `spec_alignment/spec-alignment`,
`candidate_sr_alignment/candidate-sr-alignment`, or
`cross_artifact_alignment/cross-artifact-alignment`. The report contract is:

```json
{
  "schema": 1,
  "record_type": "checkpoint_review",
  "run_id": "<safe-id>",
  "checkpoint": "spec_alignment|candidate_sr_alignment|cross_artifact_alignment",
  "stage_id": "<exact-stage-id>",
  "lineage_id": "feat17/<run-id>/<stage-id>/v1",
  "revision": 1,
  "attempt": 1,
  "input_manifest": {
    "sha256": "<manifest-sha256>",
    "entries": [{"path": "<relative>", "sha256": "<sha256>", "role": "<input-role>"}]
  },
  "artifact_hashes": {"<artifact-role>": "<sha256>"},
  "status": "clean|findings|escalated|invalid",
  "finding_ids": ["F-001"],
  "findings": [{"id": "F-001", "scope": "<exact artifact/anchor/boundary>", "category": "<category>", "evidence_refs": ["<relative-path-or-record-id>"], "blocking": true}],
  "reviewer": {
    "kind": "independent_reviewer",
    "identity": "<authenticated reviewer identity>",
    "provider": "<provider>",
    "model": "<fixed-run-model>",
    "session_id": "<session-id>",
    "invocation_id": "<invocation-id>"
  },
  "report_hash": "<sha256>"
}
```

The report's `report_hash` is calculated over the canonical strict-JSON serialization with only the
`report_hash` member excluded; it is then recorded in the immutable report and stage manifest. No
other field may change after publication. `finding_ids` and `findings[].id` must match exactly, every
finding has an exact scope, and a `clean` report has empty finding arrays. The reviewer identity must
be independent of the producer/fixer and must be recorded even for `invalid` reports.

The checkpoint-gate path is exactly
`.factory/planning/<run-id>/stages/<stage-id>/r<revision>/a<attempt>/checkpoint-gate.json`. Its
contract is:

```json
{
  "schema": 1,
  "record_type": "checkpoint_gate",
  "run_id": "<safe-id>",
  "checkpoint": "<same-checkpoint-as-report>",
  "stage_id": "<same-stage-id-as-report>",
  "revision": 1,
  "attempt": 1,
  "review_report": {"path": "<relative>", "sha256": "<report-hash>"},
  "input_manifest_sha256": "<same-manifest-hash-as-report>",
  "artifact_hashes": {"<artifact-role>": "<sha256>"},
  "status": "pass|fail|invalid",
  "evidence": {"required": ["<deterministic-check>"], "observed": {"<check>": true}},
  "evidence_sha256": "<sha256-of-canonical-evidence>",
  "gate_hash": "<sha256>"
}
```

`gate_hash` is calculated with only `gate_hash` excluded. The gate must bind the exact report hash,
report input-manifest hash, stage/revision/attempt, and current artifact hashes. `status=pass` is
permitted only when the bound report is current, `clean`, and independently validated; `findings`,
`escalated`, `invalid`, stale, or missing reports make the gate fail or invalid. A current pointer may
name only one matching report/gate tuple. Handoff and every downstream gate must consume that tuple,
not a status projection, prior attempt, human response, or Kanban card.

### 6.6 Implementation-plan contract

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

### 6.7 Generated-task contract

A materialized task must preserve the plan/spec/SR links and source task number. Its canonical
metadata/body must include `id`, `title`, `lifecycle_state`, `run_id`, `stage_id`, `lineage_id`, `revision`,
`attempt`, `source_plan`, `source_task`, `source_spec`, `sr_bindings`, `acceptance_criteria`,
`test_paths`, `test_commands`, `implementation_evidence`, `verification_evidence`,
dependencies, allowed/prohibited paths, and the exact plan/spec/candidate hashes used. Each SR
binding has one of `implements`, `verifies`, or `supports`. A reviewed non-SR record has
classification, reason, reviewer/report hash, and source anchor. The versioned
`task-materialization.json` projection records the exact generated-task paths and hashes; a current
pointer selects one revision/attempt and never overwrites prior task evidence. Missing or ambiguous
bindings block handoff.

### 6.8 Bidirectional trace closure

The trace gate must prove both forward and reverse coverage. It must enumerate every intent decision,
challenge, and independently governable spec obligation, then resolve it to exactly one candidate SR
or reviewed non-SR classification, plan task, generated task, and verification evidence. It must also
start from every candidate/adopted SR and task and resolve back to a valid spec anchor and intent or
reviewed rationale. Explanatory prose is not silently promoted to SRs; omitted obligations are not
silently accepted.

### 6.9 DecisionFile and human-boundary contracts

A `DecisionFile` is an immutable, repository-relative JSON record written only by the validated
human-decision writer. Its exact path is
`.factory/planning/<run-id>/decisions/<decision-kind>/r<revision>/a<attempt>/decision-<decision-id>.json`,
where `<decision-kind>` is one of `challenge-resolution`, `warning-disposition`,
`feature-boundary`, `sr-consent`, or `canonical-adoption`, and `<decision-id>` is an allocated positive
decimal ID (`D-1`, `D-2`, ...). The common schema is:

```json
{
  "schema": 1,
  "record_type": "decision_file",
  "decision_id": "D-1",
  "decision_kind": "warning-disposition",
  "run_id": "<safe-id>",
  "stage_id": "<exact-stage-id>",
  "lineage_id": "feat17/<run-id>/<stage-id>/v1",
  "revision": 1,
  "attempt": 1,
  "finding_scope": {
    "finding_ids": ["F-001"],
    "boundary_ids": [],
    "coverage": "exact"
  },
  "source_review": {"path": "<immutable-review-report-path>", "sha256": "<report-hash>"},
  "current_inputs": {
    "manifest_sha256": "<input-manifest-hash>",
    "artifacts": [{"path": "<relative>", "sha256": "<current-hash>"}]
  },
  "response_text": "<exact non-secret human response, with [REDACTED] where required>",
  "response_hash": "<sha256-of-response-text>",
  "status": "<kind-specific-status>",
  "actor": {
    "kind": "authenticated_human",
    "subject_id": "<authenticated-human-id>",
    "auth_method": "<host-authentication-method>",
    "authn_event_id": "<authentication-event-id>",
    "session_id": "<human-session-id>",
    "verified_at": "<timestamp>"
  },
  "replay": {
    "idempotency_key": "feat17/<run-id>/<stage-id>/decision/<decision-id>/v1",
    "nonce": "<unique-nonce>",
    "previous_event_hash": "<prior-journal-event-hash-or-null>"
  },
  "decision_hash": "<sha256>"
}
```

The writer rejects missing or unauthenticated human provenance, incomplete finding/boundary
coverage, a source report or input manifest that is not current, stale artifact hashes, invalid
status for the decision kind, reused decision ID/nonce, or a replay binding that does not match the
append-only journal. `decision_hash` is computed over canonical strict JSON with only
`decision_hash` excluded. `response_text` is the exact post-redaction human text; raw secret-shaped
input never reaches this record. The response and decision hashes are distinct and both are required.
A free-text answer, model output, agent flag, or `accept_warning` boolean is not a DecisionFile.

Kind-specific additions are part of the closed DecisionFile schema, not extension fields. The exact
top-level key set for a DecisionFile is the common schema above plus the fields explicitly named by
its row in the kind table below, and no other keys are permitted. For `canonical-adoption`, the exact
additional member is required and is:

```json
"target_bindings": [
  {"path": "<exact-registered-canonical-target>", "pre_sha256": "<sha256-or-null>", "post_sha256": "<sha256>"}
]
```

`target_bindings` has exactly one item for each of `canonical-sr`, `canonical-feat`, and
`canonical-bundle`, in canonical target-path order, with no duplicates or omissions. `pre_sha256=null`
means the target was absent and the handle-bound prepare phase proved absence beneath its regular
parent; rollback of that item must remove the newly created target using expected-current-new-hash
CAS. A non-null `pre_sha256` is the handle-bound preimage hash. `post_sha256` is the hash of the
exact intended bytes staged before the immutable DecisionFile is published. This member is included
in `decision_hash`; it is never populated after publication, replaced, or encoded in `response_text`.
For every other decision kind, only its row's named kind-specific members may be added, with their
exact types and ordering defined by that row or the writer's strict schema.

Every accepted DecisionFile maps to exactly one append-only
`.factory/planning/<run-id>/resolution-events.jsonl` event. The event contains `schema`, monotonic
`event_seq`, `event_id`, `decision_id`, `decision_hash`, `decision_kind`, run/stage/lineage,
revision/attempt, source report hash, current input manifest/artifact hashes, response hash, status,
authenticated actor identity, the decision path, and `previous_event_hash`. The writer validates the
DecisionFile and the current pointer before taking the journal lock, appends one canonical line,
flushes it durably, and only then publishes the corresponding derived pointer. It never rewrites or
compacts prior events. A human response/DecisionFile is an input that queues a fresh review; it is not
terminal evidence. `deferred`, `rejected`, `withheld`, and `invalid` decision statuses leave the
relevant stage in `needs_input` (including `consent_withheld` and `deferred`); `fixed` and
`fixed` and `accepted_risk` require fresh independent review evidence and do not erase findings.

For the combined adoption transaction, the resolution journal order is exact: append the validated
`sr-consent` event first and the validated `canonical-adoption` event second, each with its own
`previous_event_hash`. A durable consent-only prefix is historical human consent but is not an
accepted adoption and cannot advance the adoption pointer or release a child. Recovery either
completes the missing second event and then publishes the adoption pointer from the complete chain,
or records safe invalidation through the existing evidence families; it never reorders, duplicates,
or treats a consent-only prefix as canonical adoption.

The kind-specific contracts and validated writer mapping are:

| Kind | Required status enum and coverage | Additional bindings | Writer |
|---|---|---|---|
| `challenge-resolution` | `resolved|revised|deferred|unresolved|invalid`; exact challenge IDs | current challenge/report hashes and response hash | `DecisionFileWriter.append_human_resolution` |
| `warning-disposition` | `fixed|accepted_risk|rejected|deferred|invalid`; exact warning IDs | current warning IDs, severity/policy scope, and current source review report/input tuple | `DecisionFileWriter.append_warning_disposition` |
| `feature-boundary` | `selected|split_sequential|withheld|deferred|invalid`; every boundary finding ID | selected feature IDs, sequential workflow/worktree assignment, and supplied-baseline pre-hashes | `DecisionFileWriter.append_feature_boundary` |
| `sr-consent` | `consent_granted|consent_withheld|deferred|invalid`; exact candidate SR IDs and boundary IDs | current candidate artifact hash, candidate-SR clean report hash, cross-artifact clean report hash, and exact phrase below | `DecisionFileWriter.append_sr_consent` |
| `canonical-adoption` | `adopted|withheld|deferred|invalid`; exact adopted IDs and boundary IDs | valid SR consent hash, feature-boundary decision hash, required ordered `target_bindings[]` (`path`, `pre_sha256|null`, `post_sha256`), and candidate artifact hash | `DecisionFileWriter.append_canonical_adoption` |

For `sr-consent`, `status=consent_granted` is valid only when `response_text` exactly equals this
phrase after substituting the values (including punctuation and the final period):

```text
I authorize adoption of candidate SR set <candidate-artifact-sha256> into the canonical SR records for run <run-id>.
```

The candidate artifact hash, candidate IDs, source clean report hash, current input manifest hash,
run/stage/revision, authenticated human actor, response hash, decision hash, and replay key must all
match the current pointer. The phrase is consent to the exact candidate set only; it is not consent to
change a supplied FEAT/SR/bundle baseline unless a separate canonical-adoption decision authorizes
that change. `accept_warning` is never an agent-controlled bypass or a substitute for any of these
writers.

### 6.10 Handoff contract

`handoff.json` and `handoff.md` are immutable outputs at
`.factory/planning/<run-id>/stages/handoff/r<revision>/a<attempt>/handoff.json` and
`.factory/planning/<run-id>/stages/handoff/r<revision>/a<attempt>/handoff.md`. The JSON contract is:

```json
{
  "schema": 1,
  "record_type": "planning_handoff",
  "run_id": "<safe-id>",
  "stage_id": "handoff",
  "revision": 1,
  "attempt": 1,
  "status": "pass|fail|invalid",
  "input_manifest_sha256": "<current-input-manifest-hash>",
  "current_clean_reviews": [
    {"checkpoint": "spec_alignment", "report_path": "<relative>", "report_sha256": "<sha256>", "gate_path": "<relative>", "gate_sha256": "<sha256>"},
    {"checkpoint": "candidate_sr_alignment", "report_path": "<relative>", "report_sha256": "<sha256>", "gate_path": "<relative>", "gate_sha256": "<sha256>"},
    {"checkpoint": "cross_artifact_alignment", "report_path": "<relative>", "report_sha256": "<sha256>", "gate_path": "<relative>", "gate_sha256": "<sha256>"}
  ],
  "artifact_hashes": {"<artifact-role>": "<current-sha256>"},
  "decision_hashes": {
    "warning_dispositions": ["<decision-hash>"],
    "feature_boundary": "<decision-hash>",
    "sr_consent": "<decision-hash>",
    "canonical_adoption": "<decision-hash>"
  },
  "resolution_journal": {"path": "<relative>", "sha256": "<journal-digest>"},
  "feat018_capability": {"requested": true, "gate_result": "pass|fail|invalid", "available": true, "result_hash": "<sha256-or-null>"},
  "selected_downstream_workflow": "<explicit-menu-value>",
  "legal_next_actions": ["<explicit action>"],
  "starts_automatically": false,
  "writer": {"kind": "validated_handoff_writer", "identity": "<writer-identity>"},
  "handoff_hash": "<sha256>"
}
```

The JSON binds the exact post-redaction prompt/intent, spec, candidate/adopted SR, plan, task, FEAT/bundle baseline,
and evidence hashes; all three current clean review report/gate tuples; the current input manifest;
human challenge, feature-boundary, warning, and consent decision hashes; the resolution-journal
integrity digest; the FEAT-018 capability result; the selected downstream workflow and legal menu;
and `starts_automatically: false`. `status=pass` is permitted only when every tuple is current,
`clean`, and `pass`, all required human decisions have valid authenticated actor provenance and exact
coverage, and no source/current pointer is invalidated. A non-clean or escalation report hash,
`needs_input` record, human-response hash, stale decision, or Kanban `done` state cannot satisfy any
field. `handoff_hash` is calculated with only `handoff_hash` excluded. The markdown rendering is
derived from the JSON; a consumer validates path safety, exact hashes, clean final gates, and
`starts_automatically` before it can do anything else.

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
instructions. Packets must delimit them and enforce role scopes. Security redaction occurs at ingress:
non-secret user text/questions/answers remain exact and verbatim, while every secret-shaped value is
replaced by `[REDACTED]` before persistence. No credential, token, password, secret, provider
configuration, raw secret, or reversible secret-derived value is written to canonical artifacts,
packets, reports, journals, Kanban metadata, summaries, or diagnostics. A redaction record contains
only field path, reason/detector, replacement, and detector version. Security precedence is explicit:
redaction wins over exact preservation and the raw value is never logged or hashed.

The versioned `SecretDetectorSchema` is mandatory at the capture boundary. Each detector declaration
requires `detector_id`, semantic `version`, `detector_kind`, configured pattern/rule identity without
secret material, and `replacement=[REDACTED]`. Each redaction event requires `field_path`,
`reason`, `detector_id`, `detector_version`, and `replacement`; it MUST NOT contain the matched
value, a reversible digest, surrounding secret bytes, or a provider credential. Detector selection
and version are recorded in the input/event provenance, and changing detector identity or version
is a source change that invalidates affected snapshots and descendants. A detector must run before
prompt construction, question/answer persistence, hashing, logging, packetization, or model/provider
transport; failure or unavailable detector version blocks capture.

### 7.4 Path safety, atomicity, and rebinding

Every persisted path is a repository-relative UTF-8 path below the selected project root. Writers
reject absolute or drive/UNC paths, NULs, empty or ambiguous components, `.`/`..` traversal,
Windows alternate-data-stream syntax, and any path whose canonical parent escapes the project root.
They reject symlinks, junctions, mount points, and every Windows reparse point in every existing
ancestor, target, and temporary path; a missing target is created only beneath a validated regular
directory. Validation is case-aware for the host and rejects aliases that can resolve to the same
path with different identity.

Safe IDs and path components additionally reject Windows aliases: case-folding collisions, trailing
spaces or dots, 8.3 short-name aliases, separator/normalization aliases, and names that resolve to a
different identity through a junction or reparse point. They reject Windows device names `CON`,
`PRN`, `AUX`, `NUL`, `CLOCK$`, `COM1` through `COM9`, and `LPT1` through `LPT9`, case-insensitively,
with or without an extension, and reject equivalent names after trimming forbidden trailing dots or
spaces. Safe IDs use only the declared safe alphabet and length bounds; a device-name or alias check
is performed before allocation and again on the opened handle. A successful alias lookup never
validates an unsafe source token.

The write primitive must use a no-follow/reparse-safe, handle-based open and atomic publish (for
example, an OS primitive with no-follow and reparse-point rejection, same-directory temporary file,
durable flush, and atomic replace), or an equivalent atomic validation-and-write primitive that
binds the opened handles to the validated identities. A check-then-write path sequence is explicitly
insufficient because of TOCTOU races, especially on Windows. If the host cannot provide these
semantics, the writer fails closed and writes no evidence. Journal appends use an exclusive lock,
durable flush, and monotonic sequence/previous-hash validation.

After any scoped fix, human decision, canonical adoption, or task/source change, the writer
recomputes the affected input manifest and artifact hashes. It appends an invalidation event, marks
the affected current pointer and every descendant pointer invalid, and creates new `r<revision>/a<attempt>`
evidence in the same derivation lineage. It must then obtain fresh reports, deterministic gates, and
where applicable fresh human decisions; old evidence remains immutable. Task, trace, plan, review,
final-gate, and handoff projections never keep using a stale pointer. Canonical adoption writes only
through the validated writer after exact consent, records target pre/post hashes, and never silently
overwrites a supplied FEAT/SR/bundle baseline. A supplied baseline is never replaced in place as an
implicit recovery action; a failed publish leaves its previous bytes and the new evidence is blocked.

## 8. Optional Hermes Kanban planning graph

When requested and supported, FEAT-017 materializes one planning transport graph. If the capability
is unavailable, the run reports an explicit capability block; it must not emulate Kanban with prose
or silently dispatch work without the graph.

### 8.0 Canonical 12-node graph manifest

The canonical planning graph is one root plus exactly eleven ordered stage nodes. The combined
`human-boundaries-and-adoption` card is deliberately one transport node, but it contains two
mandatory sequential Coherence barriers: `human-boundaries` first and `canonical-adoption` second.
Those barriers are not extra graph nodes and must not change the twelve-node count.

`KanbanGraphManifest` is the exact embedded object in `KanbanRunSchema` and has no fields beyond
those shown here:

```json
{
  "schema": 1,
  "record_type": "kanban_graph_manifest",
  "graph_id": "feat17/<run-id>/planning/v1",
  "run_id": "<safe-id>",
  "node_order": [
    "planning-run", "capture", "provisional-spec-authoring", "spec-alignment",
    "candidate-sr-derivation", "candidate-sr-alignment", "implementation-plan-authoring",
    "task-materialization", "cross-artifact-alignment", "human-boundaries-and-adoption",
    "final-gates", "handoff"
  ],
  "nodes": [
    {"ordinal": 0, "node_id": "planning-run", "parent_ids": [], "child_ids": ["capture"], "barrier_ids": []},
    {"ordinal": 1, "node_id": "capture", "parent_ids": ["planning-run"], "child_ids": ["provisional-spec-authoring"], "barrier_ids": []},
    {"ordinal": 2, "node_id": "provisional-spec-authoring", "parent_ids": ["capture"], "child_ids": ["spec-alignment"], "barrier_ids": []},
    {"ordinal": 3, "node_id": "spec-alignment", "parent_ids": ["provisional-spec-authoring"], "child_ids": ["candidate-sr-derivation"], "barrier_ids": []},
    {"ordinal": 4, "node_id": "candidate-sr-derivation", "parent_ids": ["spec-alignment"], "child_ids": ["candidate-sr-alignment"], "barrier_ids": []},
    {"ordinal": 5, "node_id": "candidate-sr-alignment", "parent_ids": ["candidate-sr-derivation"], "child_ids": ["implementation-plan-authoring"], "barrier_ids": []},
    {"ordinal": 6, "node_id": "implementation-plan-authoring", "parent_ids": ["candidate-sr-alignment"], "child_ids": ["task-materialization"], "barrier_ids": []},
    {"ordinal": 7, "node_id": "task-materialization", "parent_ids": ["implementation-plan-authoring"], "child_ids": ["cross-artifact-alignment"], "barrier_ids": []},
    {"ordinal": 8, "node_id": "cross-artifact-alignment", "parent_ids": ["task-materialization"], "child_ids": ["human-boundaries-and-adoption"], "barrier_ids": []},
    {"ordinal": 9, "node_id": "human-boundaries-and-adoption", "parent_ids": ["cross-artifact-alignment"], "child_ids": ["final-gates"], "barrier_ids": ["human-boundaries", "canonical-adoption"]},
    {"ordinal": 10, "node_id": "final-gates", "parent_ids": ["human-boundaries-and-adoption"], "child_ids": ["handoff"], "barrier_ids": []},
    {"ordinal": 11, "node_id": "handoff", "parent_ids": ["final-gates"], "child_ids": [], "barrier_ids": []}
  ],
  "edges": [
    ["planning-run", "capture"],
    ["capture", "provisional-spec-authoring"],
    ["provisional-spec-authoring", "spec-alignment"],
    ["spec-alignment", "candidate-sr-derivation"],
    ["candidate-sr-derivation", "candidate-sr-alignment"],
    ["candidate-sr-alignment", "implementation-plan-authoring"],
    ["implementation-plan-authoring", "task-materialization"],
    ["task-materialization", "cross-artifact-alignment"],
    ["cross-artifact-alignment", "human-boundaries-and-adoption"],
    ["human-boundaries-and-adoption", "final-gates"],
    ["final-gates", "handoff"]
  ],
  "graph_hash": "<sha256>"
}
```

The manifest hash is SHA-256 over the canonical strict-JSON bytes of the manifest with only
`graph_hash` omitted. `node_order`, `nodes`, and `edges` are ordered arrays, and the ordinal, parent,
child, and edge lists MUST match exactly; sorting or deduplicating them changes the hash and makes
the graph invalid. There are exactly 12 nodes and exactly 11 edges. `graph_hash` is recorded in the
`kanban-run` record, root card, every card reference, and any final-gates record that requested the
transport graph.

The transport `state` is closed to `pending|ready|running|needs_input|blocked|done|failed|reclaimed|invalidated`.
`pending` is an unreleased card; `ready` requires every parent to be `done` and its current
Coherence predecessor gate to be `pass`; `running` requires an active lease; `needs_input` requires
an unresolved human boundary or escalation; `blocked` is any fail-closed prerequisite; `done`
requires current output hashes and the required Coherence gate, and is never sufficient by itself;
`failed` requires immutable failure evidence; `reclaimed` is a recovery transition back to the same
attempt; and `invalidated` cannot run or release a child. A parent in any state other than `done`
keeps its child unrunnable.

Every `running` card has exactly one `lease` with `lease_id`, `owner_id`, `fencing_token`,
`acquired_at`, `heartbeat_at`, `expires_at`, and `attempt`. The lease is acquired and renewed by
CAS; each heartbeat proves the same attempt and a strictly increasing fencing token. A card may
publish output only while holding the current lease. An expired lease transitions to `reclaimed`;
the reclaim takes the same revision and attempt, increments the fencing token, appends recovery
evidence, and then returns to `running`. A stale owner cannot publish, mark `done`, or release a
child.

Retries are bounded by the recorded `retry_policy`. A retry creates the next attempt for the same
revision and a new evidence path only after the previous attempt is durably failed or invalidated;
it never duplicates children or canonical artifacts. A crash reclaim is not a retry and never
increments attempt. A scoped fix, task/source change, or canonical adoption increments revision,
resets attempt to one, invalidates the affected node and every descendant, and requires a fresh
graph reconciliation. The coordinator materializes and hash-checks all twelve nodes and eleven
edges before setting any child to `ready`.

The combined human card cannot be marked `done` until its internal `human-boundaries` barrier has
validated boundary/challenge/warning decisions and its internal `canonical-adoption` barrier has
validated exact SR consent, target pre/post hashes, and adoption evidence. A failed or deferred
first barrier prevents the second; a withheld or invalid second barrier prevents `final-gates`.
The barrier records retain their separate exact paths and decision kinds even though the transport
no silent execution is permitted: no card state, lease, retry, or graph hash is an alternate release path.

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

All paths in this table are repository-relative and use the artifact naming contract in §2.2. Every
stage card has `run_id`, `stage_id`, `lineage_id`, `revision`, `attempt`, and
`attempt_key=feat17/<run-id>/<stage-id>/r<revision>/a<attempt>/v1`. Its stable lineage
`idempotency_key=feat17/<run-id>/<stage-id>/v1` is reused for replay/reclaim within the lineage;
revision and attempt are never omitted from evidence paths or manifests. A crash reclaim resumes the
same attempt and appends evidence; a retry starts the next attempt path. A scoped fix creates a new
revision in the same durable stage lineage and invalidates its descendants. Review reports use the
exact stage paths from §2.2 and contain the normative checkpoint enum/schema from §6.5. Every
review/resolution row also owns the exact DecisionFile path family from §6.9; Task 4 cannot use a
human response, decision, or later adoption card as a substitute for its current clean report/gate.

| Stage | Inputs -> outputs | Role and paths | Workspace, key, retry/block/completion | Downstream gate |
|---|---|---|---|---|
| `planning-run` (root) | request/policy/catalog -> `.factory/planning/<run-id>/state.json`, `.factory/planning/<run-id>/revision-index.jsonl`, `.factory/planning/<run-id>/current/planning-run.json`, and optional `.factory/planning/<run-id>/stages/planning-run/r<revision>/a<attempt>/kanban-run.json` | coordinator; run directory only; no canonical writes | coordinator workspace; lineage key `feat17/<run-id>/planning-run/v1`; attempt key includes `r<revision>/a<attempt>`; reclaim resumes the same run/attempt; block on unsafe/missing inputs; complete only after graph reconciliation | all stage cards exist with exact edges and contract hash |
| `capture` | prompt, questions, repository observations -> `.intent/intent.json` and `.factory/planning/<run-id>/stages/capture/r<revision>/a<attempt>/events.jsonl` | capture agent; `.intent/` and the versioned run capture path only | serialized project `dir`; lineage key `feat17/<run-id>/capture/v1`; attempt key includes `r<revision>/a<attempt>`; append evidence on retry/reclaim; block on incomplete/unsafe capture; complete on durable redacted-verbatim read-back/hash | current intent/provenance gate |
| `provisional-spec-authoring` | captured intent, facts, SR context -> `docs/superpowers/specs/<approved-name>.md` and `.factory/planning/<run-id>/stages/provisional-spec-authoring/r<revision>/a<attempt>/spec-authoring.json` | spec producer; approved spec target plus versioned run evidence only | serialized writer workspace; lineage key `feat17/<run-id>/provisional-spec-authoring/v1`; attempt key includes `r<revision>/a<attempt>`; never overwrite evidence silently; block on producer/read-back/schema failure; complete on strict parse and hash | current spec-alignment preflight |
| `spec-alignment` (Pass 1 review/resolution) | spec, intent, challenges, full SR context -> `.factory/planning/<run-id>/stages/spec-alignment/r<revision>/a<attempt>/review-report.json` and `.factory/planning/<run-id>/stages/spec-alignment/r<revision>/a<attempt>/checkpoint-gate.json` | fresh semantic reviewer; read-only versioned review/gate paths, `.factory/planning/<run-id>/resolution-events.jsonl`, and approved fixer target only | read-only review workspace; lineage key `feat17/<run-id>/spec-alignment/v1`; attempt key includes `r<revision>/a<attempt>`; unresolved findings/warnings or missing context leave `blocked`/`needs_input`; escalation never completes it; a validated DecisionFile queues a fresh independent review on the same lineage; complete only with the current clean report and matching deterministic gate | current candidate-derivation gate requires this clean report/gate tuple |
| `candidate-sr-derivation` | reviewed spec -> `.factory/planning/<run-id>/stages/candidate-sr-derivation/r<revision>/a<attempt>/candidate-sr-derivation.json` containing the one run-local candidate SR/feature/bundle projection and derivation record | candidate derivation agent; versioned run directory only, canonical records read-only | serialized run writer; lineage key `feat17/<run-id>/candidate-sr-derivation/v1`; attempt key includes `r<revision>/a<attempt>`; retry/reclaim resumes one lineage and never duplicates; block on stale spec or unsafe/ambiguous boundaries; complete on immutable candidate/projection and source hashes | current candidate-SR alignment preflight |
| `candidate-sr-alignment` (Pass 2 review/resolution) | candidate set, spec, full SR context -> `.factory/planning/<run-id>/stages/candidate-sr-alignment/r<revision>/a<attempt>/review-report.json` and `.factory/planning/<run-id>/stages/candidate-sr-alignment/r<revision>/a<attempt>/checkpoint-gate.json` | fresh SR reviewer; read-only versioned review/gate paths plus `.factory/planning/<run-id>/resolution-events.jsonl` | read-only review workspace; lineage key `feat17/<run-id>/candidate-sr-alignment/v1`; attempt key includes `r<revision>/a<attempt>`; duplicate/conflict/unsupported/missing-obligation/security findings leave `blocked`/`needs_input`; escalation never completes it; a validated DecisionFile queues a fresh independent review; complete only with the current clean report and matching deterministic gate | current plan-authoring gate requires this clean report/gate tuple |
| `implementation-plan-authoring` | reviewed spec and candidate SR set -> `docs/superpowers/plans/<approved-name>.md` and `.factory/planning/<run-id>/stages/implementation-plan-authoring/r<revision>/a<attempt>/plan-authoring.json` | plan producer; approved plan target plus versioned run evidence only | serialized writer workspace; lineage key `feat17/<run-id>/implementation-plan-authoring/v1`; attempt key includes `r<revision>/a<attempt>`; no supplied-path shortcut or evidence overwrite; block on stale inputs or invalid task grammar; complete on strict parse/hash with implementation and verification obligations together | current task-materialization preflight |
| `task-materialization` | reviewed plan -> `tasks/T-<digits>-<slug>.md` records and `.factory/planning/<run-id>/stages/task-materialization/r<revision>/a<attempt>/task-materialization.json` | plan-to-task producer; approved task targets plus versioned run evidence only | serialized task writer or isolated worktree reconciled before child; lineage key `feat17/<run-id>/task-materialization/v1`; attempt key includes `r<revision>/a<attempt>`; idempotent replay; block on parity/unbound task/path violation; complete when every task has required links/evidence | current cross-artifact review/trace preflight |
| `cross-artifact-alignment` (Pass 3 review/resolution) | intent/spec/candidate SR/plan/tasks/trace evidence -> `.factory/planning/<run-id>/stages/cross-artifact-alignment/r<revision>/a<attempt>/review-report.json`, `.factory/planning/<run-id>/stages/cross-artifact-alignment/r<revision>/a<attempt>/checkpoint-gate.json`, and `.factory/planning/<run-id>/stages/cross-artifact-alignment/r<revision>/a<attempt>/traceability.json` | fresh independent reviewer plus deterministic trace gate; read-only versioned review/gate paths | read-only review workspace; lineage key `feat17/<run-id>/cross-artifact-alignment/v1`; attempt key includes `r<revision>/a<attempt>`; one-way/missing trace, stale hash, or warning leaves `blocked`/`needs_input`; escalation never completes it; a validated DecisionFile queues a fresh independent review; complete only with current clean report, matching gate, and current bidirectional trace evidence | current human-boundaries preflight requires this clean report/gate tuple |
| `human-boundaries-and-adoption` | clean reviews, candidate set, warnings, boundary choices -> `.factory/planning/<run-id>/stages/human-boundaries-and-adoption/r<revision>/a<attempt>/warning-decisions.json`, `.factory/planning/<run-id>/stages/human-boundaries-and-adoption/r<revision>/a<attempt>/sr-consent.json`, `.factory/planning/<run-id>/stages/human-boundaries-and-adoption/r<revision>/a<attempt>/feature-boundary-decision.json`, `.factory/planning/<run-id>/stages/human-boundaries-and-adoption/r<revision>/a<attempt>/canonical-adoption.json`, and only after consent canonical SR/FEAT/bundle records | validated human-decision writer; `.factory/planning/<run-id>/decisions/<decision-kind>/r<revision>/a<attempt>/decision-<decision-id>.json` plus versioned stage outputs; supplied baselines read-only until explicit replacement | serialized decision/canonical writer workspace; lineage key `feat17/<run-id>/human-boundaries-and-adoption/v1`; attempt key includes `r<revision>/a<attempt>`; reclaim preserves pending `needs_input`; block on any unresolved warning/challenge, missing consent, or scope choice; complete only on validated hash-bound decisions and exact adoption | current final-gates preflight |
| `final-gates` | all current artifacts, decisions, optional graph, FEAT-018 capability -> `.factory/planning/<run-id>/stages/final-gates/r<revision>/a<attempt>/final-gates.json` | deterministic gate runner; versioned run evidence only, read-only canonical inputs | read-only gate workspace; lineage key `feat17/<run-id>/final-gates/v1`; attempt key includes `r<revision>/a<attempt>`; retry recomputes current hashes; block on stale consent/evidence, unavailable required capability, or graph mismatch; complete only on green current report bound to all current clean review/gate tuples | current handoff preflight |
| `handoff` | green final gates -> `.factory/planning/<run-id>/stages/handoff/r<revision>/a<attempt>/handoff.json` and `handoff.md` plus explicit next-action menu | handoff writer/presenter; versioned run handoff paths only; never dispatches | read-only inputs, atomic run write; lineage key `feat17/<run-id>/handoff/v1`; attempt key includes `r<revision>/a<attempt>`; idempotent by final-gate hash; block on any hash/pointer change; complete with validated `starts_automatically: false` | no automatic downstream execution |

No card may be marked complete from prose, a model assertion, fixture data, or Kanban `done` alone.
The coordinator must reconcile each card’s recorded inputs, outputs, role, paths, workspace claim,
attempt history, and required Coherence gate before releasing its children. Every downstream gate
must require the predecessor's current artifact/input hashes and, for a review/resolution predecessor,
the fresh clean report and deterministic gate evidence described in that row. A missing stage, edge,
hash, clean report, or completion record leaves the child unrunnable and visible as `blocked` rather
than being silently skipped. A non-clean escalation hash or a human-response hash can never satisfy
the handoff's three-clean-review requirement.

### 8.2 No downstream bypass rule

A downstream release is valid only if it resolves the predecessor's `current/<stage-id>.json` pointer,
recomputes every named artifact and input hash, verifies matching run/stage/lineage/revision/attempt,
and validates the required report as `status=clean` with a matching `checkpoint-gate.json`
`status=pass`. For human-boundary and final-gate releases it must additionally validate every required
DecisionFile, actor, coverage, replay binding, and canonical pre/post hash. It must reject prior
revisions, stale pointers, human responses, `accept_warning`, in-memory flags, model output, prose,
fixtures, missing DecisionFiles, escalations, non-clean reports, failed gates, and Kanban `done` as
substitutes. No adapter, card transition, handoff presenter, FEAT-018/019/020 capability, or future
workflow may provide an alternate release path; `starts_automatically: false` is enforced by the
consumer, not merely displayed.

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

1. Exact post-redaction prompt, questions, answers, repository observations, challenges, decisions,
   unresolved state, and provenance are durable, verbatim for all non-secret text, append-only, and
   recoverable; redaction records contain no credentials.
2. A real provisional-spec producer is invoked, writes the approved target, reads it back, validates
   it, and records its hash; a prompt or supplied path alone does not satisfy this criterion.
3. `PLANNING_ALIGNMENT` runs after that spec producer and before candidate derivation.
4. Exactly one run-local candidate SR derivation occurs before plan authoring; one immutable artifact
   contains the candidate SR/feature/bundle projections with concrete fields and no review back-
   reference; its separately stored adversarial review checks duplicates, conflicts, unsupported
   claims, compatibility, missing obligations, complete context, and feature boundaries without
   requiring a redundant second derivation.
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
   unresolved challenges, consent, and canonical adoption use the fixed DecisionFile schemas/enums,
   exact finding/boundary coverage, authenticated human provenance, current hashes, replay protection,
   and validated writer mappings.
9. Every security/operability warning blocks until fixed or explicitly human-dispositioned; no
   `accept_warning`, model response, silence, or fixture data bypasses that gate.
10. Optional Kanban materialization proves the root/stage graph, dependencies, idempotency,
    serialized workspace, retry/reclaim, recovery, reconciliation, and no silent downstream
    execution. Hermes Kanban is transport state, not a second scheduler.
11. FEAT-018 capability is checked honestly and blocks when unavailable; FEAT-017 does not claim
    FEAT-018, FEAT-019, or FEAT-020 behavior.
12. Final gates reject stale consent/evidence, reports, gates, pointers, or task projections and
    require clean re-derivation plus fresh exact human consent after any scoped change. Handoff is
    current, hash-bound, validated against all three clean report/gate tuples, and explicitly
    `starts_automatically: false`.
13. Review/fix cycles use fresh independent review, deterministic read-back, append-only evidence,
    known-debt separation, and no merge without explicit authorization.

This document is a design authority only. It does not certify implementation, consent, canonical
adoption, repository health, or plan acceptance.
