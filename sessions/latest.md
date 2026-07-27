# Session 2026-07-27T14-29-58Z

- T-032 (escalated, 3 iters): WaypointSequencer

## Summary

Task T-032 (WaypointSequencer) was implemented successfully — the code compiles, all 62 unit tests pass, and the DoD is met. The pipeline was derailed by a **pre-existing gate failure** in `test_watch_ext_gate_passes` (TypeScript extension smoke test in `pi-ext/factory-watch`), which is completely unrelated to the Python task. The review agent found 0 findings and confirmed `dod_met: true`, but the gate failure caused the review node to be marked as `changes-requested` (gate=1, findings=0). This consumed 2 extra dev cycles and 2 extra review cycles before escalating to human-review, which rejected with "rejected: dev will retry" — but the dev had already addressed the only feedback item (adding RuntimeError guard in step()).

## KB entries added

- **kb-0003**: Full-gate `watch_ext` smoke test fails on pre-existing TypeScript extension issue — unrelated to the Python task, but blocks the pipeline.

## Suggestions

1. **Decouple gate failures from review outcomes**: A gate failure in an unrelated test suite (`pi-ext/factory-watch` TypeScript extension) should not trigger a `changes-requested` on the review node for a Python task. Consider separating the review's `findings` from the gate's `failures` — a gate failure should either:
   - Be reported as a note on the review without blocking it, OR
   - Only block if the gate failure is in the same scope as the task's deliverables.

2. **Fix or exclude the broken smoke test**: The `test_watch_ext_gate_passes` test is a known flaky failure (smoke test for `mission-control-review.ts`). Either fix the TypeScript script or exclude the test from the full gate until fixed.

3. **Human-review should provide specific actionable feedback**: The "rejected: dev will retry" handoff is vague. The dev had already addressed the RuntimeError guard feedback. If the human-review meant something else, it should be stated explicitly.

4. **Pipeline should detect no-progress loops**: When the review node records `findings=0` but `gate=1` (from an unrelated test), and the dev has already made changes, escalating to human-review without a clear path forward wastes cycles. Consider adding a check: if the only failure is an unrelated gate, skip the escalation and mark the review as pass with a warning.