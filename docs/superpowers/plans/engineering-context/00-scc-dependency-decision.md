# DECISION 001 — Engineering-Context v2 consumes the System Control Center

**Status:** accepted
**Date:** 2026-08-11
**Scope:** program-level coordination between the **System Control Center (SCC)** and the
**Engineering-Context v2** programs, both in `pi-agent-factory` / `cool_physical_ai_project`.

## Context

Two initiatives target the same repos, the same `/system` navigator, and the same product
repo, in overlapping space:

- **System Control Center** (`docs/superpowers/specs/2026-08-10-system-control-center-program-decomposition.md`,
  sub-projects SP-A → SP-B → SP-C → SP-D) — traceability control center: feature spine and
  coverage, control-center browser, remediation tools, business-requirement tier.
- **Engineering-Context v2** (`Engineering Context, V-Cycle Navigation and Goal-Driven
  Validation.md`; plans under `docs/superpowers/plans/engineering-context/`) — feature-centric
  V-cycle vertical slices, goals with metric-driven evaluation, simulation evidence, feature
  dossiers, `present()`, `/catchup`.

They share a substrate (`factory.trace`, `factory.system`, `factory.evidence`, `factory.validation`)
and the browser surface (`system-page.ts`). Running them as two independent tracks would collide
on `queries.py`, `bundles.py`, `cli.py`, `system-page.ts`, and the product repo's `bundles/:`
and gate configuration.

## Decision

1. **SCC is upstream.** SP-A (feature spine: `adr:` member/scope kind, bundle map, coverage,
   ordering, gate) is the basis for the v2 feature model; SP-B (control-center browser) is the
   surface v2's human views are built on. v2 **consumes** SP-A's `adr:` and bundle map and SP-B's
   navigator — it **never rebuilds** them.

2. **One coordinated sequence.** The merged order lives in
   `docs/superpowers/plans/engineering-context/00-execution-roadmap.md`: SP-A → SP-B →
   v2 Inc 1–3 → SP-C / v2 Inc 4–5 → v2 Inc 6–7 → SP-D.

3. **One human surface.** The System Control Center browser is the sole primary human
   engineering-context surface. Obsidian integration is out of scope (D2).

4. **Additive-only.** Every v2 increment keeps the current v1 workflow working and un-changed
   (D3); v2 Inc 6 is the only v2 increment that edits `system-page.ts`, and only as additive tabs
   after SP-B.

5. **Boundaries preserved.** Business requirements stay the SCC's SP-D concern; goals, metrics,
   V-cycle slices, simulation evidence and `/catchup` stay the v2 concern. Neither silently
   absorbs the other's scope.

## Consequences

- Both programs' reviewers must cross-check against this decision: SCC must not build goals/
  V-cycle; v2 must not re-derive feature spine, `adr:`, coverage, or a second human surface.
- v2 Inc 1's ontology intentionally excludes a `design`/`docs/designs` kind: design decisions
  are owned by SCC SP-A's `adr:`.
- Execution order is binding; an increment may not start until its upstream dependency (per the
  roadmap) has landed.

## Cross-references

- SCC decomposition: `docs/superpowers/specs/2026-08-10-system-control-center-program-decomposition.md`
- SCC SP-A design / plan: `2026-08-11-system-feature-spine-design.md`, `2026-08-11-system-feature-spine.md`
- v2 program: `docs/superpowers/plans/engineering-context/00-program-architecture.md`
- v2 roadmap: `docs/superpowers/plans/engineering-context/00-execution-roadmap.md`
