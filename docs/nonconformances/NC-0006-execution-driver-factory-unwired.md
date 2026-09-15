---
id: NC-0006
title: No production driver_factory exists anywhere; dispatch-task cannot complete any task through any host
external_ref: null
detected_by: T-057 governed-execution dispatch attempt
status: open
---

## Symptom

`coherence execution dispatch-task` fails closed with `EXECUTION_WIRING_UNAVAILABLE` for
**every** task, on **every** host, today — not specific to any one task, run, or invocation
mistake. Reproduced on this session's attempt to dispatch `T-057` (`run_id=T-057`,
`task_id=T-057`): `legal-actions` correctly reported `state: "ready"` with `dispatch-task`
legal, but `dispatch-task` returned `blocked`, `reason: "EXECUTION_WIRING_UNAVAILABLE"`,
`detail: "no driver_factory wired this run's GovernedExecutionDriver collaborators; refusing
to fabricate a result"`. The run journal was not mutated by the failed attempt (`legal-actions`
immediately after still showed `state: "ready"`), consistent with a clean, documented
fail-closed refusal rather than a crash.

Root cause, confirmed directly from source rather than inferred:

- `src/coherence/execution/cli.py`'s own module docstring states outright: *"SR-034 has no
  concrete `TestCampaignRunner`/`WorkspaceOwner` implementation yet, so this CLI passes the
  caller-supplied factory straight through and, when none exists, returns a blocked
  `EXECUTION_WIRING_UNAVAILABLE` projection instead of fabricating a result."*
- `src/factory/orchestrator/runner.py`'s `run_governed_task`/`resume_governed_task` both
  accept `driver_factory: Callable[..., TaskResult] | None = None` and raise/refuse when it is
  `None`; `run_governed_task`'s docstring: *"defaults to the driver's own constructor, which is
  not self-contained, so production callers pass a wiring closure."*
- No production caller anywhere in the repository ever supplies one. A full-repo search for
  `driver_factory=` turns up exactly three files: `src/coherence/execution/cli.py` (the
  parameter definition/default itself), `tests/unit/coherence/test_execution_cli.py`, and
  `tests/unit/orchestrator/test_execution_driver.py` — both call sites that actually pass a
  non-`None` value are unit tests, not production wiring.
- The Pi host adapter (`pi-ext/factory-watch/src/execution-tools.ts`, from `T-044`, landed in
  commit `59f7217`) does not supply this either: it shells out to the identical bare `uv run
  coherence execution ...` command (`buildExecutionCommand`), which still defaults
  `driver_factory` to `None`. `T-044`'s own frontmatter still reads `status: todo` (a known
  stale-status pattern in this repo — the commit is real) — but even reading its actual
  deliverable in full, it only exposes the *existing* CLI verbs as Pi tools; it never claimed to
  supply the driver wiring, and doesn't.
- `docs/features/FEAT-013.md` states *"Pi and Claude Code can execute the same governed run
  through direct transports without Hermes"* — no such direct-transport driver wiring exists in
  code for either host today.

`report-worker-result` is not a substitute path: per the same module's docstring, it *"appends
one validated worker event through the existing run-evidence writer and **can never mark a
task complete**."*

Not fixed here: implementing a real `driver_factory` (a concrete `TestCampaignRunner`/
`WorkspaceOwner`/`AgentBackend` wiring bound to a real worker mechanism) is substantial
engineering work in its own right, well beyond the scope of the task (`T-057`, an unrelated
`coherence.planning.check` bugfix) that surfaced this gap.

## Correction

Not yet corrected. Needs its own scoped planning run, not an ad hoc fix inside an unrelated
task:

1. Design and implement a concrete `driver_factory` for at least one direct-transport host
   (Claude Code and/or Pi, per FEAT-013's own stated scope) — a real `TestCampaignRunner`,
   `WorkspaceOwner`, and `AgentBackend` that can actually invoke a worker to perform governed
   work, bound to a specific repo/run as `run_governed_task`'s signature already expects.
2. Wire that factory into the bare `coherence execution` CLI (or a documented production
   entrypoint that supplies it) so `dispatch-task` can succeed for a real task without a
   caller having to construct test-only plumbing by hand.
3. Add an integration test (not a unit test with an injected fake) proving one task can be
   dispatched end-to-end through the real CLI invocation and reach `completed`.
4. Until this lands, every task in this repo that needs governed dispatch must instead be
   executed directly (by a human or an agent working outside the driver, using the project's
   normal engineering practices) and have its `status` set by hand once genuinely verified —
   the precedent already established by `T-029`, which used the same standalone pattern for the
   same reason (no governed path was available to it either).
