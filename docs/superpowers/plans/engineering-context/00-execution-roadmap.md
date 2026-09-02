# Execution Roadmap — System Control Center ⇄ Engineering Context v2

**Date:** 2026-08-11
**Status:** Live orchestration view. Single source of truth: `00-program-architecture.md` (§4 order, decisions D1–D6, reuse rules §6).
**Repos:** `pi-agent-factory` (the factory) and `cool_physical_ai_project` (the product).

## Principle

One coordinated sequence. Two programs share the same repo, the same navigator, and the
same product repo — **never two blind parallel tracks**. SCC builds the feature spine and
the browser control center; Engineering-Context v2 builds the goals / V-cycle / simulation
layer on top. Every v2 step is **additive-only** on the current v1 surface, so the two
programs never re-write the same line.

## Merged order

```
PHASE 0  SCC SP-A   feature spine + coverage + adr: + bundle map + gate
                    (prereq for v2 Inc 1/2 feature model; consume, not rebuild)
PHASE 1  SCC SP-B   control-center browser: health, sidebar, traversal
                    (prereq for v2 Inc 6 UI)
──────────────────────────────────────────────────────────────────────────
PHASE 2  v2 Inc 1   engineering ontology + V-cycle/feature-context queries
                    (extends factory.trace.model kinds/edges; consumes SP-A adr:/bundles)
PHASE 2  v2 Inc 2   /goal + goals core  (lifecycle, evaluator, evidence, regression)
PHASE 2  v2 Inc 3   simulation evidence  (drone scenarios -> goal chain)
──────────────────────────────────────────────────────────────────────────
PHASE 3  SCC SP-C   system-* remediation tools          (parallel to v2 Inc 4–5)
PHASE 3  v2 Inc 4   pi-ext agent tools (eng_*)
PHASE 3  v2 Inc 5   presentation router (present -> SCC browser / IDE / sim)
──────────────────────────────────────────────────────────────────────────
PHASE 4  v2 Inc 6   Human Engineering Context UI (5 tabs on landed SP-B browser)
                   + diagram rendering (D7) woven into dossier/V-cycle/ADR/goal tabs

         v2 Inc 7   context delta + freshness reconciliation
                   + goal-aware validation state
                   + dependency-driven impact propagation
                   + safe automatic evidence rerun / generated-artifact regeneration
                   + freshness closure
                   + comprehension hooks (D8)
──────────────────────────────────────────────────────────────────────────
PHASE 5  v2 Inc 8   durable memory & failure records  (brief §5.6; compact)
PHASE 5  SCC SP-D   business-requirement tier   (last; reviews through SP-B)
```

## Dependencies that must not be violated

| v2 increment | Requires landed | Notes |
|---|---|---|
| Inc 1 (feature/`feat:`) | SCC SP-A (`adr:`, bundle map, coverage) | consume, don't rebuild |
| Inc 2 (`/goal`) | Inc 1 | standalone otherwise |
| Inc 3 (sim evidence) | Inc 1, Inc 2 | + product harness |
| Inc 4 (agent tools) | Inc 1–3 | pi-ext route (D1) |
| Inc 5 (present router) | Inc 4 | routes to SP-B browser (D2) |
| Inc 6 (Human UI) | **SCC SP-B**, Inc 1–3, Inc 5 | only v2 edit of `system-page.ts`; additive tabs |
| Inc 7 (context delta + freshness) | Inc 1–3, Inc 6 | consumes ontology, evidence and landed SP-B/Inc-6 human surfaces; adds freshness reconciliation without changing SP-B |
| Inc 8 (durable memory) | Inc 1–7 | compact failure-record + memory tier; diagrams are D7-woven into Inc 1/5/6/7 (no separate increment) |

## Decision cross-reference (D1–D9)

| # | Direction | Documented in |
|---|---|---|
| D1 | agent surface = pi-ext tools (no MCP) | `00-program-architecture.md` §7 |
| D2 | human surface = SCC browser; Obsidian ~~out of scope~~ **amended 2026-09-01 (D-P7): read-only navigable projection, never a write/consent surface** | §7 |
| D3 | extend in place, additive-only, v1 keeps working | §7 |
| D4 | feature = `feat:` files AND bundles | §7 |
| D5 | requirement-status spec vocabulary, additive | §7 |
| D6 | SCC is upstream; SP-A/B consumed, never rebuilt | §7 + `00-scc-dependency-decision.md` |
| D7 | diagrams = committed reviewable HTML, authored via `.pi/skills/diagram-design`; TS never re-derives | §7 + `00-program-architecture.md` §3b |
| D8 | comprehension = reference installed `grill-understanding` + `visual-explainer` skills (no quiz engine) | §7 + §3b |
| D9 | freshness = detect + propagate + policy-controlled repair + reconcile + closure; safe generated artifacts do not remain manually stale | §7 + HLR-09 + Inc 7 |

## Product repo signals

- `cool_physical_ai_project` consumes the factory as an editable path dependency, so each
  committed v2 increment is live there as soon as it lands — no reinstall step.
- The bundle map + `adr:` (SP-A) and the `Catch me up`/Human UI (v2) all render against the
  same product repo.
- `cool_physical_ai_project` already ships a **measured requirement slice** the v2 chain can
  consume: 43 requirements are bound to the `sim-testbench` harness and pass
  `validate_task_requirements` with `value 1.0, passed true`. This includes a deterministic
  mission state-machine family — SR-066 + SR-067/068/071/076/080/081/082 — measured via the
  evolved harness's pytest trial source (`unit_pass_rate`, `== 1.0`), plus SR-001/066
  (frame-trace) and SR-086/087/088/101 (planner contracts), the observation/relevance/belief
  family (SR-040/041/042/043/044/045/047/048), the mission-trigger + event-store families
  (SR-032/036/092/135/164/166/167/174), and the safety-governor family
  (SR-034/102/103/104/105/106/107/108/109/111/112/113/114/115, SR-110/151 honestly left
  `[proposed]`). Inc 3 / Inc 7 can treat these as
  available `requirement → ... → evidence` inputs and goal/status material.
## Active SP-B implementation boundary

SCC SP-B is currently under implementation by another coding-agent workflow.

Until SP-B lands:

- do not edit SP-B-owned browser implementation as part of HLR-09 work;
- do not amend SP-B acceptance criteria to absorb Engineering Context freshness;
- HLR-09 implementation may prepare Python/domain primitives only where they do not conflict with
  SP-B work;
- browser-facing freshness controls/status are integrated through Inc 6/7 after SP-B lands.

SP-B remains a substrate dependency, not part of the freshness implementation scope.

---

## Parallelizable streams (git-worktree based development)

The merged order above is the **dependency-safe** sequence (a stream may not start before the
artifacts it consumes have landed). This section separates **dependency sequencing** from
**file-conflict sequencing**: two streams may run in isolated git worktrees **only** if (a) all of
the downstream stream's consumed interfaces are already landed or pinned as frozen contracts, and
(b) the two streams do not edit the same file. Where they share a file, they must be sequenced, not
parallelised.

The superpowers path is: `using-git-worktrees` to isolate each stream, then
`executing-plans` / `subagent-driven-development` (or `dispatching-parallel-agents`) inside each
worktree, then `finishing-a-development-branch` to merge each stream back to `main`. Each stream is
an independent branch/worktree off the shared `main` at the point the prior stream's interfaces
landed.

### File-ownership map (what must not collide)

| File / area | Owned by | Conflict risk across streams |
|---|---|---|
| `system-page.ts` (+ browser tabs/views) | Inc 6, then Inc 7 catch-up view, then Inc 8 memory view | **single-writer** — all browser work is sequential on this file (SP-B → Inc 6 → Inc 7 → Inc 8) |
| `src/factory/trace/model.py` (artifact kinds) | Inc 1, then Inc 7 (`diag:`/`explainer`) | Inc 1 must land before Inc 7 starts |
| `src/factory/evidence/*` + sim harness | Inc 3, then Inc 7 (auto rerun) | Inc 3 before Inc 7 |
| `validation_status.py` (goal-aware status) | Inc 2, then Inc 7 | Inc 2 before Inc 7 |
| `factory/goals/*` (goal core) | Inc 2, Inc 8 (consumes) | Inc 2 before Inc 8 |
| `src/factory/system/queries.py` | Inc 4, Inc 7 (`query_catchup`), Inc 8 (`query_memory`) | **merge hazard** — Inc 7 and Inc 8 both extend it; sequence & merge carefully |
| `src/factory/system/health.py` | Inc 7 (`vcycle_health`), Inc 8 (orphan findings) | **merge hazard** — Inc 7 before Inc 8, or careful split |
| `src/factory/presentation.py` (router) | Inc 5 | disjoint from pi-ext |
| `pi-ext/factory-watch` tools (eng_*) | Inc 4 | disjoint from `factory.presentation` |
| `src/factory/memory/*` + `schemas/failure.schema.json` | Inc 8 | new package, no conflict |
| `factory/delta/*` + `factory/commands/catchup.py` | Inc 7 | new, no conflict with other streams |

### Streams that CAN run in parallel (isolated worktrees)

**Window 1 — after Inc 1 (ontology + index) lands** (Inc 1 is the interface trunk: artifact kinds,
scopes, `query_vcycle`/`feature_context`):

- **Stream A: Inc 2** (goals core) — pure `factory/goals`, disjoint from other work.
- **Stream B: Inc 3** (sim evidence) — product repo + `factory/evidence` + harness. Depends on the
  Inc 2 **goal-evaluation interface**. Parallel only if that interface is pinned as a frozen contract
  in the Inc 1/Inc 2 spec before both start; otherwise Inc 3 must wait for Inc 2.

  *Routing decision:* if the goal contract is frozen early, run A∥B; if not, run Inc 2 → Inc 3.

**Window 2 — after Inc 2/3 land** (SCC SP-C already runs parallel to Inc 4–5 by the merged order):

- **Stream A: Inc 4** (pi-ext `eng_*` tools) — `pi-ext/factory-watch`.
- **Stream B: Inc 5** (presentation router) — `factory/presentation`. Depends on the `present()`
  signature. Parallel only if `present(artifact, focus)` is pinned up front; files are disjoint, so
  the merge is trivial once the contract holds.
- **Stream C: SCC SP-C** (system-* remediation tools) — already parallel per the merged order.

  *Routing decision:* pin the `present()` dispatch contract, then run A∥B∥C.

**Window 3 — after SP-B + Inc 1–3 + Inc 5 land** (this is where HLR-09's own parallelism lives):

- **Stream A: Inc 6** (Human UI browser tabs) — the browser work, writer of `system-page.ts`.
- **Stream B: Inc 7 Python/domain freshness (Tasks 5c–5o, non-browser)** — the HLR-09 engine in
  `factory.trace` / `factory.freshness` / `factory.delta`. This is Python-only and independent of the
  SP-B browser substrate, so it runs **without touching `system-page.ts`**.

  These two are the highest-value parallel pair: Inc 6 owns the UI, Inc 7 owns the domain engine, and
  their file sets do not overlap. The browser-facing part of Inc 7 (the `system-catchup-view.ts` tab)
  is sequenced **after** Inc 6 within Window 3's tail.

  *Routing decision:* run Inc 6 ∥ Inc 7-domain, then Inc 7-browser-view after Inc 6's tabs land.

**Window 4 — after Inc 7-domain lands** (Inc 8 needs the reconciliation/provenance model):

- **Stream A: Inc 7 browser catch-up view** (finish the remaining Inc 7 UI).
- **Stream B: Inc 8** (durable memory + history integration) — `factory/memory`, new package. Can
  start once Inc 7's provenance model lands; it shares `queries.py`/`health.py` with Inc 7, so its
  additive extensions are merged against Inc 7's landed versions, not run on top of unmerged Inc 7
  edits.

  *Routing decision:* after Inc 7-domain merges, run A∥B with the `queries.py`/`health.py` merge
  handled in the shared `main` tip.

### Within-Increment parallelism (Inc 7 — the freshness DAG)

Inc 7 holds the largest internally-parallelisable surface. Its tasks form a dependency DAG, not a
chain:

```
5c  artifact dependency provenance model   ← backbone
 ├─ 5d  transitive impact resolver
 ├─ 5e  authority-aware refresh policy
 ├─ 5n  historical preservation
 └─ 5l  v-cycle health integration      (also needs 5g)
5e → 5f  auto generated-artifact regeneration
5c/5d → 5h  semantic implementation invalidation
5d/5e → 5g  auto evidence refresh
5f/5g → 5m  refresh loop protection
5d+5f+5g+5h → 5i  freshness reconciliation
5i → 5j  feature freshness closure
5i/5j → 5k  /catchup freshness integration
5k..5j → 5o  thin-slice acceptance
```

Because tasks 5c–5o are **Python/domain-only** (no `system-page.ts`), they can be split across
worktrees once 5c has landed: e.g. one agent runs 5d∥5e∥5n∥5l after 5c; then 5f∥5g∥5h; then
5i→5j→5k; then 5o last. Task 5b (comprehension hook) and Tasks 1–5/6 (existing `/catchup`) stay
with the Inc 7 UI sequence.

### Rules for every parallel split

1. **Pin the contract before the split.** The consuming stream needs a frozen interface (Inc 2 goal
   eval, Inc 5 `present()`, Inc 6 tab contract) or it must wait. A frozen contract is written down,
   not assumed.
2. **No two worktrees edit the same file.** If a shared file appears (e.g. `queries.py`/`health.py`
   between Inc 7 and Inc 8), sequence it or assign one stream as the sole writer and merge in the tip.
3. **The browser is a single-writer file.** Everything that touches `system-page.ts` is sequential:
   SP-B → Inc 6 → Inc 7 catch-up view → optional Inc 8 memory view.
4. **SP-B is frozen.** No freshness work touches SP-B-owned files until SP-B lands.
5. **Every stream stays additive-only (D3)** and keeps the full v1 suite green; each merges to `main`
   with its own gates before the next window opens.
