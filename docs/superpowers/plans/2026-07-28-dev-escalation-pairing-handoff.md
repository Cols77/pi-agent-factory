# Dev-Escalation Pairing Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a human open the stuck dev `pi` session from mission control, pair with the agent to get unit tests green, then re-run the task so `already_done` routing continues the pipeline.

**Architecture:** Pure factory-watch (TypeScript) enhancement over machinery that already exists — the escalated `dev` pipeline entry already carries the last attempt's `session_id` (via `status.py` sticky-field logic), and `spawnTerminalWindow("pi", ["--session", ...])` + `already_done` re-run routing already exist. We add: a `devEscalated` detector, a dashboard "pair" affordance (banner + Enter action), an `index.ts` action case that opens the session in a new window, and a widget alert line. **Zero Python/orchestrator changes.**

**Tech Stack:** TypeScript (NodeNext ESM), vitest, `@earendil-works/pi-tui`. All files under `pi-ext/factory-watch/`.

## Global Constraints

- **Zero changes to `src/factory/` (the Python orchestrator).** This feature is TypeScript-only.
- **NodeNext module resolution — match the file you're editing.** Import-extension convention differs per file: `mission-control-dashboard.ts` imports siblings with a `.ts` extension (e.g. `from "./status-format.ts"`), while `index.ts` uses `.js` (e.g. `from "./status-format.js"`). In each task, copy the extension style already used by that file's existing imports.
- **Node 18 `@types/node`**, TypeScript `^5.5`, vitest `^2.0`.
- **Follow existing factory-watch patterns.** Mirror the human-review affordance (`mission-control-dashboard.ts` banner + `index.ts` `case "review"`) and the existing `spawnTerminalWindow("pi", ["--session", path])` call at `index.ts:94`.
- **Escalated-dev detection contract:** a `dev` pipeline entry with `node_state === "escalate"` **or** `outcome === "escalated"`, and a string `session_id`.
- **Full gate command:** `uv run python scripts/gates/watch_ext.py` (runs `tsc --noEmit` then `vitest run` for factory-watch). Single-file test filter: `npm --prefix pi-ext/factory-watch test -- <name-fragment>`.

---

## File Structure

- **Modify** `pi-ext/factory-watch/src/status-format.ts` — add the pure `devEscalated(record)` detector alongside the existing record types and `formatMissionControlRows` (this file already owns record-shape helpers).
- **Modify** `pi-ext/factory-watch/src/mission-control-dashboard.ts` — add `pair-dev` to `MissionControlAction`, branch `handleEnter` for an escalated dev row, render the `DEV STUCK` banner.
- **Modify** `pi-ext/factory-watch/src/index.ts` — handle the `pair-dev` action (open `pi --session <path>` in a new window + notify), and append a `dev stuck` widget line in `startBackgroundWidgetPoll`.
- **Modify** `pi-ext/factory-watch/test/status-format.test.ts` — tests for `devEscalated`.
- **Modify** `pi-ext/factory-watch/test/mission-control-dashboard.test.ts` — tests for the escalated-dev Enter branch and banner.
- **Modify** `pi-ext/factory-watch/README.md` — document the pairing workflow.

No new files: each change extends an existing, focused module.

---

### Task 1: `devEscalated` detector

**Files:**
- Modify: `pi-ext/factory-watch/src/status-format.ts` (add exported function after `formatMissionControlRows`, end of file)
- Test: `pi-ext/factory-watch/test/status-format.test.ts`

**Interfaces:**
- Consumes: `StatusRecord`, `PipelineEntry` (already exported from `status-format.ts`).
- Produces: `export function devEscalated(record: StatusRecord | null): { sessionId: string } | null` — returns the last dev attempt's pi session id when the dev node is escalated, else `null`. Consumed by Tasks 2 and 3.

- [ ] **Step 1: Write the failing tests**

Append to `pi-ext/factory-watch/test/status-format.test.ts` (add `devEscalated` to the existing import from `../src/status-format.js`, and `import type { StatusRecord } from "../src/status-format.js"` if not already present):

```typescript
import { devEscalated } from "../src/status-format.js";
import type { StatusRecord } from "../src/status-format.js";

function recordWithDev(dev: Record<string, unknown>): StatusRecord {
  return {
    session_id: "s1", task_id: "T-1", current_node: "dev", current_state: "escalate",
    pipeline: [
      { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: null, updated_at: "t" },
      { node: "dev", node_state: "pending", attempt: 0, max_attempts: 3, snippet: "", outcome: null, handoff: null, updated_at: "t", ...dev },
    ],
    started_at: "t", updated_at: "t",
  } as StatusRecord;
}

describe("devEscalated", () => {
  test("returns the session id when dev node_state is escalate", () => {
    const rec = recordWithDev({ node_state: "escalate", outcome: "escalated", session_id: "dev-abc" });
    expect(devEscalated(rec)).toEqual({ sessionId: "dev-abc" });
  });

  test("returns the session id when only outcome is escalated", () => {
    const rec = recordWithDev({ node_state: "escalate", outcome: "escalated", session_id: "dev-xyz" });
    expect(devEscalated(rec)).toEqual({ sessionId: "dev-xyz" });
  });

  test("returns null when dev is escalated but has no session id", () => {
    const rec = recordWithDev({ node_state: "escalate", outcome: "escalated", session_id: null });
    expect(devEscalated(rec)).toBeNull();
  });

  test("returns null when dev is still running", () => {
    const rec = recordWithDev({ node_state: "running", session_id: "dev-abc" });
    expect(devEscalated(rec)).toBeNull();
  });

  test("returns null when there is no dev entry", () => {
    const rec: StatusRecord = {
      session_id: "s1", task_id: "T-1", current_node: "context-gather", current_state: "pass",
      pipeline: [{ node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: null, updated_at: "t" }],
      started_at: "t", updated_at: "t",
    };
    expect(devEscalated(rec)).toBeNull();
  });

  test("returns null for a null record", () => {
    expect(devEscalated(null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix pi-ext/factory-watch test -- status-format`
Expected: FAIL — `devEscalated is not a function` / no matching export.

- [ ] **Step 3: Implement `devEscalated`**

Append to `pi-ext/factory-watch/src/status-format.ts`:

```typescript
// Detects the dev-escalation handoff state: the dev node exhausted its
// retries with unit tests still red. Returns the last dev attempt's pi
// session id (preserved on the entry by FileStatusReporter's sticky-field
// logic) so the dashboard can open `pi --session <id>` for the human to pair
// with the agent. Returns null unless the dev node is escalated AND a session
// id was captured.
export function devEscalated(record: StatusRecord | null): { sessionId: string } | null {
  const entry = (record?.pipeline ?? []).find(
    (e) => e.node === "dev" && (e.node_state === "escalate" || e.outcome === "escalated"),
  );
  if (entry && typeof entry.session_id === "string") {
    return { sessionId: entry.session_id };
  }
  return null;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix pi-ext/factory-watch test -- status-format`
Expected: PASS — all `devEscalated` tests green, existing `status-format` tests still green.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/status-format.ts pi-ext/factory-watch/test/status-format.test.ts
git commit -m "feat: devEscalated detector for dev-escalation handoff"
```

---

### Task 2: Dashboard pair-dev affordance (action + banner)

**Files:**
- Modify: `pi-ext/factory-watch/src/mission-control-dashboard.ts` (action union ~9-13, `handleEnter` ~31-41, `render` banner ~59-62)
- Test: `pi-ext/factory-watch/test/mission-control-dashboard.test.ts`

**Interfaces:**
- Consumes: `devEscalated` (Task 1).
- Produces: `MissionControlAction` gains `{ type: "pair-dev"; sessionId: string }`. Consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Append to `pi-ext/factory-watch/test/mission-control-dashboard.test.ts`:

```typescript
function escalatedDevRecord(): StatusRecord {
  return {
    session_id: "s1", task_id: "T-029", current_node: "dev", current_state: "escalate",
    pipeline: [
      { node: "context-gather", node_state: "pass", attempt: 1, max_attempts: 1, snippet: "", outcome: null, handoff: "-> dev", updated_at: "t" },
      { node: "dev", node_state: "escalate", attempt: 3, max_attempts: 3, snippet: "", outcome: "escalated", handoff: "escalated: unit tests still red", updated_at: "t", session_id: "dev-abc" },
    ],
    started_at: "t", updated_at: "t",
  };
}

test("Enter on an escalated dev row resolves pair-dev with its sessionId", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(escalatedDevRecord(), onAction);
  down(d, 1); // dev row
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "pair-dev", sessionId: "dev-abc" });
});

test("Enter on a running dev row still resolves inspect (not pair-dev)", () => {
  const onAction = vi.fn();
  const d = new MissionControlDashboard(RECORD, onAction);
  down(d, 1); // dev row (RECORD has dev running)
  d.handleInput("\r");
  expect(onAction).toHaveBeenCalledWith({ type: "inspect", sessionId: "dev-abc" });
});

test("shows a DEV STUCK alert when dev is escalated", () => {
  const d = new MissionControlDashboard(escalatedDevRecord(), () => {});
  expect(d.render(80).join("\n")).toContain("DEV STUCK");
});

test("no DEV STUCK alert when dev is not escalated", () => {
  const d = new MissionControlDashboard(RECORD, () => {});
  expect(d.render(80).join("\n")).not.toContain("DEV STUCK");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix pi-ext/factory-watch test -- mission-control-dashboard`
Expected: FAIL — Enter on escalated dev resolves `inspect` (current behavior), and no `DEV STUCK` text is rendered.

- [ ] **Step 3: Add the action type and import**

In `pi-ext/factory-watch/src/mission-control-dashboard.ts`, add the import near the top (after the existing `formatMissionControlRows` import):

```typescript
import { formatMissionControlRows, devEscalated } from "./status-format.ts";
```

(Replace the existing `import { formatMissionControlRows } from "./status-format.ts";` line — keep the `import type { StatusRecord }` line as-is.)

Extend the `MissionControlAction` union:

```typescript
export type MissionControlAction =
  | { type: "inspect"; sessionId: string | null }
  | { type: "gate-log" }
  | { type: "review" }
  | { type: "pair-dev"; sessionId: string }
  | { type: "quit" };
```

- [ ] **Step 4: Branch `handleEnter` for an escalated dev row**

Replace the `handleEnter` body so an escalated dev row dispatches `pair-dev` before the generic agent-node `inspect` path:

```typescript
  private handleEnter(): void {
    if (this.record === null) return;
    const row = formatMissionControlRows(this.record, STAGE_ORDER)[this.selectedIndex]!;
    const escalated = devEscalated(this.record);
    if (row.node === "dev" && escalated !== null) {
      this.onAction({ type: "pair-dev", sessionId: escalated.sessionId });
    } else if (AGENT_NODES.has(row.node)) {
      this.onAction({ type: "inspect", sessionId: row.sessionId });
    } else if (row.node === "validation") {
      this.onAction({ type: "gate-log" });
    } else if (row.node === "human-review") {
      this.onAction({ type: "review" });
    }
  }
```

- [ ] **Step 5: Render the DEV STUCK banner**

In `render`, after the existing `hrBlocked` banner block (right before the `formatMissionControlRows(...).forEach(...)` call), add:

```typescript
    if (devEscalated(this.record)) {
      lines.push("⚠ DEV STUCK — select developer and press Enter to pair, then re-run the task", "");
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `npm --prefix pi-ext/factory-watch test -- mission-control-dashboard`
Expected: PASS — new pair-dev/banner tests green; existing tests (running-dev inspect, HUMAN REVIEW NEEDED, navigation) still green.

- [ ] **Step 7: Typecheck**

Run: `npm --prefix pi-ext/factory-watch run typecheck`
Expected: no errors (the `pair-dev` variant is exhaustively handled once Task 3 lands; until then `index.ts`'s `switch` has no `pair-dev` case but its `switch` is not exhaustive-typed, so this passes — confirm no TS error is reported).

- [ ] **Step 8: Commit**

```bash
git add pi-ext/factory-watch/src/mission-control-dashboard.ts pi-ext/factory-watch/test/mission-control-dashboard.test.ts
git commit -m "feat: dashboard pair-dev affordance for escalated dev"
```

---

### Task 3: Wire pair-dev in index.ts + widget alert + docs

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts` (`runMissionControl` switch ~80-131; `startBackgroundWidgetPoll` ~208-214)
- Modify: `pi-ext/factory-watch/README.md`

**Interfaces:**
- Consumes: `MissionControlAction` `pair-dev` variant (Task 2), `devEscalated` (Task 1), existing `resolveSessionPath` and `spawnTerminalWindow`.
- Produces: end-user behavior; nothing downstream consumes it.

This task is integration glue over already-tested primitives (`resolveSessionPath`, `spawnTerminalWindow`, `devEscalated`), mirroring the untested-at-index-level `inspect`/`review` cases and the `hrBlocked` widget line. Verification is typecheck + full suite + a manual smoke check.

- [ ] **Step 1: Import `devEscalated` in index.ts**

Update the `status-format.js` import to include `devEscalated`:

```typescript
import { formatStatusLines, parseStatus, devEscalated } from "./status-format.js";
```

- [ ] **Step 2: Add the `pair-dev` action case**

In `runMissionControl`'s `switch (action.type)`, add after the `case "review"` block (before the closing `}` of the switch):

```typescript
      case "pair-dev": {
        const path = resolveSessionPath(action.sessionId);
        if (path === null) {
          ctx.ui.notify("dev session not ready", "info");
          break;
        }
        spawnTerminalWindow("pi", ["--session", path], { cwd: ctx.cwd });
        ctx.ui.notify(
          "paired dev session opened — get unit tests green, then re-run the task to continue",
          "info",
        );
        break;
      }
```

- [ ] **Step 3: Add the dev-stuck widget line**

In `startBackgroundWidgetPoll`, after the existing `hrBlocked` push, add a dev-stuck line:

```typescript
        const hrBlocked = (record?.pipeline ?? []).some((e) => e.node === "human-review" && e.node_state === "blocked");
        if (hrBlocked) lines.push("⚠ human review needed — /factory-watch");
        if (devEscalated(record)) lines.push("⚠ dev stuck — /factory-watch to pair");
        ctx.ui.setWidget("factory", lines);
```

- [ ] **Step 4: Typecheck**

Run: `npm --prefix pi-ext/factory-watch run typecheck`
Expected: no errors — the `switch` now handles `pair-dev`; `resolveSessionPath`/`spawnTerminalWindow`/`devEscalated` are all in scope.

- [ ] **Step 5: Run the full factory-watch suite**

Run: `uv run python scripts/gates/watch_ext.py`
Expected: typecheck clean; `vitest run` reports all test files passed (including Task 1 & 2 additions). No regressions.

- [ ] **Step 6: Document the workflow in the README**

Add a section to `pi-ext/factory-watch/README.md` (under the mission-control / `/factory-watch` documentation):

```markdown
### Unblocking a stuck developer

When the developer node exhausts its retries with unit tests still red, mission
control shows `⚠ DEV STUCK` and the widget shows `⚠ dev stuck — /factory-watch
to pair`. To unblock:

1. Open `/factory-watch`, select the **developer** row, and press **Enter**.
   A new terminal window opens in the exact dev `pi` session that got stuck.
2. Pair with the agent until unit tests pass; let it finish (committing its
   work is natural but not required).
3. Close the window and re-run the task (`/factory-run <task>`). The factory
   detects the work is done (`already_done` routing), skips the dev node, and
   runs validation → review → done.

If the work isn't actually finished on re-run, the context-gatherer won't mark
it done, the dev node runs again, and it may escalate again — pair and re-run
as needed. The factory run is never held open waiting on you.
```

- [ ] **Step 7: Manual smoke check (document result in the commit)**

With a real run that escalates the dev node (or a hand-written `sessions/.factory-status.json` whose `dev` entry has `node_state: "escalate"`, `outcome: "escalated"`, and a real `session_id` from a prior `pi` run):
- `/factory-watch` shows the `⚠ DEV STUCK` banner.
- Selecting **developer** + Enter opens a new window running `pi --session <id>` in the repo, attached to that session's history.
- Confirm the notify hint appears.

Expected: the window opens and reattaches to the dev conversation. If `resolveSessionPath` returns null (session file not found), the notify says "dev session not ready" — check the session dir matches where the dev `pi -p` run saved (see spec §5.4).

- [ ] **Step 8: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/README.md
git commit -m "feat: open stuck dev session to pair, plus dev-stuck widget alert"
```

---

## Notes on the optional Python nicety (spec §6)

The spec flags one optional, purely cosmetic Python touch: `run_dev`'s escalate
`handoff` string (`src/factory/orchestrator/nodes.py:203-207`). It is **not**
part of this plan (the Global Constraint is zero orchestrator changes). If you
later want the dashboard's dev handoff line to mention pairing, that is a
separate one-line change with its own test update in the orchestrator suite —
do it deliberately, not as part of this feature.

## Self-review

- **Spec coverage:** §2 realization (session id already present, `already_done`, changed_files) → relied on, not re-implemented (correct — Task 1 only *reads* the sticky session id). §5.1 detector → Task 1. §5.2 banner + widget → Task 2 (banner) + Task 3 (widget). §5.3 pair action → Task 3. §5.4 session-dir robustness → Task 3 Step 7 smoke note. §5.5 README workflow → Task 3 Step 6. §7 testing → Tasks 1–2 unit tests + Task 3 full-suite/smoke. §6 optional nicety → explicitly excluded, documented above. No gaps.
- **Placeholder scan:** none — every code and test step shows complete content; commands have expected output.
- **Type consistency:** `devEscalated(record: StatusRecord | null): { sessionId: string } | null` defined in Task 1, consumed identically in Tasks 2 & 3; `MissionControlAction` `pair-dev` variant `{ type: "pair-dev"; sessionId: string }` defined in Task 2, matched by the Task 3 `case "pair-dev"` reading `action.sessionId: string` and passing it to `resolveSessionPath(sessionId: string)`. Consistent.
