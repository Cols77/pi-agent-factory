---
id: kb-0008
title: "Context-gather agent times out (1200s total) without emitting manifest on large tasks"
status: active
severity: high
created: "2026-07-31"
last_seen: "2026-07-31"
occurrences: 1
tags: [context-gather, timeout, time-management, pipeline, agent-behavior]
scope:
  files: ["src/factory/orchestrator/runner.py", "src/factory/orchestrator/__main__.py", ".pi/roles/context-gatherer/role.md"]
  error_signatures:
    - "agent killed after total timeout"
    - "it stalled or ran away without finishing"
    - "Partial stdout follows"
detection: "Session JSON shows 'outcome': 'rejected' with 'attempts': 2, but the node 'extra.errors' is empty (no schema validation errors). The transcript logs show the agent was still in the thinking/reading phase when killed. The total timeout (1200s) was exhausted by the first attempt; the second attempt is killed immediately because the total timeout is shared across attempts within the same session."
---

## Symptom

The context-gather node on a large task (T-046 — SimTestbench Main Orchestrator) runs for 1200s without emitting a manifest. The agent is killed by the total timeout. The transcript shows extensive file reading and thinking, but no output JSON. The second attempt is killed immediately because the 1200s total timeout is shared across all attempts within the session.

The factory-run log shows:
```
pi_backend: agent killed after total timeout (idle=300.0s, total=1200.0s) -- it stalled or ran away without finishing. Treating this attempt as failed.
```

The session JSON shows:
```json
{
  "node": "context-gather",
  "result": "reject",
  "attempts": 2,
  "extra": {
    "errors": [],  // no schema errors — never emitted a manifest
    "backend_ok": false
  }
}
```

## Root cause

The context-gather agent has no time-budgeting instruction. On large tasks with many file dependencies (T-046 depends on 7+ source files from Tasks 1-5, plus a 2400-line plan doc, plus schema/validator files), the agent reads extensively without budgeting time for the output phase. Additionally:

1. **No output time reserve**: The agent reads the plan doc, schema, validator, and every dependency module before beginning to format the manifest. This reading phase consumes the entire 1200s budget, leaving 0s for the JSON output.

2. **Unnecessary reading**: The agent reads the schema (`context_manifest.schema.json`) and validator (`manifest_validator.py`) even though the role prompt already describes the expected output format. This adds ~10 tool calls that are unnecessary.

3. **Shared total timeout**: The factory's total timeout (1200s) is shared across all attempts within a session. Attempt 1 exhausts the budget, making attempt 2 a guaranteed no-op. This is unlike the per-attempt max_attempts counter, which would give each attempt a fresh budget.

4. **No early output**: The agent should emit a partial or preliminary manifest early, then refine it, rather than trying to produce the perfect manifest in one shot at the end.

## Rule / fix

1. **Add time-budgeting instruction to the context-gather role prompt**: Include an explicit instruction like "Budget your time: you have 1200s total. Reserve the last 120s for formatting and emitting the manifest JSON. Do not read the schema or validator — the format is described in the role prompt."

2. **Consider per-attempt timeout**: Change the factory to use a per-attempt timeout (e.g., 600s per attempt, max 2 attempts) instead of a shared total timeout. This ensures each attempt gets a fair budget and a runaway attempt 1 does not doom attempt 2.

3. **Reduce unnecessary reading**: The context-gather role prompt explicitly tells the agent the manifest format. The agent should not read the schema or validator to verify the format — this wastes time and isn't needed since the factory runs its own validation.

4. **Emit early, refine later**: The agent should emit a preliminary manifest (with placeholder checks) early in the session, then refine it with real checks as it reads files. This ensures the output buffer is populated before the timeout.

5. **Verify with a mock test**:
   ```bash
   # Simulate context-gather with a time budget to confirm the fix works
   uv run python -c "
   import time
   start = time.time()
   budget = 1200.0
   reserve = 120.0
   # Agent should check remaining time periodically
   elapsed = time.time() - start
   if budget - elapsed < reserve:
       print('EMIT OUTPUT NOW — time reserve reached')
   else:
       print(f'Still reading... ({budget - elapsed:.0f}s remaining)')
   "
   ```