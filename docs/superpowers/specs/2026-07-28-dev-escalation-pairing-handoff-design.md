# Design: Dev-escalation pairing handoff — resume the stuck dev session

**Date:** 2026-07-28
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Problem

When the dev node exhausts its retries with unit tests still red, `run_dev`
returns `NodeOutcome.ESCALATE` and `run_task` returns terminally
(`runner.py:114-116`). `run_next` flips the task back to `todo`
(`runner.py:261`) and the run ends. The dev agent's partial edits are left in
the working tree, and there is **no supported path for a human to step in,
finish the work with the agent, and have the pipeline continue.**

The desired experience: drop into the exact dev `pi` session that got stuck,
pair with the agent to get unit tests green, and have the pipeline continue
cleanly through validation → review → done.

## 2. Key realization — the machinery already exists

Two mechanisms already present in the repo, combined, deliver this with **no
orchestrator (Python) changes at all**:

1. **Open-session-in-a-window already exists.** `index.ts:94` already calls
   `spawnTerminalWindow("pi", ["--session", path], { cwd })`. Dropping into a
   saved pi session in a fresh interactive window is a solved problem, and `pi`
   natively supports `--session <partial-uuid|id>` (verified via `pi --help`).

2. **`already_done` re-run routing already exists.** When a task re-runs and
   its deliverables already satisfy the Definition of Done, the context-gatherer
   marks the manifest `already_done` and the runner **skips the dev node,
   routing straight to validation → review** (`nodes.py:93`, `runner.py:82-85`).
   The sim/review gates still confirm the work; if it is *not* actually done,
   the gates fail and dev runs normally on the next iteration — the routing is
   self-correcting by design.

Three supporting facts make this robust and confirm no Python change is needed:

- **The dev session id is already in the status file.** During its running
  phase, `run_dev` reports `session_id` for the `dev` node
  (`nodes.py:161-167`). The `FileStatusReporter` sticky-field logic
  (`status.py:148-156`) preserves `session_id` on the node's entry across its
  final (escalate) report. So the escalated `dev` entry already carries the
  **last dev attempt's** pi session id, ready for the dashboard to read.

- **The escalated state is already detectable.** The `dev` pipeline entry ends
  with `node_state: "escalate"` and `outcome: "escalated"`
  (`nodes.py:203-207`).

- **The fix is visible to review whether or not it is committed.**
  `changed_files` uses a single-ref diff (`git diff --name-only <start_commit>`,
  `git_ops.py:41-53`), which picks up committed *and* uncommitted working-tree
  changes. On re-run, `start_commit` is HEAD at run start; an uncommitted
  pairing fix is therefore still seen by the review node. A committed fix
  funnels into the standard `already_done` (empty-diff) review path. Either way
  works.

By escalate time the dev `pi -p` subprocess has **already exited** (all retries
ran to completion, `nodes.py:155-208`), so its session transcript is a closed
file on disk. The human resumes it in a fresh interactive process — no pty
juggling, no concurrency on the session file.

## 3. Decision

Deliver dev-escalation intervention as a **first-class resumable handoff**, not
a new blocking gate:

- On dev-escalate (today's terminal behavior is unchanged), the dashboard
  surfaces a "pair to unblock" affordance that opens `pi --session <id>` in a
  new window, reusing the existing `spawnTerminalWindow` call.
- The human pairs with the agent, gets unit tests green, exits.
- The human re-runs the task (`/factory-run <task>` / `factory.orchestrator run
  --task <id>`). The `already_done` routing carries it cleanly through
  validation → review → done.

Rejected alternative — a **blocking `DevEscalationGate`** cloning the
human-review apparatus (new Protocol + File/Fake gate + poll file + window-spawn
+ inline re-verify + round bounds + `--auto` branch). It gives a single
uninterrupted "block → pair → auto-continue" flow, but at the cost of a large
new failure surface and holding the run (and lock) open, polling for an
unbounded human pairing session. The handoff approach reuses two tested paths,
never blocks the orchestrator, and costs the human one explicit "re-run" action
after pairing.

Also rejected — **routing escalation into the existing human-review gate**
(diff browser + file editor). Reuses the most code, but "help" becomes editing
files in a diff browser rather than pairing with the agent in its session, which
is not the requested experience.

## 4. Scope

**In scope (all in `pi-ext/factory-watch/`, TypeScript):**
- Detect the dev-escalated state from the status record.
- A dashboard affordance to open `pi --session <devSessionId>` in a new window.
- A user-facing hint to re-run the task after pairing.
- README documentation of the workflow.

**Out of scope:**
- Any change to `src/factory/` (the Python orchestrator). This feature adds
  **zero** orchestrator changes.
- Intervening *before* escalation (only the post-escalate state is handled).
- `--auto` runs (no dashboard, no human; terminal escalate unchanged).
- Auto-committing the pairing fix or auto-re-running the task (the human does
  the re-run explicitly; the resume is robust with or without a commit).

## 5. Design — dashboard enhancement

Mirror the existing human-review affordance
(`mission-control-dashboard.ts:59-62`, which already renders a
"⚠ HUMAN REVIEW NEEDED" banner + Enter action when a `human-review` entry is
`blocked`). Add a parallel path for the dev-escalated state.

### 5.1 Detection helper

A pure function over the parsed status record, unit-testable in isolation:

```
devEscalated(record): { sessionId: string } | null
  → find pipeline entry where node === "dev"
      and (node_state === "escalate" || outcome === "escalated")
      and typeof session_id === "string"
  → return { sessionId } or null
```

Returns `null` (no affordance) when the dev node is not escalated or no session
id was captured (e.g. an escalate before the agent ever emitted a session
event).

### 5.2 Banner + widget

- **Dashboard banner** (`mission-control-dashboard.ts`): when `devEscalated`
  is non-null, render
  `⚠ DEV STUCK — select dev and press Enter to pair, then re-run the task`,
  alongside the existing human-review banner logic.
- **Status widget** (`index.ts` ~209-214): when dev-escalated, append
  `⚠ dev stuck — /factory-watch to pair`, mirroring the existing
  `hrBlocked` widget line.

### 5.3 Pair action

In the dashboard action handler (`index.ts`, alongside the existing `"review"`
case ~110-115): a `"pair-dev"` action reads the record, resolves the escalated
dev session id via `devEscalated`, and calls:

```
spawnTerminalWindow("pi", ["--session", sessionId], { cwd: ctx.cwd })
```

This is the identical call already used on `index.ts:94`. No new spawn
machinery. The window is a normal interactive `pi` (no `-p`, no `--mode json`),
so the human and the resumed agent pair freely.

### 5.4 Session-dir agreement (robustness note)

The dev `pi -p` runs save sessions to pi's default session dir (no
`--no-session`), and `pi --session <id>` resolves against that same default from
the repo root (`cwd: ctx.cwd`), so they agree by default. If a future change
pins `--session-dir` for dev runs, the pairing spawn must pass the same
`--session-dir`. Called out so the two invocations never drift apart.

### 5.5 Workflow (README)

Document the loop in `pi-ext/factory-watch/README.md`:

1. Dashboard shows `⚠ DEV STUCK` for a task.
2. Select the dev node, press Enter → a new window opens in the stuck dev
   session.
3. Pair with the agent until unit tests pass; let the agent finish (committing
   its work is natural but not required).
4. Close the window and re-run the task. The factory detects the work is done
   (`already_done`), skips dev, and runs validation → review → done.

If the work is not actually finished on re-run, the context-gatherer will not
mark it `already_done`, dev runs again, and it may escalate again — pair and
re-run as needed. The orchestrator is never held open waiting.

## 6. Optional nicety (not required)

`run_dev`'s escalate report sets `handoff="escalated: unit tests still red"`
(`nodes.py:203-207`). A one-line copy tweak to mention pairing (e.g.
`"escalated: unit tests still red — pair in the dev session to unblock"`) would
improve the dashboard message. This is the *only* place a Python touch could
help, it is purely cosmetic, and it is explicitly optional — the feature works
without it.

## 7. Testing

All new code is TypeScript in `factory-watch`; mirror the existing
`mission-control-review.test.ts` / `mission-control-dashboard.test.ts` /
`status-format.test.ts` patterns.

- **`devEscalated` detection** — unit tests over crafted status records:
  escalated dev entry with session id → returns it; escalated dev entry with no
  session id → `null`; non-escalated dev → `null`; no dev entry → `null`;
  escalated dev with sticky session id preserved from a prior running report →
  returns it (guards the sticky-field assumption in §2).
- **Banner / widget rendering** — the dev-stuck line appears exactly when
  `devEscalated` is non-null, and does not clobber the existing human-review
  banner when both could apply.
- **Pair action** — resolves the correct session id and invokes
  `spawnTerminalWindow` with `["--session", <id>]` and the right `cwd`
  (spy/fake the spawn, mirroring how `terminal-window.test.ts` and the review
  spawn are tested).

No Python tests are added, because no Python changes are made. (If the optional
§6 handoff copy tweak is taken, its only assertion is the string in an existing
`run_dev` escalate test.)

## 8. Risks

- **The dev session must be resumable.** Depends on the dev `pi -p` run having
  saved its session (it does — no `--no-session`) and on the captured
  `session_id` matching what `pi --session` accepts (it is pi's own `session`
  event id). Low risk; both are existing, observed behaviors, but worth a live
  smoke check on the first real escalate.
- **The pairing fix must be genuinely complete for a clean re-run.** If not,
  `already_done` will not trigger and dev re-runs — acceptable and
  self-correcting, but the human should verify unit tests are actually green
  before re-running to avoid a wasted cold dev cycle.
- **Sticky `session_id` assumption.** The whole "zero Python change" claim rests
  on `status.py:148-156` preserving `session_id` onto the escalated dev entry.
  The `devEscalated` detection tests (§7) pin this; if a future status refactor
  changes sticky behavior, those tests fail loudly.
