# Coherence-Project Health-Resolution Plan

_Date: 2026-08-27._ **Planning only — no execution, no code changes, no git pushes.**
_Status: draft plan, input to the Inc-9 programme. This is the **health-resolution track**
(execution order step 1): before building new surfaces, the coherence repo itself must
become demonstrably healthy by genuinely walking its own requirement→obligation→evidence
spine. It does not declare health; it builds the register + evidence and proves each SR.

_Related docs:_
- Parent: `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md` (§5 features, §4 D-A…D-H).
- Skill: `coherence-health-resolution` (procedure; auto-vs-human split).
- Console surface it feeds: `docs/superpowers/specs/2026-08-27-coherence-console-webui-design.md`.

---

## 1. Objective

Bring `coherence navigate health` on `C:/coding/pi-agent-factory` to maximum by **genuinely
registering what exists**. The baseline (verified 2026-08-26):

```
worst dimension executed_evidence (0/1)
  requirement_quality: 1/1      decomposition_allocation: 0/0
  implementation_trace: 2/24    verification_strategy: 1/1
  executed_evidence: 0/1        validation_scenarios: 0/1
  evidence_freshness: 0/0       suspect_relationships: 1/1
  nonconformance_closure: 1/1   deferrals_waivers: 3/62
  human_review: 0/0
  task->plan: 22/23 (exempt 1)  task->SR: 1/23 (exempt 1)
  plan->spec: 44/78             SR satisfied: 0/1   SR validated: 0/0
bundles: 0   unbundled (158)
register check: "SR-001: no measurement, task, or deferral accounts for this requirement"
```

Core problem: **the register is almost empty.** 1 SR (bound to HLR-02), 0 bundles,
158 unbundled artifacts, most evidence dimensions blank because there is almost no registered
content to evaluate. The toolset is healthy-engineered, but its *own* project has never been
the dogfood subject.

## 2. Guiding principles (locked)

1. **Auto vs human split** (the `coherence-health-resolution` skill core):
   - **Mechanical/declared links auto-refined, non-human:** bundling, `task->SR`, `plan->spec`,
     `task->plan` forwarding, opening `NC-*` for genuinely-missing items.
   - **Semantic SR-authoring MUST keep a human consent gate** — "this spec paragraph *is* SR-X"
     is a judgment that cannot be auto-certified (an LLM can be confidently wrong).
   - **The health-max claim MUST include a real `human_review`** (dim `human_review: 0/0` at
     baseline). Declaring "green" without it is the self-cert the toolset forbids.
- **Build from the real specs, not a wish list.** The requirements register mirrors what the
  coherence specs *actually guarantee* (toolset D1–D15, progressive-assurance 2B, agentic-I/O
  D11-13, §5/§6). This is what makes "what is implemented" testable.
- **Reuse existing executables.** The repo already has a real factory test suite + gates
  (`factory.yaml` `unit`/`full`, `ruff`, `pyright`, the ~182-run suite). Evidence = hooking these
  into per-SR `verification_result` obligations and **running them**, not inventing parallel gates.
- **Verify landed state against `main`, never trust a handoff doc.**
- **Windows:** native tools use `C:/...` paths, not `/c/...`.

## 3. Actors / responsibilities

| Role | Does |
|---|---|
| Dev worker(s) | build the register from specs, declare features/bundles, propose SRs |
| Human (user) | approves each authored SR (consent gate), does real `human_review` where the profile requires it |
| Reviewer agent(s) | independent spec-compliance + code-quality review of the *authoring* not the claim |
| Coherence backend | compiles obligations, runs gates, computes health — never "health by declaration" |

The final gate is **driven by the toolset itself** (`coherence register check`,
`coherence navigate health`, obligation `_blocking_for`), not by prose.

## 4. Execution order (tracer-bullet discipline)

Each task is a **thin end-to-end cut**: substrate models → coherence reads → factory gates →
the health surface. Tasks build on the previous state; no horizontal "declare all SRs" bulk.

### Task T-1 — Health snapshot formalization
- Capture the exact baseline counts above as the official health baseline.
- **Verify:** `coherence navigate health --json` parity to the recorded numbers.
- **Acceptance:** health output matches recorded baseline to within drift; dims enumerated.

### Task T-2 — Feature declaration + bundle map skeleton
- Declare the FEAT-1..13 dossiers (from the session capture §5) as `feat:` records with owning
  SRs + satisfying code paths + `verification_result` + `human_review` slot.
- Create the bundle map: every feature belongs to a `bundle`.
- **Files (planned):** `docs/features/FEAT-*.md` (FEAT-1..13 dossiers — count locked at **13** per capture §5/§8,
  incl. FEAT-13 GOVERNED-EXECUTION-DRIVER; the bundle map under `bundles/`), SR records under `requirements/`.
- **Verify (exact):** `coherence navigate health --json` → `decomposition_allocation` = `13/13` (one green slot per
  FEAT that carries a `contains` edge) and coverage reports `bundles: 13`; every declared feature has a bundle.
- **Acceptance:** 13 features declared → `decomposition_allocation` green; 0 logged-unbundled for
  declared features.

### Task T-3 — SR authoring from the real specs (HUMAN-APPROVED)
- Turn toolset D1-D15 + 2B progressive-assurance + agentic-I/O D11-13 + §5/§6 wording into SR
  nodes, each `source:` pointing at the exact spec `§`/decision (e.g. `.../2026-08-18-coherence-toolset-design.md#D-11`),
  `domain`, `upstream`.
- **This is the step-by-step artifact-sufficiency case.** For each SR, attach its satisfying
  code paths (codemap `satisfies`/`implements`), its obligation compile, and a one-line "why this
  SR is satisfied by that artifact". Show the reviewer human-readable, no shortcuts.
- **Consent gate:** the USER approves each authored SR (or explicitly declines). No bulk auto-adopt.
- **Files (planned):** `requirements/SR-*.md` (new, one per spec-derived requirement).
- **Verify (exact):** `requirements/` populated; `coherence register check --json` shows a list of the
  authored SRs in a reviewable doc (e.g. `coherence register list --pending` renders the consent queue);
  every SR has `source:` pointing at a spec `#D-*`.
- **Acceptance:** every authored SR has an explicit approve/decline; none auto-certified.

### Task T-4 — Obligation compile + evidence wiring
- For each approved SR, compile obligations (requiredness ∈ {not_applicable, advisory, required,
  blocking}) and hook the **existing** gate commands into per-SR `verification_result`.
- Run the gates once; record the **manifests**.
- **Verify:** `coherence register check` in the SR now shows a measurement/task/deferral account;
  obligations compiled; manifests on disk.
- **Acceptance:** no "no measurement, task, or deferral" pending for the seeded register.

### Task T-5 — Declare the dangling-link closure
- Forward-link repairs: `task->SR` (target 23), `plan->spec` (target 78), `task->plan` (target 23)
  — declare each missing forwarded link as a **doc/declaration task**, NOT a code task.
- Open `NC-*` for genuinely-missing-for-real items, tying to a `gh-issue` via `corrects`.
- **Files (planned):** the forward-link declarations (doc/declaration-task records), `NC-*` records
  (+ `corrects -> gh-issue`).
- **Verify (exact):** `coherence navigate health --json | jq '{task_sr: .dimensions["task->SR"], plan_spec: .dimensions["plan->spec"], task_plan: .dimensions["task->plan"]}'`
  shows the target counts (23/78/23) with no unbundled drift.
- **Acceptance:** the once-red `task->SR`, `plan->spec`, `task->plan` dims green.

### Task T-6 — Evidence close + `human_review`
- Re-run the full suite once both register + gates are wired; record final manifests.
- Real `human_review` entries for each feature (the user consents/rejects the SR + evidence).
- **Files (planned):** verification manifests (evidence store), `human_review` records.
- **Verify (exact):** `coherence navigate health --json` → previously-red dims green, with
  `executed_evidence`, `human_review`, `validation_scenarios` accounted; inspect a manifest is on disk
  for a required/blocking SR (e.g. `evidence/manifests/<sr>.json`).
- **Acceptance:** re-run health; the dims green; inspectable, evidence-backed.

## 7. Testing & gate

- Each task's verify command runs against **main**.
- The health claim is checked **programmatically** by the toolset, then **human-reviewed**.
- No green declared by prose; green is shown by running `coherence navigate health` to reflect
  the new register/obligation/evidence state.

## 8. Files likely to change

- `requirements/SR-*.md` (new), `requirements/features/*.md` (new FEAT dossiers), the bundle map
  under `.factory/`.
- Forward-link declarations; new `NC-*` records; evidence `manifests/`; `human_review` records.
- `.factory/factory.yaml` (if gate wiring for evidence needs adjusting) — read/reuse priority.

## 9. Risks & open questions

- **Spec prose is ambiguous** — turning some spec paragraphs into SRs may be blocked on interpretation;
  flag and route to the user via the consent gate (never auto-resolve).
- **Existing gate commands may not map cleanly to per-SR obligations** — some `factory.yaml` commands
  are suite-level, not per-SR; the per-SR `verification_result` may need a mapping/subset step.
- **`human_review` dim is 0/0** — it cannot go green without real human entries; an agent cannot bypass
  this (self-cert), so the plan's completion depends on the user doing the review pass.
- **Baseline drift between authoring** — re-run `coherence navigate health` at each task start to avoid
  chasing a stale snapshot.

## 10. Out of scope (this plan)

- No code implementations; no new backend surfaces. Purely register, features, obligations,
  evidence-wiring, link-closure, and human-review for the coherence project itself.
- Rust/WASM (D-G, roadmap-only). No virtual-execution/simulation content.

## 11. Definition of done

`coherence navigate health` exits with the recorded red dimensions now green **and** the green is
accountable: each green dim is backed by (a) a real executed verification_config manifest, (b) a
real (auto) obligation for required/blocking, and (c) a real `human_review` record. Both the
register and the evidence chain are on disk, linked, and reviewers in the review node saw the
artifact-sufficiency per SR.