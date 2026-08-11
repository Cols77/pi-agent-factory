# Increment 5 — Presentation Router (Implementation Plan)

**Status:** Draft for written review. Assumes locked D1 (pi-ext), D2 (SCC browser = primary,
Obsidian out of scope), D3 (additive), D6 (SCC upstream).
**Source phase:** Engineering Context spec §37 **Phase 5 — Presentation Router** and spec §22–§24.
**Landing repo:** pi-agent-factory (Python router + adapters; thin UI shims).
**Sub-agents:** dev=`pi -p prompts/increment-05-dev.md`, review=`pi -p prompts/increment-05-review.md`.

## Goal

A small `present(artifact, focus?, level)` router that mediates human-facing presentation,
with three levels (spec §23 INSPECT/PRESENT/REVIEW) and a noise policy (spec §24: never open
UI for every lookup). Adapters (SCC browser, IDE, simulation) are independently replaceable.
This sits behind `eng_present` (Inc 4).

## Reuse (do not rebuild)

- **Tool entry:** `eng_present` (Inc 4) is the only caller surface here.
- **SCC browser adapter:** opens the artifact in the System Control Center browser
  (`docs-server`/`system-page`, SP-B) at its page — this is the only human surface (D2); its
  V-cycle/Feature/Goal pages land in Inc 6.
- **IDE link:** a URI opener (`vscode://file/<path>?line=N`) — plain, no new dependency.
- **Simulation adapter:** first needs the run recording path from `factory.simulation` (Inc 3) +
  a viewer entry (Inc 6/browser); adapter stub here.

## Global constraints (Program §6 + D3)

- `present()` is pure intent resolution + a dispatch table; it NEVER shells out directly with
  unvalidated user strings (path traversal guard). Resolved action depends on level + adapter availability.
- Additive: no existing command changes; new `present`-specific cli subcommand only.
- Deterministic default: INSPECT (no focus change); PRESENT/REVIEW only on explicit request,
  important validation failure, or goal newly reached (spec §23/§24).

## File structure (additive)

| File | Responsibility |
|---|---|
| `src/factory/presentation/__init__.py` `router.py` | `resolve_intent`, `dispatch(level, intent)`. |
| `src/factory/presentation/level.py` | INSPECT/PRESENT/REVIEW enum + policy predicates. |
| `src/factory/presentation/browser.py` | SCC-browser adapter: resolve artifact → the SP-B docs page URL/page for the scope. |
| `src/factory/presentation/ide.py` | IDE adapter: `vscode://`/`jetbrains://` line link. |
| `src/factory/presentation/sim.py` | Simulation adapter: resolve run+focus → viewer/url (stub until Inc 6). |
| `src/factory/presentation/cli.py` | `present` subcommand (EXPOSE the router for agents/CLI). |
| `tests/unit/presentation/test_router.py` `test_ide.py` `test_policy.py` | tests. |

## Task 1: Levels + policy

- [ ] **Step 1: Failing tests** — encode spec §23/§24:
  - default level is INSPECT for any bare lookup;
  - `"show me X"` / `"where is X"` → PRESENT;
  - a significant simulation failure (goal not reached) → PRESENT the failing run (spec §24);
  - newly REACHED goal → PRESENT successful run (spec §24);
  - unit test pass → no UI (stays INSPECT);
  - an explicit feature/task review checkpoint → REVIEW (multi-artifact context).
- [ ] **Step 2: Implement** `Level` enum + `decide(dialect_intent-ish, facts) -> Level` pure function.
- [ ] **Step 3:** full suite + lint + commit.

## Task 2: Artifact → target resolution + path traversal guard

- [ ] **Step 1: Failing tests** — artifact refs (`feat:`/`sr:`/`goal:`/`metric:`/file path) resolve
  to a concrete adapter target; a `../../etc/passwd` style path resolves to `None`/error, never a shell call.
- [ ] **Step 2: Implement** `resolve_intent(artifact, focus, repo_root) -> ResolvedIntent{level, adapter, target}`.
  Keep the spec §22 mapping (`present(artifact=...) → SCC-browser V-cycle / dossier / IDE line / sim@event`).
- [ ] **Step 3:** full suite + lint + commit.

## Task 3: Adapters (IDE + SCC browser + sim)

- [ ] **Step 1: IDE** — given a resolved file+line, build a sanitized URI and hand it to the
  cockpit's existing opener (proven non-exec for non-file inputs).
- [ ] **Step 2: SCC browser** — resolve to the SP-B docs page for the artifact's scope (V-cycle/
  Feature/Goal page landed in Inc 6); this is the sole human surface (D2). Never error loudly
  when the page is not yet built — degrade to the scope's Brief page.
- [ ] **Step 3: Simulation** — resolve run+focus to a viewer URL/entry point; stub returns the
  run's evidence path + a "viewer in Inc 6" marker until Inc 6 lands the viewer.
- [ ] **Step 4:** full suite + lint + commit.

## Task 4: `present` CLI + wire into `eng_present`

- [ ] **Step 1:** `python -m factory.presentation present <artifact> [--focus F] [--level L] --repo-root R`
  for headless/agent use (returns the resolved action as JSON).
- [ ] **Step 2:** point `eng_present` (Inc 4) at this CLI; action tools stay gated (only present/evaluate are actions).
- [ ] **Step 3:** full suite + lint + commit.

## Task 5: Review handoff

- [ ] **Step 1:** reviewer sub-agent — compliance vs spec §22–§24 (levels, noise policy, no UI for
  every lookup, traversal safety) + D3 additive rule.

## Acceptance for Increment 5

- `present()` resolves to the correct adapter/level for every spec §22 example with NO accidental
  application focus change at INSPECT, and NO shell/URI injection (guard tested).
- Adapters are independently replaceable (interface boundary tested).
- v1 suite green; additive only.
