# Coherence Increment Implementation Analysis

## Executive Summary

> **⚠ STALE as of 2026-09-01 (NC-E).** This document reports Increments 5 and 6 as unmerged
> feature branches and 7/8 as not started. Verified against `main` on 2026-09-01:
> `src/coherence/{status,focus,explain,router}.py`, `src/coherence/gate/`,
> `src/coherence/{inbox,deferrals,staleness}.py`, `src/coherence/runs/`,
> `src/coherence/course/`, `src/coherence/register/markers.py` and
> `src/factory/memory/baseline.py` are all present. **Increments 5, 6, 7 and most of 8 have
> landed.** Do not trust the Ship Status Matrix below without re-verifying against `main`.


The Coherence programme has implemented **2B, 2C (CI obligations), 3B, and 4 on `main`**, with **Increment 5 and 6 in parallel feature branches** (`feat/coherence-increment-{5,6}`) that are **not yet merged**. The current checked-out branch is `docs/coherence-progressive-assurance-design` — a documentation branch on main. Two worktrees are actively being developed in parallel.

### Ship Status Matrix

| Increment | Planned Scope | Shipped on `main`? | Branch Status |
|-----------|--------------|-------------------|---------------|
| 0 | Evidence register | ✅ Yes | — |
| 1 | Substrate extraction | ✅ Yes | — |
| 1B | Neutral substrate extraction | ✅ Yes | — |
| 1C | Codemap / KB signatures | ✅ Yes | — |
| 2 | Trace / register | ✅ Yes | — |
| 3 | Navigate / present / goals / sim | ✅ Yes | — |
| **2B** | Progressive-assurance foundation (obligations, `NC-*`, CI) | ✅ Yes | Merged to main |
| **2C** | CI obligation consumer | ✅ Yes | Merged to main |
| **3B** | Obligation-aware views | ✅ Yes | Merged to main |
| 4 | Audit / measurement (observations) | ✅ Yes | Merged to main |
| 5 | Status / focus / dispatcher | ❌ No | `feat/coherence-increment-5` (9 commits ahead) |
| 6 | Gate protocol / inbox / staleness | ❌ No | `feat/coherence-increment-6` (13 commits ahead, includes Inc 5) |
| **6B** | Thin vertical slice (dogfood) | ❓ Planned | No branch yet |
| 7 | Unified long-run surface / mission-control | ❓ Planned | No branch yet |
| 8 | Artifact families (specs/courses/SR markers) | ❓ Planned | No branch yet |

---

## Increment-by-Increment Implementation Analysis

### Increment 0 — Evidence Register
- **Git:** Shipped and merged.
- **Execution quality:** Excellent. Landed the foundational distinction between missing and empty evidence, making `evidence record` resolvable. This was the critical correctness fix that unblocked the entire programme.
- **Gap addressed:** FEAT-NAV-017's audit returned a blank result because two satisfying tasks (`T-058`, `T-067`) had no run manifests at all — the audit conflated this with "ran and touched nothing." Increment 0 corrected this and was verified by re-auditing FEAT-NAV-017.
- **Test coverage:** `test_audit_parallel.py` and NC-0001 nonconformance record exist on the current branch.

### Increment 1 — Substrate Extraction
- **Git:** Shipped and merged.
- **Execution quality:** Solid. The three-layer architecture (`factory` → `coherence` → `substrate`) is enforced: `substrate` modules do not import `factory` or `coherence`. Shims with `DeprecationWarning` maintain backward compatibility for consumer repos. `src/substrate/` contains all the extracted shared modules.
- **Key files on main:** `src/substrate/{artifacts,observations,projections}.{py}`, `src/substrate/{paths,config,schemas}/`, `src/substrate/{agents,codemap,evidence,freshness,kb,ledger,documents,validators}/`.

### Increment 2B — Progressive-Assurance Foundation
- **Git:** Shipped and merged. 13 commits on main, including the core policy machinery.
- **Execution quality:** Excellent. The `Obligation` contract, `ci_verification` + `task_justification` compiler, and `NC-*` nonconformance records are all in place. The commit `bfc84fb` ("correct task_no_sr text drift + minor findings (2B fix wave)") shows active correction post-merge.
- **Key files on main:** `src/coherence/policy/{__init__,ci,compiler}.py`, `src/substrate/policy/{__init__,obligation,vocabulary}.py`, `src/factory/memory/nonconformance.py`, `src/substrate/schemas/nonconformance.schema.json`.
- **CI integration:** `tests/integration/test_ci_workflow_dry_run.py` tests `required_ci_commands` against the repo's actual config, and `tests/unit/coherence/policy/` covers both CI compilation and obligation compilation.

### Increment 2C — CI Obligation Consumer
- **Git:** Shipped and merged as the `feat/coherence-increment-2c` branch into main.
- **Execution quality:** Strong. Parallel per-SR audits implemented (`c689937`), obligation-driven GitHub Actions workflow (`adc11e4`), CI exit-5 semantics aligned (`dca17c4`, `cf1f57a`). The CI obligation compiler reads the compiled obligation set (`30ba9c9`).
- **Test coverage:** `test_audit_parallel.py`, `test_ci.py`, `test_compiler.py` all present.

### Increment 3B — Obligation-Aware Views
- **Git:** Shipped and merged.
- **Execution quality:** Good. The `obligations` subcommand, `present --why-required`, and obligation-aware goal/sim views are implemented. `navigate/obligations.py` and `navigate/present.py` are on main. Typed lifecycle edges (`a39df20`) and `task_no_sr` corrections are included.
- **One issue:** `9e76e81` restored an uncommitted amendment to the 3B plan, suggesting the plan was updated mid-flight — minor process noise, not an implementation defect.

### Increment 4 — Audit / Measurement / Observations
- **Git:** Shipped and merged (31 commits on main).
- **Execution quality:** Excellent. Audit and measurement groups are exposed, measurement observations migrated, audit uses codemap overlap, parallel deterministic SR review implemented, policy-bound auto-rerun (`f39c020`), final-review gaps closed (`f1066d1`).
- **Key files on main:** Full `src/coherence/audit/` and `src/coherence/measurement/` directories (15 files each), `src/coherence/navigate/obligations.py`.

### Increment 5 — Status / Focus / Dispatcher
- **Git:** **NOT on main.** 9 commits on `feat/coherence-increment-5` branch.
- **Execution quality:** Solid for what's implemented. The deterministic phrase-to-intent router (`971e557`), coherence status CLI (`cd89b34`), session focus (`61a689d`), explain (`61a689d`), health dimensions (`39903e7`, `91c4aff`), and `factory-doctor` → `factory-selfcheck` rename (`51ef9c7`) are all present.
- **Test coverage:** `test_status.py`, `test_focus.py`, `test_router.py`, `test_explain.py`, `test_health_dimensions.py` all present and passing (54 tests pass in `tests/unit/coherence`).
- **Worktree:** `C:/coding/pi-agent-factory-wt/coherence-5` is at HEAD of this branch, clean (no uncommitted changes).

### Increment 6 — Gate Protocol / Inbox / Staleness
- **Git:** **NOT on main.** 13 commits on `feat/coherence-increment-6` (extends Inc 5, which is its base).
- **Execution quality:** Strong. The gate protocol with explicit decision persistence is the headline feature: `src/coherence/gate/{__init__,model,service,store}.py` (4 files, 693 lines) plus `tests/unit/coherence/test_gate.py` (312 lines). The suspect edge (`trace/suspect.py`) and suspect-edge validity are integrated.
- **Uncommitted work:** The Inc 6 worktree (`C:/coding/pi-agent-factory-wt/coherence-6`) has **uncommitted changes to `tests/unit/coherence/test_gate.py`** — the developer is actively adding tests for decision validation (ISO `review_after` shape checking, reject-over-defer precedence, defer-only resolution). This is active in-progress work.
- **Worktree status:** `feat/coherence-increment-6` branch, 1 modified file in working tree (test additions).

### Increment 6B — Thin Vertical Slice (Dogfood)
- **Git:** **No implementation yet.** Plan documents were landed on `docs/coherence-progressive-assurance-design` branch (commit `e26ee48`).
- **Status:** The plan exists but no code has been started. Per the release strategy spec (D3), 6B is **de-gated** — it is a validation pass, not a release gate. No work appears to have begun.

### Increment 7 — Unified Long-Run Surface
- **Git:** **No implementation yet.** Plan documents exist.
- **Status:** Not started. Dependent on Inc 6 landing (gate/inbox/staleness must exist first).

### Increment 8 — Artifact Families
- **Git:** **No implementation yet.** Plan documents exist.
- **Status:** Not started. Explicitly **cuttable** per the release strategy — not load-bearing for Release A or B.

---

## Parallel PIF Sessions Analysis

There are **two active worktrees** working on coherence in parallel:

| Worktree | Branch | Status |
|----------|--------|--------|
| `C:/coding/pi-agent-factory-wt/coherence-5` | `feat/coherence-increment-5` | Clean — 9 commits ahead of main, no uncommitted changes |
| `C:/coding/pi-agent-factory-wt/coherence-6` | `feat/coherence-increment-6` | **Active** — 13 commits ahead of main (includes Inc 5 + 6), 1 uncommitted file modification (`test_gate.py` with new decision-validation tests) |
| `C:/coding/pi-agent-factory-wt/merge-main` | `main` | Clean — baseline reference |

Additional worktrees (`coherence-4`, `coherence-1c`, `legibility-fixwave`, `tool-catalog-cleanup`, `t-031-catchup-tab`) appear to be from earlier rounds and are not actively developing coherence increments.

**Key observation:** The Inc 6 worktree's uncommitted change adds test coverage for edge cases in gate decision validation (ISO date shape checking, reject-over-defer precedence, defer-only resolution). This suggests the developer is in the final test-hardening phase of Inc 6, preparing it for merge.

---

## Execution Quality Assessment

### Strengths
1. **Strict layer enforcement** — `substrate` has zero upward imports; shims preserve compatibility.
2. **Incremental delivery** — each increment is independently mergeable; 2B/2C/3B/4 are all on main without breaking the build.
3. **Test-first culture** — every new module has corresponding unit tests; the 2B fix wave (`bfc84fb`) shows tests catching implementation drift.
4. **Process discipline** — handoff documents, plan tick marks, version-controlled plans alongside code.
5. **Determinism enforced** — no mtime, no random, no LLM inference in the freshness/checksum pipeline.

### Weaknesses
1. **No 2B implementation branch exists in git history** — 2B was developed and merged directly; the `feat/coherence-increment-2b` branch has no commits unique to it (they merged into 2C). This suggests 2B was developed on what became the 2C branch.
2. **Inc 5 and 6 not merged to main** — they sit in feature branches, blocking downstream increments 7 and 8.
3. **The `subagent` tool is broken** in this environment — noted in the Inc 7 handoff as preventing reviewer sub-agent dispatch. This has been a persistent issue across increments 4 and 6.
4. **Worktree proliferation** — 10+ worktrees make it hard to track which branch is the active development head.

### Verification
- 2B/2C/3B/4 on main: fully tested (unit + integration coverage present, CI workflow green per `test_ci_workflow_dry_run.py`).
- Inc 5 on its branch: `tests/unit/coherence` — 54 tests pass, 16 deprecation warnings (from factory shims).
- Inc 6 on its branch: 1 uncommitted modification adding test coverage for gate decision edge cases.

---

## Recommendation: Next Step — Increment 6B

Given the current state, **Increment 6B** is the logical next step:

1. **Inc 5 and 6 are nearly complete** — Inc 6 is in the final test-hardening phase (uncommitted test additions in progress).
2. **6B is de-gated** (per release strategy D3) — it is a validation pass, not a release gate, so it won't block other work.
3. **6B has a clear scope** — a thin vertical slice dogfooding the full status → gate → inbox loop on the project's own repo.
4. **6B is parallelizable** — it can be developed in a new worktree while Inc 5/6 are finalized in their existing branches.

Starting 6B would: (a) validate the entire Inc 0–6 chain end-to-end, (b) produce the dogfood evidence the release strategy requires, and (c) unblock the downstream sequence (7 → 8) once 5/6 merge to main.

Increment 7 should follow once Inc 6 is merged, since it builds the mission-control layer that depends on the gate protocol and inbox being in place.