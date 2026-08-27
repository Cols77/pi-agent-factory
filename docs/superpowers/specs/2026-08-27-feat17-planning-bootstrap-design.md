---
id: SPEC-FEAT-017-PLANNING-BOOTSTRAP
title: "FEAT-017 Planning Bootstrap Design"
status: draft
---

# FEAT-17 Planning-Bootstrap (PLANNING-BOOTSTRAP)

_Status: **design dossier** (2026-08-27). Owner: coherence bootstrap + plan pipeline (front door).
Defines coherence's built-in, recommended way to **start a new system**. Planning/design only.

_Parent: `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md` (FEAT-17
proposal). Companions: FEAT-16 (MODULAR-WORKFLOWS — the `bootstrap` template), FEAT-13
(GOVERNED-EXECUTION-DRIVER executes the plans this produces), health-resolution track (SR/feature
registration + human approval)._

---

## 1. Purpose

Answer the questions: **"How does the framework handle a new system? What's the built-in /
recommended planning workflow inside coherence?"** Today the answer is scattered and there is **no
first-class entry point**. This FEAT makes coherence **bootstrap a new project from a blank directory
to a governed first task** through a named, composed pipeline — the **front door** of the product.

It is distinct from execution: execution (FEAT-13, the driver) *runs plans*; PLANNING-BOOTSTRAP
*produces and registers* them (requirements → plan → tasks → feature registration).

---

## 2. Built-already vs genuinely-new (honest delta)

### Already built (machine exists — don't claim it's missing)
- **Plan → task decomposition:** `src/factory/orchestrator/plan_to_tasks.py`.
- **Bootstrap/init:** `src/factory` factory-init; specs `2026-08-06-factory-init-design.md`,
  `2026-08-06-requirement-doctor-design.md`.
- **Plan authoring:** the `plan` / writing-plans skill (author a plan markdown). Format question
  (bite-sized vs light) was settled in the review session: exact paths + verify per task; no
  paste-code micro-TDD unless executing.
- **Requirement/SR + feature registration + human consent:** the `coherence-health-resolution` skill /
  track (SR authoring is **human-approved**, mechanical links auto). This FEAT's prerequisite
  (FEAT-13 precondition).
- **Filesystem-first storage treaty:** `2026-08-27-filesystem-first-architecture-assessment.md` —
  plan/SR files are canonical versioned files; indexes derived; git = history.

### The honest delta (why it needs a FEAT)
- None of the above is wired into **one named, first-class planning pipeline**; there is **no
  `coherence plan` / `coherence bootstrap` front door** visible to a user; it is **absent from the
  feature list**.
- The **sequence/roles** (who authors the plan, who approves SRs, when plan_to_tasks runs, how it
  becomes FEAT-13 runnable) are not codified.

So FEAT-17 = **define + wire the pipeline** as a named workflow (FEAT-16 `bootstrap` template) reusing
all existing machinery — **NOT** building an LLM-only plan generator. The plan *format* is
deterministic files; an agent authors the text, but the pipeline, validation, and registration are code.

---

## 3. Proposed design

### 3a. The built-in pipeline (a `bootstrap` workflow under FEAT-16)

```
1.  coherence init <dir>                  # project skeleton + .factory/factory.yaml + requirements/
2.  CLARIFY & ALIGN (brainstorm user intent)   # NEW phase — see 3a.1
    ├─ structured brainstorming            (ask goal, scope, constraints, "what done means")
    ├─ capture -> spec.md                  (authority artifact: the "why/what" the user agreed)
    └─ alignment-review -> ESCALATE        (subagent checks spec.md vs user's verbatim answers/prompts;
                                            escalates to the user when it cannot confirm alignment)
3.  requirement capture                   # requirement-doctor; SR authoring derived from spec.md
    └─ HUMAN-APPROVED                       (consent gate — no bulk auto-adopt; per health-resolution)
4.  plan authoring                        # agent authors docs/superpowers/plans/*.md per plan skill
    └─ filesystem-first                     (canonical file; derived index; git history)
5.  plan_to_tasks                         # decompose plan → tasks (exists)
6.  feature + bundle registration         # health-resolution T-2/T-3 (SR/feature/bundle)
7.  first governed run                    # FEAT-13 runs task 1 through the standard workflow
```

#### 3a.1 The Clarify & Align phase (new)

Before any SR/feature is authored, bootstrap must **clarify what the user actually expects** and lock
it as a grounded authority — otherwise derived SRs are a wish list rather than a decision trace.

- **Structured brainstorming:** the agent runs an interactive clarification pass with the user covering
  goal, scope, constraints, non-goals, and "what done looks like" — the same question family this
  project's own governance uses.
- **Capture → `spec.md`:** the answers are distilled into one authoritative Markdown spec
  (`spec.md` — or `docs/superpowers/specs/<name>.md`) that states the agreed intent. This is the
  artifact the alignment-review validates and the later SR/feature derivation sources from.
- **Alignment review (`align`), then escalate:** a subagent reviews `spec.md` **against the user's
  verbatim answers and prompts**, confirming every captured point traces to a real user statement.
  If the reviewer cannot confirm alignment (a gap, an invented claim, or an un-backed statement), it
  **escalates to the user** — it does NOT auto-adopt. This is the same no-self-cert invariant as the
  SR consent gate, applied at the source: a spec is not trusted until a human confirms it matches
  what they said.
- **Output layering (per user decision, 2026-08-27):** brainstorming first yields `spec.md` (the seed);
  SRs and FEAT dossiers are **derived from `spec.md`** in the subsequent capture/registration steps,
  not invented alongside it. Each derived SR keeps the existing human-approval consent gate.

### 3b. Ordering
**PLANNING-BOOTSTRAP sequences EARLY** — it is the front door producing the plans FEAT-13 executes.
It should be planned *before* FEAT-13 is a sealed feature (or in the same tranche), and its SR/feature
registration depends on the health-resolution track.

**Suggested roadmap position (corrected for FEAT-16 dependency):**
`health-resolution → PLANNING-BOOTSTRAP → GOVERNED-EXECUTION-DRIVER → MODULAR-WORKFLOWS → validation/polish → console`.

**Sequencing resolution (from review, 2026-08-27):** B-02 consumes FEAT-16's `bootstrap` workflow
template, but the roadmap above ships MODULAR-WORKFLOWS AFTER PLANNING-BOOTSTRAP — a dependency
contradiction. **Resolution:** the `bootstrap` template is a *thin, self-contained* FEAT-16 template
that is delivered **in the PLANNING tranche** (it only needs the workflow model + a single template —
the minimal FEAT-16 core), while the full broader workflow *library* (standard/polish/coverage-audit/
safe-refactor/experiment) is delivered later by FEAT-16 itself. Equivalently, B-02's verify is
**conditional**: it runs once the `bootstrap` template exists, phased with FEAT-16's minimal core so
FEAT-17 is not a hard-block on the full FEAT-16.

Also call out: FEAT-17 delegates **feature/bundle registration to the health-resolution track** as the
single registration path (and, if FEAT-11 owns that registry, FEAT-11 is the same track / DELEGATES to
it — FEAT-17 never re-implements registration).

### 3c. Reuse vs new-LLM
- **Reuse:** `plan_to_tasks.py`, factory-init, requirement-doctor, `plan` skill, health-resolution
  SR registration, the `bootstrap` workflow template, and the existing trace/register/obligation
  readers and writers.
- **New (thin):** a `coherence plan` CLI composition plus the post-init `bootstrap` gate and progress surfacing (FEAT-12/10); a deterministic planning contract/gate that reads persisted artifacts, checks cross-artifact consistency, and emits an explicit downstream suggestion.

### 3d. Deterministic planning contract and gates (new)

FEAT-17 is not merely a prompt that happens to call `/plan`. It is a deterministic workflow whose
agent-authored text is constrained by durable artifacts and whose transitions are backend-gated.
The canonical artifact chain is:

```text
intent.json (verbatim prompt + clarified answers)
    -> spec.md (agreed authority)
    -> plan.md (implementation plan)
    -> tasks/T-*.md (decomposition)
    -> requirements/SR-*.md + docs/features/FEAT-*.md + bundles/*.json
```

Each planning run writes a schema-versioned run record under a derived/session location, containing
relative paths and hashes of the artifacts it checked. The source artifacts remain the authority;
the run record is evidence/projection and is never read as a replacement for them.

The `planning-consistency` gate runs before requirement adoption or downstream development. It is
pure over files and fails closed. It must verify, at minimum:

1. **Presence and parseability:** intent, spec, plan, and every referenced task/requirement/bundle
   exist, are UTF-8, and satisfy their required frontmatter/section grammar.
2. **Reference closure:** plan `spec_ref` resolves to the authority spec; generated tasks point to
   this plan; each declared FEAT-17 SR is present in the FEAT dossier and FEAT-017 bundle.
3. **Decision/constraint coverage:** every decision or constraint identifier declared in the intent
   is represented in the spec and plan; an unreferenced spec decision is a blocking finding.
4. **Plan/task parity:** every plan task has exactly one generated task identity, and no generated
   task points at another plan or an unknown plan section.
5. **Staleness:** hashes in the run record match the files being checked; changed inputs require a
   fresh planning run rather than a silently reused verdict.

The gate returns a stable JSON report with `schema`, `ok`, `run_id`, `artifacts`, `findings`, and
`next_actions`. A missing, malformed, contradictory, or stale input yields `ok: false` and a
non-zero CLI exit; it never degrades to a green result or silently invents a link.

### 3e. Intent alignment and human-review seam

The available deterministic alignment check compares each verbatim answer's explicit stable token
(or decision/constraint identifier) with the authority spec and records uncovered answers and
unsupported spec claims as findings. This is a mechanical coverage check, not semantic approval.
A future alignment-review agent may add a report, but the backend must still require a human decision
for semantic adoption; an agent cannot self-certify that the spec means what the user meant.

FEAT-17 therefore defines a stable review contract now:

```json
{
  "schema": 1,
  "run_id": "...",
  "decision": "approve|reject|defer",
  "reviewed_artifacts": ["<all canonical report artifact paths, sorted>"],
  "reviewer": "human",
  "reason": "...",
  "report_sha256": "<sha256 of the canonical report>"
}
```

The current slice may emit `review_required` and a deterministic path/command for this contract. The
reviewer surface writes the decision out-of-band; the planner never writes it. The decision must bind to
the exact canonical report digest and is accepted only through the project-root-bound reader capability,
so a report cannot be replaced under the same run id after review and a synthesized in-memory mapping
cannot emit a downstream suggestion. The separate `.factory/planning/<run-id>/requirement-consent.json`
contract must likewise explicitly approve the exact derived SR set before a downstream suggestion:

```json
{
  "schema": 1,
  "run_id": "...",
  "decision": "approve",
  "reviewer": "human",
  "reason": "...",
  "requirements": ["SR-043", "SR-044", "SR-050", "SR-051", "SR-052", "SR-053", "SR-054"]
}
```

The consent file is read-only input to this workflow; the planning agent never creates it.
The later SR human-review browsing/visualization feature (for example an Obsidian projection over `requirements/SR-*.md`) can consume and write this
same contract without changing the planning authority or gate.

### 3f. Downstream development suggestion

After `planning-consistency` passes and before any development command is started, FEAT-17 emits a
machine-readable suggestion such as:

```json
{
  "action": "suggest_downstream",
  "workflow": "standard",
  "plan": "docs/superpowers/plans/<name>.md",
  "tasks": ["T-001"],
  "prerequisites": ["human_review", "requirement_consent"],
  "starts_automatically": false
}
```

The suggestion is an inspectable boundary, not an implicit call. A host may present a button/command
for FEAT-13 later, but only a separate explicit user action starts governed development. If the
human-review surface is deferred or no consent is recorded, the suggestion remains blocked/advisory
and states exactly which prerequisite is missing.

> **Implementation note (2026-08-27):** The first deterministic slice is now landed: schema-versioned intent/spec/plan/task checking, atomic planning-run evidence, strict external human-review validation bound to the report digest, read-only FEAT-017 dossier/bundle/source closure plus exact-set requirement consent, a suggestion-only downstream handoff, the `coherence plan` CLI (including the thin post-init `bootstrap --decompose` composition), and `/plan` host guidance. SR authoring/adoption and the human browsing/visualization projection remain delegated or deferred; the existing register is the single registration path.

---

## 4. Scope — ONE tracer-bullet through every layer

Vertical: substrate (SR/plan files) → factory (init, plan_to_tasks) → coherence (register /
requirement-doctor) → host (CLI `coherence plan/init`) → governed driver (FEAT-13 `--workflow
bootstrap` → standard run).

- **B-01 — `coherence init` front-door.** Reuse factory-init. **Verify:** `coherence init tmp-proj`
  produces a valid skeleton + `factory.yaml` + empty `requirements/`. **Acceptance:** a blank dir is
  coherence-ready (filesystem-first).
- **B-02 — `bootstrap` workflow template (FEAT-16).** **Verify (phased):** `coherence run bootstrap`
  walks init→requirements→plan→plan_to_tasks, steps compose end-to-end — runs once the minimal FEAT-16
  `bootstrap` template (delivered in the PLANNING tranche, per §3b) exists; NOT blocked on the full
  FEAT-16 library. **Acceptance:** the pipeline is a named, inspectable workflow.
- **B-03 — Requirement + plan authoring + consent.** Reuse requirement-doctor + plan skill; SR authoring
  is human-approved. **Verify:** authored SRs require explicit approve (no bulk auto-adopt); a plan
  file lands under `docs/superpowers/plans/`. **Acceptance:** the human consent gate is enforced (can't
  be bypassed by an agent).
- **B-04 — plan_to_tasks + registration + first governed run.** **Verify:** a 3-task plan decomposes →
  registers feature/bundle (health-resolution) → task 1 runs via `standard` workflow (FEAT-13).
  **Acceptance:** a NEW system reaches a governed, traced first task.

---

## 4a. Deterministic workflow acceptance matrix

The implementation is accepted only when the following gates are executable and produce inspectable evidence:

| Gate | Deterministic check | Blocking result |
|---|---|---|
| `planning-input` | intent/spec/plan exist, are UTF-8, and parse under their declared schemas | missing or malformed source artifact |
| `planning-references` | `spec_ref`, task `source_plan`/`source_task`, FEAT-017 SR membership, bundle membership, and requirement source links resolve exactly | dangling, duplicate, or contradictory reference |
| `planning-parity` | every plan task maps to exactly one generated task and every generated task maps back to this plan | missing, duplicate, or foreign task mapping |
| `planning-alignment` | stable intent answer identifiers are covered by both spec and plan; unsupported explicit `claim:<id>` tokens are reported | uncovered answer or unsupported claim |
| `planning-freshness` | persisted report hashes match current source artifacts | changed source since report |
| `planning-human-review` | strict decision file is written by the human review surface, names exactly the reviewed artifacts, and binds the report digest | absent, malformed, stale, rejected, or self-authored approval |

| `planning-requirement-consent` | FEAT-017 dossier, bundle, requirement source links, and external exact-set consent are current | missing registration, source drift, or absent/malformed consent |

The first implementation ships the source checks, task freshness, registration/consent closure, and
the stable file contract for human review; the browsing/visualization surface remains deferred.
Human browsing/visualization is a deferred projection over that contract, not a reason to weaken the
blocking semantics. All gates return stable JSON findings; no gate invokes a model or silently assumes
an approval.

## 4b. Downstream handoff boundary

When all deterministic planning gates pass and a valid human decision exists, the planning workflow
emits `suggest_downstream` for FEAT-13's governed development workflow. It includes the selected plan,
current task ids, required prerequisites, and `starts_automatically: false`. Planning never invokes
FEAT-13 itself. This boundary lets a later host render an explicit action while preserving the
separation between planning (FEAT-17), workflow interpretation (FEAT-16), gates (FEAT-14), and
execution (FEAT-13).

## 5. Files likely to change (planned)

- **New:** `coherence plan` deterministic planning gate/composition, `bootstrap` workflow template,
  schema-versioned intent/run/review contracts, `docs/superpowers/plans/` scaffolding, progress
  surfacing (FEAT-12/10).
- **Reuse:** `plan_to_tasks.py`, factory-init, requirement-doctor, `plan` skill, health-resolution
  registration/gate, existing trace/register/obligation readers and writers.
- **Modify:** the thin `/plan` host seed so it instructs the author to use the canonical `/plan-gate`
  argv adapter rather than reimplementing checks. The existing `/plan` command remains the session/prompt
  launcher; automatic post-session callback wiring is explicitly deferred until the host exposes a safe
  completion hook.
- **Deferred:** SR human-review browsing/visualization (including an Obsidian projection) writes the
  stable review-decision contract later; FEAT-17 must not fabricate that approval today.

## 6. Risks & open questions

- **Must reuse, not re-implement** — the trap is shipping an LLM-only "plan generator." The plan
  FORMAT is deterministic files; the pipeline/validation/registration is code. Keep the agent as the
  author of text, not the authority.
- **Deterministic cross-consistency is a blocking gate** — the authority spec, plan, generated tasks,
  and derived register artifacts must agree on paths, decision identifiers, task parity, and hashes;
  missing or contradictory evidence fails closed.
- **Intent alignment is two-tiered** — deterministic identifier/coverage checks are available now;
  semantic alignment and SR adoption still require a human decision. No model or host may self-certify
  the meaning of the user's request.
- **Downstream development is an explicit suggestion only** — a passing planning run emits a
  `suggest_downstream` contract for FEAT-13, but never starts it automatically.
- **Plan-format decision** — honor the review session's verdict (light version: exact paths + verify
  per task, no paste-code micro-TDD) so plan authoring is cheap and execution-obvious.
- **Human-approval must not be bypassable** — this is coherence's no-self-cert core. The `bootstrap`
  path must force the SR consent gate.
- **Ordering/sequencing** — PLANNING-BOOTSTRAP depends on health-resolution (SR/feature machinery) and
  produces input to FEAT-13. Sequence before sealing FEAT-13.
- **Scope vs FEAT-13** — FEAT-13 *executes* plans; FEAT-17 *creates+registers* them. Keep distinct.

## 7. Feature completion / acceptance (NOT a task DoD)

> Note on levels: "Definition of done" is **task-scoped** — `dod_met` is a field on
> `TaskResult` (`src/factory/orchestrator/types.py`), the gate a *task* passes. A feature is an
> aggregate: it is complete only when the tasks satisfying its SRs each pass their own DoD and the
> feature's SR/consent/registration invariants are satisfied. These completion criteria are that
> feature-level aggregate.

### Feature completion criteria

`coherence bootstrap <dir>` (or `coherence plan`) takes a blank directory to a **governed first task**:
skeleton → human-approved SRs → plan file → `plan_to_tasks` decomposition → feature/bundle
registration (health-resolution) → first `standard`-workflow run via FEAT-13 — all filesystem-first,
reusing existing machinery, with the SR human-approval consent gate enforced.

The full blank-directory front door described above remains a later composition: this increment exposes the deterministic post-init planning slice and its fail-closed gates. It does not invoke factory-init, author/adopt SRs, create feature/bundle registration, or start FEAT-13. A later increment must close those steps before claiming the aggregate criterion.
