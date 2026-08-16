# Plan: Shared Pipeline Node Registry + Transition-Driven Notification

**Date:** 2026-08-14
**Status:** Draft for review
**Source:** `docs/superpowers/specs/2026-08-14-pipeline-node-registry-design.md`
**Required sub-skill:** superpowers:subagent-driven-development (task-by-task,
checkboxes below). Reuses the factory's own gate vocabulary (unit / sim / integration / full).

## Grounding (verified against current `design/curation-workflow`)

- Node render order + labels are hard-coded in `pi-ext/factory-watch/src/status-format.ts`
  (`NODE_LABELS`) and `mission-control-dashboard.ts` (`STAGE_ORDER`); action routing
  dispatches on literal node names; the widget-detection list lives in `index.ts`.
- `maybeOfferGrill` is invoked exactly once at the top of `runMissionControl`
  (`index.ts`), before the loop, so a grill that appears later is never offered.
- The orchestrator already writes `node="grill", node_state="blocked"` into the
  status pipeline (`runner.py`), so the UI side only needs to render + react.
- `FileStatusReporter.report` (`src/factory/orchestrator/status.py`) persists
  `pipeline[]` with per-entry `updated_at` and mirrors each task to
  `sessions/.factory-runs/<task>.json`.

## Global constraints

- No Python behavioral change: the registry is a UI-facing contract; the executor's
  `status.report` contract is unchanged.
- Additive: grill and human-review behavior are preserved; only the *repetition*
  (hard-coded stage order/labels/switch) is consolidated.
- Reuse existing `offeredGrillFor` + `grill-result.json` dedup; do not add a parallel
  "already offered" state.
- TS: vitest; Py: pytest `unit`; ruff 100 / pyright standard.

---

### Task 1: Add the node registry artifact

**Files:** new `pi-ext/factory-watch/node-registry.json` (consumed by TS; a copy is
also placed at repo root `docs/...` or a shared `share/` path for Python later).

- [x] **Step 1 (failing tests):** a `loadNodeRegistry()` reader in
  `pi-ext/factory-watch/src/node-registry.ts` returns typed nodes; a test asserts
  `order` covers `context-gather, grill, dev, validation, review, human-review,
  session-review` and that `grill`/`human-review` are marked `interactive`.
- [x] **Step 2 (implement):** author `node-registry.json` per §3 of the spec; add
  `loadNodeRegistry()` (cached, safe parse, fallback to a minimal built-in so a
  missing file degrades, not crashes).
- [x] **Step 3:** vitest + lint; commit.

### Task 2: Renderer derives from the registry

**Files:** `status-format.ts`, `mission-control-dashboard.ts`.

- [x] **Step 1 (failing tests):** `formatMissionControlRows` and the dashboard take the
  registry's `order` + `label`, and a test asserts a `grill` row appears with label
  `grill` (not dropped), and that removing a node from the registry removes its row.
- [x] **Step 2 (implement):** replace `STAGE_ORDER` and `NODE_LABELS` literals with
  registry reads; keep `labelForNode`/`iconForState` thin over the registry.
- [x] **Step 3:** vitest (`test/status-format.test.ts`, `test/mission-control-dashboard.test.ts`)
  + lint; commit.

### Task 3: Transition-driven action

**Files:** new `pi-ext/factory-watch/src/pipeline-diff.ts` (pure), `index.ts`
(mission-control poll).

- [x] **Step 1 (failing tests):** `diffTransitions(prev, next, registry)` returns an
  event when a node flips into `blocked` and is `interactive`, and returns nothing
  for a node already blocked in `prev` (nag-free) or non-interactive nodes. A
  handler test drives the poll and asserts `maybeOfferGrill` fires on the
  transition, exactly once.
- [x] **Step 2 (implement):** track last-seen `(node, node_state)` per session in
  the poll; on transition invoke the interactive-node handler (grill →
  `maybeOfferGrill`). Remove the single pre-loop `maybeOfferGrill` call.
- [x] **Step 3:** vitest + full suite + lint; commit.

### Task 4: Review handoff

- [x] **Step 1:** reviewer sub-agent — verify (a) grill now renders + is offered on
  transition (not only at open); (b) nag-free on re-entry / pickle-existing-result;
  (c) removing a node from the registry removes its row + action; (d) no Python
  behavior change; (e) additive to uncommitted `/visual-explain` hunks.
- [x] **Step 2:** fix findings; tick checkboxes.

---

## Risks / open items

- The registry lives in the extension dir for now (fastest single-consumer path).
  Promoting it to a shared path readable by `status.py` (to drop Python-side node
  literals too) is a follow-up, not this plan; the contract is stable JSON either way.
- Browser watch mode (`--browser`) renders mission control in the docs server; the
  registry must be available to that render path without a hard dependency on the
  extension loading order.
