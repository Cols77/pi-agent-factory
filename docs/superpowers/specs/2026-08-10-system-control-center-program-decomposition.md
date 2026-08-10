# System Control Center — Program Decomposition

**Date:** 2026-08-10
**Status:** Approved decomposition. Each sub-project gets its own design → plan → implementation cycle.
**Scope:** `pi-agent-factory` (the factory) and `cool_physical_ai_project` (the product under construction).

## Goal

Make `/system` a control center: a surface where a human can hold one feature in
their head — requirements, the tasks meant to implement it, the design decisions
behind it, and eventually the code — and see at a glance where the project's
traceability is thin.

The driving constraint is speed asymmetry. Agents produce requirements, tasks,
and evidence faster than a human can read files. The navigator's job is to make
the system's state legible at the rate the system changes.

## Diagnosis (measured 2026-08-10)

### What `/system` is today

`/system` is registered in `pi-ext/factory-watch/src/index.ts:836` and opens the
docs browser on `/system`, rendered entirely by `renderSystemPageHtml()` in
`pi-ext/factory-watch/src/system-page.ts:17` (1220 lines). Python
(`src/factory/system/`, ~3.1k lines) computes JSON projections; TypeScript only
renders them. Seven tabs per scope: Brief, Matrix, Timeline, Guide, Story,
Reverse, Trace. Four prior plans built it — briefing/validation/guide, the
Increment B V-cycle, navigation/readability, and sidebar+trace — all implemented.

### State of the product's system definition

Measured against `cool_physical_ai_project` with `factory.trace status`:

```
traceability health: 69%  (174/253 slots)
  task->plan     43/43        task->SR       23/23  [20 exempt]
  plan->spec     5/5          SR satisfied   102/181
  SR validated   1/1          dangling refs  1
  deferred       74           proposed       180
gaps: 280 (5 pending)
```

Supplementary counts:

- **180 of 181 SRs are `proposed`** — no binding, no checksum. Only SR-001 is `current`.
- **`SR validated 1/1`** is a green ratio over a denominator of one. One SR carries a validation binding.
- **22 of 43 tasks are `trace_exempt`**, so real link density is well below the headline 69%.
- **1 bundle** (`reactive-planner`, 8 members, covering 4 of 181 SRs). **2 ADRs. 1 evidence run directory.**
- **No `BR-*` files exist.** SR-001's `upstream: BR-002` is the single dangling ref. The top of the V is empty.
- `source:` puts **153 of 181 SRs in one 67 KB spec**, so it cannot group features. `domain:` yields 8 coarse buckets — a taxonomy, not features.

### Why the navigator cannot serve the use case

1. **It opens blank.** `#content` is `hidden` until a scope is chosen. There is no landing page and no project-level view.
2. **Health is computed and never shown.** `factory.trace status` produces every number above; `factory.system` has no health projection, and `factory.trace status` has no `--json`.
3. **The sidebar is 182 flat atoms** — 1 bundle plus 181 individual requirement sentences. Feature-level entry does not exist.
4. **Tasks are not listed.** `task:` is an openable scope (Story tab) but `factory.system scope` emits only `bundle` and `sr`, so reaching a task requires already knowing its ID.
5. **Design decisions have no home.** `decision` is a citation kind, but `bundles.py:32` allows only `spec:`/`plan:`/`task:`/`sr:` members. An ADR cannot belong to a feature.
6. **No remediation path.** All eleven `system_*` tools (`system-context-tools.ts:71`–`321`) are read-only. Closing a gap means `factory.requirements bind|defer|new`, `factory.trace link|exempt|defer`, or `factory.doctor mint|promote` — none surfaced, none in the `system_*` namespace.

## Decisions taken

| Decision | Ruling |
|---|---|
| Unit of "a feature" | **Curated bundles, expanded.** Every SR, task, spec, and ADR belongs to at least one bundle. Explicit, reviewable in git, nothing inferred. |
| Remediation interface | **Split by nature of the act.** Mechanical operations get navigator buttons; judgment operations get agent-facing tools. |
| Definition workstream depth | **Bundle-scoped and incremental.** Author the complete bundle map in one pass; bind and cover SRs per bundle, as each feature is actually worked. No speculative binding of 181 requirements. |
| Build order | **A → B → C.** |

## Sub-projects

### SP-A — Feature spine and coverage

The navigable skeleton, and the prerequisite for everything else.

Delivers:

- `adr:` accepted by `_parse_member_ref` (`bundles.py:49`) as `adr:<stem>` → `docs/adr/<stem>.md`, and as an openable scope so a decision has a page rather than a dead link.
- `bundle_coverage(repo_root) -> Coverage` in `factory.system.bundles`: a pure function over existing loaders returning, per artifact kind, the bundled/unbundled split and the unbundled refs. No persisted index, no cache.
- The complete bundle map for `cool_physical_ai_project` — all 181 SRs, 43 tasks, 6 specs, 2 ADRs assigned.
- Resolution of the dangling `BR-002` reference: create the artifact or unlink it.
- A coverage gate wired into `.factory/factory.yaml`'s `gates.full`, failing on any unbundled artifact.

Lands in: pi-agent-factory (contract, API, gate implementation) and cool_physical_ai_project (the map, the gate wiring).

The coverage gate is SP-A's acceptance instrument. It is why SP-A is reviewable
without SP-B's UI: completeness of the map is a mechanical property, decidable by
code.

### SP-B — Control center

Delivers:

- `factory.system health --json`, a projection composing `compute_health()` (`trace/health.py:53`), `classify()` (`requirements/closure.py:29`), and SP-A's `bundle_coverage()`. It duplicates no logic; it re-shapes existing computations into the navigator's projection contract.
- A landing page that opens on project health instead of blank.
- A feature-first sidebar: bundles as the primary axis, with the unbundled remainder visible rather than hidden.
- Working traversal for the core use case: requirement → satisfying tasks → design decisions → changed files.
- A structural split of `system-page.ts` along the seam already present in it (shell and CSS, per-tab renderers, client bootstrap). The existing DOM tests pin current behavior, so the split is verifiable. The "only edit `system-page.ts`" constraint carried by the three prior plans was correct for small increments and is wrong for this one.

Lands in: pi-agent-factory.

### SP-C — `system-*` remediation toolset

Delivers the write side, split by the classification rule below: mechanical
operations as navigator buttons backed by docs-server POST routes, judgment
operations as agent-facing PIF tools in the `system_*` namespace plus a dispatch
affordance in the navigator.

Lands in: pi-agent-factory.

## Interfaces

### SP-A → SP-B

SP-A publishes three things SP-B consumes: the `adr:` member and scope kind, the
`bundle_coverage()` API, and the coverage gate's pass/fail as a health input.

### SP-B → SP-C

SP-B's health projection emits each gap with a stable identity and the operation
that closes it, so SP-C's tools consume what SP-B renders rather than
re-deriving it:

```json
{ "gap_id": "sr_unbound:SR-007",
  "subject": { "kind": "sr", "ref": "sr:SR-007" },
  "bundle": "shark-detection",
  "operation": "bind",
  "class": "judgment" }
```

### The classification rule

One question decides where an operation lives: **does executing it require
authoring text, or choosing a number, that becomes durable evidence?**

- **No → mechanical → navigator button.** Inputs are fully determined by refs already on screen, the operation is reversible by a single inverse operation, and it records no free text. Examples: add or remove a bundle member; reaffirm an existing deferral.
- **Yes → judgment → agent tool.** Examples: `bind` (metric, assert, harness, trials), `exempt` and `defer` (rationale), bundle creation (label and membership), requirement creation.

The rule is deliberately conservative. The moment an operation writes prose that
is later read as justification, a human clicking a button is the wrong author.

### Repo boundary

Everything reusable lands in pi-agent-factory. Only bundle files and gate wiring
land in cool_physical_ai_project. This preserves PIF's direction of travel: an
installable package that discovers per-repo extensions.

## Inherited constraints

These hold across all three sub-projects and are not renegotiated per design:

- Python computes, TypeScript renders. No query, freshness, or provenance logic in the browser.
- Claim class ∈ `recorded|derived|synthesized|missing`; freshness ∈ `fresh|stale|degraded|n/a`; `missing` ⟺ `n/a`. No new claim classes.
- Freshness is content-based, never mtime-based.
- Scope refs are exact and case-sensitive. Never fuzzy.
- No derived index and no cache. Projections are computed on demand.
- Payload-derived strings reach the DOM via `createTextNode`/`textContent`. `innerHTML` is only ever assigned a quoted literal.
- Payload values (`claim.kind`, `freshness.state`, `status`, `actor`, `action`, `run.source`, `stops_at`) render verbatim — never remapped, filtered, or distinguished by colour alone.
- No model-based synthesis. The guide is fixed scaffolding plus verified verbatim spans.
- Missing or corrupt evidence degrades one scope, not the whole navigator.
- Reuse existing loaders (`factory.evidence.manifests`, `factory.trace.model`, `factory.orchestrator.ledger`, `factory.requirements.register`). No parallel parsing rules.
- `pyproject.toml` sets `addopts = "-m unit"`; integration commands must pass `-m 'unit or integration'` or they collect nothing and exit green.

## Non-goals

- Binding all 181 requirements. Binding is per-bundle and on demand.
- Restoring the `BR-*` layer as a navigable tier. SP-A resolves the one dangling reference; a business-requirement tier is a separate future program.
- Replacing `/review-plans` or the existing evidence surfaces.
- Any whole-suite or repo-wide test pass rate in the health projection.

## Open questions, deferred to each sub-project's design

- **SP-A:** bundle granularity and count; whether a bundle may nest; whether an artifact may belong to more than one bundle; whether the coverage gate blocks `full` immediately or warns for one increment.
- **SP-B:** what the landing page leads with; how per-bundle readiness is expressed without inventing a score; whether `sr:` scopes remain individually listed once bundles are the primary axis.
- **SP-C:** the exact operation inventory and its classification; undo semantics for mechanical operations; how a dispatch is handed to an agent from the browser.
