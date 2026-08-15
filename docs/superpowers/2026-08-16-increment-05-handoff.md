# Handoff — Engineering Context Increment 5 (Presentation Router)

**Created:** 2026-08-16
**Branch / worktree:** `feature/increment-05`
**Worktree path:** `C:/Users/33630/.config/superpowers/worktrees/pi-agent-factory/increment-05`
**Plan:** `docs/superpowers/plans/engineering-context/increment-05-presentation-router.md`
**Dev/review prompts:** `docs/superpowers/plans/engineering-context/prompts/increment-05-{dev,review}.md`
**Based on:** `feat/system-comprehension-layer` HEAD `c3f1808` (Inc 1–4 + SP-B landed).

## What is DONE and committed (4 commits from `c3f1808`)

| Commit | Task |
|---|---|
| `13d38d5` | Task 1 — levels + noise policy |
| `c350b6e` | Tasks 2–3 — router + traversal guard + ide/browser/sim adapters |
| `8045a9a` | Task 4 (python) — `present` CLI + delegate `system present` |
| `1f24bae` | Task 4 (ts) — point `eng_present` at the router |

### New package: `src/factory/presentation/`
- `level.py` — `Level` (INSPECT/PRESENT/REVIEW), `Facts`, pure `decide(Facts)->Level`
  (spec §23–§24), strict `parse_level`.
- `ide.py` — traversal-guarded `resolve_repo_file` + `build_ide_uri` (`vscode://file/…?line=N`).
- `browser.py` — SCC-browser adapter: every scope → `system?scope=<ref>` Brief page (D2; V-cycle/
  Dossier/Goal pages land in Inc 6) with a degrade note; `diag:<id>` → canonical committed diagram
  HTML (D7) via `query_diagram`, degrading to Brief when unavailable.
- `sim.py` — `RUN-<ts>`/`run:<id>` → durable evidence bundle (spec §20) + honest "viewer in Inc 6" marker.
- `router.py` — `resolve_intent`, `dispatch`, `present` (§22 mapping, default INSPECT, `--level`/`facts` override).
- `cli.py` + `__main__.py` — `python -m factory.presentation present <artifact> [--focus F][--level L] --repo-root R [--json]`.
- Tests: `tests/unit/presentation/{test_policy,test_router,test_ide,test_cli}.py` (40 tests).

### Wired in
- `factory.system.cli.cmd_present` now delegates to the router (keeps the exact
  `PresentResult` JSON shape the pi-ext tool consumes); added `--level`.
- `pi-ext/factory-watch`: new `buildPresentationCommand`, `loadSystemPresent` now invokes
  `factory.presentation`; `formatPresent` renders adapter/target; `eng_present` description
  updated to reflect routing.

## Verification (all green in the worktree)
- **Python unit suite:** 1405 passed, 1 skipped, 40 deselected (baseline 1364 → +40 new).
- **factory-watch TS suite:** 908 passed, 1 skipped, 0 failed.
- `ruff check .` clean; `tsc --noEmit` clean.
- Plan checkboxes Tasks 1–5 ticked.

## Review outcome (Task 5)
**COMPLIANT** vs spec §22–§24 and D3 additive rule. Checked: §22 mapping (sr→V-cycle,
feat→Dossier, file→IDE line, run→sim@event), §23 levels, §24 noise policy (unit pass stays
INSPECT; failure/reached → PRESENT; explicit checkpoint → REVIEW), traversal/URI-injection
guard, D7 (`diag:` → canonical HTML, never TS-re-derived), reuse (parse_scope_ref, query_diagram,
sim registry — no forked parser), determinism (exact refs, no random/mtime), additive-only
(only the Inc-4 `present` stub body superseded; no v1 verb touched).

### One honest boundary (not a violation)
Actual *opening* of the interface (browser navigation / IDE open) is performed by the caller —
`eng_present` returns the resolved `target` and Inc 6/SP-B renders it. This matches the plan's
own framing ("the pi-ext caller / Inc 6 performs the actual open") and the Inc 5 acceptance
("present() resolves to the correct adapter/level … NO accidental application focus change").

## Remaining (next increments)
- **Inc 6 — Human Engineering Context UI**: the V-cycle / Feature Dossier / Goal pages the
  browser adapter degrades to (target `system?scope=<ref>` already points at the `/system` route).
- **Inc 7 — context delta + freshness**; **Inc 8 — durable memory**.

## Finishing / merge
Follow `finishing-a-development-branch`: rebase `feature/increment-05` onto latest main, verify
full suites, merge back to `feat/system-comprehension-layer`, remove the worktree. Coordinate
timing with the concurrent main session (uncommitted code-index / comprehension files stay in
main; do not `git add -A`).
