---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
disable-model-invocation: true
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## When to Use

Use for ANY technical issue: test failures, bugs, unexpected behavior, performance problems, build failures, integration issues.

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:** the issue seems simple (simple bugs have root causes too), or you're in a hurry (rushing guarantees rework).

## The Four Phases

You MUST complete each phase before proceeding to the next.

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully** - don't skip past errors/warnings, read stack traces completely, note line numbers/file paths/error codes.
2. **Reproduce Consistently** - can you trigger it reliably? If not reproducible, gather more data, don't guess.
3. **Check Recent Changes** - what changed that could cause this? git diff, recent commits, new dependencies, config/environment differences.
4. **Gather Evidence in Multi-Component Systems** - when the system has multiple components (orchestrator -> sub-agent -> gate), add diagnostic instrumentation at each boundary (log what enters/exits, verify env/config propagation) before proposing fixes. Run once to see WHERE it breaks, then investigate that specific component.
5. **Trace Data Flow** - when the error is deep in a call stack, see `root-cause-tracing.md` in this directory for the full backward-tracing technique. Quick version: where does the bad value originate? What called this with the bad value? Keep tracing up until you find the source. Fix at source, not at symptom.

### Phase 2: Pattern Analysis

1. **Find Working Examples** - locate similar working code in the same codebase.
2. **Compare Against References** - if implementing a pattern, read the reference implementation completely, don't skim.
3. **Identify Differences** - what's different between working and broken? List every difference, however small.
4. **Understand Dependencies** - what other components, settings, config, environment does this need?

### Phase 3: Hypothesis and Testing

1. **Form Single Hypothesis** - state clearly: "I think X is the root cause because Y."
2. **Test Minimally** - make the smallest possible change to test the hypothesis. One variable at a time.
3. **Verify Before Continuing** - worked? -> Phase 4. Didn't work? -> new hypothesis. Don't add more fixes on top.
4. **When You Don't Know** - say so explicitly rather than pretending to know; research more or ask.

### Phase 4: Implementation

**Fix the root cause, not the symptom:**

1. **Create Failing Test Case** - simplest possible reproduction, automated if possible, MUST exist before fixing. Use the `test-driven-development` skill for writing proper failing tests.
2. **Implement Single Fix** - address the root cause identified. One change at a time. No "while I'm here" improvements, no bundled refactoring.
3. **Verify Fix** - test passes now? No other tests broken? Issue actually resolved?
4. **If Fix Doesn't Work** - STOP. Count attempts. If < 3: return to Phase 1 with new information. If >= 3: STOP and question the architecture (below) rather than attempting fix #4.
5. **If 3+ Fixes Failed: Question Architecture** - pattern indicating an architectural problem: each fix reveals new shared state/coupling in a different place, fixes require "massive refactoring," each fix creates new symptoms elsewhere. This is NOT a failed hypothesis — it's a wrong architecture. Flag this explicitly rather than attempting a fourth patch.

## Red Flags - STOP and Follow Process

- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- Proposing solutions before tracing data flow
- "One more fix attempt" (when already tried 2+)
- Each fix reveals a new problem in a different place

**ALL of these mean: STOP. Return to Phase 1.**

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "I see the problem, let me fix it" | Seeing symptoms != understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question pattern, don't fix again. |

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **1. Root Cause** | Read errors, reproduce, check changes, gather evidence | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare | Identify differences |
| **3. Hypothesis** | Form theory, test minimally | Confirmed or new hypothesis |
| **4. Implementation** | Create test, fix, verify | Bug resolved, tests pass |

## When Process Reveals "No Root Cause"

If systematic investigation reveals the issue is truly environmental, timing-dependent, or external:
1. You've completed the process.
2. Document what you investigated.
3. Implement appropriate handling (retry, timeout, error message).
4. Add monitoring/logging for future investigation.

**But:** most "no root cause" conclusions are incomplete investigation, not genuine dead ends.

## Supporting Techniques

Available in this directory:
- **`root-cause-tracing.md`** - trace bugs backward through the call stack to find the original trigger.
- **`defense-in-depth.md`** - add validation at multiple layers after finding root cause.
- **`condition-based-waiting.md`** - replace arbitrary timeouts with condition polling.

**Related skills:** `test-driven-development` (creating the failing test case in Phase 4), `verification-before-completion` (verify the fix worked before claiming success).
