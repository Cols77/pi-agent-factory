---
spec_ref: docs/superpowers/specs/intent-spec.md
status: proposed
fixture_label: test-data-not-approval
---
# Fixture Deterministic Planner Plan

### Task 1: Capture contract

**Files:**
- Create: `src/capture.py`

**Interfaces:**
- Produces: durable capture events.

### Task 2: Planning report

**Files:**
- Create: `src/report.py`

**Interfaces:**
- Produces: deterministic report and hash-bound handoff.
