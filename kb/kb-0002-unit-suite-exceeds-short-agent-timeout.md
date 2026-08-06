---
id: kb-0002
title: "Full unit suite can exceed a 120-second agent timeout"
status: active
severity: medium
created: "2026-07-27"
last_seen: "2026-07-27"
occurrences: 1
tags: [pytest, gates, timeout, verification]
scope:
  files: [".factory/factory.yaml", "tests/unit/**"]
  error_signatures:
    - "Command timed out after 120 seconds"
    - "pytest -m unit"
detection: "A direct full-unit pytest run times out at 120 seconds even though the deterministic unit gate completes successfully with a longer timeout."
---

## Symptom
A Dev attempt completes the implementation and targeted tests, but its direct full-unit
verification is killed after 120 seconds. The pipeline then spends another Dev attempt
repeating verification even though the suite is healthy and normally takes slightly more
than two minutes.

## Root cause
The agent command timeout was shorter than the repository's normal full-unit-suite runtime.
In this run, the deterministic unit gate completed 249 tests in about 130 seconds, just over
the 120-second limit used by the first Dev attempt.

## Rule / fix
Use the project's declared `unit` gate (see `.factory/factory.yaml`, run via `ConfigGateRunner`)
for full-unit verification and allow at least 300 seconds. Reserve shorter timeouts for targeted
tests; do not interpret a timeout near the suite's known runtime as a test failure without
rerunning through the canonical gate.
