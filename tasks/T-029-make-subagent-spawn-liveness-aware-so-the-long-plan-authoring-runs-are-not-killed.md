---
dod:
- 'Subagent/pi_backend spawn is liveness-aware: a child that writes its target
  file (or otherwise progresses) is not killed by the idle timeout.'
- 'The idle/timeout contract distinguishes "quiet because thinking hard and
  about to deliver" from "stalled"; no false-positive kills on long
  text-authoring runs.'
- All steps in this task complete; tests/gates pass; committed
id: T-029
status: todo
title: Make subagent spawn liveness-aware so long plan-authoring runs are not killed
---

- Modify: `src/factory/orchestrator/pi_backend.py`
- Test: `src/factory/orchestrator/test_pi_backend.py` (or nearest existing backend test)

## Background

Dispatching four plan-authoring subagents (all four wrote their 30–55K plan
files successfully) reported three as *failed/timeouts*, even though the
deliverables landed on disk. Root cause: `_drain_lines` treats "no stdout line
for N seconds" as a stall (`idle` timeout, default `FACTORY_AGENT_IDLE_TIMEOUT_S`
= 300 s) and "no total completion within wall-clock" as runaway (`total`,
`FACTORY_AGENT_TOTAL_TIMEOUT_S` = 1200 s). A child that spends tens of minutes
authoring a large text deliverable is legitimately quiet at the end (long
generate-then-write burst), so it trips the idle/total kill *after* writing its
file but *before* returning its structured result. The work survives; the
completion signal does not — the harness treats the run as failed.

Refs: `src/factory/orchestrator/pi_backend.py` `_drain_lines` +
`run_pi_command` timeout handling. When this task is scheduled, it gets its own
implementation plan (source_plan) under docs/superpowers/plans/.

## What "liveness-aware" means here

The fix must not weaken the guard that a genuinely stalled agent cannot hang the
pipeline forever (the 38 MB runaway that motivated the timeout). Rather, a
*productive* child — one whose stdout shows it is mid-generation, or whose
working directory shows its target files being written — must count as alive.
Minimum honest options a plan-author session could take:

- Treat "newly-written or modified files under a configured target/watch dir
  (the plan's own output path or the repo's tasks/docs/…) since the last idle
  tick" as a heartbeat that resets the idle bound.
- Only trip the idle kill after N consecutive idle breaches (a grace multiplier),
  so a single quiet think-then-write burst does not kill a working child.
- For plan-authoring (or any text-heavy) spawns, surface a live
  "still working" marker (progress heartbeat) so the idle detector never
  trips during a long generation.

Pick and implement the option that keeps a genuinely-stalled child bounded
(same total ceiling) while letting a productive-but-quiet child finish. The
behaviour duplication with `grill.py`'s agent lock/timeout is in scope to align
or call the shared helper.

## Acceptance

- A stubbed/livelihood test reproduces the old failure: a child that writes its
  target file and then stays quiet is *not* killed during the idle window.
- A genuine-stall still trips the idle/timeout kill (regression guard).
- Existing backend/grill tests still pass; ruff/pyright clean.