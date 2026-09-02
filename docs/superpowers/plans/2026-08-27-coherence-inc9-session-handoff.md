# Coherence Inc-9 Session Handoff — 2026-08-27

_Status: session stopped cleanly at a design boundary. Register landed + pushed; bootstrap
deliberately NOT built in this session (user: avoid context bloat). Next session picks up here._

## Where things stand (branch `feat/coherence-health-t1-t2`, pushed to origin)

Health-resolution T-1..T-3 are done and committed. Three commits in order:
- `8bac720` — T-2: 13 FEAT dossiers + bundle map (original feature set)
- `4a9de9f` — T-3: **decision-level register, 49 SRs** (SR-001..049) + FEAT→SR ownership + bundles + index
- `33efc33` — **FEAT-17 design: Clarify & Align phase added** (capture-only; implementation deferred)

`git rev-list origin/...left-right...` confirms local == origin (0/0). **Not merged to main** — merge
is the user's call ("yes push" happened; "merge" has not).

## Gate (from this branch)
- `requirement_quality` **49/49**, `verification_strategy` **49/49**, `decomposition_allocation` **17/17**
- `bundles` **17** (all load, 0 errors); **49 SRs** registered, all owned by a feature

## The register (why it's decision-grain)
17 features each own 1–7 SRs, one SR per spec decision. Built after the user challenged an earlier
1:1 feature-grain register as under-specified. Fidelity + **completeness** review (coverage baseline
enumerating toolset D1–D14, progressive D15–D19, agentic AIO-1..7, capture D-A..D-H) found and we
closed: SR-001 orphaned → bound to FEAT-001; added inbox, D-G persistent-backend, D-D produced-code
trace-edge, CI-as-obligation, and using-coherence-dispatcher SRs; SR-036↔SR-040 cross-referenced.

**SR-authoring consent gate:** the register is PROPOSED. T-4 (obligations + evidence wiring) drives
`executed_evidence`/`verification_strategy` from `0/N` → real, and `human_review` (still 0/0) needs
REAL human review entries — an agent cannot self-cert those.

## Agreed strategic direction (locked this session — do NOT reverse)

> **⚠ AMENDED 2026-09-01 by `docs/superpowers/specs/2026-09-01-coherence-product-definition.md`
> (D-P18).** Item 1 stands in intent — bootstrap still precedes *bulk* registration. It is
> narrowed in one respect: **exactly one feature (FEAT-001) is registered by hand first**, as the
> reference run that FEAT-17 then encodes. FEAT-17 cannot be built before it, because FEAT-17's
> own design composes SR authoring, feature registration and human consent as prerequisites —
> and those are unproven (0 evidence, 0 consent decisions, 0 marker bindings), with the
> `acceptance:` schema not yet existing. FEAT-17's acceptance test becomes: registering FEAT-002
> through bootstrap reproduces the shape FEAT-001 reached manually. Everything after FEAT-002
> registers through bootstrap, as this lock intended.

1. **Bootstrap-first.** Land register (done) → build FEAT-17 bootstrap front-door → then dogfood
   health-resolution THROUGH bootstrap. Do not reverse to finish T-4..T-6 before bootstrap.
2. **FEAT-17 gains a Clarify & Align phase** (design doc §3a.1): structured brainstorming →
   `spec.md` (authority) → **alignment-review subagent** checks spec vs user's verbatim answers →
   **escalate to user** on any misalignment (no-self-cert at the source). SRs/FEATs are **derived from
   `spec.md`**, never invented beside it; each derived SR keeps the human-approval consent gate.
3. **Human requirement-review/consent workbench is a real product gap.** Chat narration is not a
   surface. Candidate thin impl: **spawn an Obsidian vault** on the canonical `requirements/SR-*.md`
   (skills already has `obsidian`); vault is a projection, never a second source of truth. Add as an
   SR (likely under FEAT-010 console) + wire into T-4's `human_review` recording.

## Docs to read first (in order)
- `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md` (§5 feature table
  now locks **17** features; §4 decisions D-A..D-H)
- `docs/superpowers/plans/2026-08-27-coherence-execution-runbook.md` (governed per-task loop)
- `docs/superpowers/plans/2026-08-27-coherence-health-resolution-plan.md` (T-1..T-6)
- `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md` (§3a, §3a.1, §3c — Clarify
  & Align; keep the dependency ordering resolution: bootstrap template ships in the PLANNING tranche
  as the minimal FEAT-16 core, NOT blocked on the full FEAT-16 library)

## Skills to load
`coherence-health-resolution`, `pi-agent-factory`, `subagent-increment-workflow`,
`free-worker-dev-gate-pipeline`, `plan`, `obsidian` (for the review-vault idea).

## Review-process lesson (this session)
Requirement-register reviewers MUST include a **completeness/coverage baseline** (enumerate the spec
decisions; check every one has an SR), not just per-SR anchor fidelity. A fidelity-only review passes
even when the register is under-specified. Applied going forward.

## Live baseline quirk
The plan docs record stale numbers (e.g. plan→spec 44/78); run `coherence navigate health --json`
against main/branch for live truth. `coherence register` verbs are `new,index,status,show,bind,
defer,check,next` (NO `list`).
