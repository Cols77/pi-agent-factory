---
name: requesting-code-review
description: Use when completing tasks, implementing major features, or before merging to verify work meets requirements
---

# Requesting Code Review

Dispatch a code reviewer subagent to catch issues before they cascade. The reviewer gets precisely crafted context for evaluation, never the requester's full session history. This keeps the reviewer focused on the work product, not the requester's thought process.

**Core principle:** Review early, review often.

## When to Request Review

**Mandatory:** after each task in subagent-driven development, after completing a major feature, before merge to main.

**Optional but valuable:** when stuck (fresh perspective), before refactoring (baseline check), after fixing a complex bug.

## How to Request

**1. Get git SHAs:**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # or origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

**2. Dispatch a code reviewer subagent**, filling the template at [code-reviewer.md](code-reviewer.md).

**Placeholders:**
- `{DESCRIPTION}` - brief summary of what was built
- `{PLAN_OR_REQUIREMENTS}` - what it should do
- `{BASE_SHA}` - starting commit
- `{HEAD_SHA}` - ending commit

**3. Act on feedback:**
- Fix Critical issues immediately
- Fix Important issues before proceeding
- Note Minor issues for later
- Push back if the reviewer is wrong (with reasoning)

## Integration with This Factory's Review Node

The orchestrator's Review role does not dispatch a subagent reviewer of its own — it *is* the reviewer, emitting a single structured report. The severity calibration, "what to check" list, and output-format discipline in [code-reviewer.md](code-reviewer.md) still apply directly to that report; only the "dispatch a subagent" mechanic in this file is specific to interactive/plan-time use and doesn't apply inside a Review node invocation.

**The Review role's actual output contract** (enforced by `run_review` in `src/factory/orchestrator/nodes.py`, not by this skill): a fenced ` ```json ` block matching `{"dod_met": bool, "principles": [...], "findings": [...]}`. The gate only passes when the deterministic full gate (lint+types+unit) is green, `dod_met` is `true`, **and** `findings` is an empty list — any finding at all, however minor, routes back to Dev as `changes-requested`. There is no "Minor, doesn't block merge" tier in this pipeline the way there is in the interactive workflow below: only list a finding if it should actually send the task back to Dev.

## Red Flags

**Never:** skip review because "it's simple," ignore Critical issues, proceed with unfixed Important issues, argue with valid technical feedback.

**If the reviewer (or requirements) seem wrong:** push back with technical reasoning, show code/tests that prove it works, request clarification.

See the review template at: [code-reviewer.md](code-reviewer.md)
