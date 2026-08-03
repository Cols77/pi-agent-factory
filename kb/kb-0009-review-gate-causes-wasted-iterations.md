---
id: kb-0009
title: "Review gate triggers 'changes-requested' with 0 code findings, causing wasted dev→validation→review iterations"
status: active
severity: medium
created: "2026-08-01"
last_seen: "2026-08-01"
occurrences: 2
tags: [review, gate, pipeline, iteration-waste, review-gate, process]
scope:
  files: ["src/factory/orchestrator/runner.py", "src/factory/orchestrator/gate.py"]
  error_signatures:
    - "findings: 0, gate: 1"
    - "changes-requested with 0 findings"
detection: "Session JSON shows a review node with 'result': 'changes-requested', 'extra.findings': 0, and 'extra.gate': 1. The subsequent dev node produces no meaningful code changes (or trivial changes). The pattern repeats until human-review approves."
---

## Symptom

The review node returns "changes-requested" with 0 code findings but gate=1. The pipeline restarts the dev→validation→review loop even though no code changes are needed. The dev agent produces no meaningful diffs (or trivial changes), validation passes trivially, and the review returns the same result. This wastes 2-3 iterations per task.

Observed in two consecutive tasks:
- **T-046** (SimTestbench): 3 iterations, all with 0 findings and gate=1 (the `[B] bug` HUD hint not wired because bug capture was deferred to T-047)
- **T-047** (Bug Capture): 3 iterations, iteration 2 had 0 findings and gate=1 (scenarios/bugs/ directory not committed, pytest marker config concerns)

## Root cause

The review pipeline has two independent signals: `findings` (code defects detected by the review agent) and `gate` (deterministic plan-conformance check). When the gate detects a mismatch, it returns 1 regardless of the findings count. The pipeline treats any "changes-requested" result — whether from findings OR gate — as a reason to restart the full dev→validation→review loop.

The gate triggers are often **task-boundary issues** or **non-code artifacts**:
- A feature deferred to a later task (T-046's `[B] bug` → T-047)
- An empty directory not tracked by git (T-047's `scenarios/bugs/` without `.gitkeep`)
- A pytest marker configuration that looks suspicious but works
- A missing `.gitkeep` or sample file

None of these are code defects, and none require a dev iteration to fix. But the pipeline treats them identically to real bugs.

## Rule / fix

1. **Distinguish gate-only from findings-driven "changes-requested"** — If `findings=0` and `gate=1`, the pipeline should annotate the issue for the human reviewer but NOT restart the dev loop. This would save 2-3 iterations per task.

2. **Add committed `.gitkeep` files to expected output directories** — The `scenarios/bugs/` directory should have a `.gitkeep` committed. This eliminates one recurring gate trigger.

3. **Consider a "soft gate" mode** — Gate issues that are not code defects (missing `.gitkeep`, deferred features, configuration concerns) should be warnings, not hard blockers. The review can still report them, but they shouldn't force a dev restart.

4. **Verify with a pipeline run** — After implementing the fix, run a task with gate-only issues and confirm the pipeline skips directly to human-review instead of looping through dev→validation→review.

## Detection

```bash
# Check if a task had wasted iterations (findings=0, gate=1)
cd /path/to/project
for f in sessions/*.session.json; do
  jq -r '.tasks[]? | select(.nodes[]?.extra?.findings == 0 and .nodes[]?.extra?.gate == 1) | "\(.task_id): \(.title) (\(.iterations) iters)"' "$f" 2>/dev/null
done
```