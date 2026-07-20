# Design: Live Workflow Visualization for the Dev Factory

**Date:** 2026-07-20
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Framing

The dev factory (Plans 1-3, all complete and merged to `main`) is a deterministic
Python orchestrator (`src/factory/orchestrator/`) that drives tasks through
Context-Gatherer → Dev → Validation → Review, spawning fresh `pi` sub-agent
processes per node, each scoped by the `scope-guard` Pi extension
(`pi-ext/scope-guard/`). It is invoked headlessly:
`uv run python -m factory.orchestrator run [--provider P] [--model M]`.

That CLI is fire-and-forget: it blocks until the whole task finishes (or
escalates/rejects) and prints nothing until then. This spec adds a way to watch
it run **live, from inside an interactive `pi` session** — which node is
active, pass/fail/retry/escalate outcomes, a short live snippet of what the
current sub-agent is doing — without turning the orchestrator itself into
something interactive.

### 1.1 Goals

- Launch a factory run from inside `pi` with a single command, using whatever
  provider/model is already active in that session — no separate
  configuration.
- Show live status in a widget inside the `pi` TUI: current node, attempt
  count, outcome, and a short live snippet of the running sub-agent's output.
- Run in the background so the user's own `pi` session stays usable while a
  task runs.
- Allow cancelling a running task from inside `pi`, without orphaning the
  child `pi` subprocess (and its still-running, still-billing LLM call).

### 1.2 Non-Goals

- **Not an interactive chat UX for the sub-agents.** The orchestrator's whole
  value is deterministic, headless routing on gate exit codes and validated
  artifacts — never free-form back-and-forth. This spec is purely observational:
  nothing it adds feeds back into routing.
  Anyone who wants `pi`'s own interactive chat UX already has it: `pi` itself.
- **Not a queue/multi-task dashboard.** `run_next` processes one task at a
  time; this spec visualizes one run at a time. A multi-task queue view is a
  separate, later concern if it's ever needed.
- **Not full-transcript viewing.** Drilling into a node's complete
  prompt/response exchange is out of scope for v1 — a short live snippet is
  enough to see what's happening.
- **No new IPC mechanism.** No sockets, no named pipes. Communication between
  the orchestrator (Python) and the watching extension (TypeScript) stays
  file-based, matching the factory's existing convention (task ledger, session
  records, KB — all files).

---

## 2. Architecture Overview

```
Interactive pi session                    Background process
┌─────────────────────────────┐           ┌──────────────────────────────┐
│ pi-ext/factory-watch/        │  spawns   │ uv run python -m              │
│  /factory                    ├──────────►│   factory.orchestrator run    │
│   - reads ctx.model           │  detached │   --provider <active>        │
│     (provider/id already      │           │   --model <active>           │
│     active in this session)  │           │                              │
│  /factory-stop                │           │  writes:                    │
│                               │           │   sessions/.factory-run.lock │
│  polls (~1/sec):             │◄──────────┤   sessions/.factory-status   │
│   sessions/.factory-status   │   reads    │    .json  (atomic writes)   │
│  renders via                 │           │                              │
│   ctx.ui.setWidget()         │           │  spawns fresh `pi` per node, │
└─────────────────────────────┘           │  same as today (unchanged)   │
                                            └──────────────────────────────┘
```

Two independent `pi` process contexts are involved, and it's important they
stay conceptually separate:

- **`scope-guard`** loads inside each *sub-agent's* `pi` process (spawned by
  `PiAgentBackend`), enforcing write scope for that node.
- **`factory-watch`** (this spec) loads inside the *user's own* interactive
  `pi` session, and only ever launches/observes the orchestrator — it never
  talks to the sub-agent processes directly.

---

## 3. Components

### 3.1 `src/factory/orchestrator/status.py` (new)

A `StatusReporter` protocol, mirroring the existing `AgentBackend`/`GateRunner`
Protocol+Fake pattern already used throughout the orchestrator:

- `FileStatusReporter(path: Path)` — writes the current status as JSON via a
  temp-file-then-rename, so a concurrent reader (the extension) can never see
  a half-written file.
- `NullStatusReporter` — default no-op. Every node executor takes an optional
  `status: StatusReporter = NullStatusReporter()` kwarg. This is purely
  additive: existing Fake-backed tests pass a `NullStatusReporter` implicitly
  and are otherwise untouched.

Status file shape (informal — see §6 on why this isn't schema-validated):

```json
{
  "session_id": "2026-07-20T10-15-00Z",
  "task_id": "T-001",
  "node": "dev",
  "node_state": "running",
  "attempt": 2,
  "max_attempts": 3,
  "snippet": "...last ~200 chars of the current sub-agent's streamed output...",
  "outcome": null,
  "started_at": "2026-07-20T10:15:00Z",
  "updated_at": "2026-07-20T10:16:42Z"
}
```

`node_state` is one of: `running`, `pass`, `fail`, `retry`, `reject`,
`changes-requested`, `escalate`, `error`. `outcome` is `null` while running,
else one of `completed | rejected | escalated`.

### 3.2 `PiAgentBackend` streaming

Currently `PiAgentBackend.run` uses a blocking `subprocess.run(...)` and only
sees output once the sub-agent process exits. This spec changes it to
`Popen` + incremental stdout read, so `status.report_snippet(...)` can be
called as text arrives (truncated to the last ~200 chars), not just at the
end. The final block-extraction logic (`parse_pi_json`, the field-mismatch
detector) is unchanged — the accumulated stdout is still handed to it exactly
as today; only the *live snippet* is new.

### 3.3 PID lock file

`run_next` writes `sessions/.factory-run.lock` (its own `os.getpid()`, not
something the extension has to infer from the `uv run` wrapper's PID, which
may not be the real interpreter's PID) at the start of a run, and removes it
in a `finally` block. A second `/factory` invocation while one is already
running checks this file and refuses to start a duplicate — showing current
status instead.

### 3.4 `pi-ext/factory-watch/` (new extension)

Following the same shape as `scope-guard`: pure, unit-tested functions for
anything that doesn't need a live subprocess or `pi`'s runtime (parsing the
status file into display lines, deciding whether a lock is stale, building
the platform-specific kill command), thin wiring in `index.ts` for the actual
`pi.registerCommand()` / `ctx.ui.setWidget()` / `child_process.spawn()` calls.

- **`/factory`** — reads `ctx.model.provider` / `ctx.model.id` (confirmed
  available on `ExtensionContext`), spawns
  `uv run python -m factory.orchestrator run --provider <provider> --model <id>`
  detached, so it inherits the session's already-working credentials with no
  extra configuration. Starts polling the status file and renders it via
  `ctx.ui.setWidget()`.
- **`/factory-stop`** — reads the lock file's PID, terminates it (§4).

---

## 4. Cancellation

The part most likely to go wrong, especially on Windows: killing only the
orchestrator's own PID risks leaving its child `pi` subprocess (and its
in-flight, still-billing LLM call) running as an orphan.

Design: the orchestrator installs its own termination handler and, on
receiving it, terminates its currently-running `pi` child before exiting and
marks the status file `node_state: "error"` / a distinct cancelled marker.
`/factory-stop` sends a **graceful** terminate first, and falls back to a
**forceful** kill only if the process hasn't exited after a short timeout —
matching the existing win32/posix branching already present elsewhere in this
codebase (e.g. `scripts/gates/ext.py`'s `npm.cmd` handling). Exact platform
commands (e.g. `taskkill` flags) are an implementation-plan-level detail, not
a spec-level one — the requirement is: no orphaned sub-agent process, on
either platform.

---

## 5. Error Handling

- **Stale lock** (orchestrator crashed without cleanup): `/factory` checks
  whether the PID in the lock file is still alive; if not, treats the lock as
  stale, clears it, and proceeds.
- **Orchestrator crash mid-run**: `run_next`'s top-level call is wrapped so
  any uncaught exception writes a final `node_state: "error"` status (with
  the exception message) before the process exits non-zero, instead of the
  status file just going silently stale.
- **Status looks stalled**: v1 just shows "last updated Xs ago" rather than
  guessing hung-vs-slow — a real LLM call can legitimately take a while, and
  building a hang-detection heuristic isn't needed yet (YAGNI).
- **Concurrent `/factory` calls**: prevented by the lock file (§3.3).

---

## 6. Deliberately Out of Scope for v1

- **No JSON Schema for the status file.** Unlike the factory's actual pipeline
  artifacts (context manifest, session record, KB entries), this file is
  purely observational — nothing routes on it, nothing downstream depends on
  its exact shape. Schema-validating it would be machinery this spec doesn't
  need yet.
- **No override of provider/model.** `/factory` always uses the session's
  currently active model. Explicit override args can be added later if it
  turns out to matter.

---

## 7. Testing Strategy

- **Python**: `FileStatusReporter`/`NullStatusReporter` get direct unit tests
  (write, read back, confirm atomicity via the temp-file+rename pattern).
  Node executors' status calls are tested the same way `AgentBackend`/
  `GateRunner` calls already are — a `FakeStatusReporter` recording calls,
  injected into the existing Fake-backed tests, asserting the right
  node/state/attempt sequence.
- **`PiAgentBackend` streaming**: the incremental-parsing logic is extracted
  into a pure function (same pattern as `_build_command` /
  `_has_json_events_without_text_field`), directly testable without a real
  subprocess.
- **TypeScript**: pure functions (status-file parsing, stale-lock detection,
  platform kill-command construction) get vitest coverage, following
  `scope-guard`'s precedent exactly. Thin wiring (`ctx.ui.setWidget()`,
  `child_process.spawn()`) stays thin and isn't the primary test surface.
- **Required manual verification** (like Plan 2's and Plan 3's live Pi
  spikes): actually run `/factory` inside a real interactive session, confirm
  the widget updates, run `/factory-stop`, and confirm via the process list
  that nothing is orphaned. This can't be fully proven by unit tests alone
  and must be an explicit step in the implementation plan, not assumed.

---

## 8. Cross-Plan Dependencies

Consumes, unchanged: the orchestrator's existing node executors and
`AgentBackend`/`GateRunner` pattern (Plan 3), `PiAgentBackend` (Plan 3, gets
the streaming change described in §3.2), and the `scope-guard` extension
(Plan 2, unchanged — it continues to load only inside spawned sub-agent
processes, unaffected by this work).
