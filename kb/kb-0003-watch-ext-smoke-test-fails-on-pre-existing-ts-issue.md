---
id: kb-0003
title: "Full-gate watch_ext smoke test fails on pre-existing TypeScript extension issue"
status: active
severity: medium
created: "2026-07-27"
last_seen: "2026-07-27"
occurrences: 1
tags: [gates, factory-watch, typescript, smoke-test, pre-existing]
scope:
  files: ["tests/gates/test_watch_ext_gate.py", "scripts/gates/watch_ext.py", "pi-ext/factory-watch/test/smoke.test.ts"]
  error_signatures:
    - "expected '' to contain 'usage:'"
    - "test_watch_ext_gate_passes"
detection: "The full-gate runs `test_watch_ext_gate_passes` which executes `npm run typecheck && npm test` in `pi-ext/factory-watch`. The smoke test `mission-control-review.ts loads under real node <file>.ts execution` fails because running `node mission-control-review.ts` with no args produces empty stderr instead of containing 'usage:'."
---

## Symptom

The full gate (`test_watch_ext_gate_passes`) fails with:

```
FAILED tests/gates/test_watch_ext_gate.py::test_watch_ext_gate_passes
```

The underlying cause is a Vitest smoke test failure in `pi-ext/factory-watch/test/smoke.test.ts`:

```
mission-control-review.ts loads under real `node <file>.ts` execution
  → expected '' to contain 'usage:'
```

## Root cause

The smoke test for `mission-control-review.ts` expects that running the script with no arguments outputs a usage string containing "usage:" to stderr. However, the current script produces no output on stderr when run with no arguments, likely because the script's entry point doesn't register a `--help`/usage handler that prints to stderr, or the `tsx`/`node` runner behavior changed.

This is a **pre-existing issue** in the `pi-ext/factory-watch` extension — it is **not related to the task being validated** (T-032 WaypointSequencer Python code). The gate failure incorrectly blocks unrelated Python tasks.

## Rule / fix

Either:
1. Fix the `mission-control-review.ts` script to print a usage message to stderr when invoked with no arguments, OR
2. Update the smoke test to match the actual behavior (e.g., expect a non-zero exit code without checking stderr content), OR
3. Exclude the `test_watch_ext_gate_passes` test from the full gate until the TypeScript extension smoke test is fixed.

The gate failure should not be conflated with the review outcome. The review node should record `findings` separately from `gate` failures, and a gate failure from an unrelated test suite should not cause a `changes-requested` on the review node.