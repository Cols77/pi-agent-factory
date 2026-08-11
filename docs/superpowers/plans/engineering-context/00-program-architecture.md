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

## 3. Genuinely new v2 surface (gap analysis)

| New capability | Where it lands | Depends on |
|---|---|---|
| **Feature** artifact kind + Feature Dossier aggregate | `factory.trace.model` new kind `feat`; new `factory.feature` summaries | Inc 1 |
| **Design / ADR / architecture** kinds already partially exist (`adr` scope + `docs/adr`) | extend `docs/adr` dress to designs `docs/designs` | Inc 1 |
| **Metric** artifact kind (`metrics/`) | new `factory.metrics` register + scope `metric:` | Inc 1 |
| **Goal** artifact kind (`goals/`), lifecycle state machine, evaluation, evidence, regression | new `factory.goals` | Inc 1–2 |
| Feature-centric **V-cycle vertical slice** query (definition⇄verification run) | new `factory.system` `query_vcycle`, `feature_context` | Inc 1–2 |
| `/goal` command + goal persistence + goal-reached notification | `factory.commands.goal` + Pi extension command | Inc 2 |
| Requirement **VALIDATED / VERIFICATION_STALE / REGRESSED** goal-aware status | extend `factory.trace.validation_status` | Inc 2, 7 |
| Simulation **run bundle → metric → evidence** ingestion + goal eval pipeline | extend `factory.evidence`, `SimTestbenchHarness` | Inc 3 |
| **Engineering Context MCP / agent tools** (`get_feature_context`, `trace_requirement`, `get_goal`, ...) | Pi extension tools (D1) | Inc 4 |
| **Presentation Router** (`present(artifact, focus)` at INSPECT/PRESENT/REVIEW) | new `factory.presentation` | Inc 5 |
| Human V-cycle / Feature / Goal views | browser (D2) or Obsidian | Inc 6 |
| **`/catchup`** context-delta + human review checkpoints | `factory.commands.catchup` | Inc 7 |

---

## 4. Increment breakdown (maps to source spec §37 Phases 1–7)

| Inc | Name | Source phase | Deliverable | Live in repo |
|---|---|---|---|---|
| **1** | Engineering ontology + indexing | §37 Phase 1 | new artifact kinds (feature, design, metric, goal, evidence), markdown→derived index, `feature:`/`metric:`/`goal:` scopes, `query_vcycle`/`query_feature_context` backbones | pi-agent-factory |
| **2** | `/goal` + goals core | §37 Phase 2 | goal lifecycle, evaluation, evidence, notification, regression; drone demo `NOT_REACHED→REACHED→REGRESSED` | pi-agent-factory + cool_physical_ai_project |
| **3** | Simulation evidence | §37 Phase 3 | run bundle ingestion, `req→goal→exp→run→metric→evidence` chain, drone scenarios bound to goals | cool_physical_ai_project |
| **4** | Engineering Context agent surface | §37 Phase 4 | `get_feature_context`, `trace_requirement`, `get_goal`, `get_goal_evidence`, `get_latest_failure`, `present` via Pi extension (D1) | pi-agent-factory (pi-ext) |
| **5** | Presentation Router | §37 Phase 5 | `present()` dispatch: browser/IDE/simulation; INSPECT/PRESENT/REVIEW policy | pi-agent-factory |
| **6** | Human V-cycle views | §37 Phase 6 | Feature Dossier + V-cycle + Goal status (D2: browser tabs vs Obsidian) | pi-agent-factory (browser) / Obsidian |
| **7** | Context delta + validation status | §37 Phase 7 | `/catchup`, human checkpoints, goal-aware `VALIDATED`/`VERIFICATION_STALE`/`REGRESSED`, change impact | pi-agent-factory |

Each increment ships its own spec review → implementation → quality gates, driven by
developer/reviewer sub-agents (see §6). No increment may start the next until its
approval questions (§7) are answered.

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

---

## 7. Decisions (locked 2026-08-11) + approval questions

Decisions are **locked** below; the affected increments are planned against them.

### D1 — Agent surface: **pi-ext (locked)**
Engineering-context operations ship as Pi-extension custom tools (deterministic,
version-locked, already wired into the cockpit). A standalone MCP server is deferred
unless a non-Pi client needs it.

### D2 — Human view: **Obsidian primary + browser port (locked)**
Ship the Obsidian V-cycle/Feature/Goal views (as the source spec §8–§10 intends) AND
port the equivalent views into the existing v1 browser (`docs-server`/`system-page`)
for eventual evolution. Both render the **same Python-derived** engineering ontology
(spec §38); Obsidian never reconstructs the graph itself — it consumes the local
service/pipe (Inc 6).

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

---

Resolved approval questions (now decided):

_These are the taste / technical / UX decisions the program cannot silently choose.
They gate Increments 4 (D1) and 6 (D2, D3); the rest can proceed under the reuse rules._

### D1 — Agent interface: Pi-extension tools vs standalone MCP server (gates Inc 4)
Source spec §25/§33 propose an "Engineering Context MCP server". v1 already exposes
agent tools as Pi-extension custom tools (`trace_tools`, `system_context_tools`),
which are deterministic, version-locked to the extension, and already wired into the
cockpit. **Recommendation: reuse the Pi-extension tool route** and expose the
engineering-context operations as tools there; defer a standalone MCP server unless a
non-Pi client (Obsidian service, external IDE) proves necessary.
**Choice needed:** reuse-Pi-ext (recommended) / standalone-MCP / both.

### D2 — Human view: extend v1 browser (`docs-server`) vs build an Obsidian plugin (gates Inc 6)
Source spec §8–§10 call for an Obsidian extension. But v1 already ships a browser
human view (`system-page.ts`: scope picker + Brief/Matrix/Timeline/Guide/Story/Reverse/
Trace + sidebar navigation) served by `docs-server.ts`, and *multiple existing
repos replace Obsidian with it*. The engineering-context views (Feature Dossier,
V-cycle, Goal status) are natural **new tabs** in this existing page, sharing the
exact Python-derived claims — obeying spec §38 (single ontology, no isolated human
knowledge base) better than a separate Obsidian plugin with its own data path.
**Recommendation: extend the browser view (new Feature/V-cycle/Goal tabs); drop
Obsidian unless you specifically require Obsidian's vault/plugins.**
**Choice needed:** browser-reuse (recommended) / Obsidian-plugin / both.

### D3 — Where v2 code lives (gates all increments)
**Recommendation: extend `pi-agent-factory` in place** (it is already a standalone,
reusable repo; `cool_physical_ai_project` consumes it as an editable path dep).
An entirely new repo would duplicate the orchestrator/system substrate for no reuse win.
**Choice needed:** in-place (recommended) / new repo.

### D4 — Feature as bundle vs new `feat:` artifact kind (gates Inc 1)
v1 has bundles (feature-scope labels) as the feature-ish primitive. The source spec
wants a first-class `Feature` artifact (§5.1, FEAT-NAV-017). **Recommendation: add a
`feat:` kind in `docs/features/` AND keep bundles as the membership map** — a feature
file is the dossier root; a bundle maps members; `feature_context` composes both.
**Choice needed:** both (recommended) / feature-as-bundle-only / feature-file-only.

### D5 — Requirement status vocabulary cadence (gates Inc 2/7)
Spec §28 wants `DEFINED/DESIGNED/IMPLEMENTED/VERIFICATION_PENDING/PARTIALLY_VERIFIED/
VALIDATED/REGRESSED`. v1 already has a validation status model + freshness. **Choice
needed:** adopt spec vocabulary (recommended, additive) / keep v1 vocabulary / map.

---

Proceed to `increment-01-engineering-ontology-index.md` for the detailed Task plan
of Increment 1. Increments 2–7 are detailed after D1–D5 are answered.
