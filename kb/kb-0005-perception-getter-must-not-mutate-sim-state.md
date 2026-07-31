---
id: kb-0005
title: "Perception getter must not mutate simulation state (clock/entity advancement in get_detections)"
status: active
severity: high
created: "2026-07-31"
last_seen: "2026-07-31"
occurrences: 1
tags: [sim, perception, design, tick, state-mutation, testbench]
scope:
  files: ["src/sim/detection_spawner.py", "src/sim/testbench.py", "tests/sim/test_detection_spawner.py"]
  error_signatures:
    - "get_detections.*_clock"
    - "get_detections.*tick"
    - "clock advances.*per call"
detection: "Review found that DetectionSpawner.get_detections() advanced _clock (+0.05) and moved entity positions on every call. The testbench calls get_detections() 3x per frame (for recording, summary, drawing), causing the clock to advance 3x faster than intended — spawn timers with e.g. start_time=0.01 fire on the first tick instead of waiting."
---

## Symptom

A Perception implementation's `get_detections()` method advances the simulation clock
and moves entities as a side effect. When the caller (e.g. SimTestbench) invokes
`get_detections()` multiple times per frame — for recording, summary display, and drawing —
the clock advances 3× faster than intended. Spawn timers configured with `start_time=0.01`
fire on the first frame instead of waiting, and entity positions drift between the
recording and drawing passes.

## Root cause

The `DetectionSpawner` was designed with `get_detections()` as the primary entry point,
bundling both detection calculation and state advancement (clock tick + entity movement).
The `Perception` protocol contract does not specify whether `get_detections()` is a pure
getter, so the implementation naturally placed all logic in one method. The testbench
then called it multiple times per frame, causing cumulative state errors.

This is an architectural design issue: the simulation advancement (clock, spawn timing,
entity movement) must be separated from the observation/query (detection math).

## Rule / fix

1. **Split the API into two methods:**
   - `tick(dt: float)` — advances the clock, moves entities, spawns pending entities.
     This is the only method that mutates state. Call it exactly once per simulation frame.
   - `get_detections() -> list[Detection]` — pure getter with no side effects.
     Call it any number of times per frame; results are idempotent.

2. **Document the contract explicitly** in the class docstring:
   - `get_detections` is a pure getter — it never mutates internal state.
   - Call `tick(dt)` once per simulation step to advance the clock.

3. **Verify in tests** that `get_detections()` is side-effect-free:
   - Call `get_detections()` three times in a row and assert positions are identical.

4. **Update the testbench** to call `tick(dt)` once per frame, not `get_detections()`
   multiple times. The testbench should call `get_detections()` only when it needs
   detection data (e.g., for recording or drawing), not to advance the simulation.

## Cross-task implications

- **T-043 Recorder** — must call `get_detections()` for recording but should not
  advance state via it.
- **T-046 SimTestbench** — must call `tick(dt)` once per frame, then call
  `get_detections()` for each consumer (recording, HUD, drawing).
- **T-045 Pygame Renderer/HUD** — must not call `get_detections()` with side effects.
- The plan reference code for Task 6 (testbench) was written against the old API and
  needs updating to use the `tick(dt)` / `get_detections()` split.