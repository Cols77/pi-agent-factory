# Handoff — Engineering Context Increment 7 (Context Delta + Freshness Reconciliation)

**Created:** 2026-08-16
**Branch / worktree:** `feature/increment-07`
**Worktree path:** `C:/Users/33630/.config/superpowers/worktrees/pi-agent-factory/increment-07`
**Plan:** `docs/superpowers/plans/engineering-context/increment-07-context-delta-validation.md`
**Dev/review prompts:** `docs/superpowers/plans/engineering-context/prompts/increment-07-{dev,review}.md`
**Based on:** `feat/system-comprehension-layer` HEAD `bf63d7f` (Inc 1–6 landed, SP-B browser landed).
**Engine note:** tree-sitter engaged — the `code-index` extra was synced in the worktree venv;
`preferred_engine()` reports `tree-sitter` (per-language packages ABI-match; `tree_sitter_languages`
bundle is ABI-mismatched and the code prefers per-language packages). The 6 previously-failing
tree-sitter/gate tests now pass.

## What is DONE and committed (11 commits from `bf63d7f`)

| Commit | Task |
|---|---|
| `7f5fde5` | Task 1 — developer checkpoint store (`.pi/checkpoints.json`, recorded never inferred) |
| `ec8e1f4` | Task 2 — deterministic `compute_delta` (git + goals + sim; spec §31 block) |
| `203c2bd` | Task 3 — `/catchup` command + `query_catchup` + `factory.system catchup` + Catch-me-up view tab |
| `3e9dd8a` | Task 4 — `VERIFICATION_STALE` goal-aware requirement status (live checksum, spec §30 A→C) |
| `f659f8a` | Task 5 — `vcycle_health` derived-impact probe + health-payload findings |
| `93b0ff8` | Tasks 5c/5d/5e/5f/5i/5j/5m — dependency provenance + transitive impact + refresh policy + reconcile + closure + loop protection |
| `4b00e7d` | Tasks 5k/5b(py) — `/catchup` freshness integration (ContextDelta invalidated/auto_refreshed/refresh_required/blocked_refreshes/closure) + feature diagram in query_catchup |
| `93cd1ac` | Tasks 5l/5n/5o — `freshness_health` findings + historical preservation tests + thin-slice acceptance (Test A/B) |
| `ee56057` | Task 5b/5k(ts) — Catch-me-up view: freshness section + D7 diagram embed + Verify-my-understanding (D8) |
| `50e5a72` | Task 6 decision (skip index, measured) + all plan checkboxes ticked + pyright fix |

All 24 plan checkboxes ticked. Reviewer sub-agent could not be dispatched (the `subagent` tool is
broken in this environment — every dispatch fails `(no stderr)`, same as Inc 4/6); the review was
performed inline against `prompts/increment-07-review.md` — no findings left open, full suites green.

## What the increment adds

**Deterministic "since your last review" (spec §31 / §9.4):**
- `src/factory/delta/{checkpoint,compute,freshness}.py` — checkpoint store; `ContextDelta`
  (PRs, changed requirements, added ADRs, new experiments, goal transitions, metric deltas, open
  items) + 5k freshness fields (invalidated / auto_refreshed / refresh_required / blocked_refreshes /
  freshness_closure_reached); `apply_freshness` feeds changed refs through the impact graph and a
  bounded, fingerprint-VERIFIED reconcile (never trusts that an action ran).
- `/catchup` extension command (runs the delta CLI, opens the Catch-me-up view) + `python -m
  factory.delta catchup` + `factory.system catchup --feature X`.

**Goal-aware status (spec §28–§30):** `requirement_validation(goals, *, stale=...)` gains
`VERIFICATION_STALE`; `query_validation` recomputes staleness LIVE from the register checksum
(`is_checksum_current`) so a statement change flips the derived status immediately (A→C).

**Freshness engine (HLR-09, D9) — new `src/factory/freshness/{deps,policy}.py`:**
- Declared/authoritative artifact dependency edges from run manifests (requirement→evidence,
  implementation→evidence, metric-definition→evidence, requirement→implementation), explainer
  fingerprints (SR + code + diagram + generator), diagram `illustrates` + `dep_fingerprint`.
- `check_artifact` → fresh/stale/UNKNOWN (missing fingerprint/source degrades, never assumed fresh).
- `compute_impact` → transitive affected-closure (cycle-protected, deterministic).
- `refresh_decision` → authoritative preserve / code ROUTE_TO_DEV / evidence RERUN_VALIDATION /
  generated REGENERATE / derived RECOMPUTE; generator/harness availability is an execution-time
  boundary (BLOCKED, never silently fresh).
- `reconcile` → bounded refresh pass that re-verifies fingerprints after executing.
- `freshness_closure` → feature coherence; ROUTE_TO_DEV code keeps closure open (5j).
- `semantically_invalidated_code` → the 5h signal driving IMPL_STALE + closure.
- `trace/explainers.py` extended additively: `code_fingerprint`, `dep_diagram`, `generator`.

**Health (Task 5 + 5l):** `vcycle_health` (trace-gap based) + `freshness_health` (IMPL_STALE,
EVIDENCE_STALE, EXPLAINER_STALE, DIAGRAM_STALE, MISSING_PROVENANCE, REFRESH_BLOCKED,
REGENERATION_FAILED, CLOSURE_UNRESOLVED) exposed via `factory.system health` /
`factory.system freshness` and the health document (`vcycle_findings` + `freshness_findings` keys).

**SCC browser:** additive Catch-me-up tab (freshness outcome, D7 diagram embed, D8 comprehension
button), wired through `system-cli.ts` `/api/system/catchup`, `system-shell.ts` renderers array,
`system-bootstrap.ts` `loadCatchupScope`.

## Key constraints honored

- D3 additive: every existing verb/test untouched. Full Python unit 1535 passed, TS vitest 1011
  passed / 2 pre-existing baseline failures (`smoke.test.ts` node-load, `system-page.test.ts`
  guide fallback), `tsc --noEmit` clean, ruff clean, pyright clean on all new code (the ~19
  pre-existing pyright errors in older modules remain).
- Determinism: no mtime, no random, no fuzzy refs, no LLM over the past; checkpoints recorded
  never inferred; `reviewed_at` on checkpoint upgrade is a recorded action timestamp.
- Reuse: `factory.freshness` fingerprints, `factory.evidence.reconcile` manifest deps,
  `factory.trace` edges/gaps, `factory.goals` registry, `factory.simulation` registry,
  `requirements.register.is_checksum_current` — no parallel checksum, no forked parser.
- SP-B boundary: browser files edited only additively after SP-B/Inc 6 landed (a new tab).
- Load-once invariant preserved: `freshness_health` threads pre-loaded nodes/edges into the deps
  engine (`collect_dependency_edges(root, nodes=, edges=)` etc.).

## Decisions / interpretations (read before extending)

- `check_artifact(code:...)` is authoritative-FRESH; semantic invalidation is a separate
  ROUTE_TO_DEV signal (IMPL_STALE + closure `route-to-dev`), never a stale code check.
- `refresh_decision` always returns the REQUIRED action (REGENERATE/RERUN) for generated/evidence
  kinds; generator/harness absence is an execution-time resource boundary that reconcile reports as
  BLOCKED (5e), not a policy change.
- `query_validation` now recomputes `stale` live (was: report's recorded flag). Same field, more
  accurate; this is the mandated D5 derived-status behavior (spec §30).
- Task 6: index SKIPPED (measured: query_catchup 0.1 ms, query_goal 2.7 ms, query_metric_history
  36 ms on `cool_physical_ai_project`; `compute_delta` ~2.7 s is a cold per-task story walk, not
  an indexable repeated read). Decision recorded in the plan.
- 5o implemented as unit tests in the factory repo on the navigation/pre-emption slice
  (FEAT-NAV-017 + SR-017 + GOAL-NAV-001 + run + diagram + explainer) — the product repo stays
  read-only per the RFC; the acceptance intent (dependency-driven, SR-special-case-free) is fully
  asserted there.
- Refresh-loop *detection at runtime* is `reconcile`'s bounded attempts; a pure query cannot
  observe it, so `freshness_health` documents it rather than fabricating a finding.

## Remaining / optional

- Task 7 Step 1 (reviewer sub-agent) — re-run once the `subagent` tool works, or accept the inline
  review (no open findings).
- The `visual-explainer` skill wiring behind the Verify-my-understanding button is prompt-only
  (D8): the button reveals the grill-understanding prompt; no quiz engine, no score.
- Pre-existing, NOT from this increment: ~19 pyright errors in older modules, 2 baseline vitest
  failures (see above).

## How to verify

- Worktree root: `uv run python -m pytest -q` (1535 passed) + `uv run ruff check .` +
  `uv run pyright src/factory/delta src/factory/freshness src/factory/commands
  src/factory/system/health.py src/factory/trace/explainers.py` (0 errors).
- `pi-ext/factory-watch`: `npm test` (1011 passed, 2 baseline fails) + `npx tsc --noEmit`.
- Manual: `/catchup FEAT-NAV-017` → Catch-me-up view; `factory.system catchup --feature
  FEAT-NAV-017`; `factory.system freshness`; `factory.system health` (freshness_findings).
