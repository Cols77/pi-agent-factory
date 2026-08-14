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
PHASE 4  v2 Inc 6   Human Engineering Context UI (5 tabs on SP-B browser)
                   + diagram rendering (D7) woven into dossier/V-cycle/ADR/goal tabs
         v2 Inc 7   context delta + goal-aware validation status (+ Catch me up)
                   + comprehension hooks (D8: grill-understanding + visual-explainer)
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
| Inc 7 (context delta) | Inc 2/3, Inc 6 | + "Catch me up" view + comprehension hooks (D8) |
| Inc 8 (durable memory) | Inc 1–7 | compact failure-record + memory tier; diagrams are D7-woven into Inc 1/5/6/7 (no separate increment) |

## Decision cross-reference (D1–D8)

| # | Direction | Documented in |
|---|---|---|
| D1 | agent surface = pi-ext tools (no MCP) | `00-program-architecture.md` §7 |
| D2 | human surface = SCC browser; **Obsidian out of scope** | §7 |
| D3 | extend in place, additive-only, v1 keeps working | §7 |
| D4 | feature = `feat:` files AND bundles | §7 |
| D5 | requirement-status spec vocabulary, additive | §7 |
| D6 | SCC is upstream; SP-A/B consumed, never rebuilt | §7 + `00-scc-dependency-decision.md` |
| D7 | diagrams = canonical committed HTML, authored via `.pi/skills/diagram-design`; TS never re-derives | §7 + `00-program-architecture.md` §3b |
| D8 | comprehension = reference installed `grill-understanding` + `visual-explainer` skills (no quiz engine) | §7 + §3b |

## Product repo signals

- `cool_physical_ai_project` consumes the factory as an editable path dependency, so each
  committed v2 increment is live there as soon as it lands — no reinstall step.
- The bundle map + `adr:` (SP-A) and the `Catch me up`/Human UI (v2) all render against the
  same product repo.
