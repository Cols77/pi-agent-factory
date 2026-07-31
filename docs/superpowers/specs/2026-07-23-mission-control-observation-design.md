# Mission Control — Observation Increment (Increment 1) — Design

**Status:** design, pending user review
**Date:** 2026-07-23
**Repo:** pi-agent-factory (`pi-ext/factory-watch` + `src/factory/orchestrator`)

## Goal

Turn mission control from a bare status board into a useful observation surface: open any agent's real pi session natively (view + continue it), see meaningful per-stage summaries in the pane, tail the log for non-agent stages, and reach the existing human-review diff navigator from the dashboard — all by reusing capabilities that already exist (`pi --session`, `review-overlay`), with no changes to the orchestration pipeline itself.

## Guiding principle: observe vs. control

The mission-control dashboard is a **pure observer** — a standalone process that reads `sessions/.factory-status.json` and spawns other windows. Everything in this increment is observational and needs no channel back to the running orchestrator. Anything that *influences* the running factory (deciding a review from the dashboard, pausing/steering the pipeline) requires a new bidirectional control channel and is explicitly **deferred to Increment 2** (see Deferred Work).

## Scope

**In scope (Increment 1):**
- **A.** Open an agent row → `pi --session <file>` in a new window (native rendering + the user can continue that agent).
- **B.** Richer per-row summaries in the dashboard (surface structured output the roles already emit).
- **D.** Rows with no pi session (validation, not-yet-started) → tail that stage's captured log instead of "no agent session."
- **E1.** Select the human-review row → open the existing `review-overlay` to **browse** the diff (navigate changes), reusing today's UI.
- **C.** Remove the old dirty-log transcript viewer (`mission-control-transcript.ts`), superseded by A + D.

**Prerequisite (must be fixed first, see below):**
- **Bug.** Human-review reports 0 changed files (and reportedly crashes) when there should be changes. E1 reuses that same diff computation, so it must be fixed before E1 is meaningful.

**Deferred (Increment 2 — its own spec):**
- **E2.** Make the review approve/reject decision *from* the dashboard (not just browse).
- **F.** Intrusive workflow control: pause between stages, take over, steer. `pi --session` already gives a partial single-agent takeover for free.

## Prerequisite bug: human-review reports 0 changes

Before E1, run a real `systematic-debugging` pass on the human-review stage. Two distinct symptoms to reproduce and root-cause separately: (1) it "crashes during execution"; (2) it reports 0 changed files when changes exist. **Leading hypothesis (must be verified, not guess-fixed):** the diff range (`start_commit..HEAD` or an equivalent) misses the dev agent's changes when they are uncommitted, or `start_commit` is captured at the wrong point relative to when dev commits — same family as the `git_ops.changed_files` working-tree fix made earlier. Investigate `start_commit` capture in `runner.py` and `computeReviewFiles` in `pi-ext/factory-watch/src/review-diff.ts`. Fix the root cause with a failing test that reproduces the 0-changes case first.

## Data model change (additive only)

`FileStatusReporter.report(...)` and its peers (`StatusReporter` protocol, `NullStatusReporter`, `FakeStatusReporter`) gain three optional keyword-only params, written into each pipeline entry:

- `session_id: str | None = None` — the pi session uuid for an agent stage (Feature A).
- `summary: str | None = None` — a short human-readable per-stage summary (Feature B).
- `start_commit: str | None = None` — the base commit for the human-review diff (Feature E1).

The `.factory-status.json` pipeline entry shape becomes:
`{ node, node_state, attempt, max_attempts, snippet, outcome, handoff, session_id?, summary?, start_commit?, updated_at }`.

Purely additive: existing fields and readers are unaffected.

## Feature A — Open agent = native pi session

**Session id capture (Python):** each role run's stdout begins with a `session` event carrying `id` (verified: that id equals the on-disk filename uuid). Add `parse_session_id(stdout) -> str | None` in `pi_backend.py`; populate a new `AgentResult.session_id: str | None = None` field in `PiAgentBackend.run()`.

**Thread through:** `nodes.py` role-runners pass `result.session_id` into `status.report(..., session_id=...)`; `runner.py` unchanged except that the value flows via the existing `status.report` calls.

**Path resolution (TS, dashboard):** the session uuid is globally unique, so resolve without depending on pi's project-slug convention: glob `~/.pi/agent/sessions/*/*_<session_id>.jsonl` and take the match. (Store the id, not a path — robust against slug-format changes.)

**Open action:** on Enter over an agent row that has a `session_id`, `spawnTerminalWindow("pi", ["--session", <resolvedPath>], { cwd })` (using the `cmd start` mechanism). Multiple attempts: the row carries the latest attempt's `session_id`, so Enter opens the latest.

## Feature B — Richer row summaries (surface-what-exists)

Build a short `summary` string in `nodes.py` where each role's output is already parsed, and pass it to `status.report(..., summary=...)`. No agent-prompt changes.

- context-gather → e.g. `"5 source files; coherence proven"` (from the manifest).
- dev → e.g. `"changed 3 files; unit tests pass"`.
- review → the actual short finding texts, e.g. `"requested: fix error handling; extract magic number"` (today only the count reaches `handoff`).

Dashboard: `formatMissionControlRows` includes `summary`; `render()` prints it under the row, width-wrapped.

## Feature D — Tail the log for non-agent / no-session rows

For rows without a `session_id`:
- **validation** (deterministic gate, no pi session): begin capturing the validation gate's stdout to a per-stage log file under the session's transcript dir; Enter opens a new window that **simply tails that log file** — a plain OS/tool tail-follow (e.g. `spawnTerminalWindow` running `powershell Get-Content -Wait -Tail` on win32 / `tail -f` on unix), printing lines verbatim. No custom viewer, no JSON parsing, no formatting.
- **not-yet-started** stages: show "pending" (nothing to tail yet).

Relationship to C: the old `mission-control-transcript.ts` viewer is deleted outright; D adds no replacement viewer — it just tails a file.

## Feature E1 — Human-review row → browse the diff

Record the human-review `start_commit` in the status entry (`start_commit=...`) when the pipeline blocks for human review (the "blocked" status report already fires here). On Enter over the human-review row, the dashboard opens the existing `review-overlay` in **browse mode** for that `start_commit` (reuse `computeReviewFiles` + the overlay's navigation). No decision is sent back in this increment — approve/reject stays in the existing pif interactive flow (E2 deferred).

## Removal — dirty-log viewer (C)

Delete `mission-control-transcript.ts`, its test, `buildTranscriptPath`, and the `onSelectTranscript → transcript` wiring. Its two roles are replaced: agent rows → `pi --session` (A); non-agent rows → minimal tail (D).

## Invariant to preserve (call out for review)

**The orchestration pipeline is untouched.** All Python changes are additive telemetry (parse a session id, build summary strings, record start_commit). None of them alter `run_task`'s control flow, the validation/review/human-review gates, the review-findings→dev feedback loop, or how roles hand off manifest/kb-entries/feedback via `compose_prompt`. The plan's reviewer must confirm the gate logic and agent-to-agent handoffs are byte-for-byte unchanged.

## Components touched

**Python:** `orchestrator/types.py` (`AgentResult.session_id`), `orchestrator/pi_backend.py` (`parse_session_id`, populate it), `orchestrator/status.py` (three new optional params), `orchestrator/nodes.py` (build `summary`, pass `session_id`/`summary`/`start_commit`), `orchestrator/runner.py` (pass `start_commit` for human-review; thread values via existing report calls), validation-gate output capture for D.

**TypeScript (`pi-ext/factory-watch/src`):** `status-format.ts` (carry `session_id`/`summary`/`start_commit` on the row), `mission-control-dashboard.ts` (resolve session path + `pi --session`; render summaries; tail for no-session rows; human-review → `review-overlay`), remove `mission-control-transcript.ts`, reuse `review-overlay.ts`/`review-diff.ts`, `terminal-window.ts` unchanged.

## Testing

- Python: unit-test `parse_session_id`; that `report` persists the new fields; that each role produces the expected `summary`. Keep the existing pipeline/gate tests green (proves the invariant).
- TS: unit-test session-path resolution (uuid glob), row rendering of `summary`, Enter dispatch (mocked `spawnTerminalWindow`) for agent rows (`pi --session`), no-session rows (tail), and human-review (review-overlay). Reuse the real-`node <file>.ts` smoke pattern for any new standalone path.
- The prerequisite bug gets its own failing-test-first fix.

## Open risks

- **pi --session on a still-writing session** (mid-run role) shows a snapshot / may be partial. Accepted per user direction; not gated.
- **validation-gate log capture** is new surface; keep it a thin redirect to a file.
- **review-overlay reuse in the standalone dashboard** must be import-clean under `node <file>.ts` (the constructor-param-property / `.ts`-import pitfalls already fixed elsewhere apply here too).
