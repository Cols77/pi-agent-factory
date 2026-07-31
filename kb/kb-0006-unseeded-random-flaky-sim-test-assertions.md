---
id: kb-0006
title: "Unseeded Random in simulation tests produces flaky distance-based assertions"
status: active
severity: medium
created: "2026-07-31"
last_seen: "2026-07-31"
occurrences: 1
tags: [sim, tests, flaky, random, seed, reproducibility]
scope:
  files: ["tests/sim/test_detection_spawner.py", "src/sim/detection_spawner.py"]
  error_signatures:
    - "random.uniform"
    - "far_conf <"
    - "seed="
detection: "Review found that test_confidence_decreases_with_distance used random.uniform without a seed for the entity position. If the random position lands within ~1m of the drone start (0,0), the assertion far_conf < 0.5 fails (~0.03% probability per invocation, but a real CI flake over many runs)."
---

## Symptom

A test that spawns an entity at a random position and asserts its detection confidence
is below a threshold (e.g., `far_conf < 0.5`) fails intermittently in CI. The failure
occurs because the random position happened to land close to the drone's origin, making
the confidence high even though the test expected a low-confidence "far" detection.

## Root cause

The test used `random.uniform()` from the global random module, which is unseeded and
produces a different position on every run. The assertion `far_conf < 0.5` implicitly
assumes the random position is far from the drone, but there is a non-zero probability
(~0.03% for a 100×100 pool with 100m sensor range) that the position lands within 50m
of the origin, causing a false failure.

## Rule / fix

1. **Add a `seed` parameter** to the simulation class constructor:
   ```python
   def __init__(self, ..., seed: int | None = None) -> None:
       self._rng = random.Random(seed)
   ```

2. **Use `self._rng` instead of `random`** for all random operations, so that the
   RNG is fully controlled by the seed.

3. **Use a fixed seed in tests** that depend on random positions:
   ```python
   spawner = DetectionSpawner(..., seed=42)
   ```

4. **Add a test** that verifies the same seed produces the same positions:
   ```python
   a = DetectionSpawner(..., seed=123).get_detections()
   b = DetectionSpawner(..., seed=123).get_detections()
   assert a[0].position == b[0].position
   ```

5. **Document the seed** in the test: note which assertion depends on the seed
   producing a position far from the origin, so a future reader knows not to
   change the seed without adjusting the assertion.

## Cross-task implications

- Any sim test that spawns entities or uses random positions should use a seeded
  RNG for deterministic assertions.
- The `seed` parameter should be exposed at the constructor level so tests can
  inject it without subclassing or mocking.