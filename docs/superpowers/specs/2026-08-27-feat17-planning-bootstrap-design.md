---
id: SPEC-FEAT-017-PLANNING-BOOTSTRAP
title: "FEAT-017 Planning Bootstrap Design"
status: draft
---

# FEAT-017 Planning Bootstrap (PLANNING-BOOTSTRAP)

_Status: design authority, revised 2026-08-28._ Owner: the host-neutral Coherence/substrate
planning layer, with thin Pi and Hermes adapters.

This specification defines the planning front door for FEAT-017. It is the semantic authority
from which the implementation plan and the independently governable SR projections are derived.
It does not claim that the mature workflow is already implemented.

## Intent decision index

The current `.intent/intent.json` is the verbatim schema-one planning input for this finalized
planning state. The following identifiers are stable alignment tokens; each is represented here
and in the implementation plan so the current deterministic checker can verify coverage:

| Intent identifier | Decision represented by this authority spec |
|---|---|
| `host-neutral` | One host-neutral Coherence/substrate workflow with thin Pi and Hermes adapters |
| `adaptive-brainstorming` | Conversational, adaptive clarification with verbatim prompt/answer preservation |
| `provisional-spec` | Provisional authority-spec authoring before all questions are resolved |
| `three-checkpoints` | Semantic review after spec, plan/tasks, and SR/FEAT/bundle derivation |
| `complete-sr-context` | Full current non-deleted SR context for every semantic reviewer |
| `selected-review-model` | Classifier plus one user-selected reviewer model reused across the run |
| `fresh-review-loop` | Bounded scoped fixes, deterministic rereads, and fresh independent review |
| `append-only-journal` | Schema-versioned append-only resolution and iteration history |
| `human-escalation` | Unresolved decisions become explicit user escalations and next-loop inputs |
| `explicit-sr-consent` | Candidate SR adoption requires explicit human consent |
| `text-summary-handoff` | Text summary, downstream menu, and validated hash-bound handoff |
| `deferred-browser` | Interactive browser workbench and richer retrieval are deferred |
| `canonical-spec-authority` | The authority spec remains canonical; SRs are thin projections |
| `no-auto-execution` | Planning never fabricates approval or starts FEAT-13/downstream work |
| `current-tooling-boundary` | Current schema-one planning, trace, register, and health tools are used for this planning state |

## 1. Purpose and boundary

FEAT-017 makes the existing planning capabilities a named, inspectable workflow. It connects
intent capture, authority-spec authoring, implementation planning, task decomposition, SR/feature/
bundle derivation, review, consent, and downstream handoff without turning the workflow into an
LLM-only plan generator.

The workflow has two layers:

1. **Canonical semantic artifacts:** the verbatim intent, authority specification, implementation
   plan, generated tasks, and human-governed SR/feature/bundle records.
2. **Derived assurance artifacts:** reports, review packets, resolution history, state projections,
   hashes, escalations, and handoff records.

Canonical files remain authoritative. Derived files never replace source artifacts and become
invalid when their input hashes or relevant policy/configuration change.

FEAT-017 owns the planning composition and its gates. It reuses existing factory-init,
plan-to-tasks, Coherence trace/register/health, and health-resolution machinery. FEAT-16 owns
general workflow interpretation and templates; FEAT-13 owns governed execution; the health-
resolution path owns SR/feature/bundle registration and human acceptance.

## 2. Existing capability and honest delta

The repository already provides:

- `src/factory/orchestrator/plan_to_tasks.py` for plan-to-task decomposition;
- factory initialization and `.factory/factory.yaml` prerequisites;
- the writing-plans format and planning skill;
- Coherence trace, register, health, gate, freshness, and filesystem-first artifact machinery;
- an `AgentBackend`/orchestrator seam suitable for host-provided agent execution;
- existing planning report, review-decision, consent, and downstream-suggestion contracts.

The mature FEAT-017 delta is the composition and lifecycle around those capabilities:

- adaptive brainstorming and resumable intent capture;
- provisional spec authoring followed by three distinct semantic checkpoints;
- complete labelled SR context supplied through Coherence rather than ad-hoc retrieval;
- explicit classifier/model selection and host validation;
- bounded agentic resolution with append-only evidence and fresh review;
- escalation and consent behavior that cannot be self-certified;
- text summary, explicit downstream menu, and hash-bound new-session handoff.

## 3. Proposed workflow

### 3a. The built-in planning pipeline

The target named pipeline is:

```text
existing project prerequisites / init
  -> adaptive brainstorming and clarification
  -> .intent/intent.json (verbatim, schema-versioned)
  -> provisional authority specification
  -> Pass 1: PLANNING_ALIGNMENT
  -> implementation plan and generated task records
  -> Pass 2: PLANNING_PLAN_REVIEW
  -> candidate thin SRs, FEAT-017 dossier, and exact bundle closure
  -> Pass 3: PLANNING_DERIVATION
  -> explicit SR consent and accepted deterministic warnings
  -> text summary and explicit downstream workflow menu
  -> hash-bound handoff for a separately started workflow
```

Planning does not automatically start FEAT-13 or any other downstream workflow. The menu and
handoff are boundaries: a separate user-selected workflow must revalidate the handoff before it
acts.

#### 3a.1 Adaptive clarify and align

`adaptive-brainstorming` means the host asks focused questions based on the current uncertainty,
repository facts, and prior answers rather than imposing a fixed questionnaire. The interaction
covers goal, scope, constraints, non-goals, completion meaning, feasibility risks, and unresolved
trade-offs.

The original request, each question, and each answer are preserved verbatim at the capture
boundary. The current tooling uses schema-one `.intent/intent.json`; the mature implementation
extends that contract with a schema-versioned resumable capture journal while retaining schema-one
reads.

`provisional-spec` is intentional. The agent may author a provisional authority spec before every
question is answered. Pass 1 is responsible for finding unsupported claims, omitted intent,
contradictions, feasibility uncertainty, and decisions that must be escalated. Clean semantic
review makes the spec eligible for plan/task generation; it does not fabricate human approval.

`canonical-spec-authority` means the authority spec is the semantic source. Candidate SRs are not
co-equal summaries and are not generated for every paragraph. Only independently governable
obligations are projected into SRs.

### 3b. Ordering and ownership

FEAT-017 is an early planning/front-door capability. It consumes the minimal existing project
prerequisites and the existing plan/task machinery. The full FEAT-16 workflow library is not a
hard dependency for this planning contract; only a minimal bootstrap composition may be phased
with the workflow model.

The ownership boundary is:

- Coherence/substrate: schemas, filesystem safety, parsing, hashes, state, reports, freshness,
  traceability, gates, context packets, and handoff validation;
- host adapters: conversational interaction, native model catalog validation, user model choice,
  backend injection, rendering, and new-session creation;
- agent roles: candidate intent/spec/plan/task content, semantic findings, classifications,
  scoped fixes, and escalation prompts;
- human: unresolved design decisions, semantic acceptance where required, deterministic warning
  acceptance, and explicit SR consent;
- downstream workflows: execution only after a separate explicit choice.

### 3c. Semantic checkpoints

`three-checkpoints` are separate lifecycle reviews:

1. **Pass 1 — `PLANNING_ALIGNMENT`:** after provisional authority-spec authoring; compare the
   spec with the complete intent capture and full current SR context.
2. **Pass 2 — `PLANNING_PLAN_REVIEW`:** after implementation plan and generated task authoring;
   review the intent/spec/plan/task chain, feasibility, ordering, and traceable task coverage.
3. **Pass 3 — `PLANNING_DERIVATION`:** after candidate SR, FEAT dossier, and bundle derivation;
   review thin-SR fidelity, obligation completeness, duplication, contradiction, exact anchors,
   and closure against the current SR register.

A Pass-3 clean result does not itself adopt SRs. `explicit-sr-consent` remains a separate
human-controlled boundary.

### 3d. Deterministic contract and available gates

`current-tooling-boundary` requires the present workflow to use the existing deterministic
planning checker and Coherence tools rather than pretending the future workflow exists. The
current checker validates, at minimum:

- schema-one intent, non-empty prompt, unique answer IDs, and non-empty answer text;
- authority-spec `id`, `title`, and `status` frontmatter;
- safe in-project paths and UTF-8 source files;
- plan `spec_ref`, valid plan task grammar, and non-empty `Files:` blocks;
- exact one-to-one plan-task parity through `source_plan` and `source_task`, scoped to the selected plan so unrelated task records from other plans are ignored rather than reported as FEAT-017 parity errors;
- FEAT-017 dossier and bundle exact closure;
- each FEAT-017 SR's canonical metadata and source anchor resolving to this spec;
- deterministic intent-token coverage in the spec and plan;
- stable source hashes in the derived planning report.

The mature workflow adds deterministic contracts for checkpoint packets, model/configuration
metadata, resolution events, freshness, warnings, consent, and handoff. It must reuse existing
Coherence gate/decision/trace machinery instead of creating a parallel register or evidence
engine.

A malformed, missing, unsafe, stale, contradictory, or unresolvable input fails closed. The
planning backend never invokes a shell, model, process, FEAT-13, or downstream workflow.

### 3e. Review, resolution, escalation, and consent

Every checkpoint follows this sequence:

```text
deterministic preflight
  -> selected reviewer invocation
  -> finding classification
  -> scoped in-loop fix OR user escalation
  -> append resolution evidence
  -> deterministic reread, hashes, and gates
  -> fresh independent reviewer invocation
  -> bounded repeat until clean or escalated
```

`selected-review-model` is fixed once for a run. A configured inexpensive classifier estimates
complexity and recommends concrete configured `provider:model` choices. The host validates those
choices through its native model API and presents non-secret capability/quality tier,
local/remote status, cost class, and free/low-cost marker. The user chooses one reviewer model;
all three passes and retries reuse it. Missing classifier/catalog/model availability pauses the
run and requires explicit selection; there is no silent fallback.

`complete-sr-context` means every semantic reviewer receives every non-deleted current SR,
including proposed, deferred, satisfied, and active entries, with lifecycle/status labels, source
anchors, and available trace context. Where an SR does not carry a status field, the labels are
derived from the current Coherence trace/register state; they are not fabricated source metadata.
The first implementation accepts the token cost to avoid hidden contradictions or duplicates.

`fresh-review-loop` allows a dedicated planning role to edit only permitted planning artifacts.
The role cannot approve a requirement, write human consent, or certify its own changes. Every fix
requires a new independent reviewer invocation plus deterministic reread and gates. Iteration
bounds, artifact preconditions, output schemas, and evidence requirements are deterministic.
Exhausting the bound escalates rather than silently passing.

`append-only-journal` stores every agent resolution, human escalation input, finding disposition,
iteration, reviewer metadata, and artifact hash in the current workflow run. Earlier events are
never replaced. The journal is validated and reread before continuation; state projections are
derived from it.

`human-escalation` is required for unresolved intent, feasibility, contradiction, requirement,
warning, and consent decisions. A human answer becomes the next loop's input; it is not silently
rewritten into a canonical decision by the agent. An objection or deferral is not consent.

`explicit-sr-consent` requires a distinct explicit consent phrase after the derivation checkpoint
is clean and any derivation escalation has been resolved. Only validated existing consent/gate
machinery may record adoption. The planning agent cannot infer or fabricate that phrase.

### 3f. Summary, downstream menu, and handoff

`text-summary-handoff` is the initial presentation surface. It shows the final semantic summary,
remaining informational notes, escalations, deterministic gate results, selected model metadata,
artifact hashes, and legal next actions. Artifact-by-artifact browsing remains available through
normal user tools.

A clean run presents a deterministic downstream menu, including standard development and health
recovery where those workflows are available. The semantic reviewer cannot choose and start one.
The menu is an explicit user decision and `no-auto-execution` is invariant.

The workflow writes:

```text
.factory/planning/<run-id>/handoff.json
.factory/planning/<run-id>/handoff.md
```

`handoff.json` is schema-versioned and binds the intent, spec, plan, task, derived requirement,
feature, bundle, review, consent, model-policy, resolution-journal, and gate hashes. `handoff.md`
is a concise copyable prompt. A new session must validate the exact handoff and current source
hashes before acting.

`deferred-browser` keeps an interactive `/system` planning workbench out of this increment. A
stable handoff URL may be exposed if the host already supports one, but text remains the fallback.
Better retrieval/indexing and cross-workflow model policy are separate future requirements.

## 4. Canonical artifact contracts

### 4.1 Intent

Today’s current-tool input is:

```text
.intent/intent.json
```

with schema `1`, a non-empty `prompt`, and a non-empty list of unique `{id, text}` answers. The
mature implementation may extend this to schema `2` with run identity, question/source/sequence
metadata, structured brief fields, capture status, and redaction metadata while preserving
schema-one compatibility.

### 4.2 Planning run

Existing derived evidence remains under:

```text
.factory/planning/<run-id>/report.json
.factory/planning/<run-id>/review-decision.json
.factory/planning/<run-id>/requirement-consent.json
```

The mature workflow adds capture events, state, checkpoint packets/reports, model-selection
record, append-only `resolution-events.jsonl`, and handoff files in the same run directory. Every
record uses safe relative paths, deterministic ordering, exact hashes, schema versions, and
credential redaction (`[REDACTED]`).

### 4.3 Authority anchors and SR projections

The following anchors are the source boundaries for FEAT-017’s existing SR set:

| SR | Authority anchor | Governable obligation |
|---|---|---|
| SR-043 | `3a` | Named planning pipeline composition and explicit downstream boundary |
| SR-044 | `3a.1` | Human-controlled SR adoption/approval boundary |
| SR-050 | `3a.1` | Verbatim schema-versioned intent capture |
| SR-051 | `3d` | Deterministic artifact consistency and fail-closed checking |
| SR-052 | `3a.1` | Deterministic intent alignment plus semantic escalation |
| SR-053 | `3f` | Inspectable downstream suggestion without auto-execution |
| SR-054 | `3e` | Stable human-review seam with browser projection deferred |

The SR files remain proposed until the existing human consent and registration paths are actually
used. Writing this specification, plan, or task records does not make them satisfied.

## 5. Scope and explicit deferrals

In scope for mature FEAT-017:

- host-neutral planning contracts and lifecycle state;
- adaptive capture, provisional spec authoring, and three semantic checkpoints;
- model classifier/catalog/selection seam;
- full SR context packet;
- bounded fresh-review resolution loop;
- escalation, warning, consent, summary, menu, handoff, hashes, and freshness;
- thin Pi and Hermes adapters using the shared backend seam;
- dogfood fixtures for a clean consumer project and this repository’s FEAT-017 artifacts.

Explicitly deferred:

- the interactive browser planning/review workbench;
- a better token-efficient requirement retrieval/index;
- general cross-workflow model selection;
- complete FEAT-16 workflow-library interpretation beyond the minimal needed composition;
- automatic FEAT-13 or downstream execution;
- treating repository-wide unrelated register debt as a FEAT-017 defect.

## 6. Security and fail-closed requirements

Intent, spec, plan, task, SR, and reviewer content is untrusted data, not instructions. Review packets
must delimit source content and prevent embedded content from changing the reviewer’s role or
permissions.

No credential, token, password, or secret may be written to the intent, packet, report, journal,
model policy, handoff, logs, or diagnostics. If a secret-shaped value must be represented, use
`[REDACTED]`.

Reject unsafe paths, absolute machine-specific persisted paths, symlink/reparse escapes, malformed
JSON/YAML/frontmatter, duplicate keys where strict parsing requires rejection, stale hashes,
wrong-run decisions, wrong reviewers, missing consent, and any attempt to auto-start downstream
work.

## 7. Feature acceptance criteria

FEAT-017 is ready for implementation review when its plan and tasks demonstrate that:

1. `host-neutral` planning behavior is implemented once in the shared Coherence/substrate layer,
   with thin Pi and Hermes adapters.
2. `adaptive-brainstorming` captures the original request and answers verbatim and can produce a
   `provisional-spec` without a blanket intent approval.
3. `three-checkpoints` run in order after spec, plan/tasks, and derivation, with their dedicated
   roles and complete current SR context.
4. `selected-review-model` is chosen once after classifier/catalog validation and reused across a
   bounded run, with no silent fallback.
5. `fresh-review-loop` and `append-only-journal` are exercised: every agentic fix is persisted,
   reread, gated, and independently re-reviewed.
6. `human-escalation` carries unresolved answers into the next iteration and never fabricates
   decisions.
7. `explicit-sr-consent` remains distinct from semantic cleanliness and requires an explicit phrase.
8. Deterministic current tools and future contracts validate paths, syntax, anchors, parity, hashes,
   traceability, registration, freshness, warnings, and handoff.
9. `text-summary-handoff` and `no-auto-execution` hold: a clean result offers choices and a
   validated handoff but never starts FEAT-13 or another workflow.
10. `deferred-browser` remains a visible boundary, not an accidentally implemented second UI.

This specification is the canonical authority for the implementation plan. It records design
intent and acceptance criteria; it does not certify implementation, human review, SR consent, or
repository-wide health.
