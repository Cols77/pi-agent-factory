# FEAT-017 Missing Requirements Authoring Plan

> **For Hermes:** Execute only after explicit human approval of the proposed SR boundaries and statements. Use the project’s SR-authoring consent workflow; do not silently create or adopt requirements.

**Goal:** Add the missing FEAT-017 requirements for planning/implementation gate separation, durable progressive intent capture, cross-artifact coherence review, implementation-time link maintenance, and planning-gate enforcement without duplicating existing SR-035/SR-036/SR-049/SR-050 responsibilities.

**Architecture:** FEAT-017 owns the planning front door and its sequencing invariants. FEAT-014 owns the gate taxonomy and contracts; FEAT-016 owns workflow interpretation; FEAT-013 owns governed implementation execution; SR-049/SR-050 own produced-code traceability and implementation-time relation review. New FEAT-017 SRs should define the planning contract and invoke those owners rather than re-implementing them.

**Source design:** [[docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design|FEAT-017 planning bootstrap design]]  
**Feature:** [[FEAT-017]] PLANNING-BOOTSTRAP  
**Existing related SRs:** [[SR-035]], [[SR-036]], [[SR-049]], [[SR-050]]

---

## Current gap and non-duplication decision

The FEAT-017 dossier currently allocates only SR-043 and SR-044. Its design mentions brainstorming, alignment review, graph validation, and a governed handoff, but does not make the five missing concerns independently testable.

Do **not** duplicate the existing implementation-traceability requirements:

- Reuse [[SR-049]] for gate validation of produced-code trace declarations.
- Reuse [[SR-050]] for implementation-time production/validation relations and per-SR structural/evidence/fidelity review.
- Add a FEAT-017 planning obligation that implementation tasks must schedule those updates and reviews; do not restate their full implementation contract.
- Reuse [[SR-035]]/[[SR-036]] for gate taxonomy and workflow gate binding; add only the FEAT-017 planning-stage and handoff behavior.

## Proposed SR set

The following are **proposed statements for approval**, not yet authored requirements.

### SR-051 — Planning/implementation gate boundary

**Statement:** The system shall keep planning assurance separate from governed implementation validation: during FEAT-017 planning it may inspect, compile, and validate workflow and gate contracts, but it shall not execute implementation validation gates or claim implementation evidence; implementation gates may execute only after an approved execution contract is handed to governed execution.

**Source anchor:** `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md#1` and `#3a` (planning is distinct from execution; handoff occurs after proposal validation).

**Why distinct:** Existing FEAT-017 prose states a boundary but does not prohibit gate execution or unsupported evidence claims.

**Expected verification:** A planning-only run cannot invoke implementation gate resolvers or produce implementation gate evidence; a post-handoff governed run can invoke the selected gate pack.

### SR-052 — Durable progressive intent capture

**Statement:** The system shall persist progressive brainstorming intent as an append-only, provenance-bearing capture stream and materialized snapshot that preserve the initial request, each accepted answer, unresolved questions, and capture status across interruption and resume, while keeping review decisions, SR consent, waivers, and execution state outside the intent artifact.

**Source anchor:** `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md#3a.1` (structured brainstorming and verbatim answers), supplemented by the FEAT-017 planning steering reference on progressive intent persistence.

**Why distinct:** The current design requires `spec.md` and alignment review but does not require durable incremental capture, resume, provenance, or failure-safe materialization.

**Expected verification:** Each accepted capture event is journaled with run identity and provenance; snapshot writes are atomic; a failed materialization leaves the prior good snapshot; resume reconstructs the capture state without mixing in consent or review decisions.

### SR-053 — Cross-artifact coherence review

**Statement:** The system shall perform a blocking cross-artifact coherence review before planning handoff that checks consistency and coverage across captured intent, specification, system requirements, feature and bundle registration, implementation plan, generated tasks, source and validation artifact relations, and the selected workflow/gate proposal, reporting missing, dangling, duplicate, weak, overstated, and contradictory links with cited findings.

**Source anchor:** `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md#3a`, `#3a.1`, and `#4` (artifact sequence, alignment review, graph validation, and handoff).

**Why distinct:** Alignment review is only spec-versus-user; graph validation is primarily orchestration structure. Neither is an end-to-end semantic coherence review.

**Expected verification:** Fixtures with omitted SR coverage, incorrect task allocation, dangling source/test links, contradictory plan/spec claims, weak or overstated implementation links, and gate/proposal mismatches fail or escalate according to policy; a coherent fixture passes with a machine-readable report.

### SR-054 — Plan-task trace-maintenance obligation

**Statement:** The system shall require every FEAT-017 implementation task that changes production or validation artifacts to identify its affected system requirements and to include completion work for updating their canonical implementation/validation relations and mirrored documentation links, with completion blocked until those declarations are reconciled with the task and review outputs.

**Source anchor:** `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md#4` and `#5`, plus `docs/superpowers/specs/2026-08-31-sr-code-validation-traceability-design.md#canonical-relations`.

**Why distinct:** SR-050 defines the relation/review contract; this SR makes the planning workflow generate and enforce the corresponding task obligation.

**Expected verification:** Generated FEAT-017 tasks contain affected SRs, source/test relation-update work, and review/gate steps; a task changing production or validation code without those updates cannot complete.

### SR-055 — Planning gate-pack compilation and enforcement

**Statement:** The system shall compile an explicit versioned planning gate pack for each FEAT-017 workflow, including stage, requiredness, resolver, dependencies, expected evidence, and failure behavior, and shall block proposal handoff when a required planning gate is missing, failed, unevidenced, silently downgraded, or not executed as required by the pack.

**Source anchor:** `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md#3a`, `#4`, and `#5`, with gate contract semantics from `docs/superpowers/specs/2026-08-27-feat14-validation-gates-design.md#3.1` and `#3.4`.

**Why distinct:** FEAT-014 owns gate contracts and FEAT-016 owns workflow interpretation; FEAT-017 still needs a requirement that its planning workflow actually consumes and enforces the applicable compiled pack before handoff.

**Expected verification:** A planning workflow with an omitted, failed, unevidenced, or downgraded required planning gate cannot hand off; the expanded gate ledger is inspectable and the resolver/evidence records are persisted.

## Authoring and allocation sequence

### Task 1: Confirm the requirement boundaries

Review SR-051 through SR-055 against SR-035, SR-036, SR-049, and SR-050. Resolve whether SR-054 should remain a distinct FEAT-017 planning obligation or be folded into the implementation-traceability plan as an explicit FEAT-017 consumer obligation. Preserve separate ownership for planning behavior versus implementation trace mechanics.

**Decision gate:** Human approval of each final SR statement, source anchor, and ownership boundary.

### Task 2: Author approved SR files

Create the approved `requirements/SR-05*.md` files using the established frontmatter fields:

- `id`
- `title`
- `statement`
- `domain: behavioral`
- `upstream`
- `source`

Use exact spec anchors and a Markdown `Source:` citation. Keep all new SRs proposed until the project’s explicit SR consent action approves them.

### Task 3: Update the requirement index

Add the authored IDs to `requirements/index.json` with the repository’s current proposed/checksum convention. Verify deterministic ordering and valid JSON.

### Task 4: Allocate FEAT-017 membership

Update `docs/features/FEAT-017.md` and `bundles/FEAT-017.json` to include the approved new SRs. Also record the intentional cross-feature dependencies on SR-035/SR-036/SR-049/SR-050 without duplicating ownership.

### Task 5: Expand the FEAT-017 implementation plan

Create or update the canonical FEAT-017 implementation plan so each work item names:

- the SR(s) it satisfies;
- source/design anchors;
- production files and symbols;
- validation files and test nodes;
- canonical relations and Obsidian links to update;
- planning versus implementation gates;
- evidence outputs;
- cross-artifact review and handoff checks.

### Task 6: Bind requirements to implementation tasks

After the plan is accepted and decomposed, every generated task must carry an explicit SR justification. Link implementation tasks to the relevant SRs while retaining SR-049/SR-050 as the authority for concrete production/test relation semantics.

### Task 7: Validate the resulting register

Run the Coherence checks after authoring and allocation:

```bash
uv run coherence navigate brief --scope feat:FEAT-017 --json
uv run coherence navigate brief --scope bundle:FEAT-017 --json
uv run coherence navigate health --repo-root . --json
uv run coherence trace status --project-root .
uv run coherence register check --project-root .
uv run coherence navigate membership --gate --repo-root . --json
```

Expected FEAT-017-specific outcomes:

- the bundle lists every approved FEAT-017 SR;
- no approved FEAT-017 SR is reported as missing a binding once implementation tasks exist;
- the FEAT-017 plan and tasks have source/SR links;
- planning-gate and cross-artifact review obligations are visible in the plan/task graph;
- no implementation gate evidence is claimed by planning-only stages.

## Risks and open decisions

- **SR duplication:** SR-054 must not become a second SR-050. Keep it about task generation and completion obligations, not relation schema or fidelity-review mechanics.
- **Gate ambiguity:** explicitly distinguish contract compilation/validation from executing implementation gates.
- **Planning gate scope:** decide which checks are planning gates versus FEAT-018 graph validation versus FEAT-13 implementation gates.
- **Human authority:** alignment review, SR consent, and unresolved semantic fidelity findings must remain human-bound where required; an agent verdict cannot close them.
- **Existing dirty worktree:** do not overwrite unrelated modified or untracked files while applying the approved SR changes.

## Acceptance criteria for this SR-authoring slice

- Human-approved SR statements exist for every missing FEAT-017 concern, or an explicit decision records why an existing SR is reused.
- FEAT-017 membership and its canonical task plan are trace-linked.
- The implementation plan distinguishes planning assurance from governed implementation validation.
- The plan systematically requires implementation tasks to update source/validation/SR/documentation relations.
- The plan requires a cross-artifact coherence review and an explicit planning gate pack.
- Coherence register, trace, membership, and health outputs are rerun and recorded; no claim of implementation completion is made from structural links alone.
