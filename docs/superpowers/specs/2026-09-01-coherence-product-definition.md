---
id: coherence-product-definition
title: "Coherence — Product Definition Specification"
status: draft
---

# Coherence — Product Definition Specification

> **Status:** draft for review · **Date:** 2026-09-01
> **Supersedes:** the 2026-08-26 HLR merge-subset lock, D2 (Obsidian out of scope), and
> S22 §13's import-direction claim.
>
> **Authority:** this is the parent product specification. It defines *what Coherence is*, its
> boundary, its doctrine, its feature map and its system acceptance. It does not restate the
> design specs; those remain normative for *how* each capability works. Where this document and
> an earlier spec disagree, this document governs and names the supersession explicitly (D15).
>
> Repo name is `pi-agent-factory`; the product identity is **Coherence**.

---

## 1. What Coherence is

An assurance substrate for agentic software engineering, built on one doctrine:

> **Code enumerates, holds state, proves on disk and verifies. The model makes exactly one
> judgement per step. The agent proposes, the substrate proves, a human decides.**

The failure mode it exists to defeat is *"an AI said it's done."* Its value is not that agents
write code; it is that **every claim about a system is backed by on-disk evidence with
provenance, freshness and an auditable trail** — and that a claim without that backing cannot
be made to look green.

Coherence spans two halves of one product:

- **The assurance spine** — traceability, obligations, evidence, freshness, nonconformance,
  health. What makes a claim provable.
- **The engineering context** — the typed V-cycle graph, goals, simulation evidence, context
  delta, durable memory. What makes a system *recoverable* by a human working at agent speed.

They are one product because the second is worthless without the first (unverified context is
narration) and the first is invisible without the second (proof nobody can navigate is not used).

---

## 2. Product boundary

**D-P1. One product, one register.** Coherence comprises the assurance spine *and* the
engineering-context layer. Every capability shipped in `src/` has an owning feature and an
owning requirement.

This supersedes the 2026-08-26 lock, which held that the engineering-context HLRs "target the
physical-AI drone product, not the coherence toolset" and were therefore normative rationale
rather than requirements.

*Reason for supersession:* the premise is contradicted by the code. Engineering-context
Increments 1–8 did not ship into the consumer project; they shipped into this repository —
`coherence/goals/`, `coherence/simulation/`, `coherence/presentation/`, `factory/delta/`,
`factory/memory/`. The lock conflated *who a requirement is about* (a developer working on a
drone) with *which codebase implements it* (this one). The consequence was roughly 40
capabilities of working code with no owning requirement — the same unbacked-claim failure the
product exists to prevent, one level up.

**D-P2. Registration is not investment.** Everything in `src/` is registered. How hard it must
be proven is set by `profile`; whether it is built further is set by release scope. Scope is
never expressed by omission from the register.

**D-P3. Consumer registers are independent.** A consuming project (PAAD) keeps its own
requirements, features and goals. Coherence supplies the engine, contracts and schemas; it does
not impose its ID scheme or its register on consumers.

---

## 3. Doctrine — the invariant set

Three invariant sets existed in the corpus (concept doc §3 objectives, programme §12 invariants,
S22 §3.3 minimal kernel) with overlapping and differently-worded rules. They are reconciled here
into one set, owned by **FEAT-000 SYSTEM-DOCTRINE** as `domain: constraint` requirements.

| # | Invariant |
|---|---|
| I-01 | **No self-certification.** The producer of work is never the sole authority that certifies it. |
| I-02 | **Evidence before claim.** No requirement is validated by implementation existence, passing compilation, or model assertion — only by recorded, schema-valid evidence. |
| I-03 | **Missing evidence is reported, never inferred.** No resolver may invent absent provenance. |
| I-04 | **Missing provenance degrades authority.** It never implies freshness. |
| I-05 | **No silent stale-as-current.** An artifact with unresolved dependency divergence is never presented as current. |
| I-06 | **No automatic path to valid.** A suspect or invalid governed edge is restored only by a recorded human decision. |
| I-07 | **Authoritative artifacts are never auto-rewritten.** Staleness routes to the owning writer. |
| I-08 | **Only declared, deterministic relations are authoritative.** No LLM-inferred edges; embeddings are never the traceability mechanism. |
| I-09 | **Projections cannot change truth.** No projection alters an outcome, hides invalidity, or claims freshness. LLM narrative never overrides deterministic state. |
| I-10 | **Derived state is rebuildable.** Deleting every index and rebuilding from canonical artifacts loses no engineering information. |
| I-11 | **History is preserved.** Refresh never erases the record; current and historical truth stay distinguishable. |
| I-12 | **One judgement per step.** Code enumerates, holds state, proves and verifies; the model makes exactly one judgement. |
| I-13 | **Bypass containment.** No change becomes validated state without traversing the gate chain; unauthorized modification degrades affected edges rather than passing. |
| I-14 | **One canonical state.** Human and agent surfaces agree; no surface is a second source of truth. |
| I-15 | **Replaceability.** Coding models, agents and hosts remain replaceable. |
| I-16 | **Performance is a global constraint,** not a feature. (Supersedes SR-047's placement under FEAT-009; restates D-G.) |

---

## 4. Architecture

### 4.1 Layers

```
factory (execution)  →  coherence (assurance)  →  substrate (shared models)
```

One direction. No cycles. `substrate` imports nothing above it.

**Current state: violated.** `coherence → factory` in 9 files, `factory → coherence` in 82 —
a live dependency cycle held together by function-local imports. Recorded as NC-A (§9). The
cause is that the engineering-context modules (`memory/`, `delta/`, `freshness/`,
`evidence.records`) sit under `factory` though they are assurance concerns; the fix is
relocation, not redesign.

This supersedes S22 §13's claim that "`coherence` may import `factory`, never the reverse,"
which was introduced to justify a single import of two pure string helpers.

### 4.2 Hosts

Python computes; hosts render. A host never reimplements workflow, gates or traceability.
Pi is the primary host; Hermes and any MCP client are peers over the same contracts.

### 4.3 Execution — governed transition surface

The host drives dispatch, worktrees, cards and scheduling. Coherence holds authority:

```
host → coherence.next_node(run)         returns the only legal next node
host → coherence.claim_node(node)       returns a Coherence-created worktree
host    (dispatches its own agent, in that worktree)
host → coherence.run_gate(node)         Coherence executes and writes the envelope
host → coherence.request_finalize(run)  refused unless obligations are satisfied
```

Coherence executes gates itself and writes evidence; the host never reports gate outcomes. This
is SR-028 as already written. Coherence does **not** build an orchestrator, per-host agent
backends, or a scheduler — those are host capabilities and are adopted.

Trust is bounded per resolution class: `repeatable_policy` evidence is independently re-run by
CI, so host honesty is irrelevant; `authoritative_gate` requires a human decision record that no
host can produce alone; `provenance_blocked` refuses to close at all.

### 4.4 Enforcement ladder

A host cannot be prevented from writing to the filesystem. The enforceable guarantee is that
**no change becomes validated state without traversing the gate chain** (I-13).

| Layer | Mechanism | Bypassable |
|---|---|---|
| L1 | Write-scope guard (`pi-ext/scope-guard`) | yes — host may decline to load it |
| L2 | Coherence-created worktree; finalize controls the merge | no, for landing |
| L3 | Repo pre-commit / pre-push hooks | yes — `--no-verify` |
| L4 | CI + branch protection (`ci_verification`, SR-048) | **no** |
| — | Fingerprint → suspect-edge degradation (SR-013) | detection, always on |

---

## 5. Feature map

28 features. **Profile** sets assurance depth; **Release** sets build investment; **Posture**
records the build/adopt verdict. Registration is unconditional.

### Assurance spine

| ID | Feature | Profile | Release | Posture |
|---|---|---|---|---|
| FEAT-000 | SYSTEM-DOCTRINE *(new)* | high_assurance | v1 | build |
| FEAT-001 | REQ-TRACEABILITY | high_assurance | v1 | build |
| FEAT-002 | PROGRESSIVE-ASSURANCE | high_assurance | v1 | build |
| FEAT-003 | NONCONFORMANCE-CLOSURE | high_assurance | v1 | build |
| FEAT-004 | NAVIGATION-UNDERSTANDING | prototype | v1 | build |
| FEAT-005 | HEALTH-STATUS | high_assurance | v1 | build |
| FEAT-006 | EVIDENCE-PROVENANCE | high_assurance | v1 | build |
| FEAT-007 | MEASURE-AUDIT | high_assurance | v1 | build |
| FEAT-026 | IMPACT-AND-REFRESH *(new)* | high_assurance | v1 | build |

### Engineering context

| ID | Feature | Profile | Release | Posture |
|---|---|---|---|---|
| FEAT-008 | SIMULATION-EVIDENCE *(goals split out)* | prototype | v1 | build |
| FEAT-021 | GOAL-LIFECYCLE *(new)* | prototype | v1 | build binding; adopt metric storage |
| FEAT-022 | CONTEXT-RECONSTRUCTION *(new)* | prototype | v1 | build |
| FEAT-024 | CONTEXT-DELTA *(new)* | prototype | v1 | build thin over git |
| FEAT-025 | DURABLE-MEMORY *(new)* | prototype | v1 | **reduce** — provenance + conflict only |
| FEAT-027 | TEACHING-COURSE *(new)* | prototype | v1 | **reduce** — `course check` only; content via skills (D8) |
| FEAT-023 | PRESENTATION-ROUTER *(new)* | prototype | v1 | **reduce** — policy only; adapters are platform primitives |

### Execution and workflow

| ID | Feature | Profile | Release | Posture |
|---|---|---|---|---|
| FEAT-011 | WORKFLOW-ENFORCEMENT | high_assurance | v1 | build |
| FEAT-014 | VALIDATION-GATES | high_assurance | v1 | build |
| FEAT-015 | POLISH-FLOW | prototype | v1 | build |
| FEAT-016 | MODULAR-WORKFLOWS | prototype | v1 (minimal) | build only the bootstrap template |
| FEAT-017 | PLANNING-BOOTSTRAP | high_assurance | v1 | build — the front door |
| FEAT-013 | GOVERNED-EXECUTION-CONTRACT *(rescoped)* | high_assurance | v1 | **reduce** — transition verbs + worktree/merge authority; no driver |
| FEAT-018 | EXECUTION-PLAN-COMPILER | prototype | v2 | build |
| FEAT-020 | KANBAN-MAPPING-OPTIMIZATION | prototype | v2 | build only after baseline measurement |

### Hosts and surfaces

| ID | Feature | Profile | Release | Posture |
|---|---|---|---|---|
| FEAT-009 | HOST-ADAPTERS | high_assurance | v1 (Pi) / v2 (MCP, Hermes) | adopt |
| FEAT-019 | HOST-CONFORMANCE | high_assurance | v1 | build — makes the contract testable |
| FEAT-010 | COHERENCE-CONSOLE | prototype | v2 | challenge: static projection vs bespoke server |
| FEAT-012 | LIVE-RUN-PROGRESS | prototype | v2 | adopt host streaming where possible |

**Note on the v1 line.** v1 was initially set as *implemented surface + bootstrap front door*.
The enforcement decision (D-P13, full ladder including worktree and merge authority) pulls the
reduced FEAT-013 into v1, because L2 is the only layer that *prevents* rather than *detects*
bypass; FEAT-019 conformance is what proves the contract is satisfiable. The wider v1 is
accepted (D-P17). v1 is therefore: **implemented surface + bootstrap front door + the governed
transition surface with its conformance suite.**

---

## 6. Requirements model

- **Grain.** SRs stay at decision grain with stable flat IDs (`SR-###`). Testable detail lives
  in an `acceptance:` array inside the SR, each entry addressable (`SR-025/AC-3`) and carrying
  its own verification binding (harness, `@pytest.mark.sr` marker, or `manual: human_review`).
- **IDs are stable.** No renumbering, no domain prefixes. Human meaning comes from the label
  index (`normalize_ref`), not from the ID string.
- **Two human gates, not one.** *Authoring consent* (SR-044) approves that a spec paragraph is
  a given SR — required for every SR. *Verification review* (the `human_review` obligation)
  reviews evidence — `not_applicable` under `prototype`, `blocking` under `high_assurance`.
- **Consent surface.** The existing gate `DecisionFile` (`accept | reject | defer`, reason
  required on reject/defer, `review_after` on defer). One gate protocol; the consent queue is
  `coherence register` plus the computed inbox. Chat narration is not a surface.
- **`proposed` is a legitimate terminal state** for a requirement outside current release scope.
- **Obsidian is a read-only navigable projection** over canonical Markdown via `[[wikilinks]]`.
  Never a write surface, never a consent surface, never a second source of truth. Supersedes
  D2's blanket exclusion.
- **Wikilink mirrors are generated,** not authored: derived from canonical frontmatter and the
  trace graph, fingerprinted, marked *derived — do not edit*, with a check that fails on
  divergence. FEAT-006's `![[SR-019]]` embed is exactly the drift this prevents.
- **`requirement_quality` gains a real criterion:** every SR has at least one acceptance
  criterion with a bound verification method. It currently returns `len(sr_nodes)` and is
  structurally incapable of failing (NC-B).

---

## 7. System acceptance

Per-SR criteria are *verification*. The following are *validation* — end-to-end, exercised
against PAAD as the reference consumer. They are adopted from the Engineering Context concept
document §36 and give `SR validated` a real denominator for the first time.

| ID | Criterion |
|---|---|
| AC-01 | Feature reconstruction: one operation returns intent, requirements, design, implementation, verification status, active goals, latest evidence and recent changes. |
| AC-02 | V-cycle navigation from a requirement to parent/child requirements, design, implementation, tests and simulation evidence. |
| AC-03 | Goal creation persists a goal artifact bound to a requirement. |
| AC-04 | Goal evaluation transitions to REACHED automatically on qualifying evidence. |
| AC-05 | A reached goal retains measured value, threshold, run, commit, experiment and evidence location. |
| AC-06 | Transition to REACHED explicitly notifies the developer. |
| AC-07 | Later contrary evidence transitions REACHED → REGRESSED with notification. |
| AC-08 | A significant simulation failure can be opened at or near the relevant event. |
| AC-09 | A requirement's place in the system can be shown without manual artifact search. |
| AC-10 | Rebuildability: deleting the derived index and rebuilding from canonical artifacts reconstructs the same graph. |

PAAD is the reference consumer and the v1 acceptance vehicle. It **does not** satisfy Release B's
external-value gate, which requires a non-author, non-project end-to-end run.

---

## 8. Decision ledger

| ID | Decision | Supersedes |
|---|---|---|
| D-P1 | One product, one register — assurance spine + engineering context | 2026-08-26 HLR merge-subset lock |
| D-P2 | Scope by profile and release, never by omission from the register | — |
| D-P3 | v1 = implemented surface + bootstrap front door | — |
| D-P4 | Decision-grain SRs with `acceptance:` criteria inside | — |
| D-P5 | Flat stable IDs; meaning comes from the label index | — |
| D-P6 | Consent through the gate `DecisionFile`; one gate protocol | — |
| D-P7 | Obsidian is a read-only navigable projection | D2 |
| D-P8 | Wikilink mirrors are generated, fingerprinted, check-gated | — |
| D-P9 | Cross-cutting constraints live in FEAT-000 as `domain: constraint` | SR-047's placement; D-G restated as I-16 |
| D-P10 | 28 fine-grained features; FEAT is the unit of profile, bundle and dossier | — |
| D-P11 | Proof layer, not whole toolset — adopt surfaces, build the graph and the proof | the locked 17-feature "whole toolset" shape |
| D-P12 | FEAT-013 is a governed MCP transition surface, not a driver | FEAT-013 design dossier |
| D-P13 | Full enforcement ladder including Coherence-owned worktree and merge authority | — |
| D-P14 | Vertical per-feature discharge; no horizontal bulk declaration | the horizontal authoring that produced 0/55 |
| D-P15 | `factory → coherence → substrate`, one direction, no cycles | S22 §13 |
| D-P16 | PAAD is the reference consumer; AC-01..AC-10 are system validation | — |
| D-P17 | Wider v1 accepted: implemented surface + bootstrap front door + governed transition surface + conformance | D-P3 (widened, not reversed) |
| D-P18 | Exactly one feature (FEAT-001) is registered by hand as the reference run; FEAT-017 encodes it; every later feature registers through FEAT-017 | **amends** the 2026-08-27 "bootstrap-first, do not reverse" lock — see note below |

**Note on D-P18 and the bootstrap-first lock.** The 2026-08-27 session handoff locked
"bootstrap-first… do not reverse to finish T-4..T-6 before bootstrap." That lock targeted the
health-resolution track's *horizontal* evidence wiring across all 49 SRs before any front door
existed — a concern this specification shares (D-P14). It does not reach a single vertical slice
whose purpose is to *define* the process FEAT-017 will encode. D-P18 therefore amends rather than
reverses it: bootstrap still precedes bulk registration, and only one feature is ever
hand-registered.

FEAT-017 cannot be built first because its own design lists SR authoring, feature registration
and human consent as already-built prerequisites it *composes*. Those are precisely what is
unproven (0 evidence, 0 consent decisions, 0 marker bindings) and the `acceptance:` schema
(D-P4) does not yet exist. Building bootstrap first would automate a pipeline nobody has run,
and would make bootstrap defects indistinguishable from requirements-model defects.

---

## 9. Known nonconformances

| ID | Finding | Severity |
|---|---|---|
| NC-A | Dependency cycle: `coherence → factory` (9 files) and `factory → coherence` (82), held together by function-local imports. Fix by relocating `memory/`, `delta/`, `freshness/`, `evidence.records` and the two pure shell helpers; invert `PiAgentBackend` through `substrate/agents/`. Extend the AST forbidden-import test to all three layers. | blocking |
| NC-B | `requirement_quality` returns `len(sr_nodes)` and cannot fail. `verification_strategy` counts compiler-generated `resolve_cmd` strings and cannot fail. Two of eleven health dimensions report green while measuring nothing. | blocking |
| NC-C | FEAT-018/019/020 carry `requirements: []` and no bundle; `decomposition_allocation` reads 17/20. | required |
| NC-D | FEAT-006 uses `![[SR-019]]` (embed) instead of `[[SR-019]]`, silently breaking navigation. Symptom of hand-maintained mirrors. | advisory |
| NC-E | `coherence-increment-implementation-analysis.md` reports Increments 5–8 as unshipped; they are on `main`. Plan checkboxes disagree with code. | required |
| NC-F | CLI usage strings still print `factory.goals` / `factory-presentation` under `coherence` entry points. | advisory |

**Live baseline (2026-09-01):** `SR satisfied 0/55`, `SR validated 0/0`, `executed_evidence 0/55`,
`human_review 0/0`, `implementation_trace 2/24`, health 39%; all 55 SRs `proposed`, all
`checksum: null`.

---

## 10. Discharge sequence

Vertical, one feature at a time. Each slice: author SRs and acceptance criteria → human
authoring consent → bind existing tests to criteria → execute evidence → `human_review` where
the profile requires it → re-run health.

**Run it by hand once, then encode it** (D-P18). Exactly one feature is registered manually, to
establish the process by example; FEAT-017 then automates that example; every feature after it
registers *through* FEAT-017. This preserves the 2026-08-27 bootstrap-first intent — dogfood the
register through the product — while giving FEAT-017 a known-good specification to encode rather
than an imagined one.

1. **FEAT-001 REQ-TRACEABILITY — the reference run.** Fully implemented, tests exist, criteria
   are concrete, and it is the foundation every other feature's evidence rests on. A retrofit,
   so the machinery can be judged against a known-good answer. Its steps are recorded as
   FEAT-017's input specification.
2. **FEAT-017 PLANNING-BOOTSTRAP** — encodes the reference run as the built-in pipeline.
   **Acceptance:** registering FEAT-002 through bootstrap produces the same registration shape
   FEAT-001 reached by hand.
3. **FEAT-000 SYSTEM-DOCTRINE** — through bootstrap; closes NC-A and NC-B.
4. **FEAT-002, FEAT-006, FEAT-026** — the assurance spine at `high_assurance`, through bootstrap.
5. Remaining v1 features at their declared profiles, through bootstrap.

Features outside current release scope stay `proposed`. That is a truthful state, not a gap.
