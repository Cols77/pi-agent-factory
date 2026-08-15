# Handoff — Engineering Context Increment 4 (pi-ext agent surface)

**Created:** 2026-08-15
**Branch / worktree:** `feature/increment-04` @ `ab8e602`
**Worktree path:** `C:/Users/33630/.config/superpowers/worktrees/pi-agent-factory/increment-04`
**Plan:** `docs/superpowers/plans/engineering-context/increment-04-agent-surface.md`
**Dev/review prompts:** `docs/superpowers/plans/engineering-context/prompts/increment-04-{dev,review}.md`

> **UPDATE (2026-08-16):** ALL remaining work is now DONE and committed on
> `feature/increment-04` (see "What REMAINS" -> marked complete below). The only
> step left is the coordinated merge-back to main — do NOT merge while the
> concurrent session's main working tree is dirty.

## ⚠️ Critical context before any work

1. **There is a concurrently-active session committing on the MAIN repo**
   (`C:/coding/pi-agent-factory`, branch `feat/system-comprehension-layer`). Main
   HEAD advances under you (`e8aed5b` at write time; likely more by resume).
   - **Do ALL increment-04 work in the worktree**, never in the main repo.
   - When resuming, first **rebase the worktree onto latest main**:
     ```bash
     cd C:/Users/33630/.config/superpowers/worktrees/pi-agent-factory/increment-04
     git fetch . refs/heads/feat/system-comprehension-layer
     git rebase FETCH_HEAD
     ```
     (Increment 4 builds on Inc 1–3 + SP-B, all landed; a rebase onto latest main
     keeps the eventual merge clean.)
   - Do not disturb the main repo's uncommitted files (currently
     `system-bootstrap.ts`, `system-renderers.ts`, `system-comprehension.ts`,
     `test_remediation.py`, `uv.lock`, session files). Those belong to the other session.

2. **Where my (parent) session went wrong:** the first draft of this increment was
   accidentally edited in the **main repo** instead of the worktree. It was recovered
   and transplanted here; the main repo was verified clean of my footprint. Be disciplined
   about `cd`-ing into the worktree.

## What is DONE and committed (`ab8e602`)

Committing to `feature/increment-04`, all verified green in the worktree:
- **Full Python unit suite:** 1363 passed, 1 skipped, 40 deselected.
- **Full factory-watch TS suite:** 886 passed, 1 skipped (incl. 9 new eng unit + 3 integration).
- `tsc --noEmit` and `ruff check` clean.
- `uv.lock` intentionally reverted to HEAD (a concurrent tree-sitter `code-index` entry is
  NOT mine — do not commit it with this work).

### Python backstop (`src/factory/system`)
- `queries.py`: added `query_goal_evidence(repo_root, goal_id)` → `{goal, runs[]}`.
- `cli.py`: new **additive** subcommands, existing verbs untouched:
  - `diagram <id>`
  - `sim run <run_id>` / `sim latest --feature <f>` / `sim failure --feature <f>`
    / `sim metric --metric <m>` / `sim goal-evidence --goal <g>`
  - `goal show <goal_id>` / `goal list --scope <ref>`
  - cmd fns + renderers + parser + dispatch added; all JSON on `--json`, structured stderr on error.
- Tests: `tests/unit/system/test_cli.py` (46 passed, incl. new diagram/sim/goal cases).

### TS tools (`pi-ext/factory-watch`)
- `src/system-cli.ts`: loaders `loadSystemVcycle`, `loadSystemDiagram`, `loadSystemSim{Run,Latest,Failure,Metric,GoalEvidence}`, `loadSystemGoal(sList)`.
- `src/eng-context-tool-format.ts`: `formatDiagram`, `formatVcycle`, `formatGoal( sList)`, `formatSim{Run,Latest,Failure,Metric,GoalEvidence}`.
- `src/eng-context-tools.ts`: `buildEngContextTools(deps)` + `registerEngContextTools(pi)` with 10 read-only tools:
  `eng_get_vcycle`, `eng_get_diagram`, `eng_trace_requirement`, `eng_get_latest_simulation`,
  `eng_get_latest_failure`, `eng_get_goal`, `eng_get_goals`, `eng_get_goal_evidence`,
  `eng_get_metric_history`, `eng_get_simulation_run`.
  Deps are injectable for unit tests (mirrors `system-context-tools.ts`).
- `src/index.ts`: registered via `registerEngContextTools(pi)`.
- Tests: `test/eng-context-tools.test.ts` (9 unit) + `test/eng-context-tools.integration.test.ts` (3, drives real CLI).

### Plan checkboxes ticked
- Task 1 (3/3), Task 2 (3/3), **Task 3 Step 0** (`eng_get_diagram`, read-only).

## What REMAINS (in order)

> **DONE as of 2026-08-16** — all of the below is implemented, tested and
> committed on `feature/increment-04` (1eb2098 eng_evaluate_goal; b8fe18a
> eng_present + action/read tests; 74124f5 /task preamble; 0648a63 reviewer
> outcome). Task 3/4/5 checkboxes are ticked in the plan. Only the merge-back
> (below) remains, and only once the concurrent main session is clean.


**Task 3 — Action tools behind policy** (remember: D1 pi-ext, deterministic, read-only-by-default):
- [ ] **Step 1:** `eng_evaluate_goal(goal_id)` — the ONLY tool that writes goal state. Calls the
  Inc 3 auto-eval. Inc 3 auto-eval lives at
  `src/factory/simulation/evidence.py::evaluate_goals_from_runs` (already committed via Inc 3) and
  `factory.goals.cli` `evaluate` subcommand. Return the resulting state transition. Reuse the
  `factory.goals set-state`/lifecycle (`can_transition`) so transitions are legal.
- [ ] **Step 2:** `eng_present(artifact, focus?)` — Inc 5 router is NOT landed yet. In Inc 4 it
  **records intent and returns the resolution plan**; it must validate args (artifact, optional
  focus). Do not fabricate a router — forward/declare only.
- [ ] **Step 3:** tests assert action tools are distinct from read tools (a reviewer can forbid the
  former without touching the latter). Full suite + lint + commit.

**Task 4 — `/task FEAT-...` workflow start (thin):**
- [ ] **Step 1:** minimal `/task <feat:...>` preamble replaying spec §26 steps 1–4: reconstruct
  feature context → inspect requirements → inspect active goals → determine affected design/code,
  by calling the read tools in order and printing a compact context block. Registered as a
  `pi.registerCommand("task", ...)` in `index.ts`. The `/goal` command handler (near line 1036) is a
  good template.
- [ ] **Step 2:** unit test the ordering; full suite + lint + commit.

**Task 5 — Review handoff:**
- [ ] **Step 1:** reviewer sub-agent — compliance vs spec §25 tool list + D1 (no MCP server, no TS
  re-derivation) + D3 (additive registration). Fix findings as `T-###`; update checkboxes.

**Acceptance (whole increment):**
- All spec §25 read operations callable from the cockpit as tools, returning Python-derived,
  citation-carrying JSON; exact id refs, no fuzzy fallback.
- `eng_get_feature_context` returns the AC-01 bundle in one call (NOT yet implemented as a distinct
  tool — `brief --scope feat:<id>` already returns the dossier; consider wrapping if §25 expects a
  separate feature-context tool distinct from generic artifact lookup).
- Existing v1 tools untouched and green; no standalone MCP process added (D1).

## Finishing / merge (when complete)
Follow `finishing-a-development-branch`: verify full suites → rebase onto latest main → merge the
worktree back to `feat/system-comprehension-layer`, remove the worktree, delete
`feature/increment-04`. Because the main branch has a concurrent session, coordinate timing so you
rebase+merge in one go and verify tests on the merged result.

## Reference (reused, do not rebuild)
- Tool plumbing: `system-context-tools.ts`, `trace-tools.ts`, `system-cli.ts`, `cli-runner.ts`.
- Query backends: `factory.system.queries` (Inc 1–3) — `query_feature_context`, `query_vcycle`,
  `query_goal(s)`, `query_simulation_run`, `query_latest_*`, `query_metric_history`,
  `query_diagram`, `query_goal_evidence`; `factory.trace` traversal; `factory.goals` registry/lifecycle.
- Program Architecture §6 reset: Python single source of truth, no TS re-derivation, additive-only,
  deterministic (no random/mtime), exact scope refs.
- Source spec: `C:/coding/Engineering Context, V-Cycle Navigation and Goal-Driven Validation.md` §25–27.
