# Design: Shared Pipeline Node Registry + Transition-Driven Notification

Date: 2026-08-14
Status: Implemented (completed 2026-08-14 — see plan `2026-08-14-pipeline-node-registry-implementation.md`; all tasks ticked)
Builds on:
- `docs/superpowers/specs/2026-08-12-grill-understanding-node-design.md` — the grill
  node whose brittle wiring motivated this.
- `pi-ext/factory-watch/src/status-format.ts`, `mission-control-dashboard.ts`,
  `index.ts` and `src/factory/orchestrator/{status,runner,nodes}.py` — the two
  disconnected subsystems this unifies.

## 1. Problem

The pipeline's node graph is modeled in **two independent places** with no shared
contract:

- **Python (executor):** node names appear in `status.report(...)` calls, the
  execution journal, and resume/`resume_at` logic (`runner.py`, `nodes.py`).
- **TS (renderer/controller):** node names appear as duplicated literals in
  `STAGE_ORDER` and `NODE_LABELS` (`mission-control-dashboard.ts`,
  `status-format.ts`) and in the widget-detection + action-routing switch in
  `index.ts`.

Adding the grill in Python updated the widget-detection list and the seed builder but
missed `STAGE_ORDER`/`NODE_LABELS`/action-routing — so the mission-control dashboard
never drew a grill row, and the only surface that knew the grill existed was the
background widget text. This is the same failure mode repeated: **adding a node is
shotgun surgery across two languages with ~8 touch points, and any miss silently
degrades one surface.**

A second, independent failure: blocking state is **pull-only**. The factory run is
spawned detached and publishes to a status file; mission control polls to refresh the
displayed record but never acts on a state **transition**. `maybeOfferGrill` is called
exactly once, before the loop, so a grill that appears *after* mission control opens
(the normal case, since the run is async) is never offered. Notification is bolted on
(a widget string) instead of structural.

## 2. Goals / non-goals

Goals:
- A **single source of truth** for the pipeline node graph that both Python and TS
  read, so adding a node is one declaration instead of N duplicated literals.
- **Transition-driven action**: the mission-control poll fires a handler when a node
  transitions into a blocking state (grill → `[Grill now]/[Skip]`), not only at open.
- The grill renders in mission control exactly like `human-review` does.

Non-goals (future work, see Memory doc `2026-08-14-context-handoff-roadmap.md`):
- A content-bearing context packet / durable code-context bundle (tree-sitter index).
- Busy-wait elimination on the Python side (the file-poll gates stay for now).

## 3. The shared registry

A machine-readable node registry that both sides consume, placed at a stable repo
path readable by Python (JSON) and TS (JSON import). Minimal schema:

```json
{
  "schema": 1,
  "nodes": [
    {"id": "context-gather", "label": "context-gatherer", "kind": "agent",   "interactive": false},
    {"id": "grill",          "label": "grill",           "kind": "gate",    "interactive": true, "order": 1},
    {"id": "dev",            "label": "developer",       "kind": "agent",   "interactive": false},
    {"id": "validation",     "label": "validation",      "kind": "gate",    "interactive": false},
    {"id": "review",         "label": "reviewer",        "kind": "agent",   "interactive": false},
    {"id": "human-review",   "label": "human-review",    "kind": "gate",    "interactive": true},
    {"id": "session-review", "label": "session-review",  "kind": "agent",   "interactive": false}
  ],
  "order": ["context-gather", "grill", "dev", "validation", "review", "human-review", "session-review"]
}
```

- `interactive: true` marks nodes that require human action; the renderer derives
  "blocked → surface a select / banner" from this bit instead of an ad-hoc switch.
- `STAGE_ORDER` is replaced by reading `order`. `NODE_LABELS` is replaced by `label`.
- The action-routing in `mission-control-dashboard.ts` derives its choices from
  `interactive` + `kind` rather than hard-coded node names.

## 4. Transition-driven notification

The mission-control poll currently only calls `dash.updateRecord(...)`. Change it to:

1. Keep a per-session map of the last observed `(node, node_state)` for each node id.
2. On each poll, diff the new record against it.
3. When a node newly enters `node_state == "blocked"` **and** its registry `interactive`
   is true, invoke the corresponding handler (for `grill`, `maybeOfferGrill`; for
   `human-review`, surface the review banner).

This replaces the single `await maybeOfferGrill(...)` before the loop. Event
delivery is idempotent/nag-free via the existing `offeredGrillFor` set and the
on-disk `grill-result.json` guard. The same transition hook is a natural seam for
future interactivity (e.g. `pair-dev` auto-offer on dev-escalation).

## 5. Reuse of existing machinery

- The status file already persists `pipeline[]` with `updated_at` per entry
  (`FileStatusReporter.report`), so transitions are derivable without new writes.
- `maybeOfferGrill` already self-guards (`offeredGrillFor` + result-file check); we
  only move its invocation into the transition path.
- No Python behavioral change required for notification; the registry is consumed
  but the executor keeps its own `status.report` contract.

## 6. Risks / open items

- **Single-source-of-truth boundary:** Python must not fork the ordering; it should
  read the registry for its own status-report ordering where useful, but the hard
  requirement is only that the UI derives its view from the registry.
- **Status-file staleness:** transition detection re-runs from the persisted mirror
  files (`.factory-runs/<task>.json`), so a reboot that clears the live
  `sessions/.factory-status.json` does not orphan the grill.
- **Test seam:** a pure `diffTransitions(prev, next, registry)` function is
  unit-testable; the TUI wiring stays thin.
