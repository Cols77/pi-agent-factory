# Handoff — Engineering Context Increment 6 (Human V-Cycle Views)

**Created:** 2026-08-16
**Branch / worktree:** `feature/increment-06`
**Worktree path:** `C:/Users/33630/.config/superpowers/worktrees/pi-agent-factory/increment-06`
**Plan:** `docs/superpowers/plans/engineering-context/increment-06-human-vcycle-views.md`
**Dev/review prompts:** `docs/superpowers/plans/engineering-context/prompts/increment-06-{dev,review}.md`
**Based on:** `feat/system-comprehension-layer` HEAD `d4b784b` (Inc 1–5 + SP-B landed; Inc 5 = presentation router).

## What is DONE and committed (8 commits from `d4b784b`)

| Commit | Task |
|---|---|
| `75f9ed3` | chore(typecheck) — pre-existing tsc breakage from the parallel session's `524b861` (3 files: `factory-init-command.ts` missing `{ root }`, `pi-types.ts` alias drift vs SDK, `system-page-dom.test.ts` `noUncheckedIndexedAccess`) |
| `7ebb959` | Task 1 — Feature Dossier tab |
| `bb19731` | Task 2 — Interactive V-cycle tab (+ additive `statuses` in `query_vcycle`) |
| `d07bdd3` | Task 3 — Goal / metric status tab |
| `fffd6a6` | Task 4 — Validation evidence tab (+ new `factory.system validation --scope sr:X`) |
| `bed5cb3` | Task 5 — Simulation-run summaries tab (+ additive `metrics`/`recording`/`recorded_ts` in `_sim_run_payload`) |
| `d8b30b2` | Task 5b — Diagram view (D7) + D8 comprehension entry point |
| `17de10d` | Task 6 — Navigation integration (AC-02 / AC-09) |

All plan checkboxes ticked except Task 7 Step 1 (reviewer sub-agent). Reviewer dispatch
was attempted but the `subagent` tool is unreliable in this environment (same known
breakage as Inc 4's handoff); the review was performed inline against
`prompts/increment-06-review.md` instead — no findings left open, full suites green.

## What the increment adds (all additive tabs on the /system SCC browser)

Five human engineering-context views + a diagram view, each a pure data→DOM widget
(`src/system-*.ts`) inlined into the page via `Function.prototype.toString()`, plus a
`system-page-additions.test.ts` DOM suite and per-widget jsdom unit tests:

1. **Feature Dossier** (`system-feature-view.ts`) — `feat:` scopes; renders
   `query_feature_context` verbatim (brief route dispatches feat: → dossier).
   Sections: Intent/Requirements/Design/Code/Tasks/Tests/Simulations/Goals/Recent
   changes/Open questions; null → "not recorded", empty → "none recorded".
2. **Interactive V-cycle** (`system-vcycle-view.ts`) — `feat:`/`sr:` scopes; renders
   `query_vcycle` slice + the additive `statuses` map (validation report / goal
   registry / task ledger — recorded state only). Empty bands → explicit missing
   state (spec §9.1).
3. **Goal status** (`system-goal-view.ts`) — `goal:` scopes; renders `query_goal`
   (Inc 4 eng_get_goal): state, requirements, metric+target, evidence, history (spec §9.3).
4. **Validation evidence** (`system-validation-view.ts`) — `sr:` scopes; renders the
   new `query_validation` (raw state + stale + D5 goal-aware status + goals + runs + metrics).
5. **Simulation-run summaries** (`system-sim-view.ts`) — `sim:RUN-...` scopes; renders
   `query_simulation_run` (§20 fields + metrics + recording link); missing recording
   degrades visibly.
6. **Diagram** (`system-diagram-view.ts`) — `diag:` scopes; embeds/link-targets the
   canonical committed HTML (D7 — never a re-derived graph); missing HTML → explicit
   "missing diagram".
7. **D8 comprehension entry** — "Verify my understanding" button on the dossier
   (reveals the grill-understanding prompt; no quiz engine, no score).
8. **Navigation (AC-02/AC-09)** — `a.scope-open` anchors rendered by the widgets; one
   delegated handler in the bootstrap navigates within the SPA; requirements land on
   the V-cycle tab via an `intendedTab` param threaded through `loadScope`.

## Python (additive only, D3)

- `src/factory/system/queries.py`:
  - `query_vcycle` gains additive `statuses` (per-node recorded state).
  - `query_validation` (new; sr: only) — validation report + `requirement_validation`
    (VALIDATED/REGRESSED/VERIFICATION_PENDING) + runs + metrics.
  - `_sim_run_payload` gains additive `metrics` (bundle metrics.json, tolerant) +
    `recording` (repo-relative manifest path or null) + `recorded_ts`; all 4 call
    sites pass `repo_root`.
- `src/factory/system/cli.py` — new `validation` verb + renderer; nothing v1 touched.

## Key constraints honored

- D3: every v1 test stays green (TS 981 + Python 1425). Two v1-behavior decisions to
  note: (a) `feat:` scopes no longer crash `loadBundleScope` (the claim-less dossier
  broke `renderBrief`); the dossier renders on the Feature tab instead. (b) the
  `pushScope` hash experiment was reverted — the pinned Back/Forward test owns that
  URL behaviour; the AC-09 tab intent is threaded via `loadScope`'s optional
  `intendedTab`, not the URL hash.
- Inlining rule: only *functions* are inlined into the page — every widget keeps maps
  (`bandLabel`, `stateClass`, `GOAL_STATE_CLASS`...) inside functions, and every helper
  a widget calls is exported and listed in the shell's renderers array (module-level
  consts/helpers otherwise become dangling references).
- Python computes, TS renders verbatim; no TS re-derivation of state, no fuzzy refs,
  no mtime/random ordering; 12px font floor respected (visual-identity gate).

## Remaining / optional

- Task 7 Step 1 (reviewer sub-agent) — re-run once the `subagent` tool works, or accept
  the inline review.
- Pre-existing, NOT from this increment: ~19 pyright errors and 2 vitest failures in
  MAIN (parallel session's `524b861` / `feat/req-validation-1c` worktree); the `75f9ed3`
  typecheck fix is on this branch and keeps `tsc --noEmit` clean here.
- Parallel-session uncommitted files in MAIN (system-bootstrap/comprehension/renderers.ts,
  uv.lock, test_remediation.py) — never `git add -A`.

## How to verify

- Worktree root: `uv run python -m pytest -q` (1425 passed) + `uv run ruff check .`.
- `pi-ext/factory-watch`: `npm test` (981 passed) + `npx tsc --noEmit`.
- Manual: `cd pi-ext/factory-watch && npm run dev` (or the extension's `/system` route),
  open `?scope=feat:FEAT-NAV-017` (Feature tab), click a requirement chip's "open"
  anchor → `sr:` scope on the V-cycle tab (AC-09).
