# Engineering Context / V-Cycle / Goal-Driven Validation — Program Plan (v2 of pi-agent-factory)

**Status:** Draft for written review (no implementation until approval questions are answered)
**Source spec:** `C:/coding/Engineering Context, V-Cycle Navigation and Goal-Driven Validation.md`
**Target use-case:** `C:/coding/cool_physical_ai_project` (Physical Agentic AI Drone)
**Execution model:** sub-agent driven (`pi -p` developer/reviewer agents), decisions escalated
**Date:** 2026-08-11

---

## 1. Purpose

Make engineering intent, V-cycle traceability, implementation state, verification
evidence and measurable goals *immediately recoverable and navigable* for both a
human and a coding agent, around a **feature-centric vertical slice** through the
V-cycle. This is **v2 of `pi-agent-factory`**: v1 already provides the deterministic
substrate (traces, evidence, requirements, system navigator, browser projection, Pi
extension). v2 adds the **engineering-context / goal-driven** layer on top, reusing
every v1 primitive that already does the job instead of rebuilding it.

### 1a. Program requirements

This program is governed by
[`00-high-level-requirements.md`](./00-high-level-requirements.md).

The increment plans are implementation decompositions of those high-level requirements.
Where an increment plan and a program-level HLR conflict, the HLR is authoritative until the
conflict is explicitly resolved through a program decision.

In particular, the program now treats **artifact freshness as a maintained system property**, not
merely stale-state detection:

```text
detect change
→ determine impacted dependency closure
→ invalidate dependent authority
→ select refresh policy
→ recompute / regenerate / rerun / route semantic repair
→ reconcile
→ report freshness closure
```

This does **not** mean blindly auto-editing every stale artifact.

The refresh policy distinguishes:

- authoritative engineering contracts;
- implementation;
- validation evidence;
- generated engineering knowledge;
- derived projections/indexes.

Authoritative upstream intent is protected from silent mutation, while safely reproducible downstream
artifacts SHOULD be restored automatically.

### Concurrency constraint — SCC SP-B

At the time this requirement update was authored, **SCC SP-B is already under active implementation**.

Therefore:

- SP-B remains an upstream frozen dependency for this change;
- this program update does not alter SP-B's implementation contract;
- no freshness work should modify SP-B-owned files while SP-B is in flight;
- later Engineering Context increments consume the landed SP-B browser substrate;
- any browser surfacing required by freshness is added after SP-B, through the already planned
    Engineering Context UI integration.

This preserves the existing SCC → Engineering Context dependency boundary.

---

## 2. What v1 already gives us (reuse map — do NOT rebuild)

| Spec concern (§ of source) | v1 primitive | Reuse decision |
|---|---|---|
| Markdown artifact load, ids, kinds (`br/sr/spec/plan/task`) | `factory.trace.model.load_nodes` | **Reuse**; extend the kind vocabulary, don't fork a parser |
| Requirements register + sr scopes | `factory.requirements.register`, `sr:<id>` | **Reuse** |
| Typed edges (`satisfies/source_plan/spec_ref/upstream`) | `factory.trace.graph.build_graph` | **Reuse**; add new edge kinds (`parent_of`, `verified_by`, ...) |
| Derived human views + freshness (`recorded/derived/synthesized/missing`, `fresh/stale/degraded/n/a`) | `factory.system.*` (brief/matrix/timeline/guide/story/reverse, `_claims`, `models`) | **Reuse** as the backbone of the Feature Dossier / V-cycle views |
| Bundle scopes + coverage | `factory.system.bundles`, `coverage` | **Reuse**; features are bundles |
| Run manifests, evidence store | `factory.evidence.manifests` (`write_run_manifest`, `list_run_manifests`) | **Reuse** ⇒ spec §20 `manifest.json` |
| Simulation harness + scorers | `factory.validation.sim_harness.SimTestbenchHarness`, `scorer_registry` | **Reuse** ⇒ run generation in cool_physical_ai_project |
| Browser human view (scope picker, Brief/Matrix/Timeline/Guide/Story/Reverse/Trace) | `pi-ext/factory-watch/docs-server.ts` + `system-page.ts` | **Reuse** as the primary human view — see Open Decision D2 |
| Agent tools via Pi extension | `pi-ext/factory-watch` custom tools (`trace_tools`, `system_context_tools`) | **Reuse** as the agent surface — see Open Decision D1 |
| Requirement validation status + freshness preflight/reconcile | `factory.trace.validation_status`, `factory.freshness`, `factory.evidence.reconcile` | **Reuse** ⇒ status/regression/stale evidence |
| Sub-agent roles/skills, plan→task, gates | `factory.orchestrator.*`, `.factory/factory.yaml`, `writing-plans`, `test-driven-development` | **Reuse** for the build itself |

---

## 3a. Brief-grounded gap matrix (Engineering Cockpit brainstorm)

Reviewed against the **Engineering Cockpit brainstorming brief** (2026-08-11) as the base
for completing this plan. Ruling: protect settled decisions (D1–D6), pull in only what this
plan is missing, keep the thin vertical slice — do not turn the brief's six pillars into a
new program. "Covered" = already planned below; "partial" = planned but missing a brief
requirement; "missing" = not planned; "outside" = deliberately excluded via an explicit
non-goal below.

| Brief pillar (§) | Status | What the plan does / what is pulled in |
|---|---|---|
| System-level traceability (§5.1) | **covered** | Inc 1 ontology + V-cycle/feature queries, on top of SCC SP-A `adr:`/bundles. |
| Simulation-backed acceptance (§5.2) | **partial** → **add sensitivity** | Inc 3 chain exists; **pull in §5.2 "tests must prove sensitivity"** (patch-reversal: disable the target capability ⇒ evidence degrades) as an Inc 3 acceptance. |
| Measurable `/goal` optimization (§5.3) | **partial** → **add contract** | Inc 2 lifecycle exists; **pull in the §5.3 contract fields** (guardrails, population, baseline, confidence, budget, stopping rule, goal/metric versioning) as an additive Inc 2 extension. |
| Automatic experiment visualisation (§5.4) | **covered** → **add diagrams** | Inc 5 presentation router + Inc 6 human views exist; **add canonical diagram rendering** (see §3b) to Inc 1/5/6. |
| Mental-model preservation (§5.5) | **covered by existing skills** | Inc 7 `/catchup` computes the deterministic delta; the **active comprehension intervention already exists as installed PI skills** (`grill-understanding` + `visual-explainer`). The plan *references* them (D8), it does not rebuild them. |
| Durable memory & failure records (§5.6) | **partial** → **add Inc 8** | v1 `kb/` + evidence + decision artifacts partially cover it; **pull in a compact Inc 8** for failure records + durable-memory provenance (no transcript archive). |
| Evidence before narrative; honest incompleteness; determinism (§3, §14) | **covered** | Carried by every increment's global constraints (D3, §6 reuse rules). |
| Automatic artifact freshness / change propagation | **partial → first-class HLR** | Existing `factory.freshness`, evidence reconciliation and explainer freshness provide detection primitives. Extend Inc 7 from stale detection to graph-based invalidation, refresh policy, automatic safe regeneration/rerun and freshness closure. See HLR-09. |

**Selected explicit non-goals from the brief** (to keep the vertical slice honest):

- Blocking every agent decision or requiring line-by-line human approval (brief §3 non-goal).
- A general digital twin / simulation platform (§3 non-goal).
- LLM-generated confidence as acceptance evidence (§3; Inc 2 already forbids LLM for REACHED).
- A second canonical knowledge store; use `kb/`/`adr:`/`features/` as the single canonical layer (`§6` information model, one source of truth).
- The brief's E1–E10 epics are *not* adopted verbatim; they are mapped onto the existing Inc 1–8 breakdown below.

## 3b. Diagram generation (integration of `.pi/skills/diagram-design`)

**Goal:** generate proper editorial diagrams (V-cycle, architecture, feature-dossier, ADR,
goal/metric charts, `/catchup` deltas) as **committed, reviewable, provenance-bearing generated
engineering artifacts** so the cockpit looks as good as it is correct. `diagram-design` is **already
vendored** at `cool_physical_ai_project/.pi/skills/diagram-design/` (SKILL.md + 27 type references +
asset gallery) and is available to coding agents — this increment plans the *integration*, not a rebuild.

**Design (D7 — locked):**

- New typed artifact kind **`diag:`** with stable ids (`DIAG-NAV-003`), files under
  `docs/diagrams/*.html` (self-contained, no build step, per diagram-design output). A diagram
  belongs to exactly one feature/ADR scope and may carry an optional `focus` (the 1–2 nodes the
  accent draws the eye to).
- Authored **by the coding agent** via the `diagram-design` skill; `.html` is a committed,
  reviewable generated projection and is reviewed like any doc. **TS never re-derives a graph** —
  it only links/embeds the committed artifact (D7-2, consistent with "Python computes, TS renders"
  and the brief's "canonical repo artifacts, projections are derived"). The diagram is not an
  independent semantic source of truth; its freshness derives from the canonical engineering
  artifacts declared in its provenance.
- A `diag:` node is **derived from the same ontology** as the object it illustrates (the V-cycle
  query, the feature context, the goal result) so the picture never contradicts the canonical
  state; regenerate by re-running the authoring step, not by hand-editing HTML alone.
- First-run gate: the skill's `style-guide.md` is onboarded to the project's palette once
  (editorial skin), stored as a canonical token file, so every diagram is consistent.

**Where it lands (woven in, vertical slice):**

| Surface | Increment |
|---|---|
| `diag:` node kind + schema + scope + edges | Inc 1 |
| `eng_get_diagram` / `present(diag:..)` route | Inc 4 / Inc 5 |
| Render/embed diagrams in Feature Dossier, V-cycle, ADR, Goal, and `/catchup` views | Inc 6 / Inc 7 |
| Author the reference feature's V-cycle + goal-chart diagrams end-to-end | Inc 6 (drone slice) |
| Docs diagrams in the specs/plans themselves (V-cycle, evidence chain) | ongoing (docs) |

**Comprehension (D8 — locked):** the active "verify the developer understands" questionnaire is
**already implemented** as the installed `grill-understanding` + `visual-explainer` PI skills
(targeted, one-question-at-a-time, tutors via explainer on wrong answers, triggers `/plan` on
design divergence; brief §5.5 "retrieval assistance over examination"). The plan **references**
these skills as the comprehension intervention reachable from `/catchup`, `/system`, and the
relevant tabs (Inc 6/7); it does not re-implement a quiz engine. It stays **optional and
risk-triggered** — never a surveillance score.

## 3. Genuinely new v2 surface (gap analysis)

| New capability | Where it lands | Depends on |
|---|---|---|
| **Feature** artifact kind + Feature Dossier aggregate | `factory.trace.model` new kind `feat`; new `factory.feature` summaries | Inc 1 |
| **Design / ADR / architecture** — ALREADY DONE by SCC SP-A (`adr:` member kind + scope + `adr.schema.json` + `docs/adr` frontmatter) | **Reuse SP-A's `adr:`** for decisions; a *detailed-design* tier (Distinct from ADRs) is separate and optional | Inc 1 (consume, don't rebuild) |
| **Metric** artifact kind (`metrics/`) | new `factory.metrics` register + scope `metric:` | Inc 1 |
| **Goal** artifact kind (`goals/`), lifecycle state machine, evaluation, evidence, regression | new `factory.goals` | Inc 1–2 |
| Feature-centric **V-cycle vertical slice** query (definition⇄verification run) | new `factory.system` `query_vcycle`, `feature_context` | Inc 1–2 |
| `/goal` command + goal persistence + goal-reached notification | `factory.commands.goal` + Pi extension command | Inc 2 |
| Requirement **VALIDATED / VERIFICATION_STALE / REGRESSED** goal-aware status | extend `factory.trace.validation_status` | Inc 2, 7 |
| Simulation **run bundle → metric → evidence** ingestion + goal eval pipeline | extend `factory.evidence`, `SimTestbenchHarness` | Inc 3 |
| **Engineering Context MCP / agent tools** (`get_feature_context`, `trace_requirement`, `get_goal`, ...) | Pi extension tools (D1) | Inc 4 |
| **Presentation Router** (`present(artifact, focus)` at INSPECT/PRESENT/REVIEW) | new `factory.presentation` | Inc 5 |
| Human Engineering Context UI (Feature Dossier, Interactive V-cycle, Goal/metric status, Validation evidence, Simulation-run summaries) | **tabs on top of the SCC browser** (`system-page.ts`, SP-B) — no Obsidian | Inc 6 |
| **`/catchup`** context-delta + human review checkpoints | `factory.commands.catchup` | Inc 7 |
| **Diagram artifact generation** (`diag:`), rendered in the cockpit | `factory.trace` `diag:` kind + Inc 5 route + Inc 6 view, authored via vendored `.pi/skills/diagram-design` | Inc 1/5/6 (D7) |
| **Comprehension intervention** (verify understanding) | reference installed `grill-understanding` + `visual-explainer` skills (D8) | n/a — exists |
| **Failure records + durable memory** (compact) | new `factory.memory` failure-record tier + durable-memory scoping | Inc 8 |
| **Artifact freshness graph + refresh reconciliation** | extend `factory.freshness` / trace dependency graph with impact resolution, refresh policy and closure | Inc 1 ontology + Inc 3 evidence + Inc 7 |

---

## 4. Increment breakdown (maps to source spec §37 Phases 1–7)

| Inc | Name | Source phase | Deliverable | Live in repo |
|---|---|---|---|---|
| **1** | Engineering ontology + indexing | §37 Phase 1 | new artifact kinds (feature, design, metric, goal, evidence), markdown→derived index, `feature:`/`metric:`/`goal:` scopes, `query_vcycle`/`query_feature_context` backbones | pi-agent-factory |
| **2** | `/goal` + goals core | §37 Phase 2 | goal lifecycle, evaluation, evidence, notification, regression; drone demo `NOT_REACHED→REACHED→REGRESSED` | pi-agent-factory + cool_physical_ai_project |
| **3** | Simulation evidence | §37 Phase 3 | run bundle ingestion, `req→goal→exp→run→metric→evidence` chain, drone scenarios bound to goals | cool_physical_ai_project |
| **4** | Engineering Context agent surface | §37 Phase 4 | `get_feature_context`, `trace_requirement`, `get_goal`, `get_goal_evidence`, `get_latest_failure`, `present` via Pi extension (D1) | pi-agent-factory (pi-ext) |
| **5** | Presentation Router | §37 Phase 5 | `present()` dispatch: browser/IDE/simulation; INSPECT/PRESENT/REVIEW policy | pi-agent-factory |
| **6** | Human Engineering Context UI | §37 Phase 6 | extend `/system` with **Feature Dossier, Interactive V-cycle, Goal/metric status, Validation evidence, Simulation-run summaries** — additive tabs on the SCC browser (`system-page.ts`, SP-B); all Python-derived; **no Obsidian** | pi-agent-factory (browser) |
| **7** | Context delta + freshness reconciliation | §37 Phase 7 + HLR-09 | `/catchup`, human checkpoints, goal-aware validation state, dependency-driven change impact, transitive staleness propagation, refresh policy, automatic safe regeneration/rerun, freshness closure | pi-agent-factory |
| **8** | Durable memory & failure records | brief §5.6 | failure records (repro, root cause, rejected hypotheses, regression), durable decision/evidence memory w/ provenance; comprehension skill hooks (D8) | pi-agent-factory (+ product) |

**Diagram generation (D7) and comprehension (D8) are woven into Inc 1/4/5/6/7**, not a separate
increment — see §3b. Inc 8 holds only the compact durable-memory / failure-record surface.

Each increment ships its own spec review → implementation → quality gates, driven by
developer/reviewer sub-agents (see §6). No increment may start the next until its
approval questions (§7) are answered.

### Execution order — merged with the System Control Center (SCC) program

These plans share the same repo, the same navigator, and the same product repo, so they run
as **one coordinated sequence, not two blind parallel tracks**. SCC SP-A/B build the feature
spine and the browser control center our v2 feature layer and Inc 6 UI sit on.

```
SCC SP-A   feature spine + coverage + adr: + bundle map + gate    (prereq for v2 Inc 1/2 feature model)
SCC SP-B   control-center browser (health, sidebar, traversal)    (prereq for v2 Inc 6 UI)
────────────────────────────────────────────────────────────────
v2 Inc 1   ontology + V-cycle / feature-context queries   (consume SP-A adr:/bundles)
v2 Inc 2   /goal + goals core
v2 Inc 3   simulation evidence                             (drone scenarios -> goals)
SCC SP-C   system-* remediation tools                     (parallel to v2 Inc 4–5)
v2 Inc 4   pi-ext agent tools
v2 Inc 5   presentation router
v2 Inc 6   Human Engineering Context UI (tabs on SP-B browser)
v2 Inc 7   context delta + goal-aware validation status
SCC SP-D   business-requirement tier                        (last; reviews through SP-B)
```

Constraints that make this safe: every v2 increment is **additive-only** (D3) on the current
v1 surface, so SCC and v2 never re-write the same line; v2 Inc 6 is the only increment that
edits `system-page.ts`, and it does so **after SP-B** and only as new additive tabs; SP-A's
bundle map and `adr:` surface are treated as **already-done upstream dependencies**, not rebuilt.

> **See also:** `00-execution-roadmap.md` (at-a-glance merged order) and
> `00-scc-dependency-decision.md` (decision that v2 consumes SCC SP-A/SP-B).

---

## 5. Execution protocol (sub-agent driven, `pi -p`)

For each increment we run, in order, as separate `pi` sub-agent sessions:

1. **spec-agent** — given the source spec + v1 reuse map, writes the increment's
   design spec (Draft for written review). Commitment: `*.md` under
   `docs/superpowers/specs/engineering-context/`.
2. **plan-agent** — from the design spec, writes `increment-NN.md` (this plan
   family's per-increment file) with TDD-sized tasks and pseudo-code.
3. **review-agent** — strict, read-only compliance/completeness review of spec+plan
   (reuse the `*-spec-review.md` pattern already used in `pi-agent-factory-sub`).
4. **dev-agent** — implements plan task-by-task (checklist `- [ ]`, test-first),
   committing in the owning repo.
5. **quality-agent / reviewer** — runs gates, `requesting-code-review`, final review
   against the plan; routes failures back to dev as `T-###` fix-tasks.

Escalation policy: **technical/engineering-direction and UX/taste decisions go back
to the human** (this document's §7 "Open approval questions") before the affected
increment is planned in detail. The reasoning progress is recorded in
`sessions/`/`pi-agent-factory-sub` as in prior work; never silently pick a side of a
marked decision.

---

## 6. Reuse rules (global constraints, carried into every increment plan)

- Python is the single source of truth for derivation; nothing is re-derived in TS.
- Claim classes / freshness vocabulary from v1 are fixed — no new claim classes.
- Scope refs are exact and case-sensitive; no fuzzy fallback.
- One parser for markdown artifacts: `factory.trace.model` (extended), never a fork.
- A malformed artifact degrades one scope, never the whole listing.
- Rebuildable derived index: SQLite only if needed; prefer on-demand projections
  (v1 pattern) until a measured query needs an index.
- Deterministic: no `random`, no time-dependent ordering in tests.
- Tests declare `pytest.mark.unit`/`integration` at module level; run full suite green
  before every commit (`uv run python -m pytest -q && uv run python -m ruff check .`).
- Gates in `.factory/factory.yaml` use the fixed gate vocabulary (`unit|sim|integration|full`).
- Do not auto-open UI for every lookup (spec §24): INSPECT by default.
- **Freshness:** extend `factory.freshness`, `factory.trace` and `factory.evidence.reconcile`;
  do not introduce a second artifact-specific checksum/freshness framework.
- **Dependency authority:** declared trace/provenance edges determine impact. LLM semantic inference
  may suggest missing links but cannot establish authoritative freshness dependencies by itself.
- **Automatic remediation is policy-controlled:** deterministic projection rebuilds and safe generated
  knowledge may refresh automatically; authoritative contracts and semantic implementation changes
  follow their existing engineering workflows.

---

## 7. Decisions (locked 2026-08-11) + approval questions

Decisions are **locked** below; the affected increments are planned against them.

### D1 — Agent surface: **pi-ext (locked)**
Engineering-context operations ship as Pi-extension custom tools (deterministic,
version-locked, already wired into the cockpit). A standalone MCP server is deferred
unless a non-Pi client needs it.

### D2 — Human view: **SCC browser = primary; Obsidian out of scope (locked)**

> **⚠ AMENDED 2026-09-01 by `docs/superpowers/specs/2026-09-01-coherence-product-definition.md`
> (D-P7).** "Out of scope" is narrowed to *authoring and enforcement*, not navigation. Obsidian
> is a **read-only navigable projection** over canonical Markdown via `[[wikilinks]]`: never a
> write surface, never a consent surface, never a second source of truth. Mirrors are generated
> and check-gated (D-P8), not hand-authored. The browser console remains the primary surface.
The **System Control Center browser** (`docs-server`/`system-page`, built by SCC SP-B) is the
SOLE primary human engineering-context surface. All v2 human views are additive **tabs on top
of that navigator** (Feature Dossier, Interactive V-cycle, Goal/metric status, Validation
evidence, Simulation-run summaries). **Obsidian integration is out of scope** — no plugin, no
local bridge, no parallel implementation. One human surface, one Python-derived ontology
(spec §38).

### D3 — Location & stability: **extend in place, additive-only (locked)**
All v2 work lands in `pi-agent-factory` (consumed by `cool_physical_ai_project`).
Hard constraint: **the current v1 workflow must stay working and un-changed** — no
breaking edits to existing CLI verbs, commands, schemas, or behaviour; new surface is
added behind its own modules/commands and fully gated. Backward compatibility is a
first-class acceptance criterion on every increment. Any change to an existing v1
surface must be opt-in/behind a flag and proven non-breaking by the full v1 suite.

### D4 — Feature modeling: **feature files AND bundles (locked)**
`feat:` artifact files (`docs/features/`) are the dossier root; bundles remain the
membership map; `feature_context` composes both.

### D5 — Requirement-status vocabulary: **spec vocabulary (locked)**
Adopt `DEFINED/DESIGNED/IMPLEMENTED/VERIFICATION_PENDING/PARTIALLY_VERIFIED/VALIDATED/
REGRESSED` as an additive layer over the existing v1 validation status.

### D7 — Diagram artifacts: committed reviewable HTML, authored by the agent (locked)
Diagrams are **committed, reviewable, provenance-bearing generated engineering artifacts**
(`docs/diagrams/DIAG-*.html`, kind `diag:`), produced by the coding agent through the
already-vendored `.pi/skills/diagram-design` skill, onboarded to one project palette
(`style-guide.md`). Derived UI **links/embeds** these artifacts; it never re-derives a graph in TS
(matches "Python computes, TS renders" and the brief's "canonical repo
artifacts, projections are derived"). Woven into Inc 1/5/6/7 (vertical slice); no new
build step, no runtime diagram engine.

The diagram is authoritative as the current approved/generated visual representation, but it is not
an independent semantic source of truth. Its freshness derives from the canonical engineering
artifacts declared in its provenance.

### D8 — Comprehension: reuse existing skills (locked)
The active "verify the developer understands" mechanism is the installed `grill-understanding` +
`visual-explainer` PI skills (targeted, optional, risk-triggered; tutors via explainer on wrong
answers; triggers `/plan` on design divergence — brief §5.5). The plan **references** these from
Inc 6/7 surfaces; it does not build a quiz engine or a mental-model score. Non-goal: surveillance-like
scoring of the developer.

### D9 — Freshness is maintained, not merely detected (locked)
**Decision:** artifact freshness is a first-class system property governed by HLR-09.

The system SHALL distinguish:

```text
change detection
→ staleness propagation
→ refresh policy
→ remediation
→ reconciliation
→ freshness closure
```

Existing fingerprint/staleness mechanisms are reused as primitives.

The implementation SHALL NOT create per-artifact freshness silos where the existing trace/freshness
graph can represent the dependency.

Refresh policy is authority-aware:

|Artifact class|Default response to invalidation|
|---|---|
|authoritative contract|preserve; require explicit author/review change|
|implementation|route semantic repair through engineering workflow|
|validation evidence|rerun automatically where safe/allowed, otherwise `REFRESH_REQUIRED`|
|generated engineering knowledge|regenerate automatically where safe|
|derived projection/index|recompute automatically|

A stale generated artifact MUST NOT remain indefinitely stale solely because regeneration was
previously defined as manual/on-demand.

Historical artifacts remain retained with their original provenance.

**Concurrency:** D9 does not alter SCC SP-B. Freshness browser integration occurs only after the
SP-B substrate has landed.

### D6 — Coordination with the System Control Center (locked)
The **System Control Center** program (`docs/superpowers/specs/2026-08-10-system-control-center-program-decomposition.md`, sub-projects SP-A→SP-B→SP-C→SP-D) is **upstream** to v2.
SCC SP-A (feature spine: `adr:` kind, bundle map, coverage, ordering, gate) is the basis for
our v2 feature model (D4); SCC SP-B (control-center browser) is the surface our Inc 6 UI tabs
on. v2 treats SP-A's `adr:`/bundle map and SP-B's navigator as **already-done dependencies —
never rebuilt, never re-edited except as additive tabs after SP-B**. Execution order is
given in §4. No parallel Obsidian work.

---

Resolved approval questions (now decided):

All five questions (D1 agent surface → pi-ext; D2 human view → SCC browser, Obsidian out of
scope; D3 location → in-place; D4 feature modeling → files AND bundles; D5 status vocabulary →
spec) are locked in §7 above, plus D6 coordinating with the SCC program. The original written-up
recommendations and rationale for each are superseded by the locked decisions and live in the
git/decision history for traceability; they are not restated here to avoid two sources of truth.

---

Proceed to `increment-01-engineering-ontology-index.md` for the detailed Task plan
of Increment 1. Increments 2–7 are detailed after D1–D6 are answered.
