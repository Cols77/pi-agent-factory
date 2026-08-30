---
id: PLAN-FEAT-017-MATURE-PLANNING-WORKFLOW
title: "FEAT-017 Mature Planning Workflow Implementation Plan"
lifecycle_state: draft
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
- FEAT-019 owns cross-host conformance and FEAT-020 may optimize only an already FEAT-018-validated
  graph; FEAT-017 must not import, invoke, schedule, or test either capability. There is no downstream
  invocation of FEAT-018, FEAT-019, or FEAT-020 from this plan; FEAT-018 is only a read-only capability
  check at final gates.
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

Every run has a safe `run_id`, a selected project root, and an input manifest. Run-local evidence is
immutable by stage revision and invocation attempt. The initial implementation retains these canonical
input paths and adds only derived, versioned projections:

```text
.intent/intent.json
.factory/planning/<run-id>/state.json
.factory/planning/<run-id>/revision-index.jsonl
.factory/planning/<run-id>/current/<stage-id>.json
.factory/planning/<run-id>/resolution-events.jsonl
.factory/planning/<run-id>/stages/<stage-id>/r<revision>/a<attempt>/stage-manifest.json
.factory/planning/<run-id>/stages/<stage-id>/r<revision>/a<attempt>/<artifact>
.factory/planning/<run-id>/decisions/<decision-kind>/r<revision>/a<attempt>/decision-<decision-id>.json
```

For concrete artifact names, `capture` uses `events.jsonl`; the three review stages use
`review-report.json` and `checkpoint-gate.json`; candidate derivation uses
`candidate-sr-derivation.json`; plan and task producers use `plan-authoring.json` and
`task-materialization.json`; cross-artifact alignment also uses `traceability.json`; human boundaries
use `warning-decisions.json`, `sr-consent.json`, `feature-boundary-decision.json`, and
`canonical-adoption.json`; final gates use `final-gates.json`; handoff uses `handoff.json` and
`handoff.md`; and the optional planning root uses `kanban-run.json`. The exact expansions are defined
in the authority spec §2.2 and §8.1 and must be used by every card and manifest.

`revision` starts at 1 for a stage lineage and increments for a scoped source/fix change. `attempt`
starts at 1 for each new invocation within that revision. A crash reclaim resumes the same attempt
and appends evidence; a retry starts the next attempt and never reuses the old output path. The
append-only revision index records predecessor, invalidation reason, and current pointer. The current
pointer is replaceable derived state, not evidence; it may name only one matching artifact/report/gate
tuple. Stable lineage idempotency is `feat17/<run-id>/<stage-id>/v1`, and the attempt binding is
`feat17/<run-id>/<stage-id>/r<revision>/a<attempt>/v1`. No review, candidate, plan, task, trace,
decision, resolution, or handoff evidence may be overwritten ambiguously.

The single versioned candidate derivation artifact contains the candidate SR set and both candidate
feature/bundle projections; separate projection files are forbidden. It has no `review_hash` or any
post-review mutation. Its immutable content hash is computed before review and is recorded in the
stage manifest, candidate review input manifest, and all downstream manifests. Canonical FEAT/SR/bundle
adoption remains a later, explicit, consent-gated human-boundaries operation.

Run-local evidence is derived and immutable by revision/attempt. It never silently replaces canonical
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
(`id`, `title`, `lifecycle_state`), stable anchors, explicit intent/challenge coverage, scope and
non-goals, provisional/unresolved state, and implementation and verification obligations. It cannot
claim human consent, canonical SR adoption, or downstream execution.

The one candidate-SR record is run-local, immutable, and stored only at the versioned stage path. Its
schema is the authority spec §6.4 schema 2: it contains `candidate_srs`, `non_sr_classifications`,
`candidate_feature_projection`, and `candidate_bundle_projection` together with run/stage/lineage,
revision/attempt, source-spec hash, full-context digest, and no `review_hash`. Its content hash is
computed before review and is carried by the stage manifest and every consumer. The adversarial review
stores that candidate input hash; it does not mutate the candidate file. Separate feature/bundle
projection artifacts are forbidden. Its adversarial review must explicitly cover duplicate,
conflict, unsupported-claim, compatibility, missing-obligation, complete-context, and
feature-boundary cases. A correction is a new immutable revision in this single derivation lineage,
not another independent derivation.

The normative review-report and checkpoint-gate schemas are in authority spec §6.5. Each report has
checkpoint enum, stage/lineage/revision/attempt identity, current input-manifest and artifact hashes,
status `clean|findings|escalated|invalid`, exact finding IDs/scopes, independent reviewer identity,
and report hash. Each gate has the matching report hash/path, current manifest/artifact hashes,
status `pass|fail|invalid`, deterministic evidence, and gate hash. A child may run only from the
current clean report plus matching pass gate; prior attempts, escalation, human responses, and card
state cannot substitute.

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
id, title, lifecycle_state, run_id, stage_id, lineage_id, revision, attempt
source_plan, source_task, source_spec
sr_bindings: [{id, type: implements|verifies|supports, source_anchor, hash}]
non_sr_classification: {classification, reason, source_anchor, review_hash}  # when applicable
acceptance_criteria
test_paths, test_commands
implementation_evidence, verification_evidence
dependencies, allowed_paths, prohibited_paths
spec_hash, plan_hash, candidate_set_hash, task_projection_hash
```

Before handoff, every task binds to an adopted SR through `implements`, `verifies`, or `supports`,
or to an explicit reviewed non-SR classification. Unbound or ambiguous tasks block.

### 2.4 Shared DecisionFile, boundary, and handoff contracts (prerequisite)

The shared `DecisionFile` contract is implemented before Task 4, not introduced by the later adoption
task. Every immutable human decision is written at the exact path
`.factory/planning/<run-id>/decisions/<decision-kind>/r<revision>/a<attempt>/decision-<decision-id>.json`,
with `decision-kind` in `challenge-resolution`, `warning-disposition`, `feature-boundary`, `sr-consent`,
or `canonical-adoption`. It uses schema 1 and the complete authority-spec §6.9 record, including
`schema`, `record_type=decision_file`, `decision_id`, `decision_kind`, `run_id`, `stage_id`,
`lineage_id`, `revision`, `attempt`, `finding_scope`, `source_review`, `current_inputs`,
post-redaction `response_text`, `response_hash`, kind-specific `status`, authenticated-human `actor`,
`replay`, and `decision_hash`. `finding_scope` is not a caller-supplied subset: the writer computes the
canonical ordered finding/boundary universe from the current review, hashes that exact universe, and
requires the DecisionFile IDs and `coverage=exact` to cover it; missing, extra, duplicate, or reordered
IDs fail closed. The universe hash and its source report/input binding are retained in validation
provenance without changing the closed authority schema.

The actor is trusted only after the host validates an authenticated human session, subject identity,
authentication event, method, freshness/revocation, trusted channel, and authorization for this exact
run/stage/decision kind. `kind=authenticated_human` is a claim to verify, not permission to trust; agent,
model, fixture, adapter, or free-text identity cannot satisfy it. The replay object contains the exact
idempotency key, unique nonce, and previous journal-event hash. The writer verifies the current journal
tail, decision-ID/nonce uniqueness, current pointer, and authorization under the journal lock before
accepting one record. `decision_hash` is the canonical JSON hash with only that member excluded. A
validated writer rejects stale reports or inputs, unauthenticated or unauthorized actors, incomplete
finding-universe coverage, duplicate IDs/nonces, invalid kind/status combinations, and replays; it maps
exactly one accepted record to one durably appended `resolution-events.jsonl` event containing the same
run/stage/revision/attempt, source report hash, input/artifact hashes, response/decision hashes, actor,
status, and previous-event hash.

The JSON `status` vocabulary is closed and kind-specific; no synonym, transport state, or lifecycle state
may appear as a `status` value. Review records use `clean|findings|escalated|invalid`; deterministic gate
records use `pass|fail|invalid`; DecisionFile records use only the following values:

| Decision kind | Closed `status` values | Required kind-specific fields/bindings |
|---|---|---|
| `challenge-resolution` | `resolved|revised|deferred|unresolved|invalid` | exact challenge IDs and finding-universe coverage; current challenge/report hashes; response hash |
| `warning-disposition` | `fixed|accepted_risk|rejected|deferred|invalid` | exact warning IDs and severity/policy scope; current warning review/input tuple; response hash |
| `feature-boundary` | `selected|split_sequential|withheld|deferred|invalid` | exact boundary IDs; selected feature IDs; sequential workflow/worktree assignments; supplied-baseline pre-hashes |
| `sr-consent` | `consent_granted|consent_withheld|deferred|invalid` | exact candidate SR IDs and boundary IDs; candidate artifact hash; candidate and cross-artifact clean report/gate hashes; current input manifest; exact phrase |
| `canonical-adoption` | `adopted|withheld|deferred|invalid` | exact adopted IDs and boundary IDs; valid SR-consent and feature-boundary hashes; candidate hash; authorized target pre/post hashes |

`fixed` and `accepted_risk` are not self-certifying and do not erase a warning or finding. Each requires a
fresh independent review of the exact warning scope against current input/artifact hashes, followed by a
current deterministic gate; the finding, decision, review, and hash transitions remain append-only. An
accepted risk remains visible in current decision/audit history. Every `unresolved`, `deferred`, `withheld`,
`rejected`, or `invalid` decision blocks its dependent stage. `consent_withheld` and `deferred` leave the
stage in transport/lifecycle state `needs_input`; a human response or DecisionFile is an input to a fresh
review, never terminal evidence and never a child-release record.

The exact SR-consent phrase is:
`I authorize adoption of candidate SR set <candidate-artifact-sha256> into the canonical SR records for run <run-id>.`
It must be exact after substitution. Consent binds exact candidate IDs/artifact hash, candidate and
cross-artifact clean report hashes, current input manifest, boundary decision, authenticated actor,
response hash, decision hash, and replay binding. Adoption additionally binds consent hash, boundary hash,
canonical target pre/post hashes, and feature-boundary coverage. No `accept_warning` flag, open-ended
status, model assertion, or free-text response can change blocking state.

The handoff schema is authority spec §6.10: it is versioned under the handoff stage revision/attempt,
contains `record_type=planning_handoff`, evidence-envelope identity, `status=pass|fail|invalid`, the
current input manifest, all three current clean report/gate path/hash tuples, current artifact and
human-decision hashes, journal digest, FEAT-018 result, legal next-action menu, validated writer
identity, and literal `starts_automatically: false`. `ready`, `blocked`, and `invalidated` are not
handoff `status` values; they are not aliases for the closed handoff enum. Only `status=pass` with all
current clean/pass tuples is consumable.

### 2.5 Secure provenance and path-write contract

At ingress, a provider-safe, versioned `SecretDetectorSchema` runs on the raw transient input before
adaptive clarification, prompt construction, question/answer capture, repository observations,
response handling, policy processing, backend/provider transport, hashing, packetization, logging, or
diagnostics. A detector declaration has `detector_id`, semantic `version`, `detector_kind`, configured
pattern/rule identity without secret material, and `replacement=[REDACTED]`. Every redaction record has
only `field_path`, `reason`, `detector_id`, `detector_version`, and `replacement`; it never contains a
matched value, surrounding secret bytes, reversible digest, credential, provider configuration, or raw
secret. Detector identity/version is part of input/event provenance. An unavailable, ambiguous,
malformed, failed, or unverified detector/version fails closed before any downstream or provider call;
there is no permissive fallback. Changing detector identity/version invalidates affected snapshots and
all descendants.

After ingress redaction, preserve every non-secret prompt/question/answer/observation/response/policy
byte exactly and verbatim, but replace every secret-shaped value with `[REDACTED]` before persistence.
Redaction coverage includes canonical artifacts, input/review packets, reports, journals, Kanban
metadata, summaries, errors, and diagnostics; none may contain a credential or reversible secret-derived
value. Security redaction takes precedence over exact preservation, and the raw ingress buffer is
transient only: never persist, log, echo, hash, or send it to a backend/provider. Tests must exercise
all capture fields and every downstream projection, not only the original prompt.

All paths are repository-relative below the selected project root. Safe IDs and path components use
ASCII lowercase grammar `safe-id := [a-z0-9]+(?:-[a-z0-9]+)*`, with 1–64 characters; `task-slug` uses
the same grammar and length; `approved-name := YYYY-MM-DD-task-slug`, with a 128-character maximum.
`run_id`, stage IDs, decision IDs, canonical names, and task slugs are validated as supplied: Unicode is
NFC-checked, but a token that changes under normalization, case-folding, trimming, separator conversion,
or other aliasing is rejected rather than silently repaired. A task target is exactly
`tasks/T-<positive-decimal-no-leading-zero>-<task-slug>.md`; the date and separators in an approved name
are literal. Reject empty components, `.`, `..`, NULs, `/` or `\\` aliases, trailing spaces/dots,
case-folding collisions, Unicode/confusable or normalization aliases, 8.3 short-name aliases, and
Windows device names `CON`, `PRN`, `AUX`, `NUL`, `CLOCK$`, `COM1`–`COM9`, and `LPT1`–`LPT9` with or
without extensions. Reject alternate-data-stream syntax, absolute/drive/UNC paths, traversal, and
aliases that resolve to a different identity. Recheck device/alias identity on the opened handle.

Every writer receives an explicit role-scoped `allowed_paths` and `prohibited_paths` set. The canonical
target allowlist is exact and per operation: provisional-spec authoring may write only the approved spec
target and its versioned evidence; plan authoring only the approved plan target and evidence; task
materialization only approved `T-<digits>-<task-slug>.md` targets and evidence; review/gate/decision
writers only their versioned run paths; and canonical adoption only the exact canonical SR/FEAT/bundle
targets named by the validated boundary/adoption decisions. A target outside the allowlist, a role/path
mismatch, a missing cross-run target lock, or a pre-hash different from the authorized expected hash
fails closed. A supplied FEAT/SR/bundle baseline is a read-only input snapshot; no unrelated baseline
or canonical target may be overwritten, and adoption is never a recovery shortcut.

The write transaction acquires the target's cross-run exclusive lock, verifies the role and allowlist,
reopens and compares the expected pre-hash, writes through a no-follow/reparse-safe handle to a
same-directory temporary file, durably flushes, atomically publishes once, reads the exact bytes back,
computes the post-hash, and records the pre/post pair before releasing the lock. A CAS mismatch, lost
lock/fence, alias/reparse discovery, or failed durable publish leaves prior bytes untouched and appends
an invalidation/failure record. Check-then-write path validation is insufficient, especially on Windows;
if handle-based no-follow/reparse-safe atomicity is unavailable, fail closed without writing evidence.

### 2.6 Normative evidence envelope and complete record schemas

This plan adopts the authority spec §6.0.1–§6.0.4, authority spec §8.0, and §§6.5–§6.10 as normative, not as an
abbreviated checklist. Every persisted JSON object or JSONL line is an `EvidenceRecordSchema` record;
the closed `record_type` set is exactly:
`stage_manifest`, `revision_index_entry`, `current_pointer`, `input_manifest`, `capture_event`,
`spec_authoring`, `candidate_sr_derivation`, `checkpoint_review`, `checkpoint_gate`, `plan_authoring`,
`task_materialization`, `traceability`, `decision_file`, `resolution_event`, `final_gates`,
`kanban_graph_manifest`, `kanban_run`, `planning_handoff`, and `state_projection`. No extension bag or
unlisted record family is permitted.

Every record inherits these mandatory envelope fields unless the authority schema explicitly embeds the
object: `schema`, `record_type`, `record_id`, `run_id`, `stage_id`, `lineage_id`, `revision`, `attempt`,
`sequence`, `previous_record_hash`, UTC `created_at`, `provenance`, `input_manifest_ref`, and exactly
one schema-named terminal hash (`record_hash`, `manifest_sha256`, `pointer_hash`, `report_hash`,
`gate_hash`, `decision_hash`, `graph_hash`, or `handoff_hash`). `provenance` includes `actor_kind`,
`producer_role`, `producer_identity`, `invocation_id`, `source_record_ids`, and `source_paths`.
`stage_id` is the exact lowercase hyphenated graph node; identities are positive; all paths are exact
repository-relative UTF-8 paths. `terminal_hash` is a schema concept, never an extra JSON member, and
is SHA-256 over canonical bytes with only that record's terminal member omitted.

The complete required-field contracts are:

- `stage_manifest`: `run_id`, `stage_id`, `lineage_id`, `revision`, `attempt`, `sequence`,
  `previous_record_hash`, `record_id`, `input_manifest_ref`, `predecessor_refs[]`,
  `produced_artifacts[]`, `producer`, `workspace_claim`, `lifecycle_state`, `gate_result`,
  `started_at`, `finished_at`, `invalidation`, and `record_hash`; each predecessor has exact
  stage/revision/attempt/path/SHA-256/record hash, and `gate_result` is `pass|fail|invalid` or null
  only for a non-gate producer stage.
- `revision_index_entry`: `run_id`, `stage_id`, `lineage_id`, `revision`, `attempt`, `sequence`,
  `previous_record_hash`, `record_id`, `transition`, `predecessor_revision`, `predecessor_attempt`,
  `input_manifest_ref`, `artifact_refs[]`, `invalidated_stage_ids[]`, `current_pointer_ref`,
  `provenance`, and `record_hash`; `transition` is exactly `new_invocation|crash_reclaim|retry|scoped_fix|human_decision|canonical_adoption|task_source_change`, with a null predecessor only for `new_invocation`.
- `current_pointer`: `run_id`, `stage_id`, `lineage_id`, `revision`, `attempt`, `sequence`,
  `previous_record_hash`, `record_id`, `pointer_state`, `expected_pointer_hash`, `selected_record`,
  `input_manifest_ref`, `descendant_pointer_refs[]`, `invalidation_event_ref`, `cas`, `provenance`,
  and `pointer_hash`; `pointer_state` is only `current|invalidated`, and `cas` has
  `compare_hash`, `publish_sequence`, and `fencing_token`.
- `input_manifest`: `run_id`, `stage_id`, `lineage_id`, `revision`, `attempt`, `sequence`,
  `previous_record_hash`, `record_id`, `entries[]`, `observed_at`, `source_snapshot`,
  `manifest_sha256`, and `provenance`; each entry has exact path, SHA-256, byte length, role,
  source record ID, and observation time, sorted by path with no duplicates.
- `ProducedArtifact`: `artifact_id`, `kind`, `path`, `sha256`, `byte_length`, `canonical`, `redacted`,
  `writer_role`, `writer_identity`, `source_refs[]`, and `input_manifest_sha256`; it has no `status`
  and no approval or execution authority. `redacted=true` is mandatory for user-originating material.
- `spec_authoring`: the envelope plus `stage_id=provisional-spec-authoring`, `input_manifest_ref`,
  `source_intent_ref`, `source_fact_refs[]`, `output: ProducedArtifact`, `target_path`, `read_back`,
  `frontmatter`, `anchor_index[]`, `challenge_refs[]`, `lifecycle_state`, `producer`, and
  `record_hash`; `read_back` has path/SHA-256/parsed/semantic-validation and frontmatter has
  `id`, `title`, `lifecycle_state`.
- `plan_authoring`: the envelope plus `stage_id=implementation-plan-authoring`, `input_manifest_ref`,
  `spec_ref`, `spec_sha256`, `candidate_sr_ref`, `candidate_sr_sha256`, `output: ProducedArtifact`,
  `target_path`, `read_back`, `task_index[]`, `verification_obligations[]`, `producer`,
  `lifecycle_state`, and `record_hash`; each task index item has source number/anchor, dependencies,
  implementation and verification evidence, test paths/commands, and acceptance criteria.
- `task_materialization`: the envelope plus `stage_id=task-materialization`, `input_manifest_ref`,
  `source_plan`, `source_plan_sha256`, `source_spec`, `source_spec_sha256`, `candidate_sr_ref`,
  `candidate_sr_sha256`, `task_records[]`, `parity`, `produced_artifacts[]`, `dependencies`,
  `allowed_paths`, `prohibited_paths`, `lifecycle_state`, `gate_result`, `producer`, and
  `record_hash`; parity includes plan/materialized counts, exact source numbers, and `duplicates=[]`.
- `traceability`: the envelope plus `stage_id=cross-artifact-alignment`, `input_manifest_ref`,
  `source_hashes`, `forward_links[]`, `reverse_links[]`, `uncovered[]`, `ambiguous[]`,
  `non_sr_classifications[]`, `status`, `evidence`, `provenance`, and `record_hash`; every link has
  exact source/target IDs, paths, hashes, anchors, and `implements|verifies|supports|non-SR` type.
- `final_gates`: the envelope plus `stage_id=final-gates`, `input_manifest_ref`,
  `current_pointer_refs[]`, `current_clean_review_gate_tuples[]`, `artifact_hashes`, `decision_refs[]`,
  `traceability_ref`, `graph_manifest_ref`, `feat018_capability`, `warning_summary`,
  `consent_summary`, `adoption_summary`, `status`, `evidence`, `provenance`, and `gate_hash`;
  each review tuple carries checkpoint, report/gate paths and hashes, input-manifest hash,
  revision/attempt, and current-pointer hash.
- `kanban_run`: the envelope plus `stage_id=planning-run`, `input_manifest_ref`, exact
  `graph_manifest`, `graph_hash`, `root_card_id`, `card_refs[]`, `edge_refs[]`, `reconciliation`,
  `state`, `lease`, `retry_policy`, `reclaim_policy`, `coherence_gate_refs[]`,
  `no_silent_execution=true`, `provenance`, and `record_hash`; it transports lifecycle only.

`checkpoint_review`, `checkpoint_gate`, `decision_file`, `resolution_event`, `planning_handoff`, and
`kanban_graph_manifest` use the complete fields and closed enums in authority §§6.5, 6.9, 6.10, and
8.0; the abbreviated task descriptions above never relax those schemas. Canonical serialization is one
RFC-8785/JCS-equivalent UTF-8 JSON form without BOM, insignificant whitespace, duplicate keys, non-finite
numbers, non-canonical number forms, or unspecified array order; JSONL has one canonical record per line
and no blank lines. Writers reject omitted/extra/unknown/duplicate fields, wrong types, invalid enums,
unsafe paths, non-positive identities, sequence gaps, mismatched previous hashes, nulls not explicitly
allowed, and path/hash/predecessor mismatches. They do not default, coerce, truncate, drop, sort a
schema-ordered array, or silently repair input. An unsafe failure may emit only a safe invalidation
record; untrusted content is never copied into an error record.

All stage records are below the exact versioned stage path; the revision index, current pointer, and
resolution journal use their exact authority paths. The path encoded in a record must equal its actual
path byte-for-byte after root validation. Every predecessor reference names the exact current record
path/hash and record hash; a missing, stale, foreign, duplicated, or invalidated predecessor blocks the
child. Evidence is immutable: same-directory temporary write, durable flush, one atomic publish, and no
replacement or compaction of a published record. A current pointer is replaceable derived state only.

### 2.7 Immutable snapshots, fresh review, and recovery transaction

Before any producer, reviewer, fixer, decision writer, gate, or downstream consumer runs, it receives an
immutable `InputManifestSchema` snapshot containing every exact repository-relative path, byte length,
SHA-256, source record ID, role, observation time, repository commit/tree identity or explicit
`uncommitted` marker, and the complete non-deleted SR-context inventory. The inventory enumerates every
current proposed, deferred, satisfied, and active SR record, its statement/status/owner, source path,
stable anchors, source hash, disposition provenance, and available trace relations; no partial or
filtered context is accepted without an explicit manifest entry and hash. The producer binds the
manifest hash to output evidence, reads the published output through the validated handle, recomputes
its exact read hash, and records that binding. Reviewers and all consumers recompute and match it.
Mutation, missing snapshot, changed tree identity, path-only evidence, timestamp-only evidence, or
successful open without read-hash binding invalidates the pointer and requires a new transition.

A fresh independent review is mechanically a new invocation on the current stage/revision lineage with
a new invocation ID, new immutable report path/record ID, current input/artifact hashes, and a reviewer
identity/provider/model that is independent from the producer and fixer and cannot self-certify. The
selected reviewer model is fixed after host catalog validation; retries reuse that model but never reuse
a report hash or path. The closed deterministic gate-check registry is versioned and hash-bound. Check
IDs are exactly `FEAT017.<checkpoint>.<check>.v1`, with no caller-supplied checks: `spec_alignment`
requires intent/provenance coverage, spec schema/anchors, unsupported claims, contradictions,
feasibility/security/operability, complete SR context, and current hashes; `candidate_sr_alignment`
requires duplicate/conflict, unsupported-claim, schema/register compatibility, missing-obligation,
non-SR rationale, complete-context, feature-boundary, and current-hash checks;
`cross_artifact_alignment` requires forward trace, reverse trace, task parity, evidence obligations,
feature boundary, and current-hash checks; final gates require current review tuples, artifact hashes,
decisions, traceability, graph reconciliation when requested, FEAT-018 capability when requested,
and handoff flags. Each registry entry records check ID/version, implementation identity, invocation,
inputs, observed boolean, evidence references, and check hash. Unknown/missing/duplicate checks or
unproven provenance fail closed; a gate passes only when every required registry check is true and its
provenance/current hashes match.

Revision/attempt semantics are fixed: a new invocation creates revision 1/attempt 1; a crash reclaim
keeps both numbers and appends `crash_reclaim`; a retry keeps the revision, increments attempt, and
uses a new path only after durable failure/invalidation; a scoped fix, task/source change, or canonical
adoption increments revision and resets attempt to 1 after invalidating the affected stage and every
descendant; a human decision queues a fresh review attempt on the same revision and never releases a
child. Attempts and revisions are never reused for another invocation or semantic state.

DecisionFile -> journal -> pointer is one fenced, recoverable transaction. Under the current lease and
exclusive locks, the writer validates the authenticated actor, exact finding-universe coverage, current
report/input hashes, ID/nonce replay binding, role, and target allowlist; atomically publishes the
immutable DecisionFile; takes the journal lock, verifies monotonic sequence and previous-event hash,
appends exactly one canonical resolution event, durably flushes it, and releases the journal lock; then
takes the pointer lock, verifies `expected_pointer_hash` and the current fencing token by CAS, and
publishes the derived pointer selecting that DecisionFile/event. No child is released before the pointer
CAS succeeds. Recovery of this DecisionFile-to-journal-to-pointer sequence requires the current
lease's strictly increasing fencing token; if the token, lock owner, journal tail, or pointer hash is
ambiguous, recovery fails closed and records an invalidation. A crash before DecisionFile publication
discards its temporary file; after DecisionFile but before journal append leaves no accepted decision;
after journal append but before pointer publish,
recovery selects only a complete hash-valid chain or records an invalidation on ambiguity. Recovery
scans durable records/journal, discards uncommitted temporaries, retains the last valid pointer, and
reconstructs a missing pointer only from a complete chain. It never promotes an orphan, duplicates an
event, or treats transport state as evidence.

Leases are closed and fenced: each running card has one `lease_id`, `owner_id`, `fencing_token`,
`acquired_at`, `heartbeat_at`, `expires_at`, and `attempt`; acquire/renew/reclaim/publish/done use CAS
under the lease/target lock, and heartbeats prove the same attempt with a strictly increasing fencing
token. A stale or expired owner cannot publish, mark done, or release a child. Expiry transitions to
`reclaimed`, increments the fencing token, appends recovery evidence, and resumes the same attempt;
bounded retry creates the next attempt only after durable failure/invalidation and never duplicates
artifacts, cards, decisions, or children. A lock/fence/CAS failure fails closed and preserves prior
bytes.

## 3. Shared implementation and review protocol

### 3.1 Vocabulary and terminality rules

The machine vocabulary is closed. JSON `status` appears only on review, deterministic-gate, and
DecisionFile records: review `clean|findings|escalated|invalid`, gate `pass|fail|invalid`, and the
kind-specific DecisionFile enums in §2.4. `lifecycle_state` is used for the workflow state machine;
Kanban uses its separate closed `state` enum; pointers use `pointer_state`; leases use `lease_state`.
These fields are never interchangeable. `needs_input`, `blocked`, and `human response recorded` are
non-terminal lifecycle/transport conditions, never `status` values and never completion states.

In this plan, `completion evidence` means the immutable, hash-bound evidence required by a producer or
transport card; it is not a state or status token. A stage is complete only when its authority-defined
producer evidence exists, its current predecessor contract is satisfied, and, for review stages, the
current independent `status=clean` report is paired with the current deterministic `status=pass` gate.
Only the authority lifecycle state `handoff_ready` is terminal for the workflow, and only a handoff with
`status=pass` is consumable. The prose verb `defer` must be encoded as `status=deferred` only where the
kind-specific DecisionFile enum permits it. `rejected` is a warning-disposition status only; `reject`
or `rejection` elsewhere describes a validation failure that is recorded as `invalid` evidence or a
safe journal failure, not a new status. There is no separate fix-required or consent-deferred status;
use the exact review/gate state and the applicable `deferred` DecisionFile status instead. A user-needed
state is not defined; use `needs_input` with an explicit human DecisionFile requirement. No response,
warning disposition, card state, or status token is completion evidence by itself.

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
reports and checkpoint gates are immutable and independently hashed; a report is not current unless
its path, run/stage/revision/attempt, input manifest, artifact hashes, and current pointer all match.
A direct fix always invalidates the affected checkpoint and all downstream projections and requires a
fresh independent review plus deterministic gate. An unresolved review finding is an escalation record
that leaves the review/resolution card blocked in `needs_input`, never a completion state. A blocked
review/resolution card may resume only after the Task 1 validated `DecisionFile` writer records a
human answer/decision with exact finding scope and current artifact/input hashes; that record queues a
fresh independent review on the same stage/revision lineage. The human response alone never releases a
child. Completion requires the fresh report to be clean, current, hash-bound, and accepted by its
matching deterministic gate. Globally, `escalated`, `needs_input`, `blocked`, and `human response
recorded` are non-terminal and never completion states. Every downstream gate consumes the current
report/gate tuple rather than a state projection, prior attempt, DecisionFile status, or Kanban `done`.

A scoped fix, canonical adoption, or task/source change recomputes hashes, appends invalidation, marks
the affected current pointer and every descendant invalid, and creates new revision/attempt evidence
in the same lineage. Plan, task, trace, final-gate, and handoff projections must be regenerated and
re-reviewed. Supplied baselines are never silently overwritten; old evidence remains immutable.

## 4. Dependency-gated implementation tasks

### Task 1: Close structured intent provenance, challenges, and recovery

**Objective:** Make the capture boundary a durable, verbatim, append-only source for prompt,
questions, answers, repository observations, challenges, human decisions, unresolved state, and
failed-snapshot recovery, and implement the shared immutable DecisionFile writer/validator that all
review resolution stages require before Task 4.

**Files:**
- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/intent.py`
- Modify: `src/coherence/planning/session.py`
- Modify: `src/coherence/planning/serialization.py`
- Modify: `src/coherence/planning/check.py`
- Create: `src/coherence/planning/decisions.py`
- Test: `tests/unit/coherence/test_planning_intent.py`
- Test: `tests/unit/coherence/test_planning_session.py`
- Test: `tests/unit/coherence/test_planning_check.py`
- Test: `tests/unit/coherence/test_planning_resolution.py`
- Test: `tests/unit/coherence/test_planning_decisions.py`

**Interfaces:**
- Existing `.intent/intent.json` schema-one reader and schema-two materializer.
- Existing `.factory/planning/<run-id>/stages/capture/r<revision>/a<attempt>/events.jsonl` and derived `state.json` paths.
- Existing strict serializers and safe path helpers.
- New schema-1 DecisionFile, authenticated-human provenance, replay/idempotency, and
  append-only-resolution-event contract from §2.4 and authority spec §6.9.

**Dependencies/order:** First runtime task. It gates every producer and review packet because all
later stages require exact post-redaction prompt/provenance and a recoverable run. Its DecisionFile schema/path
validator and journal mapping must be complete before Task 2–4 can release work; Task 7 consumes the
same writer and must not redefine it.

**RED/documentation verification:** Add failing tests for the provider-safe versioned detector at
ingress: exact non-secret byte preservation; redaction of secrets in prompt, questions, answers,
observations, policy, responses, packets, reports, journals, Kanban metadata, errors, summaries, and
diagnostics; no raw/reversible secret or provider credential in any hash or output; detector identity/
version provenance; and fail-closed behavior for unavailable, ambiguous, malformed, or failed detector
configuration before adaptive clarification or backend/provider invocation. Test question/answer source
provenance, repository-observation hashes, challenge states encoded only as
`resolved|revised|deferred|unresolved|invalid`, exact human response provenance, unresolved state,
duplicate sequence/event rejection, and atomic materialization failure preserving the last known-good
snapshot while keeping a safe journal event. Also test the schema-1 DecisionFile path and complete
EvidenceRecordSchema fields, kind/status validation, authenticated-human trust and authorization
verification, exact finding-universe hash/coverage, current report/input/artifact hashes, response and
decision hashes, nonce/idempotency replay rejection, one-event journal mapping, and the fact that a
response remains non-terminal. Run:

```bash
uv run pytest tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_session.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_resolution.py tests/unit/coherence/test_planning_decisions.py -q -o addopts=''
```

Record which existing tests pass and which new assertions are RED; do not delete tests to make the
baseline look green.

**Implementation/GREEN:** Extend the strict event schema and deterministic state projection, retain
schema-one reads, run the versioned secret detector before any clarification/backend/provider/
diagnostics path, preserve all captured non-secret text exactly, redact secrets before persistence or
hashing, and use atomic replace semantics that never destroy the last good snapshot on failure.
Implement the shared DecisionFile validator/writer with exact repository-relative paths, the closed
kind-specific enums, current report/input/artifact hashes, authenticated-human trust/authorization
checks, exact finding-universe coverage/hash verification, response/decision hashes, replay protection,
and one-to-one append-only resolution-event mapping. Use the handle-bound DecisionFile -> journal ->
pointer transaction in §2.7. Do not infer a decision from silence or model output; do not make a human
response terminal.

```bash
uv run pytest tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_session.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_resolution.py tests/unit/coherence/test_planning_decisions.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_intent.py tests/unit/coherence/test_planning_session.py tests/unit/coherence/test_planning_decisions.py
uv run pyright src/coherence/planning
```

**Acceptance criteria:** The journal is strictly ordered and append-only; schema-one reads remain
compatible; every challenge/decision/unresolved value is queryable with exact provenance; unsafe,
malformed, duplicate-key, non-finite, non-UTF-8, or secret-shaped data is redacted/rejected before
persistence; a failed snapshot replacement preserves the prior bytes; state/hash evidence names the
journal and intent sources; and every accepted DecisionFile maps once to a replay-protected journal
event while leaving deferred/rejected/unresolved responses in `needs_input`.

**Prohibited scope:** Do not author a specification or plan, create actual consent/warning decisions,
allocate/adopt SRs, alter FEAT files, create Kanban cards, invoke downstream work, or modify the two
canonical documents except for a separately authorized verified-fact update. Implement only the
shared DecisionFile contract and writer needed by later stages; do not bypass its authentication or
status validation.

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
assert it writes a real spec from an immutable input snapshot, records the exact read-hash binding, and
emits a complete `spec_authoring`/`ProducedArtifact` evidence record. Assert that a missing backend
result, malformed frontmatter, unsupported claim, incomplete/changed input manifest, output-path escape,
unsafe ID or approved-name grammar, role/allowlist mismatch, cross-run lock failure, expected-prehash
CAS mismatch, stale input hash, or write/read-back mismatch blocks without overwriting the supplied
baseline. A test with only a caller-supplied spec path must be rejected as not having run the producer.
The producer oracle must inspect the created bytes and their recorded path/hash, not merely observe a
successful return. Run:

```bash
uv run pytest tests/unit/coherence/test_planning_producers.py tests/unit/coherence/test_planning_bootstrap.py -q -o addopts=''
```

**Implementation/GREEN:** Validate a structured producer result against the immutable input
manifest, provider capability, fixed producer role, safe ID/name grammar, and the exact role-scoped
spec target allowlist. Acquire the cross-run target lock, compare the authorized expected pre-hash,
atomically write through a no-follow/reparse-safe handle, read the exact output back, validate
frontmatter and stable anchors, compute SHA-256, and persist complete `spec_authoring` and
`ProducedArtifact` records. Expose `lifecycle_state`/gate evidence to the host, not an open-ended
`status`. Keep agent invocation behind the injected backend; the Python writer must not launch a shell
or provider itself.

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
- Immutable review-report/checkpoint-gate schemas from §6.5, including report/gate hash scope,
  current-pointer validation, and deterministic evidence.
- Shared DecisionFile schema/writer and append-only resolution journal from Task 1.

**Dependencies/order:** Depends on Tasks 1 and 2. It must run after the current clean `spec_alignment`
report plus deterministic gate and before any implementation-plan producer. The shared DecisionFile
writer is already implemented by Task 1; a human response or later Task 7 adoption code is not a
dependency or bypass. Update `REVIEW_STAGES` and workflow state to
`spec_alignment`, `candidate_sr_alignment`, and `cross_artifact_alignment`. Do not preserve the
old late-derivation stage as an alias that can run after the plan.

**RED/documentation verification:** Add tests proving candidate derivation cannot run without a
current clean hash-matching `spec_alignment` report and deterministic gate, produces exactly one
run-local candidate set, and receives a complete immutable SR-context inventory: every current
non-deleted proposed, deferred, satisfied, and active record, status/owner/statement, source path/hash/
anchor, disposition provenance, and available trace relation. A missing, filtered, stale, duplicate, or
changed context entry must fail closed. Add adversarial cases for duplicate and near-duplicate
obligations, contradictory statements/status/ownership, unsupported claims, schema/register
compatibility, missing independently governable obligations, explanatory prose, complete-context
manifest/hash, feature splits, and supplied FEAT baseline preservation. Assert that a second independent
derivation request is rejected or treated as a revision of the same lineage, that the candidate artifact
contains both concrete feature/bundle projections, that no projection sidecar is accepted, and that
review publication cannot add a `review_hash` or mutate candidate bytes. The derivation and review
oracles must inspect the artifact bytes, manifest entries, hashes, and exact required check IDs.

```bash
uv run pytest tests/unit/coherence/test_planning_candidate_sr.py tests/unit/coherence/test_planning_semantic.py tests/unit/coherence/test_planning_workflow.py -q -o addopts=''
```

**Implementation/GREEN:** Write the candidate record only under the versioned run stage directory,
bind it to the reviewed spec and full-context digest, include the exact `candidate_feature_projection`
and `candidate_bundle_projection` fields from authority spec §6.4, make candidate IDs/anchors/
relations deterministic, and persist adversarial findings in a separate immutable review report.
Compute and publish the candidate content hash before review; do not put `review_hash` in the
candidate artifact or mutate it after review. Allow only scoped revision attempts within this one
derivation lineage; every revision invalidates its review and downstream artifacts. Keep canonical SR
registration/adoption for the later human boundary.

```bash
uv run pytest tests/unit/coherence/test_planning_candidate_sr.py tests/unit/coherence/test_planning_semantic.py tests/unit/coherence/test_planning_workflow.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning src/coherence/navigate tests/unit/coherence/test_planning_candidate_sr.py
uv run pyright src/coherence/planning src/coherence/navigate
```

**Acceptance criteria:** Candidate derivation is observable before plan authoring, one candidate set
and revision lineage is hash-bound, the candidate artifact alone contains the SR/feature/bundle
projection and has no review back-reference, every required adversarial category is represented in
the review contract, all current non-deleted SR context is supplied, duplicates/conflicts are retained
for review rather than hidden, and no candidate becomes canonical without later exact human consent.

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

**Dependencies/order:** Depends on Task 3 and the shared DecisionFile schema/validator/journal writer
implemented in Task 1. It must run only after the current `candidate_sr_alignment` report is clean,
current, hash-bound to the candidate/spec/context inputs, and its deterministic gate passes. The
DecisionFile contract is a prerequisite already available here; Task 4 must not wait for or call the
later Task 7 adoption writer. An escalation record, `needs_input` state, human response, human disposition,
`accept_warning`, or human decision does not substitute for that clean-review tuple.
If any candidate finding is unresolved or a response was recorded without a fresh review, plan
production remains blocked. It must complete before task materialization.

**RED/documentation verification:** Add a fake-backend producer test that fails until the plan
contains both implementation and verification sections, explicit test-artifact obligations, exact
commands, acceptance criteria, prohibited scope, source-spec reference, candidate-set provenance,
and implementation-evidence obligations. Test incomplete or mutated immutable input manifests, stale
candidate/spec/context read hashes, malformed output, unsafe approved-name/task-slug, duplicate task
numbers, empty `Files:` blocks, role/target-allowlist mismatch, cross-run lock/CAS failure, and
read-back mismatch. The producer oracle must compare the bytes written at the authorized target with
the `plan_authoring`/`ProducedArtifact` path, byte length, and SHA-256 evidence, and must prove a
pre-existing plan was not mistaken for producer output.

```bash
uv run pytest tests/unit/coherence/test_planning_producers.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_workflow.py -q -o addopts=''
```

**Implementation/GREEN:** Require the reviewed candidate record and its immutable input snapshot as
inputs, invoke the injected plan-authoring backend, validate the safe approved-name/task-slug and
exact role-scoped plan target allowlist, and acquire the cross-run target lock. Compare the authorized
expected pre-hash, atomically write the selected plan target through a no-follow/reparse-safe handle,
read it back, validate frontmatter and every task section, compute the exact plan/read hash, and persist
complete `plan_authoring`/`ProducedArtifact` evidence. Keep implementation and verification obligations
in one plan; a coverage report may be derived later. Do not silently reuse a pre-existing plan as
producer success, and do not publish after a lost lock/fence or failed CAS.

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

**Objective:** Make plan-to-task generation idempotently create versioned task projections that
preserve source spec/plan/SR links, typed relations or reviewed non-SR classification, acceptance
criteria, exact tests/commands, evidence obligations, and run/stage/revision/attempt identity.

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

**Dependencies/order:** Depends on Task 4. It runs after plan read-back and before the current clean
`cross_artifact_alignment` review/gate. It must not pre-create spec, plan, SR, FEAT, or bundle
artifacts merely to satisfy a consumer check. A task/source fix increments the stage revision,
invalidates the current task/trace/handoff descendants, and creates a new versioned projection; it
never overwrites prior task evidence.

**RED/documentation verification:** Add tests that fail for missing source spec/plan links,
missing or ambiguous SR bindings, unreviewed non-SR classification, missing acceptance criteria,
missing exact test paths/commands, missing implementation/verification evidence, wrong hashes,
duplicate IDs/source numbers, foreign-plan records, and non-idempotent reruns.

```bash
uv run pytest tests/unit/coherence/test_planning_task_materialization.py tests/unit/test_plan_to_tasks.py tests/unit/coherence/test_planning_check.py -q -o addopts=''
```

**Implementation/GREEN:** Extend the existing writer or add the narrowest wrapper so each plan task
maps to exactly one generated record, with deterministic IDs, source fields, and run/stage/lineage/
revision/attempt identity. Validate typed
`implements`/`verifies`/`supports` relations against candidate IDs and source anchors, or require a
reviewed non-SR record. Persist `task-materialization.json` with plan/spec/candidate hashes. Reruns
return existing records for the same plan hash/source task/revision and never duplicate them; a
changed source hash is a new revision, not an in-place update.

```bash
uv run pytest tests/unit/coherence/test_planning_task_materialization.py tests/unit/test_plan_to_tasks.py tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning src/substrate/ledger tests/unit/coherence/test_planning_task_materialization.py tests/unit/test_plan_to_tasks.py
uv run pyright src/coherence/planning src/substrate/ledger
```

**Acceptance criteria:** One and only one generated task exists per selected plan task; unrelated
plans remain distinguishable; every record has the complete target contract, exact hashes, and
revision/attempt identity; running materialization twice is idempotent; source changes invalidate
the old projection rather than overwrite it; missing/ambiguous bindings block; and no task claims
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
after the real plan and typed tasks exist and their current input/artifact hashes are bound. It must
publish the immutable `cross_artifact_alignment` review-report/checkpoint-gate tuple before human
adoption. The resulting current clean trace/review gate must precede human adoption.

**RED/documentation verification:** Add failing forward and reverse cases: omitted intent decision,
unsupported spec claim, candidate with no spec anchor, spec obligation with no candidate or reviewed
non-SR classification, candidate with no plan task, task with no generated record, generated task
with no exact test/evidence, reverse links to the wrong plan/spec, incomplete SR-context inventory,
and stale hashes. Verify that a derived coverage report does not replace canonical links. Verify the
closed `FEAT017.<checkpoint>.<check>.v1` registry: missing, extra, duplicate, unknown, false, stale,
or unproven check provenance fails the deterministic gate, and a fresh reviewer cannot self-certify its
own producer/fixer output.

```bash
uv run pytest tests/unit/coherence/test_planning_traceability.py tests/unit/coherence/test_planning_trace_contract.py tests/unit/coherence/test_planning_workflow.py -q -o addopts=''
uv run coherence trace check --project-root .
```

**Implementation/GREEN:** Materialize a versioned deterministic trace report with run/stage/lineage/
revision/attempt, forward and reverse edges, source anchors, relationship types, test/evidence paths,
and all relevant hashes. Publish the immutable `cross_artifact_alignment` report and deterministic
checkpoint gate using the §6.5 schemas and the closed registry in §2.7; persist each required check's
version, implementation/provenance, input hashes, observation, evidence references, and check hash.
Make the current-pointer gate fail closed on any gap, contradiction, duplicate, foreign source, stale
artifact, missing/extra/unknown check, or unproven check provenance. Keep known repository-wide debt as
a separately labelled finding. Any trace/task/source change invalidates this report/gate and descendants
and requires fresh evidence.

```bash
uv run pytest tests/unit/coherence/test_planning_traceability.py tests/unit/coherence/test_planning_trace_contract.py tests/unit/coherence/test_planning_workflow.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_traceability.py tests/unit/coherence/test_planning_trace_contract.py
uv run pyright src/coherence/planning
uv run coherence trace check --project-root .
```

**Acceptance criteria:** `cross_artifact_alignment` runs after task materialization; every
independently governable obligation is represented exactly once or has a reviewed non-SR reason;
every candidate/task points back to valid source authority; implementation and verification
artifacts close both directions; the report has exact finding IDs/scopes, independent reviewer
identity, and hashes; the gate has matching current report/input/artifact hashes and deterministic
evidence; and a clean report is impossible with stale or incomplete links.

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
- Shared schema-1 `DecisionFile` writer/validator from Task 1, including its exact path, replay,
  authentication, journal mapping, and current-pointer rules; Task 7 must not redefine it.
- Immutable read-only planning reports and checkpoint-gate tuples from §6.5.
- Task 3 immutable candidate-artifact hash and separately stored candidate-SR review-report hash.
- Task 6 clean cross-artifact/traceability report.
- Human-facing host escalation and consent prompt boundary.

**Dependencies/order:** Depends on Tasks 1 and 6. It runs after the current clean cross-artifact
report plus deterministic gate and before the combined card's canonical-adoption barrier/final gates. A
feature split must stop before any canonical FEAT write. The validated DecisionFile schema/writer is a
Task 1 prerequisite; this task adds only the kind-specific writers and mappings described in §2.4 and
authority spec §6.9.

**RED/documentation verification:** Add tests proving unresolved challenges, feature splits, stale
baselines, security warnings, and operability warnings remain blocked; only the Task 1 validated
human DecisionFile can disposition a warning; `accept_warning` cannot alter blocking state; semantic
cleanliness, agent/model output, silence, fixture data, and free-text escalation answers cannot
create consent; fixed status enums and exact finding-universe/boundary coverage are enforced; actor
trust requires an authenticated, authorized, fresh, non-revoked human event/session; exact SR consent
uses the authority-spec phrase and binds candidate IDs, candidate-artifact hash, candidate and
cross-artifact clean report/gate hashes, input manifest, run/stage/revision, authenticated actor,
response/decision hashes, and replay binding. Test that `fixed` and `accepted_risk` each require a new
independent warning-scope review plus a current deterministic gate and retain the warning/finding in
history; neither status clears the finding. Adoption binds consent/boundary hashes, exact allowlisted
target pre/post hashes, role, cross-run lock, and CAS. Replayed, tampered, unauthorized, stale,
wrong-universe, wrong-role, lock-loss, or CAS-mismatched decisions fail; failed current consent/evidence
snapshots require fresh re-derivation and fresh consent.

```bash
uv run pytest tests/unit/coherence/test_planning_review_resolution.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
npm test --prefix pi-ext/factory-watch -- --run test/plan-review-command.test.ts
```

**Implementation/GREEN:** Use the Task 1 validated DecisionFile writer and existing gate writers
rather than a second warning store. Replace arbitrary in-memory warning acceptance with validation of
an exact human decision bound to warning IDs and the computed full warning/finding-universe hash,
current hashes, authenticated and authorized actor, closed kind/status enum, and append-only journal.
For `fixed` or `accepted_risk`, retain the original finding and disposition, invalidate the old review,
obtain a fresh independent review of the exact warning scope, and require its current clean report plus
pass gate before releasing the dependent stage. Add explicit feature-boundary decision writing with
selected feature IDs and sequential workflow/worktree assignments, preserving supplied FEAT/SR/bundle
bytes until a human authorizes replacement. Add the exact SR consent phrase and canonical adoption
writer only after the cross-artifact clean report/gate and the validated human-boundaries barrier are
current; under the authorized target allowlist, role, cross-run lock, expected-prehash CAS, and fencing
rules, record target pre/post hashes and invalidate downstream projections after any adoption.

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
pause/resume, unauthorized path rejection, graph mismatch, and proof that an escalated review stays
blocked until a validated `DecisionFile` answer/decision with exact finding-universe coverage and
current artifact/input hashes queues a fresh independent review. Test the combined
`human-boundaries-and-adoption` card's ordered internal barriers: validated boundary/challenge/warning
decisions commit first, exact consent validates second, canonical adoption is impossible before both
barriers and the adoption target CAS/lock, and a crash between barriers resumes without adoption.
Also prove that no child or downstream workflow runs from prose or a Kanban `done` state alone.

```bash
uv run pytest tests/unit/coherence/test_planning_kanban.py tests/unit/coherence/test_planning_workflow.py -q -o addopts=''
```

**Implementation/GREEN:** Persist the optional `kanban_run` transport record at the versioned root-stage
path `.factory/planning/<run-id>/stages/planning-run/r<revision>/a<attempt>/kanban-run.json` with
complete EvidenceRecordSchema fields and exact stage contracts: inputs/outputs and hashes, role/
assignee, allowed/prohibited paths, workspace mode, parents, lineage idempotency key, revision/attempt/
attempt key, lease/fencing/heartbeat/reclaim metadata, blocking reason, completion evidence, and the
required Coherence gate. Reconcile actual root/cards/edges against the intended graph before dispatch
and before handoff. Use CAS under the lease/target lock; a stale owner cannot publish or mark a card
`done`. Reclaim the same attempt key and fencing lineage, append evidence, and never duplicate artifacts
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
without duplicates; human blocks remain `needs_input` until a fresh current clean review/report/gate
evidence exists; all child dispatch is dependency- and gate-gated; graph/artifact hashes are
reconciled; and the graph never schedules implementation,
FEAT-018 execution, FEAT-019 conformance, FEAT-020 optimization, or health recovery.

**Prohibited scope:** Do not implement a second scheduler, alter Hermes Kanban lifecycle ownership,
use prose as a card, execute downstream work, or mark a Coherence gate green from Kanban state.

The stage-card contract in the authority spec §8.1 is part of this plan, not descriptive background.
Task 8 must implement one root card and one strictly dependent card per listed stage, using the
exact repository-relative versioned artifact paths and graph stage IDs from that table. A card's
stable lineage idempotency key is `feat17/<run-id>/<stage-id>/v1`; its attempt key is
`feat17/<run-id>/<stage-id>/r<revision>/a<attempt>/v1`. Reclaims keep the same attempt key and
append evidence; a retry uses the next attempt path; a scoped fix uses the next revision and
invalidates descendants. Review reports use
`.factory/planning/<run-id>/stages/<stage-id>/r<revision>/a<attempt>/review-report.json`, where the
checkpoint enum is exactly `spec_alignment`, `candidate_sr_alignment`, or
`cross_artifact_alignment`, and the matching `checkpoint-gate.json` is required.

Review stages own append-only resolution attempts. An unresolved finding is an escalation record that
keeps the stage `blocked`/`needs_input`; escalation, `blocked`, `needs_input`, and `human response
recorded` are never completion states. A scoped fix invalidates the affected stage and all descendants
and requires a fresh independent review. A blocked review stage may resume only when the validated
`DecisionFile` writer records a human answer/decision with exact finding scope and current
artifact/input hashes; that event queues a fresh independent review on the same stage/revision
lineage. A human response alone never releases a child. The review stage completes only when that
fresh report is current, hash-bound, clean, and its deterministic gate passes. Every downstream gate
must require this current clean review/report/gate evidence from its predecessor; no escalation hash,
human-response hash, card `done`, prose, or second scheduler can substitute for it.

The candidate SR/feature/bundle projection is created once in the versioned run-local
`.factory/planning/<run-id>/stages/candidate-sr-derivation/r<revision>/a<attempt>/candidate-sr-derivation.json`
record before plan authoring; the single document contains both projections and no separate projection
artifact is permitted. Its pre-review content hash is stored in the stage manifest and candidate
review input manifest, never as a `review_hash` back-reference. Canonical writers run only in the
explicit human-boundaries-and-adoption stage after exact human consent. There is no late SR
derivation, separate verification plan, or prose fallback.

For each card persist and reconcile, at minimum: run/stage/lineage/version; revision, attempt, and
both lineage and attempt keys; exact input and output paths and hashes; role and assignee; allowed
and prohibited paths; workspace claim/mode; parent IDs; timeout, heartbeat, retry, and reclaim
metadata; blocking state/reason; completion evidence; and the required current Coherence gate. The
implementation and dogfood must cover
the root plus capture, spec authoring, Pass 1 review/resolution, candidate projection, Pass 2
review/resolution, plan authoring, task generation, Pass 3 review/resolution, human consent and
canonical adoption, deterministic final gates, and handoff. Missing or stale parent evidence keeps a
card blocked; it must never be released because a prior card says `done` or because a stage is
described in a prompt.

#### Task 8 internal transaction: human boundaries before canonical adoption

The twelve-node graph keeps `human-boundaries-and-adoption` as one transport card with exactly two
ordered durable barriers, not two graph nodes. The exact barrier sequence `[human-boundaries, canonical-adoption]` is fixed. The card may enter `running` only from the current
clean/pass `cross_artifact_alignment` tuple. Its coordinator records a card transaction ID and barrier
sequence in the versioned `kanban_run`/stage evidence and serializes these steps:

1. **Human boundaries barrier:** acquire the card lease and decision locks; validate the complete
   challenge/warning/finding universe, authenticated-human trust and authorization, exact boundary
   coverage, selected feature IDs, sequential workflow/worktree assignments, and supplied-baseline
   pre-hashes; append the validated boundary/warning DecisionFiles and their one-to-one journal events;
   publish their derived pointers by CAS; then durably commit barrier `human-boundaries`. This barrier
   writes no canonical adoption output.
2. **Canonical adoption barrier:** only after barrier 1 is durably current, validate fresh exact SR
   consent (including the exact phrase, candidate IDs/hash, current clean review/gate tuples, and replay
   binding); acquire the authorized canonical target allowlist/role and cross-run locks; re-read target
   pre-hashes; append the consent and adoption journal events; publish canonical SR/FEAT/bundle outputs
   atomically through fenced pre-hash CAS; read back and record post-hashes; publish the adoption pointer
   by CAS; then durably commit barrier `canonical-adoption`.

The card is `done` only after both barriers, all outputs, and the current adoption evidence are hash
verified. A failed, deferred, withheld, invalid, stale, unauthorized, lock-lost, or CAS-mismatched
first barrier prevents the second. A crash after barrier 1 resumes from that committed barrier but does
not perform adoption without a fresh current consent transaction; a crash before a barrier commit is
recovered or invalidated without promoting partial output. A withheld or invalid second barrier keeps
the card in `needs_input`/`blocked` and prevents `final-gates`. No card state, lease, retry, graph hash,
model response, or human response is an alternate release path.

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

**Dependencies/order:** Depends on Tasks 1, 6, and 7; it is checked during final gates after human
boundaries and before handoff. Final gates must bind all three current clean review/gate tuples plus
current decision and artifact pointers before evaluating this capability. Task 8 may include its
result in the optional transport record but cannot implement FEAT-018.

**RED/documentation verification:** Add tests for capability present and validating the expected
governed graph, capability absent, provider error, stale/invalid proposal, and provider that tries
to run implementation. Assert absent/error returns an explicit blocked result and cannot be reported
as FEAT-018 validation or handoff readiness.

```bash
uv run pytest tests/unit/coherence/test_planning_capabilities.py tests/unit/coherence/test_planning_handoff.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
```

**Implementation/GREEN:** Define a read-only capability check with provider/version/contract hash,
proposal/expected-graph hash, and result. Bind its result to the current final-gate revision/attempt
and input manifest. Require a current positive FEAT-018 result for handoff when the governed execution
proposal is requested; otherwise surface a named block. Never invoke execution or let FEAT-020
optimize an unvalidated graph.

```bash
uv run pytest tests/unit/coherence/test_planning_capabilities.py tests/unit/coherence/test_planning_handoff.py tests/unit/coherence/test_planning_integration.py -q -o addopts=''
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_capabilities.py
uv run pyright src/coherence/planning
```

**Acceptance criteria:** FEAT-018 availability and result are explicit and hash-bound to the current
final-gate input manifest; absence or failure blocks without a false success; handoff is impossible
without all three current clean report/gate tuples; FEAT-017 does not claim FEAT-018/019/020
implementation; FEAT-020 is never called from planning; and the handoff records the capability
result.

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

**RED/documentation verification:** Start each fixture with only the exact post-redaction prompt,
captured answers,
repository facts, and an empty approved output location. Invoke the real producers. Add tests for:

- provisional spec write/read-back/hash and spec alignment;
- one candidate derivation/review before plan authoring, including duplicate/conflict/missing-
  obligation context;
- plan write/read-back/hash with implementation and verification tasks;
- typed task materialization and idempotent rerun;
- bidirectional trace closure and a deliberate missing-edge failure;
- one agentic scoped fix followed by a new immutable revision and fresh independent review/gate;
- human challenge escalation staying `blocked`/`needs_input` until the validated decision-writer
  answer/decision with exact finding-universe coverage/current hashes queues a fresh clean review;
- every security/operability warning blocking until a labelled human decision, with `fixed`/
  `accepted_risk` requiring a fresh clean warning-scope review while retaining findings;
- feature split stopping for human selection without overwriting a supplied baseline;
- interrupted/resumed capture and failed snapshot replacement preservation;
- non-secret prompt/question/answer byte preservation, versioned detector identity, ingress redaction
  before clarification/backend/provider/diagnostics, fail-closed detector ambiguity/failure, and
  credential-free summaries/diagnostics across every output projection;
- reparse-point/symlink/junction/traversal/device/alias rejection and race-safe no-follow atomic writes;
- immutable input snapshots and read-hash handle binding, complete SR-context inventory, exact
  `EvidenceRecordSchema` envelopes, canonical serialization, unknown/duplicate/path/hash/predecessor
  rejection, and safe-id/approved-name/task-slug grammar;
- authorized target allowlists, role scope, cross-run locks, expected-prehash CAS, fencing, and proof
  that unrelated canonical/baseline bytes are not overwritten;
- immutable revision/attempt paths, current-pointer invalidation, DecisionFile authentication,
  authorization, kind-specific fields, exact finding-universe hash/coverage, replay protection,
  DecisionFile-to-journal-to-pointer crash recovery, and one-to-one resolution-event mapping;
- closed deterministic gate-check registry/provenance with missing/extra/unknown/duplicate check
  failures and producer/reviewer oracle inspection of real bytes and hashes;
- Kanban materialization/reconciliation/lease/fencing/reclaim/retry when the optional capability is
  injected, including the two internal human-boundaries/adoption barriers and no adoption before
  validated boundaries plus consent;
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
all corrected lifecycle stages are observed in order; producer hashes/read-backs, immutable
revision/attempt evidence, candidate projection containment, review/gate schemas, DecisionFile
authentication/replay protection, challenges, warning decisions, consent, trace closure, recovery,
capability block, and handoff are verified; fixtures never count as human approval; path races and
reparse escapes fail closed; diagnostics contain no credentials; and unrelated debt is reported
separately.

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
- Create/modify: `.factory/planning/<run-id>/stages/final-gates/r<revision>/a<attempt>/final-gates.json` only through the validated writer

**Interfaces:**
- All prior task outputs and exact authority/plan contract.
- Existing unit, integration, Coherence, extension, and repository gate commands.
- Fresh spec-compliance and code-quality/security reviewers with no self-certification.

**Dependencies/order:** Final task; depends on Tasks 1–10. It must consume the current pointers and
all three current clean review/gate tuples, and must be rerun after every implementation, decision,
canonical-adoption, or fix cycle that changes a relevant artifact. No merge, push, canonical adoption,
or downstream workflow is allowed without explicit authorization.

**RED/documentation verification:** Add holistic assertions that the run cannot hand off when any
producer is skipped, any checkpoint is out of order, candidate review is late or duplicated, a task
is unbound, trace closure is one-way, a warning lacks human disposition, feature scope is unresolved,
FEAT-018 is unavailable when required, a snapshot/hash/consent is stale, a Kanban edge is missing, a
barrier is out of order, or `starts_automatically` is true. Also assert that an escalation/non-clean
review hash or a recorded human response cannot release a child, that `fixed`/`accepted_risk` without
fresh clean warning-scope evidence remains blocked, and that only a fresh current clean report plus
all required deterministic registry checks and gate evidence can complete a review stage. Verify exact
EvidenceRecordSchema serialization/field/path/hash/predecessor rules, detector fail-closed/redaction
coverage, target allowlist/role/CAS and recovery invariants, no FEAT-019/020 invocation, and no
contradictory normative order. Explicitly mark implementation, consent, and adoption as pending until
proved; do not turn plan text or fixture values into runtime claims.

```bash
uv run pytest tests/integration/coherence/test_planning_holistic.py tests/unit/coherence/test_planning_trace_contract.py -q -o addopts=''
```

**Implementation/GREEN:** Run the complete independent review protocol. First perform a fresh
spec-compliance review against every acceptance row in the authority spec, then a fresh
code-quality/security review covering path safety, prompt injection, secret detector version/fail-closed
coverage, stale-hash rejection, EvidenceRecordSchema/serialization, atomic writes, role/target scope,
allowlist/CAS/cross-run locks, workspace serialization, lease/fencing/retry/reclaim/recovery, the
ordered combined-card barriers, exact DecisionFile fields/authentication/replay coverage, closed
registry provenance, and no auto-execution or FEAT-019/020 invocation. Use fresh-context fixers for
findings, append all resolution events, reread changed artifacts, recompute hashes, and repeat both
reviews. Produce a derived coverage report if useful, but retain canonical evidence and known-debt
separation. A green result must be reported only as implementation evidence; this plan does not claim
that the runtime, consent, adoption, acceptance, or human validation exists today.

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
verification evidence; final gates are hash-current and fail closed on stale consent/evidence,
reports, gates, or pointers; the optional Kanban graph is reconciled when requested; FEAT-018 behavior
is honestly present or blocked; all security/operability warnings have resolution or explicit human
disposition; handoff is validated with all current clean report/gate tuples and
`starts_automatically: false`; the final summary distinguishes known debt and unavailable
capabilities; and there is no claim of merge or plan acceptance without explicit authorization.

**Prohibited scope:** Do not merge, push, mutate Kanban outside the requested optional planning graph,
start implementation/downstream workflows, fabricate human consent, or rewrite history.

## 5. Final acceptance matrix

| Area | Required proof |
|---|---|
| Intent provenance | Exact post-redaction prompt/question/answer text for all non-secret content, source, sequence, observations, challenges, decisions, and unresolved state are durable and hash-bound; versioned detector provenance and redaction metadata contain no secret |
| Snapshot/recovery | Immutable input snapshots/read-hash handle bindings, append-only journal and revision index survive interruption; failed materialization preserves the last known-good snapshot; DecisionFile -> journal -> pointer recovery never promotes an orphan |
| Evidence envelope | Complete `EvidenceRecordSchema` record families and required fields for stage, revision, current pointer, input, producer, task, trace, final-gate, Kanban, decision, and handoff records; canonical serialization; duplicate/unknown/path/hash/predecessor rejection |
| Spec producer | Real backend-injected producer writes, reads back, validates, and hashes the provisional spec under its role-scoped target allowlist, expected-prehash CAS, and cross-run lock |
| Spec checkpoint | `PLANNING_ALIGNMENT` runs after the producer and before candidate derivation |
| Candidate SR | Exactly one run-local derivation lineage occurs before plan authoring; one immutable artifact contains SR/feature/bundle projections with no review back-reference; adversarial duplicate/conflict/unsupported/compatibility/missing-obligation/full-context review is explicit |
| SR context | Every current non-deleted proposed/deferred/satisfied/active SR record, status/owner, source anchor/hash, disposition provenance, and available trace relation is present in the immutable inventory |
| Plan producer | Real backend-injected producer writes, reads back, validates, and hashes a plan containing implementation and verification work together under its approved-name/target/role/CAS contract |
| Task contract | Generated tasks bind source spec/plan/SR or reviewed non-SR, acceptance, exact tests/commands, and implementation/verification evidence |
| Cross-artifact gate | `CROSS_ARTIFACT_ALIGNMENT` runs after tasks and proves bidirectional closure |
| Review resolution | Schema-1 immutable report/gate identities, current input/artifact manifests, closed status enums, exact finding-universe coverage/hash, independent reviewer, report/gate hashes, closed check registry/provenance, and current-pointer rules are enforced; escalation is blocked `needs_input`; a validated hash-bound human answer/decision queues a fresh independent review, and only its current clean report plus deterministic gate evidence releases the child |
| Human boundaries | Feature splits stop for human sequential workflow/worktree choice; supplied FEAT baseline is never silently overwritten; the combined transport card commits human boundaries before its canonical-adoption barrier |
| Warnings | Every security/operability warning blocks until fixed or explicitly dispositioned by a human; `fixed`/`accepted_risk` require fresh clean warning-scope review evidence and retain findings; no `accept_warning` bypass |
| Consent/adoption | Fixed kind-specific enums and validated writers bind exact candidate IDs/artifact hash, report/input hashes, boundary coverage, authenticated/authorized human actor, exact consent phrase, response/decision hashes, replay protection, and canonical target pre/post hashes; adoption is impossible before validated boundaries plus consent |
| Path/target safety | Safe-id/approved-name/task-slug grammar and Windows alias/device rules, exact role-scoped target allowlists, no-follow writes, cross-run locks, fencing, and expected-prehash CAS prevent unrelated baseline overwrite |
| Kanban | Optional root/stage cards, dependencies, idempotency, workspace serialization, lease/fencing/retry/reclaim, recovery, reconciliation, ordered two-barrier human card transaction, and no silent downstream execution are tested |
| FEAT boundary | FEAT-018 capability is checked/blocked honestly; FEAT-019 conformance and FEAT-020 optimization remain separate and are never invoked by FEAT-017 |
| Freshness | Any relevant input, output, context, model, decision, policy, canonical adoption, or task/source change appends invalidation, advances revision/attempt identity, invalidates current pointers and descendants, and requires fresh evidence |
| Handoff | JSON/Markdown handoff is current, validated, hash-bound, includes all three current clean review report/gate evidence tuples, rejects escalation/non-clean/human-response hashes, and has `starts_automatically: false` |
| Known debt | Existing repository debt and unavailable capabilities are reported separately, never converted into false success |
| Authorization | No merge, push, canonical adoption, or downstream launch without explicit authorization; plan text never claims runtime implementation, acceptance, consent, adoption, or human validation |

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
