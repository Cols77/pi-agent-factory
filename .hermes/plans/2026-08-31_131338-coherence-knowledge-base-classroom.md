# Coherence Knowledge Base and Classroom Implementation Plan

> **For Hermes:** Use the `subagent-driven-development` skill to implement this plan task-by-task only after the owner approves the scope and the escalation decisions. This plan is documentation/visualization work; it must not be used as permission to change Coherence implementation behavior.

**Goal:** Build an evidence-backed, newcomer-friendly knowledge base and visual classroom that explains the complete Coherence product surface, separates implemented behavior from design and roadmap claims, exposes health and freshness, and escalates every unresolved semantic decision to the human owner.

**Architecture:** The repository's Markdown and deterministic Python/CLI outputs remain the canonical knowledge source. `docs/course/` will contain traceable learner notes that `coherence course check` can validate; committed visual explainers will be linked from those notes. Obsidian is a navigable classroom projection of those artifacts, not a second authority. Every claim is represented as a typed record with provenance, lifecycle state, verification state, and an escalation state; no diagram may silently convert a plan, test, or operational status into evidence of implementation.

**Tech Stack:** Markdown/frontmatter, Obsidian wikilinks, Coherence CLI JSON, Python AST/static inspection, pytest, the repository's schemas and evidence records, Pi TypeScript extension metadata, inline-SVG HTML diagrams from `architecture-diagram`, and optionally Excalidraw source files for editable concept maps.

---

## 1. Scope and non-negotiable interpretation rules

### 1.1 What the classroom covers

The inventory is deliberately wider than the `coherence` package. It covers the complete system a newcomer needs to understand:

1. **The shared substrate:** paths, schemas, artifact parsing, ledgers, codemap/imports/signatures, knowledge-base validators, policy vocabulary, freshness, evidence models, agent/skill metadata, and projections.
2. **Coherence assurance:** trace graph/model, register, doctor, navigation, presentation/router, status/focus/explain, audit/measurement/observations, obligations, gates, inbox/deferrals, staleness, and course checking.
3. **Factory execution:** orchestration, planning-to-task conversion, run state, worker sessions, evidence manifests, validation, gate runners, simulation/goals, polish, coverage, recovery, memory/nonconformance, and compatibility shims.
4. **Host surfaces:** the Pi `factory-watch` and `scope-guard` extensions, commands, registered tools, dashboards, browser/doc servers, review surfaces, and the boundary to Hermes skills, plugins, MCP, Kanban, and other transports.
5. **Project artifacts and process:** requirements/SRs, BRs, FEAT dossiers, bundles, plans, specs, tasks, sessions, evidence, schemas, configuration, scripts/gates, tests, worktrees, and release/health workflows.
6. **What is absent or ambiguous:** code that has no authoritative spec, planned work with no production path, stale plans, dead/unwired surfaces, contradictory architecture statements, and missing evidence.

### 1.2 Claim vocabulary

Every inventory row and every learner-facing explanation must use one or more of these explicit states:

- **Specified:** an authoritative design/spec decision exists; implementation is not implied.
- **Planned:** a plan or roadmap describes future work; implementation is not implied.
- **Implemented:** a production path exists and is reachable from a supported entry point.
- **Implemented but unspecified:** a production path is observed but no authoritative requirement/spec claim has been found.
- **Observed:** seen in code, configuration, a registered surface, or a live command; not yet sufficient to claim verified behavior.
- **Verified:** exercised by a focused test or reproducible runtime command, with the date and result recorded.
- **Stale:** prior evidence or explanation no longer matches current inputs/fingerprints.
- **Contradicted:** authoritative sources or observed sources disagree; do not resolve by preference.
- **Unknown:** the repository does not provide enough evidence to decide.
- **Human decision required:** an owner must choose, consent, reject, or supply missing context.

These are separate axes. For example, a feature can be `specified + implemented + verification-stale`, or `planned + not implemented`, or `implemented but unspecified + verified`. A passing test is not automatically a requirement, a gate, or a human decision.

Use these machine-readable axes rather than a single mutually-exclusive badge:

```yaml
lifecycle: specified | planned | implemented | unknown
observation: observed | not_observed
verification: verified | unverified | stale
source_state: current | contradicted | unknown
material: canonical | generated | curated | mixed
escalation: none | human_decision_required
```

`implemented_but_unspecified` is a derived teaching label for `lifecycle: implemented` plus no authoritative requirement/spec, not a replacement for the axes.

### 1.4 Decisions recorded on 2026-08-31

- **Curriculum scope:** Coherence is first-class, with substrate, factory, and host surfaces included as supporting context; historical/legacy material is labeled explicitly.
- **Product authority:** the 2026-08-18 toolset, 2026-08-20 agentic-I/O, 2026-08-22 progressive-assurance, and 2026-08-24 release documents govern the Coherence product model; older HLR/engineering-context material is legacy unless separately re-authorized.
- **Dependency contradiction:** classify current factory–Coherence coupling as transitional; show declared architecture, observed imports, and legacy shims as separate facts until a future architecture decision.
- **Health scope:** author/document/visualize first; create a separate human-consented health-resolution track rather than silently repairing the project register here.
- **Obsidian:** projection-only; repository Markdown and deterministic CLI output remain canonical.
- **Verification threshold:** use the strong standard—production path + focused test + live command/fixture when feasible; if a capability cannot meet all three, label the weaker verification explicitly.
- **`using-coherence` gap:** teach its original deterministic read-only behavior, label the desired interactive/teaching experience as a separate design gap, and create a later feature plan only if approved.
- **Roadmap:** teach Console A/B/C and Hermes MCP as roadmap-only concepts; do not promote their implementation in this initiative.
- **Visual acceptance:** require all eight proposed visual explainers in the first classroom review.
- **Review process:** use dedicated topic-specific agents for semantic/coverage review, then the owner reads the result as final human review. Agent output is evidence and criticism, never human consent or acceptance authority.
- **Newcomer evaluator:** the owner will perform the newcomer walkthrough, reading and exercising the classroom without relying on project-history context.

Open questions in Section 7 remain blocking where they affect dirty-path protection, classroom schema/refresh policy, exercise safety, generated-asset ownership, and any future health/SR decisions.

### 1.5 Evidence hierarchy

For each claim, record the source class and exact locator:

1. **Runtime/CLI output** for what the current checkout actually does.
2. **Production code path and registration** for what is reachable.
3. **Focused tests and gates** for what has been exercised.
4. **Schemas/configuration** for accepted data contracts and policy.
5. **Feature/requirement records** for intended acceptance and ownership.
6. **Specs/designs** for decisions and constraints.
7. **Plans/roadmaps** for proposed sequencing only.
8. **Existing prose/course notes** as explanatory material, never sole proof.

When two levels disagree, display both readings and create an escalation record.

---

## 2. Current baseline captured before classroom authoring

This is the baseline from the current checkout and must be re-run at the beginning of every later increment; the numbers are not permanent facts.

- The repository contains 49 SR nodes, 24 task nodes, 64 spec nodes, and 84 plan nodes: 221 trace nodes before any new plan/document changes.
- `coherence navigate health --repo-root . --json` exits 0 and currently reports health `72/179` (40%). Its classes include `task->plan 22/23`, `task->SR 1/23`, `plan->spec 49/84`, `SR satisfied 0/49`, `decomposition_allocation 17/20`, `executed_evidence 0/49`, `validation_scenarios 0/49`, `deferrals_waivers 51/159`, and `human_review 0/0`.
- The same output reports 17 bundles, 49 bundled nodes, 24 unbundled tasks, 64 unbundled specs, and 84 unbundled plans as the current coverage shape; `ordering_available` is true and `sr_listed` is false.
- The V-cycle projection reports 71 findings, while freshness findings are 0. These are different health views and must not be collapsed into one “green/red” claim.
- `coherence course check --project-root . --json` exits 1 with `ok: false`, `notes: []`, 49 unreached SRs and 64 unreached specs. This is the honest starting point for a traceable course, not a reason to invent links.
- Register and trace help confirm their exact root option is `--project-root`; navigator health uses `--repo-root`. Command examples in classroom notes must follow actual `--help` output, not stale plan syntax.
- Static import inspection currently observes both `factory -> coherence` and `coherence -> factory` imports (for example, Coherence status/audit code imports factory orchestration components while factory coverage/doctor modules import Coherence). The class-level architecture prose says “factory -> coherence -> substrate” but also says Coherence may import factory. This is a mandatory contradiction entry, not something the diagram may smooth over.
- The existing `factory.*` compatibility modules explicitly warn and re-export canonical `coherence.*` modules in several paths. The course must explain “canonical surface vs legacy import shim” before presenting package layers.

### 2.1 Post-plan refresh

Adding the canonical plan created one additional plan node. A fresh read-only refresh now reports health `72/180` (40%), coverage `49/222` bundled with `173` unbundled, `71` V-cycle findings, and `0` freshness findings. `coherence status --project-root . --json` exits 0 at the process level but its payload has `exit_code: 1` and ranks failing trace/register/membership gates, a proposed audit backlog for 20 unaudited features, and 49 suspect-edge inbox items. The course checker reports `ok: false`, `notes: []`, and 113 unreached nodes (49 SRs + 64 specs). The pre-authoring numbers above remain useful as a before/after baseline; all later material must identify which snapshot it uses.

All baseline numbers must be stored with command, checkout identifier, timestamp, and raw JSON path. Do not hard-code them into generated status views without a snapshot date.

---

## 3. Available assets and how they will be used

### 3.1 Repository assets

- `README.md`, `IDEA.md`, and `course-text.txt` provide orientation and an existing 11-lesson traceability narrative; they must be mined, corrected against live behavior, and not treated as authoritative where dated.
- `docs/superpowers/specs/` is the design decision archive. Anchor documents include the Coherence toolset design, agentic I/O/freshness design, progressive assurance design, system traceability course overhaul, Pi package adoption, and release strategy.
- `docs/superpowers/plans/` contains the historical execution record, including the Coherence increment map, health-resolution work, console slices, evidence, navigation, and host-surface plans. Plan checkboxes are not completion evidence.
- `docs/features/FEAT-*.md`, `requirements/SR-*.md`, `requirements/BR-*.md`, `requirements/index.json`, `bundles/*.json`, `tasks/T-*.md`, `evidence/`, `sessions/`, and `.factory/factory.yaml` are the artifact graph to explain.
- `src/substrate/`, `src/coherence/`, and `src/factory/` are the implementation surfaces. The inventory must use AST/import and production-call-path inspection, not only directory names.
- `src/substrate/schemas/*.json` includes contracts for requirements/features, bundles, context, system responses/matrix/timeline/claims, runs, sessions, evidence, metrics, goals, ADRs, diagrams, profiles, and nonconformance.
- `pi-ext/factory-watch/README.md`, its TypeScript sources, `scope-guard`, and `.pi/factory/tools.json` describe the host adapter and derived registered-tool catalog. `.pi/factory/tools.json` is a derived snapshot, not a hand-maintained authority.
- `scripts/gates/` and the project test suites provide executable verification surfaces. Their scope and limitations must be shown explicitly.
- A local Obsidian vault exists at `C:/Users/33630/Documents/Obsidian Vault`; current targeted searches found no existing Coherence course notes. It is available for later projection, but it must not become the canonical ledger.
- The local vault has core graph/canvas/search/backlinks/properties/bases capabilities and community plugins including PlantUML, Tasks, Git, and table generation. Graphviz is present on disk but is not listed as an enabled community plugin. The vault also contains unrelated material and a nested vault, so the classroom should use a dedicated `Coherence/` namespace or a separate projection, not the root graph indiscriminately.
- A generated system-traceability classroom exists at `C:/Users/33630/.pi/agent/classrooms/system-traceability`. It is a useful historical/reference asset but is materially stale relative to the current checkout and lacks a complete claim/source ledger. Treat it as superseded or regenerate it only after an explicit retention decision.

### 3.1.1 Minimum live surface inventory

The classroom inventory must preserve the following currently observed command matrix, while re-discovering it from source/help during each refresh rather than treating the list as permanent:

- Root `coherence` groups: `trace`, `register`, `navigate`, `audit`, `doctor`, `presentation`, `goals`, `simulation`, `measurement`, `course`, `status`, `route`, `focus`, and `explain`.
- `coherence trace`: `status`, `graph`, `link`, `unlink`, `next`, `check`, `exempt`, `defer`.
- `coherence register`: `new`, `index`, `status`, `show`, `bind`, `defer`, `check`, `next`.
- `coherence navigate`: `brief`, `dossier`, `worker`, `matrix`, `timeline`, `story`, `reverse`, `guide`, `traversal`, `vcycle`, `validation`, `catchup`, `diagram`, `sim`, `goal`, `obligations`, `present`, `scope`, `health`, `freshness`, `labels`, `vocabulary`, `remediation`, `panels`, `new`, `coverage`, and `membership`; nested `sim` has `run`, `latest`, `failure`, `metric`, and `goal-evidence`, nested `goal` has `show`, `list`, and `evaluate`, and nested `bundle` has `check`.
- `coherence audit`: `audit`, `verdict`, `record-failure`, `consolidate`, `gate`, `report`, `list-features`, and `run`.
- `coherence doctor`: `context`, `mint`, `promote`, and `task`.
- `coherence presentation`: `present`.
- `coherence goals`: `list`, `show`, `create`, `set-state`, `evaluate`, and `history`.
- `coherence simulation`: `runs` and `sensitivity`.
- `coherence measurement`: `validate`.
- `coherence course`: `check`.
- Root-only commands: `coherence status`, `coherence route TEXT`, `coherence focus SCOPE_REF`, and `coherence explain TERM`.
- Separate live module CLIs: `factory.evidence` (`run`, `task`, `record`, `list`, `reconcile`); `factory.orchestrator` (`run`, `list`, `run-state`, with `current`, `inspect`, `resume`, `restart`, `abandon`, `preserve-external-edits`, and `doctor` under `run-state`); `factory.preflight`; `factory.polish` (`list`, `run`, `serve`); `factory.memory` (`memory show`, `memory conflicts`, `failure list`, `failure show`, `failure add`); `factory.delta` (`catchup`); and `substrate.codemap`.
- Compatibility module paths remain operational but warn and forward to canonical surfaces: `factory.trace`, `factory.requirements`, `factory.doctor`, `factory.system`, `factory.goals`, `factory.simulation`, `factory.presentation`, `factory.coverage`, `factory.validation`, and `factory.codeindex`. There is no verified root `python -m factory` CLI.

Source anchors for this matrix are `src/coherence/cli.py`, the package `cli.py` modules under `src/coherence/*`, `src/factory/evidence/cli.py`, `src/factory/orchestrator/__main__.py`, `src/factory/orchestrator/run_cli.py`, `src/factory/preflight/cli.py`, `src/factory/polish/cli.py`, `src/factory/memory/cli.py`, `src/factory/delta/__main__.py`, and `src/substrate/codemap/cli.py`. Unsupported commands, such as planned `coherence workflows`, `coherence run-governed`, and `coherence console`, must be recorded as absent rather than silently omitted.

### 3.2 Installed Hermes/authoring assets

Use the following skills and tools as process support, not as acceptance authority:

- `pi-agent-factory`: repository map, Coherence CLI vocabulary, host-adapter boundary, health pitfalls, register/bundle schema, SR-consent workflow, and portability notes.
- `coherence-execution-governance`: FeaturePlan → ExecutionProposal → RunContract → transport, deterministic graph validation, gate visibility, reconciliation, and host conformance.
- `coherence-health-resolution`: the seven-step requirement → obligation → implementation → evidence → gate → observation → review spine and the mandatory human consent boundary for semantic SR authoring.
- `obsidian`: filesystem-first note creation, concrete vault paths, Markdown links, and wikilinks.
- `architecture-diagram`: self-contained inline-SVG HTML for system topology, lifecycle, and health visuals.
- `excalidraw`: editable concept/flow/architecture diagrams where hand-drawn collaborative exploration is useful.
- `grounded-citations`: claim/source/evidence discipline; for this project the primary sources are local files and CLI captures rather than web citations.
- `dogfood`: systematic browser/UI exploration for any live console or browser server that is claimed to be usable.
- `durable-kanban-orchestration` and `subagent-increment-workflow`: only for later multi-task execution; they require durable lifecycle evidence, bounded workers, independent review, fresh fix/re-review cycles, and a holistic integration review.
- `hermes-agent` and `inspecting-hermes-desktop-dom`: Hermes surface boundaries and live desktop DOM verification if a classroom projection or host integration is built.
- `plan`: preserves this plan-mode boundary; no implementation work is authorized by this document.

Future contributors may also use the available test-driven development, systematic debugging, requesting-code-review, codebase-inspection, and Git/worktree skills where their triggers apply.

---

## 4. Proposed knowledge-base shape

### 4.1 Repository layout

The implementation increment should create or populate only the following documentation/visual surfaces after scope approval:

- `docs/course/00-course-map.md` — landing page, legend, evidence rules, navigation path, current baseline.
- `docs/course/01-newcomer-orientation.md` — what problem Coherence solves, with a glossary before jargon.
- `docs/course/02-artifact-ontology.md` — SR/BR/FEAT/bundle/plan/task/code/evidence/gate/observation/review/NC relationships.
- `docs/course/03-repository-anatomy.md` — directory-to-responsibility map and canonical vs derived vs runtime state.
- `docs/course/04-cli-and-tools.md` — every supported Coherence group, verb, host command, registered Pi tool, and use case.
- `docs/course/05-trace-register-doctor.md` — how requirements become declared edges and how gaps are handled.
- `docs/course/06-navigate-present-explain.md` — navigator scopes, briefing/matrix/timeline/story/reverse/guide, routing, focus, explanation, and projection boundaries.
- `docs/course/07-evidence-validation-gates.md` — obligations, requiredness, gate taxonomy, manifests, reconciliation, freshness, and human review.
- `docs/course/08-audit-measurement-observations.md` — what audit and measurement can prove, what they cannot, and provenance.
- `docs/course/09-memory-context-and-catchup.md` — the three memory layers, context engineering/context packets, code-context injection, task preambles, delta/catch-up, checkpoints, freshness, and preflight.
- `docs/course/10-goals-simulation-vcycle.md` — goals, metrics, simulation runs, V-cycle findings, and the distinction between execution and assurance.
- `docs/course/11-factory-execution.md` — planning/task export, orchestrator, worker sessions, gate runner, recovery, polish, and compatibility shims.
- `docs/course/12-bootstrap-packaging-and-trust.md` — installation/configuration, `/factory-init`, packaging, scope-guard, child-worker fail-closed behavior, project trust, and direct Python entry points.
- `docs/course/13-pi-host-and-hermes.md` — Pi commands/tools, dashboards, browser/terminal modes, thin-host invariant, and possible Hermes projections.
- `docs/course/14-real-workflows.md` — symptom-to-command decision tree and fully worked newcomer exercises.
- `docs/course/15-implemented-vs-roadmap.md` — evidence-backed status matrix, including FEAT-018/019/020, planned console/teach surfaces, Hermes MCP, and unspecified code.
- `docs/course/16-health-and-escalation.md` — health vector, freshness, unresolved contradictions, consent gates, and the escalation contract.
- `docs/course/99-glossary.md` — plain-language definitions and “do not confuse” pairs.

Each note must have frontmatter containing at least `title`, `audience`, `claim_class`, `status`, `last_verified`, `sources`, and exact Coherence traceability IDs where those IDs are authoritative and referenceable. Course body wikilinks must use the parser’s accepted node grammar (`SR-*` or `SPEC-*`); ordinary note links should be Markdown links to avoid ambiguous bare-title wikilinks.

The graph model must retain the canonical node kinds and relationship vocabulary discovered from the implementation. At minimum, explain `br`, `sr`, `spec`, `plan`, `task`, `adr`, `feat`, `metric`, `goal`, `run`, and `diag`, and distinguish declared edges such as `source_plan`, `spec_ref`, `contains`, `satisfies`, `implements`, `verifies`, `validates`, `evidences`, `corrects`, `mitigates`, `impacts`, `supersedes`, `maintains`, and `explores`. A wikilink is a learning/navigation link; it is not evidence of a canonical graph edge unless the underlying artifact declares or derives that edge.

Present the notes in three mandatory tiers: **Orientation** (course map, problem, vocabulary, ontology, repository anatomy), **Operator workflows** (trace/register/doctor, navigation/presentation, evidence/validation, audit/measurement, memory/context/catch-up, goals/simulation, execution/bootstrap), and **Assurance/host surfaces** (health, gates, staleness, Pi/Hermes, roadmap, escalation). The landing page gives one short mandatory route; the graph remains optional exploration.

### 4.2 Visual artifact set

Create committed, reviewable visuals linked from the course notes. Each visual must carry a legend, source list, generated/verified timestamp, and a status disclaimer:

1. **System topology:** substrate, Coherence, factory, Pi, and external transports; show observed import edges, declared architecture edges, and legacy shim edges with different line styles.
2. **Assurance spine:** requirement → obligation → implementation → evidence → gate → observation → review, with the “missing data stays unknown” rule.
3. **Newcomer decision tree:** symptom (“what is this?”, “what is missing?”, “did it run?”, “is it stale?”, “what should I do next?”) → exact command/tool → output interpretation.
4. **Artifact lifecycle/V-cycle:** intent → feature/SR → plan/task → implementation → validation/evidence → review/NC → change impact.
5. **Health matrix:** dimensions and classes with plain-language glosses, current snapshot values, and links to remediation commands; never use one scalar to hide dimension failures.
6. **Implemented/spec/planned swimlane:** production evidence on one lane, authoritative specification on another, roadmap-only items on a third, and contradictions/unknowns on a fourth.
7. **Feature dossier walk-through:** clickable or linked path through requirement, obligations, trace, code, evidence, simulation, observation, review, and escalation.
8. **Host-adapter map:** Python authority versus Pi/Hermes/browser/CLI projections, including what each surface can read or write.

Use inline-SVG HTML for stable committed explainers and Excalidraw for editable workshop maps. No visual may be treated as evidence merely because it renders. The visual must link back to source artifacts and the command that regenerated its data.

Existing classroom visuals must be audited before reuse. Within the historical classroom at `C:/Users/33630/.pi/agent/classrooms/system-traceability`, `assets/course-map.html` uses external font/CDN dependencies and does not carry a source ledger or snapshot metadata; `coherence-programme-visual.html` risks feeding multiple Mermaid blocks to one render call. Split diagrams by information type, prefer offline-safe rendering, and mark any browser-render conclusion as unverified if the harness requests unavailable remote-debugging approval.

### 4.3 Optional Obsidian projection

After the repository notes pass `coherence course check`, mirror or link them into the resolved vault path. The Obsidian graph should have folders/tags for `course`, `concept`, `workflow`, `tool`, `artifact`, `status`, `health`, `visual`, and `escalation`. Use graph views for exploration, not for authoritative counts. Do not auto-open or mutate the user’s vault without explicit approval.

---

## 5. Exhaustive discovery workflow

### Phase A — freeze baseline and boundaries

1. Re-run `git status --short --branch` and `git worktree list`; record dirty/untracked paths and prohibit the classroom work from overwriting them.
2. Re-run `coherence navigate health --repo-root . --json`, `coherence status --project-root . --json`, `coherence register check --project-root .`, `coherence trace check --project-root .`, and `coherence course check --project-root . --json`; capture exit codes, stdout, stderr, and timestamps.
3. Ask the owner to resolve the blocking scope escalations in Section 7 before authoring semantic SRs or claiming a canonical product boundary.

### Phase B — machine inventory

4. Enumerate all non-generated Python, TypeScript, Markdown, JSON, YAML, schema, script, and test files, excluding `.git`, caches, `node_modules`, and worktrees; report counts by domain.
5. Parse `pyproject.toml`, extension package manifests, `.factory/factory.yaml`, and schema registries; extract entry points, dependencies, gate definitions, and generated/derived surfaces.
6. Parse Python AST imports to produce an observed dependency graph and flag cycles, compatibility re-exports, deprecated modules, and imports crossing the declared layer boundary.
7. Extract every CLI parser group/subcommand and run each group’s `--help`; store the exact usage/options text as evidence. The first-class top-level vocabulary currently includes `course`, `trace`, `register`, `doctor`, `navigate`, `presentation`, `goals`, `simulation`, `audit`, `measurement`, `status`, `route`, `focus`, and `explain`; verify this list against the live dispatcher rather than treating it as permanent. Include direct `python -m factory.*` and `python -m substrate.*` entry points where reachable.
8. Extract every Pi `registerCommand`, `registerTool`, host route, browser/server route, and generated tool-catalog entry. Cross-check the derived catalog against actual registration; report parity failures.
9. Extract test files, test names, gate scripts, fixtures, and documented verification commands; map each to the production module and claim it exercises.
10. Extract artifact IDs, schema fields, edges, status literals, requiredness literals, freshness states, and remediation commands from source and schemas. This is the controlled vocabulary for the glossary and diagrams.

The inventory must explicitly include the following domains discovered during review:

- **Roadmap-only FEAT-018/019/020:** the FeaturePlan → ExecutionProposal → GatePlan/RunContract/compiler bridge, cross-host conformance/dogfooding, and legality-preserving Kanban graph optimization. These are specified/proposed dossiers unless production paths are independently found; do not label them implemented because adjacent orchestration code exists.
- **Three memory layers:** durable lessons/KB (`src/substrate/kb/*`), durable engineering memory/nonconformance/failure records (`src/factory/memory/*`), and volatile session continuity (`pi-ext/factory-watch/src/session-memory.ts`, policy, and feeds). Explain `/remember`, `/factory-context`, `python -m factory.memory`, and deprecated `src/factory/kb/` wrappers separately.
- **Context engineering:** context packets, code-context injection, task preambles, session policy, bounded context, and what is volatile versus canonical (`src/factory/orchestrator/context_packet.py`, `pi-ext/factory-watch/src/context-packet.ts`, `code-context-inject.ts`, and `task-preamble.ts`).
- **Incremental change workflow:** delta computation/checkpoints/freshness, `factory.commands.catchup`, and preflight checks; teach “what changed since the checkpoint?” as distinct from generic staleness.
- **Bootstrap/trust:** packaging/configuration, `/factory-init`, `scope-guard`, child-worker behavior, project trust, and fail-closed write boundaries.

### Phase C — source reconciliation

11. Build a row per capability/tool/workflow/technique with: identity, newcomer explanation, use case, inputs, outputs, production entry point, code paths, tests, schema/config, spec source, plan source, observed CLI result, lifecycle state, verification state, health dimensions, freshness, and open escalation.
12. Compare specs to production call paths and tests. Mark “specified but not implemented,” “implemented but unspecified,” “planned but already shipped,” “dead/unwired,” and “contradicted” explicitly.
13. Compare plans to `git` and runtime rather than checkboxes; record stale plans and superseding sources.
14. Reconcile Coherence health with normal exploration. Explain why an item can be implemented while `SR satisfied`, executed evidence, validation scenarios, or human review remains zero.
15. Reconcile the course inventory itself: every learner note must point to a real node or explicitly carry `unknown/human decision required`; no orphaned concepts.

Never satisfy course coverage by adding artificial SR/spec links. If all referenceable nodes remain required by the checker, author real lessons; if some are catalog-only or out of scope, obtain an explicit owner-approved disposition/schema before using that classification.

### Phase D — author, visualize, verify

16. Author the landing map and glossary first, then the ontology and repository anatomy, then the workflows in dependency order. Every lesson starts with “If you are new, the short answer is…”.
17. Add the command decision tree and one worked path per core workflow: trace gap disposition, requirement/register inspection, feature briefing, reverse navigation, evidence/validation inspection, health triage, execution/recovery, and human review. The first exercise is read-only and runs against a throwaway fixture or disposable copy; it must never ask a newcomer to write to the real checkout.
18. Generate the visual set from the inventory ledger. Keep source data and diagrams deterministic; embed snapshot metadata and source links.
19. Run `coherence course check --project-root . --json` and fix malformed/ambiguous references or unreached authoritative nodes. A clean course check is necessary, not sufficient: it proves graph coverage, not newcomer comprehension.
20. Re-run targeted tests/gates for any claim that changed, then run a manual newcomer walkthrough and a human owner review. Record unresolved questions instead of filling them with prose.

---

## 6. Status, health, and verification presentation rules

Every capability page must include the following compact panel:

| Field | Meaning |
|---|---|
| What it is | Plain-language definition for a new contributor |
| Why it exists | Concrete user/problem/use case |
| How to invoke it | Exact CLI, Pi command, tool, or file workflow |
| What it reads/writes | Canonical, derived, runtime, and external side effects |
| Implemented? | Production-path status, never inferred from a plan |
| Verified? | Test/command/evidence and timestamp |
| Health impact | Dimensions/classes it can affect, with current values if measured |
| Freshness | Current/stale/unknown and the dependency causing it |
| Spec/plan | Exact source anchors, clearly labeled as intent or design |
| Escalation | Blocking human question, if any |

The underlying claim record should carry `claim_id`, `subject_ref`, `claim`, `claim_type`, the status axes above, source entries (`kind`, `path`, `locator`, checkout, fingerprint, captured timestamp), evidence (`command`, cwd, exit code, raw-output reference, artifact hash), freshness, health dimensions, escalation reference, and owner. This record is the audit trail; prose is a projection.

Health must be shown as a vector and as beginner language:

- `requirement_quality`: “Are requirement records well-formed and meaningful?”
- `decomposition_allocation`: “Are requirements allocated to a feature/dossier?”
- `implementation_trace`: “Can declared requirements be followed to implementation?”
- `verification_strategy`: “Does each requirement say how it should be checked?”
- `executed_evidence`: “Did the stated check actually run and leave evidence?”
- `validation_scenarios`: “Was the behavior checked in an appropriate scenario?”
- `evidence_freshness`: “Does the evidence still describe the current inputs?”
- `suspect_relationships`: “Are declared relationships trustworthy rather than stale/suspect?”
- `nonconformance_closure`: “Are known failures linked to an owned correction?”
- `deferrals_waivers`: “Are gaps explicitly disposed of, with reasons?”
- `human_review`: “Did a real human make the decisions that cannot be automated?”

The course must explicitly teach these non-equivalences:

- plan checkbox ≠ implementation;
- code exists ≠ requirement is satisfied;
- test passed ≠ the right requirement was tested;
- operational `done` ≠ assurance complete;
- empty evidence ≠ implementation absent;
- deferred ≠ healthy;
- a generated diagram ≠ a verified architecture;
- an LLM/skill/MCP/tool response ≠ acceptance authority.

The classroom must also explain the implemented grill semantics in `src/factory/orchestrator/grill.py`: `agreed`, `skipped`, and `not-agreed` all proceed; timeout becomes `not-agreed`; and `not-agreed` is surfaced in the review guide. A grill is a comprehension checkpoint and escalation signal, never proof that code, a requirement, or a gate is satisfied.

---

## 7. Mandatory escalation/grill gate

The following resolved decisions are binding for this classroom and must be reflected in the notes rather than re-opened as if they were unknown:

1. **Product boundary:** Coherence is first-class; substrate, factory, and host surfaces are supporting context, with legacy material labeled explicitly.
2. **Authority conflict:** The 2026-08-18 toolset, 2026-08-20 agentic-I/O, 2026-08-22 progressive-assurance, and 2026-08-24 release documents govern the Coherence product model; older HLR/engineering-context material is legacy unless re-authorized.
3. **Layer contradiction:** Current factory–Coherence coupling is transitional; declared architecture, observed imports, and legacy shims remain separate facts until a future architecture decision.
4. **Obsidian authority:** Obsidian is projection-only; repository Markdown and deterministic CLI output remain canonical.
5. **Health objective:** This initiative documents and visualizes health; health repair is a separate human-consented track.
6. **Built-but-unwired behavior:** Teach `using-coherence` according to its implemented deterministic read-only scope; the interactive teaching/action surface is a separate design gap.
7. **Roadmap boundary:** Console A/B/C and Hermes MCP are roadmap-only and are not promoted by this initiative.
8. **Evidence standard:** Use production path + focused test + live command/fixture when feasible; label weaker verification explicitly.
9. **Visual acceptance:** All eight proposed visual explainers are required for the first review.
10. **Human review:** Topic-specific agents may critique coverage and semantics; the owner performs the final human review.
11. **Newcomer evaluator:** The owner is the newcomer evaluator and will attempt the exercises without relying on project-history context.

The following questions remain intentionally blocking. Do not infer answers from silence, existing prose, or a passing command. Present the full context and ask for an explicit decision:

12. **Dirty worktree ownership:** Which currently modified/untracked paths are protected from this effort? No cleanup or broad formatting is permitted to make the inventory look cleaner.
13. **Course-check scope:** Must every one of the current 49 SRs and 64 specs receive substantive coverage, or will the owner approve a `catalog_only`/`out_of_scope` disposition that the checker and classroom both understand? Artificial links are prohibited.
14. **Status schema ownership:** Are the lifecycle/observation/verification/source/material/escalation axes above the canonical classroom schema, and who may change their allowed values?
15. **Refresh policy:** What source-path/content/registration/schema/CLI-behavior fingerprint event makes a lesson or diagram stale, and what exact regeneration mechanism should be used?
16. **Exercise write policy:** Are all exercises fixture-only/read-only, with real-checkout writes requiring separate explicit approval?
17. **Visual dependencies/accessibility:** Are offline-safe visuals mandatory, with no color-only meaning and readable labels, keyboard/reduced-motion consideration, and explicit contrast requirements?
18. **Historical assets:** Should the generated system-traceability classroom and older course visuals be retained as dated snapshots, regenerated, or marked superseded?
19. **Projection ownership:** Which vault location should receive the projection, and may generated Obsidian notes be committed to the repository?
20. **Stable IDs:** What stable identity policy should apply to specs, plans, lessons, concepts, diagrams, and code/symbol projections when filenames are not authoritative IDs?
21. **Course graph authority:** Should course traceability eventually become a compiled obligation, or remain a separate course-checker concern?
22. **Visual format:** Should the eight visuals use SVG/HTML, Obsidian Canvas, Excalidraw, or a controlled combination, and which source format is editable versus generated?
23. **Code projection granularity:** Should code/symbol nodes be exposed individually, or only embedded as evidence inside feature/workflow dossiers?
24. **Review identity:** What canonical identity/schema links human-review decisions to SRs, gates, runs, and observations?
25. **Transcript/privacy policy:** What session transcript retention, redaction, and access policy applies to classroom evidence and review handoffs?
26. **Label maintenance:** How are live/roadmap/historical labels updated and reviewed when implementation moves faster than course material?

Each open question receives a durable decision record with `decision`, `rationale`, `owner`, `date`, `sources`, and `supersedes`. Unanswered questions remain visible as escalations in the landing page.

---

## 8. Verification and acceptance gates

### Gate 1 — Inventory completeness

- Every supported CLI group/subcommand and direct module entry point appears in the inventory.
- Every production Pi command/tool and every extension is mapped.
- Every source package, schema family, gate script, major test family, and state directory is represented.
- The report distinguishes generated/derived assets from canonical assets.
- A completeness script reports zero unclassified entries, except rows explicitly marked `unknown` with an escalation.

### Gate 2 — Evidence integrity

- Every “implemented” row has a reachable production path.
- Every “verified” row names a real test/command/evidence artifact and timestamp.
- Every “specified” or “planned” row names its exact source anchor.
- Contradictions and stale evidence are displayed, not resolved by wording.
- No secrets, tokens, credentials, or connection strings are copied into notes, diagrams, snapshots, or reports.

### Gate 3 — Course integrity

Run:

```bash
uv run coherence course check --project-root . --json
```

Expected: `ok: true`, no parser errors, no unknown node references, and no unreached referenceable SR/spec nodes. Non-referenceable nodes, if ever reported, must be explained rather than hidden.

### Gate 4 — Runtime/health truthfulness

Re-run:

```bash
uv run coherence navigate health --repo-root . --json
uv run coherence status --project-root . --json
uv run coherence register check --project-root .
uv run coherence trace check --project-root .
```

Expected: the notes show actual exit codes and outputs. A failing health/register/trace result is allowed and informative; the classroom must not alter the implementation or records just to turn the display green.

### Gate 5 — Newcomer comprehension

A new contributor must be able to answer, without author assistance:

1. What problem does Coherence solve?
2. Which artifact owns intent, requirement, plan, implementation, evidence, and review?
3. Which command answers “what is missing?” versus “did it run?” versus “is it stale?”
4. Why can an implemented feature have zero satisfied SRs?
5. What does a trace gap disposition change, and what does it not change?
6. Where is the human decision boundary?
7. How do they follow one feature from intent to code to evidence?
8. Which claims are roadmap-only or contradictory?

The walkthrough records confusion points and creates fixes or escalations; it does not silently rewrite the model.

### Gate 6 — Visual integrity

- Every diagram has a legend, source links, date, and status/lifecycle legend.
- Diagram edges are declared/observed/planned by style, not all rendered alike.
- The architecture visual shows the current import contradiction.
- Health visuals show dimensions rather than one misleading scalar.
- HTML/SVG assets render in a modern browser and are linked from course notes.
- Excalidraw files, if used, contain readable labels and no tiny text.

### Gate 7 — Final independent review

Use two independent reviews:

- **Coverage/reconciliation review:** searches for missing tools, workflows, assets, command paths, and source disagreements.
- **Newcomer/quality review:** checks explanations, visual clarity, claim labels, security/redaction, and whether the course teaches actions rather than merely naming modules.

Fix findings in fresh context and repeat until both reviewers are silent or the owner accepts a documented exception. Then perform one holistic review across the whole classroom graph.

---

## 9. Likely files and boundaries

### Documentation/visual files expected to be created or modified after approval

- `docs/course/*.md` — learner-facing, trace-linked lessons.
- `docs/visual-explain/*.md` and/or committed HTML/SVG/Excalidraw assets — only if the existing source/loader conventions are confirmed first.
- `docs/superpowers/plans/2026-08-31-coherence-knowledge-base-classroom.md` — this canonical plan.
- `.hermes/plans/2026-08-31_131338-coherence-knowledge-base-classroom.md` — session plan copy.
- Optional, only after design approval: a deterministic inventory/report generator under `scripts/` and its tests; this is not authorized by the current planning turn.

### Files explicitly out of scope for this planning turn

- All `src/` implementation code.
- `pi-ext/` behavior and package wiring.
- Requirements/SR authoring, bundle creation, evidence creation, or health repair.
- `.factory/`, `sessions/`, task ledgers, and user worktrees.
- External Obsidian vault contents.
- Git commits, pushes, merges, or history rewriting.

If later work needs any excluded surface, create a new approved task with exact scope and a human gate.

---

## 10. Recommended execution order after approval

1. Resolve Section 7 questions and record decisions.
2. Capture a clean, timestamped baseline and protect dirty paths.
3. Build the machine inventory and observed import/registration graphs.
4. Reconcile the authoritative spec/plan hierarchy and generate the contradiction ledger.
5. Author the glossary, ontology, and course map.
6. Author tool/workflow lessons in dependency order.
7. Generate the eight visual explainers with explicit status legends.
8. Add worked exercises and symptom-to-command routing.
9. Run course, CLI, test, and visual gates.
10. Conduct independent coverage and newcomer reviews; fix until silent.
11. Present the remaining escalation ledger for human decisions.
12. Only then decide whether to create a separate implementation plan for any missing/interactive Coherence capability.

**Definition of done:** A newcomer can navigate the repository and choose the correct workflow from a symptom; every claimed capability has provenance and an honest lifecycle/health state; course references pass the deterministic course checker; visuals agree with the inventory; known contradictions and gaps are visible; and unresolved semantic matters are explicitly waiting on the human rather than being guessed.
