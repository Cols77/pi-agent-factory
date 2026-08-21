---
dod:
- 'Subagent/pi_backend spawn is liveness-aware: a child that writes its target file
  (or otherwise progresses) is not killed by the idle timeout.'
- The idle/timeout contract distinguishes "quiet because thinking hard and about to
  deliver" from "stalled"; no false-positive kills on long text-authoring runs.
- 'Process-tree termination: a timed-out/cancelled child is killed as a whole tree
  (SIGTERM -> grace -> SIGKILL, verified), so grandchildren/descendants do not leak
  after a kill.'
- 'Transient spawn retry: a failed launcher spawn (pi ENOENT/one-off) is retried with
  bounded backoff before being reported as a spawn failure.'
- 'Output hard-cap: the streaming consumer enforces a total stdout/stderr ceiling
  (and bounded per-line retention) so a pathological child cannot flood memory or
  disk.'
- Tests/gates pass (backend/grill for python, vitest for pi-ext) and changes committed.
id: T-029
status: done
title: 'Harden subagent/pi_backend spawn lifecycle: liveness-aware idle, process-tree
  kill, transient retry, output cap'
trace_exempt: true
trace_exempt_reason: 'T-029 is exempt from both open gaps. (1) task_no_sr: no
  requirement node governs this hardening task -- the repo-wide task->SR
  linkage is 0/22 (no SRs exist to satisfy), and T-029 is a
  resilience/hardening task executed directly from its own brief. (2)
  task_no_plan: the original plan ref
  (docs/superpowers/plans/2026-08-20-subagent-liveness-aware-timeouts.md) was
  dropped as dangling in commit 0f40d87 because that plan file was never
  created; the task note says it ''gets its own implementation plan when
  scheduled'' -- none was ever authored, and the task was executed directly
  from its own brief (the task file IS the spec), so there is no plan file to
  link.'
---

## Scope

- Python orchestrator: `src/factory/orchestrator/pi_backend.py` (+ `test_pi_backend.py`)
- TypeScript extension sibling: `pi-ext/factory-watch/src/subagent-tool.ts` (+ its
  vitest). The **liveness-aware idle on the TS side landed earlier** (this session):
  `createIdleKeeper` + `probeFileHeartbeat` + deliverable-dir heartbeat in
  `executeSubagent`. Treat that as the **reference implementation** to port to the
  python side; it is NOT left to redo on TS.

## Background

Dispatching four plan-authoring subagents (all four wrote their 30–55K plan
files successfully) reported three as *failed/timeouts*, even though the
deliverables landed on disk.

Root cause 1 (liveness): `_drain_lines` treats "no stdout line for N seconds"
as a stall (`idle`, default `FACTORY_AGENT_IDLE_TIMEOUT_S` = 300 s) and "no total
completion within wall-clock" as runaway (`total`, 1200 s). A child that spends
tens of minutes authoring a large text deliverable is legitimately quiet at the
end (long generate-then-write burst), so it trips the kill *after* writing its
file but *before* returning its structured result. The work survives; the
completion signal does not. Reference rationale from mature OSS (pi-subagents /
pi-background-tasks): idle must exceed the longest plausible *single turn*, and
a "strike count" + file-activity signal distinguishes quiet-but-productive from
stalled.

The remaining items are the sibling hardening:
1. **Process-tree termination** — kill the whole child tree (SIGTERM → grace →
   SIGKILL, poll until descendant group is gone) so grandchild processes do not
   leak after an idle/total kill or a cancelled dispatch. POSIX-focus; keep a
   safe fallback on Windows.
2. **Transient spawn retry** — retry the `pi` launcher spawn with bounded backoff
   on clear-once failures (missing bin, one-off race) before reporting
   `subagent spawn failed`; do not retry genuine stalls.
3. **Output hard-cap** — a total stdout/stderr ceiling on the streaming consumer
   (on top of our bounded per-line retention) so a pathological or runaway child
   cannot flood memory/disk unboundedly.

Alignment: the behaviour duplication with `grill.py`'s agent lock/timeout is in
scope to align or call the shared helper.

## What "liveness-aware" means here

The fix must not weaken the guard that a genuinely stalled agent cannot hang the
pipeline forever (the 38 MB runaway that motivated the timeout). A *productive*
child — one whose stdout shows it is mid-generation, or whose working directory
shows its target files being written — must count as alive. The TS reference
does this with a strike-count grace (default 4 silent windows) plus a
file-heartbeat probe over the deliverable dirs (docs/plans/tasks/requirements),
resetting the strike on any output line, stderr byte, or fresh file write. The
same contract, plus items 1–3 above, must hold on `pi_backend.py`.

## Acceptance

- A stubbed/liveness test reproduces the old failure: a child that writes its
  target file and then stays quiet is *not* killed during the idle window.
- A genuine-stall still trips the idle/timeout kill (regression guard).
- Killing a child that spawned grandchildren leaves no live descendant
  (process-tree assertion, POSIX).
- A failed transient spawn is retried (bounded backoff) but a true stall is not.
- A pathological stream is capped at the configured stdout/stderr ceiling while
  still returning the extracted answer.
- Existing backend/grill tests still pass; ruff/pyright clean; TS vitest green.