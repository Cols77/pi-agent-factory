# Increment 6 — Human Engineering Context UI (Implementation Plan)

**Status:** Draft for written review. Assumes locked **D2 = SCC browser is the sole primary
human surface (Obsidian out of scope)**, D3 = additive / keep v1 working, D6 = SCC upstream
(SP-B builds the navigator we add tabs to).
**Source phase:** Engineering Context spec §37 **Phase 6 — Obsidian Plugin**, re-scoped: the
views the spec asked Obsidian for (spec §8–§10, §9.1–§9.3) are delivered as **additive tabs in
the System Control Center browser**, not as an Obsidian plugin.
**Landing repo:** pi-agent-factory (`pi-ext/factory-watch/*`).
**Prerequisite:** SCC **SP-B** (control-center browser: health projection, sidebar, traversal)
landed and its tabs stable.
**Sub-agents:** dev=`pi -p prompts/increment-06-dev.md`, review=`pi -p prompts/increment-06-review.md`.

## Goal

Extend `/system` (the SCC browser served by `docs-server.ts` and rendered by
`system-page.ts`, SP-B) with five Python-derived engineering-context views:

1. **Feature Dossier** — the spec §9.2 / §7 aggregate: intent, requirements, design (ADRs),
   code, tasks, tests, simulations, goals, recent changes, open questions.
2. **Interactive V-cycle** — the spec §9.1 vertical slice: definition⇄verification bands,
   node id + title + status, clickable, with missing / failed / stale rendered distinctly.
3. **Goal / metric status** — the spec §9.3 goal view: requirement, metric, target, current,
   state, evidence, history; plus a reusable metric status list.
4. **Validation evidence** — requirement validation status (goal-aware) with its supporting
   evidence (runs, metrics), spec §28–§30.
5. **Simulation-run summaries** — spec §20/§21 run bundle summary: experiment, feature,
   requirements, goals, commit, result, metrics, recording link.

**All five views consume Python-derived projections only.** No TS re-derivation, no
independent graph reconstruction (spec §38). There is **no Obsidian implementation** and no
separate human surface (D2).

## Reuse (do not rebuild)

- **Backend queries:** Inc 1 `query_feature_context`/`query_vcycle`; Inc 2 `query_goal`/
  `query_goals`; Inc 3 `query_simulation_run`/`query_latest_simulation`/`query_metric_history`;
  Inc 2 Task 7 + Inc 7 goal-aware `validation_status`; `factory.system` claim/freshness model.
- **Renderer plumbing:** `system-page.ts` tab shell, `system-cli.ts` fetch path, and the
  existing claim/freshness rendering — the exact pattern SP-B's Brief/Matrix/... tabs use.
- **Sidebar traversal:** SP-B's feature-first sidebar; Inc 6 views are reached *from* it.

## Global constraints (Program §6 + D3 + D6)

- Additive tabs **only** in `system-page.ts`. Existing Brief/Matrix/Timeline/Guide/Story/
  Reverse/Trace tabs keep exact behaviour; the entire existing browser test suite
  (`system-page-*.test.ts`) must stay green. This is the only v2 increment that edits
  `system-page.ts`, and it runs after SP-B.
- Python computes every status/freshness/claim; TS only renders payload verbatim.
- Node statuses render exactly as Python decided — never remapped or distinguished by colour alone.
- Missing links/states render as explicitly missing (never dropped), matching the claim model.
- No Obsidian, no plugin, no bridge service, no new HTTP surface.

## File structure (additive)

| File | Responsibility |
|---|---|
| `pi-ext/factory-watch/src/system-feature-view.ts` | Feature Dossier widget. |
| `pi-ext/factory-watch/src/system-vcycle-view.ts` | Interactive V-cycle widget. |
| `pi-ext/factory-watch/src/system-goal-view.ts` | Goal / metric status widget. |
| `pi-ext/factory-watch/src/system-validation-view.ts` | Validation evidence widget. |
| `pi-ext/factory-watch/src/system-sim-view.ts` | Simulation-run summaries widget. |
| `pi-ext/factory-watch/src/system-diagram-view.ts` | **Diagram** widget: embed/launch canonical `diag:` HTML (D7) + comprehension entry (D8). |
| `pi-ext/factory-watch/src/system-page.ts` (additive) | register five new tabs + render dispatch. |
| `pi-ext/factory-watch/test/system-feature-view.test.ts`, `...-vcycle-view.test.ts`, `...-goal-view.test.ts`, `...-validation-view.test.ts`, `...-sim-view.test.ts`, `...-page-additions.test.ts` | widget + registration tests. |

## Task 1: Feature Dossier tab

- [ ] **Step 1: Failing tests** — given a `query_feature_context` JSON fixture, the widget renders
  each dossier section (intent, requirements, design/ADRs, code, tasks, tests, simulations, goals,
  recent changes, open questions); a missing section renders as explicitly "missing", never blank/hidden.
- [ ] **Step 2: Implement** `system-feature-view.ts` as a pure data→DOM function (testable without
  the docs server), reusing the existing claim-rendering helpers. Register `tabFeature` in the tab strip.
- [ ] **Step 3:** TS vitest + `uv run python -m pytest -q` + lint green; commit.

## Task 2: Interactive V-cycle tab

- [ ] **Step 1: Failing tests** — a `query_vcycle` fixture with a definition side
  (needs→sys-req→sub-req→adr/design→code) and a verification side (unit→integration→sim→system)
  renders as ordered bands; the anchor node is centred; a node is clickable (navigation intent);
  empty bands render as explicitly missing (spec §9.1 "show missing links distinctly");
  failed/stale nodes render distinctly.
- [ ] **Step 2: Implement** `system-vcycle-view.ts` reusing SP-B's graph-layout/click affordances;
  register `tabVcycle`.
- [ ] **Step 3:** tests + full suites + lint; commit.

## Task 3: Goal / metric status tab

- [ ] **Step 1: Failing tests** — a goal fixture renders requirement, metric, target, current value,
  state, evidence (run/commit), and history (spec §9.3); REACHED/REGRESSED/NOT_REACHED/BLOCKED each
  render from payload state; multiple goals and a metric list render.
- [ ] **Step 2: Implement** `system-goal-view.ts`; register `tabGoal`. Wire `eng_get_goal` (Inc 4)
  data through the same payload.
- [ ] **Step 3:** tests + full suites + lint; commit.

## Task 4: Validation evidence tab

- [ ] **Step 1: Failing tests** — a requirement with goal-aware status (`VALIDATED`/
  `VERIFICATION_STALE`/`REGRESSED`/`VERIFICATION_PENDING`) renders its status and the supporting
  evidence (validating runs, metrics, the goal that produced the state).
- [ ] **Step 2: Implement** `system-validation-view.ts`; register `tabValidation`.
- [ ] **Step 3:** tests + full suites + lint; commit.

## Task 5: Simulation-run summaries tab

- [ ] **Step 1: Failing tests** — a run bundle renders spec §20 fields (experiment, feature,
  requirements, goals, commit, result) plus metrics and a link to the recording; failed runs are
  distinct; a run with missing recording degrades visibly.
- [ ] **Step 2: Implement** `system-sim-view.ts`; register `tabSim`. `eng_present` (Inc 5) routes
  the simulation adapter here.
- [ ] **Step 3:** tests + full suites + lint; commit.

## Task 5b: Diagram rendering + comprehension entry (D7 / D8)

**Files:** `pi-ext/factory-watch/src/system-diagram-view.ts`, `test/system-diagram-view.test.ts`,
and additive calls in `system-feature-view.ts` / `system-vcycle-view.ts` / `system-goal-view.ts`.

- [ ] **Step 1: Failing tests** — a `diag:` payload (stub + `diagram_file` + `focus` + `illustrates`)
  renders by **linking/embedding the canonical HTML** (an `<iframe>`/`object` or link target resolved
  via Inc 5 to `docs/diagrams/DIAG-*.html`); a diagram whose HTML is missing renders as explicitly
  **"missing diagram"** (honest incompleteness, never a broken blank); a V-cycle view can show the
  anchor feature's diagram; `focus` surfaces which node to look at first.
- [ ] **Step 2: Implement** — `system-diagram-view.ts` as a pure data→DOM function that embeds the
  committed HTML (D7: no TS re-derivation of the graph), reachable from the Feature Dossier,
  V-cycle and ADR views, and via `present(diag:..)`; register `tabDiagram`.
- [ ] **Step 3: Comprehension entry (D8)** — from a dossier/V-cycle/`/catchup` view, offer an
  optional, explicit **"Verify my understanding"** action that invokes the installed
  `grill-understanding` + `visual-explainer` skills on the focused feature (targeted, one question,
  tutors via explainer, triggers `/plan` on divergence — brief §5.5). Pure entry point; the skill
  does the work; no quiz engine built here, no comprehension score surfaced.
- [ ] **Step 4:** tests + full suites + lint; commit.

## Task 6: Navigation integration (spec AC-02, AC-09)

- [ ] **Step 1:** from a requirement in the V-cycle view, navigate to parent/child requirements,
  design (ADR), implementation, tests, simulation evidence — AC-02; and "show me where this
  requirement fits" (AC-09) opens the V-cycle view for that ref without manual artifact search.
- [ ] **Step 2:** exercise the feature dossier as a hub: dossier → goals → goal evidence → run → sim.
- [ ] **Step 3:** integration tests drive the full navigation against seeded real data; existing tab
  behaviour unchanged.

## Task 7: Review handoff

- [ ] **Step 1:** reviewer sub-agent — compliance vs spec §7–§10, §9.1–§9.3, §20–§21, AC-02/AC-09,
  and D2 (one human surface, no Obsidian), D3 (additive, v1 tabs untouched), D6 (layered on SP-B).
- [ ] **Step 2:** fix findings as `T-###`; update checkboxes.

## Acceptance for Increment 6

- `/system` shows all five views as new tabs; each renders only Python-derived projections.
- Missing / failed / stale states are distinct and never silently dropped (spec §9.1, §28–§30).
- AC-02 (V-cycle navigation) and AC-09 (contextual navigation) work; feature dossier is a runnable hub.
- No Obsidian code, no bridge service (D2). Every pre-existing browser tab test stays green (D3).
- Canonical diagrams (D7) render by embedding committed HTML; a diagram view degrades honestly when
  its artifact is missing. Comprehension is an optional, explicit entry to the installed skills (D8).
- Full Python + TS suites green.
