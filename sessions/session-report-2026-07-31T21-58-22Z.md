# Session Report — 2026-07-31T21-58-22Z

## Pipeline Summary

| Task | Outcome | Iterations | Key Nodes |
|------|---------|------------|-----------|
| **T-046** — SimTestbench (Main Orchestrator) | ❌ **rejected** | 1 | context-gather (reject, 2 attempts exhausted) |

### T-046 — SimTestbench (Main Orchestrator) (Rejected)

Failed at **context-gather** after 2 attempts. Both attempts were **killed by timeout** (1200s total timeout) — the agent never emitted a manifest.

#### Attempt 1 (2575 lines of log)

The agent started reading files systematically:
1. Checked deliverable files: `src/sim/testbench.py`, `src/sim/injector.py`, `src/sim/__main__.py` — none exist, so `already_done` is false.
2. Read the plan doc (`docs/superpowers/plans/2026-07-30-sim-testbench.md`) — Task 6.
3. Read the manifest schema (`src/factory/schemas/context_manifest.schema.json`).
4. Read the manifest validator (`src/factory/validation/manifest_validator.py`).
5. Read existing source files: `src/sim/__init__.py`, `src/sim/scenario.py`, `src/sim/detection_spawner.py`, `src/sim/recorder.py`, `src/sim/text_input.py`, `src/sim/renderer.py`, `src/sim/hud.py`, `src/drone/interfaces.py`, etc.
6. Was still in the **thinking phase** when the 1200s total timeout was reached — never emitted a manifest.

The last thinking excerpt shows the agent was constructing the manifest structure (planning `context.task`, `coherence.checks`, and `context.source_files` fields) but never got to the output stage.

#### Attempt 2 (89 lines of log)

The agent was killed immediately by the same timeout — the session had already exceeded the 1200s total timeout from attempt 1, so attempt 2 was killed on startup before any real work happened.

```
pi_backend: agent killed after total timeout (idle=300.0s, total=1200.0s) -- it stalled or ran away without finishing. Treating this attempt as failed.
```

#### Root Cause Analysis

The context-gather agent for T-046 spent too long in the **read-and-analyze** phase and never reached the **output** phase. Several factors contributed:

1. **Large plan doc + many dependencies**: The plan doc is ~2400 lines, and T-046 depends on files from Tasks 1-5 (`__init__.py`, `scenario.py`, `detection_spawner.py`, `recorder.py`, `text_input.py`, `renderer.py`, `hud.py`) plus drone system modules. The agent read all of them.

2. **Schema/validator reading**: The agent read both the schema and the validator implementation to understand the expected output format — adding unnecessary tool calls since the role prompt already describes the format.

3. **No time budget for output**: The agent spent 100% of the 1200s on reading/thinking, with 0 seconds left to format and emit the manifest JSON. This is a **time management failure** — the agent should have budgeted time to produce the output.

4. **Attempt 2 was a no-op**: The total timeout (1200s) is shared across attempts within the same session. Attempt 1 consumed the entire budget, leaving nothing for attempt 2. The factory treats this as "attempt 2 exhausted" and rejects the task, but the agent never had a chance to produce a corrected manifest.

## Pipeline Health

- **`nul` file** — still present in the working tree (`C:/coding/pi-agent-factory/nul`, 179 bytes). kb-0004 remains active. This file has been flagged in 5 consecutive session reports (2026-07-31T13-27-07Z, 2026-07-31T14-00-05Z, 2026-07-31T19-40-38Z, 2026-07-31T20-59-41Z, and this one) without being addressed.

- **`tests/sim/__init__.py`** — still missing. Flagged in T-041, T-042, and T-045 reviews. Referenced in the plan (Task 1, Step 1 lists `Create: tests/sim/__init__.py`) but never created by any task so far.

- **kb-0007 NOT resolved** — The `context-completeness-audit/SKILL.md` still contains the old example format with `proven`, `pass`, and `evidence` fields. The `manifest_validator.py` was updated to tolerate these fields (via `_normalize_manifest`), but the skill file itself was never updated. This was NOT the cause of rejection in this session (the agent timed out before emitting a manifest), but the stale skill example remains a risk for future context-gather runs.

- **Total timeout sharing** — The factory's total timeout (1200s) is shared across all attempts within a session. Attempt 1 exhausted the budget, making attempt 2 a guaranteed failure. This is a pipeline design issue: a runaway attempt 1 can doom the entire task.

## KB Entry Assessment

**One new KB entry warranted** — the timeout-on-context-gather pattern is genuinely reusable.

### New: kb-0008 — Context-gather agent times out before emitting manifest on large tasks

| Symptom | Root Cause | Rule / Fix |
|---------|------------|------------|
| Context-gather on T-046 (and potentially other large tasks) runs for 1200s without emitting a manifest. The log shows extensive file reading and thinking but no output. Attempt 2 is a no-op because the total timeout was exhausted by attempt 1. | The agent reads too many files (plan doc, schema, validator, all dependency modules) without budgeting time for the output phase. The 1200s total timeout is shared across all attempts, so a runaway attempt 1 consumes the entire budget. | (1) The context-gather role prompt should include a time-budgeting instruction: reserve the last ~120s for output formatting. (2) Consider per-attempt timeout in addition to total timeout, so attempt 2 gets a fresh budget. (3) The agent should not read the schema or validator implementation — the role prompt already describes the format. |

### Existing KB entries status

| KB ID | Issue | Status |
|-------|-------|--------|
| kb-0004 | Windows `nul` file breaks `git add -A` | **active — file still exists** (5th consecutive report) |
| kb-0007 | Context-completeness-audit skill example contradicts schema | **partially addressed** — validator tolerates old format, but skill file STILL has old example (not fixed) |

## Suggestions

1. **💥 DELETE THE `nul` FILE** — This has been flagged in 5 consecutive session reports (2026-07-31T13-27-07Z, 2026-07-31T14-00-05Z, 2026-07-31T19-40-38Z, 2026-07-31T20-59-41Z, and this one). The file at `C:/coding/pi-agent-factory/nul` (179 bytes) is a Windows reserved filename that blocks `git add -A` and has caused at least one pipeline crash. Run `rm nul` (or `del nul` on Windows) from the repo root. This is now the highest-priority action item.

2. **Fix kb-0007 properly** — Update `.pi/skills/context-completeness-audit/SKILL.md` to remove the stale `proven`/`pass`/`evidence` example format. The `manifest_validator.py` tolerates the old format, but the skill file will confuse future agents. The example in "Your Output Contract" should match the `kind`/`args` format described in the role prompt, and the "The Gate That Actually Checks This" section's points #2 and #3 (which reference `proven` and `pass`) should be removed or updated to match the current validator behavior.

3. **Add time-budgeting to context-gather role prompt** — The context-gather agent should be instructed to reserve time for output. A simple instruction like "Budget your time: you have 1200s total. Reserve the last 120s for formatting and emitting the manifest JSON. Do not read the schema or validator — the format is described in the role prompt." would prevent this recurrence.

4. **Consider per-attempt timeout** — The factory's total timeout is shared across all attempts. This means a runaway attempt 1 consumes the entire budget, making attempt 2 a guaranteed no-op. Adding a per-attempt timeout (e.g., 600s per attempt, max 2 attempts) would give each attempt a fair chance.

5. **Create `tests/sim/__init__.py`** — This empty file has been flagged in multiple reviews across T-041, T-042, and T-045 sessions. It's referenced in the plan as a Task 1 deliverable but never created.

6. **T-046 retry** — After the time-budgeting fix is applied, T-046 should be re-tried. The task is well-defined and the timeout was the only blocker. The context-gather agent should:
   - Skip reading the schema and validator (the format is in the role prompt)
   - Read only the plan doc and essential dependency files (not all of them)
   - Budget time for output
   - Emit a manifest with `kind`/`args`-based checks (not `pass`/`evidence`)