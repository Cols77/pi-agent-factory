# Coherence Inc-9 Programme — Session Capture (2026-08-26)

> **Status:** interim capture for joint review. This records verified findings and
> **locked decisions** from the 2026-08-26 working session so the next steps (settle
> the feature set, then brainstorm the health-resolution / console / dossier / teach
> implementations) start from one shared, grounded baseline. Nothing here is executed
> code — no git operations, no implementation. It is a decisions + agenda document.
>
> **Authority note:** this capture is **not** itself a coherence spec, an execution map,
> or an SR. It is the parent record that will drive the creation of those. The normative
> coherence authority remains the existing specs
> (`2026-08-18-coherence-toolset-design.md`, `2026-08-22-coherence-progressive-assurance-design.md`,
> `2026-08-20-coherence-agentic-io-design.md`) and the
> `2026-08-20-coherence-programme-execution-map.md`.

---

## 1. Purpose of the capture

Frozen record of a multi-part working session with these threads:

1. Deep review of the coherence toolset's tools/workflows/UI against spec and plans
   (4 parallel DeepSeek review agents) → defects found and the "Inc-9" new-surface idea.
2. Claim: confirm whether the `00-high-level-requirements.md` HLRs (older, 2026-08-12
   Engineering-Context/Goal-Driven v2 program) correspond to the coherence spec.
3. Decide the Inc-9 feature set, increment mechanics, and host strategy (Pi / Hermes / MCP).
4. Plan (not execute) the coherence-project own-health diagnosis + resolution.
5. Add performance (Python slowness → Rust/WASM) + live-progress-UI requirements.

This document fixes the outcomes of 1–5 so the next session starts oriented.

---

## 2. Verified ground truth (from this session, not handoff)

### 2.1 The coherence project's own health is NOT healthy (verified live, 2026-08-26)

Running `coherence navigate health` on `C:/coding/pi-agent-factory` (main) yielded:

```
health: worst dimension executed_evidence (0/1)
  requirement_quality: 1/1
  decomposition_allocation: 0/0
  implementation_trace: 2/24
  verification_strategy: 1/1
  executed_evidence: 0/1
  validation_scenarios: 0/1
  evidence_freshness: 0/0
  suspect_relationships: 1/1
  nonconformance_closure: 1/1
  deferrals_waivers: 3/62
  human_review: 0/0
  task->plan: 22/23 (exempt 1)
  task->SR: 1/23 (exempt 1)
  plan->spec: 44/78
  SR satisfied: 0/1
  SR validated: 0/0
bundles: 0
unbundled (158): sr:SR-001, task:T-001.., spec:docs/superpowers/specs/...
```

`coherence register check --project-root .` fails:

```
requirements closure: 1 requirement(s) evaluated
1 pending, 0 measured, 0 declined
  ! SR-001: no measurement, task, or deferral accounts for this requirement
```

The sole SR is `requirements/SR-001.md` whose `source:` is
`docs/superpowers/plans/engineering-context/00-high-level-requirements.md#HLR-02`.

So the coherence project has **exactly one SR, no bundles, 158 unbundled artifacts**,
and most health dimensions are red because there is almost no registered content.
The health-resolution task is real and concrete (see §5 agenda).

### 2.2 The HLR set is the OLDER spec (confirmed)

- `docs/superpowers/plans/engineering-context/00-high-level-requirements.md` —
  dated **2026-08-12**, the **Engineering Context / V-Cycle / Goal-Driven Validation v2**
  program. HLR-01…09 describe deterministic orchestration, end-to-end traceability,
  evidence-backed acceptance, no self-certification, mental-model, proactive surfacing,
  failure records, metric `/goal` engineering, artifact freshness. **It targets the
  physical-AI drone product**, not the coherence toolset.
- The coherence specs (`2026-08-18` toolset, `2026-08-22` progressive-assurance,
  `2026-08-20` agentic I/O) **never cite HLR-0x** (grep confirmed). Only SR-001 borrows
  HLR-02 as its origin.
> **⚠ SUPERSEDED 2026-09-01 by `2026-09-01-coherence-product-definition.md` (D-P1).** The lock
> below rests on a premise the code contradicts: engineering-context Increments 1–8 shipped into
> *this* repository (`coherence/goals/`, `coherence/simulation/`, `coherence/presentation/`,
> `factory/delta/`, `factory/memory/`), not into the drone product. The lock conflated *who a
> requirement is about* with *which codebase implements it*, leaving ~40 capabilities of working
> code with no owning requirement. The HLRs are now registered as requirements of Coherence.

- **Decision (locked, SUPERSEDED):** the HLRs are the normative *why / origin* (retained as one
  operator note under the coherence spec), **not** a separate feature list. The "how"
  is the coherence feature set. The two-spec confusion is resolved by merging HLR → subset.

### 2.3 Coherence tooling is present and working in both repos (verified)

- `coherence` importable + CLI runs in `pi-agent-factory` and in the consumer project
  `C:/coding/paad` (Physical AI / agentic drone).
- CLI group surface present: `course, trace, register, doctor, navigate, presentation,
  goals, simulation, audit, measurement, status, route, focus, explain`.
- `coherence status --json`, `coherence route --json` produce live canonical contracts
  (`StatusSnapshot`, `RouteMatch`).
- Pi extension `pi-ext/factory-watch/src/index.ts` (wear "") registers 18 commands and
  provides UI primitives (`ctx.ui.custom` full TUI, `select/confirm/editor`,
  `spawnInteractive`, `MissionControlDashboard`, browser servers).
- Hermes feasibility already exists as `pi-agent-factory` skill
  `references/hermes-port.md` — concludes the Hermes adapter is **low-friction**, thin-host.

### 2.4 Tooling for planning the Inc-9 slices is sufficient (verified)

The three new slices (console, dossier browser, explain/teach) can be specified/planned
directly against the existing coherence spine — no prerequisite slice required.

---

## 3. Defects found by the four review agents (increment-5 surface)

Four parallel DeepSeek review agents audited the current toolset. Consolidated defects
(the "Inc-9" motivation):

1. **`/using-coherence` is a non-interactive text dump.** `coherence-command.ts` only
   `ctx.ui.notify(...)`s the ranked status menu. Every `resolve_cmd` prints as inert shell
   text. **Nothing is clickable/runnable/learnable.** The full TUI/UI machinery exists but
   is unused. (Grade: 3/10 for a beginner.)
2. **The surface uses undocumented language:** menu prints `failing_gate`, `stale_audit`,
   intent names (`CLOSE_GAPS`, `RECOVER`) verbatim, but `coherence explain` only knows
   `navigate/vocabulary.py` keys → **0 hits** for those terms. Live dead-end:
   `pending_inbox`'s resolve re-runs the command the user just ran.
3. **Reach gap:** the extension reaches only **9 of 14** coherence CLI groups. `doctor`,
   `register`, `course`, `focus`, `explain` have **no Pi surface**. Where health/obligations
   are shown (mission-control), resolve commands render as text; only `resume_cmd` is live.
4. **Spec-truth debt:** increments 2B/2C/6B/8 still show `[ ]` in plan files although code
   shipped — a reader trusting the checkboxes concludes they were never built.
5. **Health dim-8 is a proxy** (`REQ_STALE`) not the real `edge_validity` classifier wiring.
   `rerun_allowed` dead in production; no `coherence inbox` CLI group (spec §5);
   `coherence explain NC-*` fails.
6. **~82% of what was specified is honestly implemented**, and the rest is
   truth-maintenance + wiring, not new architecture.

These drive the Inc-9 new-surface features (console / dossier / teach) and the
health-resolution task.

---

## 4. Locked design decisions (joint, this session)

### D-A. Host architecture: **Pi host primary + Hermes as a thin MCP/viewer adapter**

- **Pi** (`pi-ext/factory-watch`) remains the **primary** interactive host and the
  determinism surface today.
- **Hermes** is the **second** surface, reached via an **MCP server** (`coherence-mcp`)
  importing the existing Python packages; plus Hermes skills / desktop plugin for the
  browser-server surfaces. **NEVER re-implements Python** — thin adapter.
- Rationale: preserves the **"agent replaceable / host replaceable"** invariant (HLR-01 /
  D1), which is the product's differentiator. Neither build-a-tool, nor **fork-hermes**
  — both were considered and rejected in this session. Noted: build-a-tool and fork-hermes
  both marry the product to one execution loop; both contradict replaceability.

### D-B — Enforcement lives in the Python factory, NOT in any host loop

- Deterministic workflow orchestration, context injection, and validation-gate
  enforcement are owned by the **Python factory/orchestrator + obligation compiler**
  (`_blocking_for`, `Obligation.resolve_cmd`, `NC-*` → task → `gh-issue`).
- Hermes/Pi surface the resulting canonical JSON and state transitions; they **never
  re-implement** the workflow, context packing, or gate.
- "Through MCP you don't enforce more — you **inherit enforcement**": MCP exposes the
  same canonical reads + the same backend-gated transition verbs; the register/obligation
  tests and `_blocking_for` programmatically reject any un-backed agent claim.

### D-C — Tool interruptions (e.g., human review) over MCP / from Hermes

- Interruptions are **ambient blocking checkpoint states**, re-entering as a controlled
  event, NOT mid-loop exceptions the agent must catch.
- A run advancing to `human-review` (already real in `node-registry.json`) reads as
  "blocked at human-review + review URL / decision prompt". Review happens out-of-band
  (browser review-server) or in-band via an MCP decision verb writing the same
  review-decision file. Until the decision file is written, the run stays blocked.
- **Option (agreed acceptable):** human-review may be **disabled** as a hard gate
  (profile setting) — it is not a switching-the-loop-off, just making the gate advisory
  / auto-pass under a chosen policy.

### D-D — Traceability is integrated INTO the code (first-class)

- Code artifacts produced by a slice carry the **codemap satisfies/implements edges** to
  their owning SR.
- Those edges feed the same **SR test-marker + obligation + register-check** mechanism
  (already wired into `coherence register check` gating + `coherence runs` `_blocking_for`).
- Consequence: traceability is **100% agent-reviewed** (in the review node) AND
  **validated program** (by the register/obligation/test-marker gates). A slice is not
  healthy unless its code's trace links are complete.

### D-F — Tracer-bullet increments (thin vertical slices through every layer)

- Each Inc-9 increment is **one thin, end-to-end path** cutting through EACH layer
  (substrate → coherence → factory → Pi adapter → Hermes adapter → shared console page).
- **Not** horizontal-layer building. Matches the "tracer bullets" algorithm the user
  explicitly requested.
- Combined with D-D: an increment is only "done + healthy" when it composes end-to-end
  AND its code is trace-linked and gate-validated.

### D-G — Performance requirement = **global constraint**, not a feature

- The dominant latency is **per-call subprocess spawn** (`uv run python -m coherence …`
  booting the interpreter) — NOT Python compute.
- **Global constraint (locked):** all coherence reads must be servable from a
  **persistent backend daemon** (no per-call spawn). The MCP adapter **is** that daemon
  (boot once, hold imports + cached trace graph, serve ~100 ms instead of multi-second).
- **Tracked optional roadmap (NOT near-term):** hand-port the hot deterministic core
  (graph extraction, obligation direct map, codemap, freshness/checksum) to **Rust via
  `pyo3`**, later **WASM** for the browser. **NOT a full rewrite** — preserves the one
  parser / one authority invariant. Optional, temp.

### D-H — Better execution progress UI = a REAL new feature (LIVE-RUN-PROGRESS)

- The run's live state (which of the 7 nodes is active, accumulated artifacts, log tails,
  ETA) must be **streamed**, not shown after the fact.
- Backend publishes node transitions + artifact accumulation as a stream; the shared
  console subscribes (SSE). Pi TUI + Hermes browser render the same stream. Reuses
  `ObservationEnvelope` / checkpoint.

---

## 5. Agreed feature set (provisional target — to be settled before implementation brainstorm)

Provisional fixed set of features we build to **maximum health** (one FEAT bundle + SR +
trace + evidence each). **PENDING final settlement** (next step).

| # | FEAT (area) | Type | Owns |
|---|---|---|---|
| 1 | REQ-TRACEABILITY | existing | trace, register, codemap-cluster, KB |
| 2 | PROGRESSIVE-ASSURANCE | existing | profiles, obligation compiler, manifests |
| 3 | NONCONFORMANCE-CLOSURE | existing | `NC-*` / `FR-*`, `corrects`, deferrals/waivers, suspect-edge review |
| 4 | NAVIGATION-UNDERSTANDING | existing | navigate, vocabulary, coverage |
| 5 | HEALTH-STATUS | existing | status/route/focus/explain, health vector |
| 6 | EVIDENCE-PROVENANCE | existing | agentic-I/O, fingerprint, freshness/reconcile |
| 7 | MEASURE-AUDIT | existing | measurement/audit/coverage-review |
| 8 | GOALS-SIMULATION | existing | goals, metrics, simulation, scenarios |
| 9 | HOST-ADAPTERS | existing→new | Pi extension + Hermes MCP + Hermes desktop plugin (the adapter railway) |
| 10 | COHERENCE-CONSOLE | new | shared browser dashboard (health + dossier + teach) |
| 11 | WORKFLOW-ENFORCEMENT | new | deterministic run loop, context injection, validation-gate binding, human-review interrupt |
| 12 | LIVE-RUN-PROGRESS | new | streamed node-progress + artifact subscription console |
| 13 | **GOVERNED-EXECUTION-DRIVER** | **new (locked 2026-08-27)** | host driver that plugs free/Hermes subagents + worktrees into the existing factory node pipeline as worker nodes; reviewer swarm + fixer-until-silent; MCP + backend-gated. Design: `2026-08-27-feat13-governed-execution-driver-design.md` |
| 14 | VALIDATION-GATES | new (locked 2026-08-27) | first-class gate taxonomy: unit / agentic code review / human review / sim regression / human-visualization playground; named composable contract (much already built: ConfigGateRunner, run_review, HumanReviewGate, sim gate, polish/playground). Make the taxonomy visible + composable. |
| 15 | POLISH-FLOW | new (locked 2026-08-27) | iterative refinement loop (find → isolate worktree → dev → fast-forward → re-gate) with human exploratory/playground face. Already implemented (`src/factory/polish/`); promote to a maintained roadmap feature + surface it. |
| 16 | MODULAR-WORKFLOWS | new (locked 2026-08-27) | workflow abstraction: a `Workflow` = ordered nodes + per-node gate selection, declared in `factory.yaml`, with PRE-DEFINED templates (standard, polish, coverage-audit, safe-refactor). THE real gap — the runner node sequence is currently hardcoded. Re-cast, not rewrite (node fns reusable). |
| 17 | PLANNING-BOOTSTRAP | new (locked 2026-08-27) | defined built-in planning pipeline for starting a new system: init → requirement capture → plan authoring → plan_to_tasks → health-resolution → task run. Machinery exists (`plan_to_tasks.py`, `factory-init`, `requirement-doctor`, `plan` skill) but is not a first-class workflow & absent from the list. |

- Freshness / HLR nine = normative "why", not a separate feature list (merged subset).
- **Feature count LOCKED at 17 as of 2026-08-27** (was 12; FEAT-13 added 27 Aug, FEAT-14..17 added 27 Aug). Three reconciliation calls made:
  1. FEAT-9 (HOST-ADAPTERS) and FEAT-10 (CONSOLE) stay distinct but tightly couple —
     FEAT-9 owns *host adaptation* (the pipe: Pi + MCP + plugin), FEAT-10 owns the
     *console UI itself* (the picture).
  2. FEAT-11 (WORKFLOW-ENFORCEMENT) is the **load-bearing new one** — it makes the
     MCP/Hermes path *honest*; it must land early enough to carry 9/10, else the
     console is decoration.
  3. Perf = **global constraint** (D-G), NOT a feature — locked.
- **Execution order agreed:** first prove FEAT-1..8 healthy (the health-resolution
  track), then build `11 → 9 → 12 → 10` (enforcement before console); dossier and
  teach are **surfaces of FEAT-10**, not standalone features.

---

## 6. Capability / host-consistency note (the "synergy" the user asked for)

- **ONE canonical interactive console** (browser dashboard served by the existing
  coherence browser server pattern). Both Pi and Hermes are thin adapters.
- Pi extension → native browser-open + status widget + `/using-coherence` TUI shell that
  points at the same page.
- Hermes MCP → same tools + a plugin rendering the **same** dashboard in the preview pane.
- This avoids two implementations of the interactive surface. FEAT-9 (HOST-ADAPTERS) and
  FEAT-10 (CONSOLE) are synergistic, not redundant.

---

## 7. Agenda / next steps (the user's requested order)

1. **(DONE) Confirm the HLR set:** older spec, merge to coherence subset. Locked.
2. **(DONE) Verify tooling:** sufficient; no prerequisite slice. Locked.
3. **"settle the features":** agree the final fixed FEAT set (from §5) — decide
   FEAT-batch and any fold/adjust of the provisional 12.
4. **Brainstorm implementation** of the health-resolution plan, the console, the
   feature-dossier, and the teach surfaces (impl angle, how each will happen).
5. Write the Inc-9 slice plans (one increment per slice, tracer-bullet through all layers)
   and the health-resolution plan as spec/plan documents.
6. **Verify on the PAAD project that the new product works** (user will test it themselves);
   we do NOT run code, do NOT. code review, do NOT execute during this planning phase.

*deliverables so far:* ground truth (§2), the four review files
(`%LOCALAPPDATA%\Temp\coherence-ux-review\`), locked decisions (§4), provisional FEAT list (§5),
and the console web-skin design spec
(`docs/superpowers/specs/2026-08-27-coherence-console-webui-design.md`, §5/§6,
linked into this trace).

---

## 8. Open questions (to settle in the session)

- ✅ Feature count LOCKED at 12 (settled).
- Console context: NOT Pi-only — **two skins over one canonical source** (Pi = native
  TUI skin; Hermes = the shared *browser* console in the preview pane / webview). MCP = tools/reads, not the picture. (settled, Part 1)
- Refine skill renamed **`coherence-health-resolution`** — names the thing it restores
  (coherence health / the requirement register), not a vague "build". Skill auto-vs-human
  split encoded (Part 2). Created 2026-08-26.
- Free-worker pipeline skill renamed **`free-worker-dev-gate-pipeline`** (Part 3).
- MissionControlDashboard confirmed a real-but-incomplete precedent: list-only machinery
  proven, but the console needs a genuine new inspector/run-action + web skin (Part 3).
- Web console browser design (reuse `/system` navigator + `popular-web-designs` tokens) —
  **landed as a spec** at `docs/superpowers/specs/2026-08-27-coherence-console-webui-design.md`
  (feasibility + approach; author wrote it directly after two failed delegated attempts —
  a hard lesson: a subagent's "done-without-output" is not trustable, verify the file
  myself). (Part 4)
- **TEACH (Part 5) DEFERRED — recorded, not discussed**: reuse `grill-understanding` +
  `visual-explainer` + `coherence course`-grammar-checker as the deep tier; improve
  content DEPTH via **glossary-fetch (hover a term → definition from `vocabulary.py`)** and
  **topic-decomposition** (never generate "the whole coherence project" as one course;
  the agent currently gets overwhelmed). Parked until health-resolution + console land.
- Whether `human-review` is hard or profile-disabled by default for the console host.
- Perf contract: (D13) global constraint locked; Rust/WASM roadmap timing (deferred).
- PRIMARY open item for next session: **write the Inc-9 slice plans** (Console, Dossier,
  Teach) + the **health-resolution plan**, one increment per slice (tracer-bullet).
- ✅ **[2026-08-27] Plans drafted** (planning only, trace-linked from this capture):
  - Health-resolution: `docs/superpowers/plans/2026-08-27-coherence-health-resolution-plan.md`
  - Console slice: `docs/superpowers/plans/2026-08-27-coherence-inc9-console-slice-plan.md`
  - Dossier slice: `docs/superpowers/plans/2026-08-27-coherence-inc9-dossier-slice-plan.md`
  - Console web-skin spec: `docs/superpowers/specs/2026-08-27-coherence-console-webui-design.md`
  - Execution runbook (new-session boot + governed loop): `docs/superpowers/plans/2026-08-27-coherence-execution-runbook.md`
- ✅ **[2026-08-27] FEAT-13 LOCKED — GOVERNED-EXECUTION-DRIVER.** Design dossier:
  `docs/superpowers/specs/2026-08-27-feat13-governed-execution-driver-design.md`.
  Key grounding: the deterministic node pipeline + gates + human-review + evidence + git **already
  exist** in the Python factory (`orchestrator/nodes.py`, `/backends.py` AgentBackend protocol,
  `/runner.py`). FEAT-13 does NOT rebuild enforcement — it adds (a) a Hermes-side `AgentBackend`
  implementation (free subagents), (b) a `WorktreeDriver` (`coherence run-governed`), (c) MCP tools
  (shared with FEAT-9) + console stream. Swarming reviewers = driver-level fan-out, not a new node type.
- 📌 **[2026-08-27] Acknowledged gap — session entry point (NOT yet a feature).** No "get started /
  start-here" menu for a NEW work session exists. `/using-coherence` is a STATUS probe menu (worst-first
  `resolve_cmd`s), not an onboarding menu; the ~14 pi commands (`/plan`, `/polish`, `/goal`,
  `/factory-*`, `/mission-control`, `/system`, …) are reachable by name but not grouped by goal. This is
  materially different from FEAT-10 (console), FEAT-17 (system bootstrap), and `/using-coherence`
  (status): it's a session-granularity entry/orientation layer (thin host adapter; goal-driven list of
  available actions for a new session). Left general for now — to refine into a scoped FEAT (or fold
  under HOST-ADAPTERS/console) later.