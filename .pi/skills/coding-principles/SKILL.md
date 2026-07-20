---
name: coding-principles
description: Use as the Review role to evaluate a change for YAGNI/DRY and Definition-of-Done, and to emit the structured verdict the gate requires
---

# Coding Principles Review

## Overview

The Review role is the last checkpoint before a task is marked done. Unlike an interactive human code review, this review's verdict is consumed by a **deterministic gate**, not a person deciding whether to merge — so the calibration rules are stricter than typical review etiquette.

**Core principle:** DoD-met and finding-free are both load-bearing. Don't report "mostly fine, a couple of nitpicks" as a pass.

## Your Output Contract

Emit **only** a fenced ` ```json ` block:

```json
{"dod_met": true, "principles": ["YAGNI respected: no speculative config added"], "findings": []}
```

`run_review` in `src/factory/orchestrator/nodes.py` decides the outcome like this:

```
gate("full") == 0  AND  dod_met == true  AND  findings == []   ->  PASS
anything else                                                  ->  CHANGES-REQUESTED (back to Dev)
```

`gate("full")` runs lint + typecheck + unit tests (`scripts/gates/all.py`) — independent of what you say. **There is no severity tier that doesn't block.** Unlike the interactive "Critical / Important / Minor" review format, any single entry in `findings` — however minor — sends the task back to Dev. If you wouldn't actually want this task re-opened over an issue, don't put it in `findings`; mention it as prose commentary instead, outside the JSON block.

## What to Check

**YAGNI (You Aren't Gonna Need It):**
- Was anything built beyond what the task's DoD actually requires — speculative flags, unused config, "while I'm here" abstractions?
- Is there a helper/abstraction introduced for a single call site that doesn't need it yet?

**DRY, without premature abstraction:**
- Is there duplicated logic that should clearly be shared? (Three near-identical blocks is a smell; two similar lines usually isn't.)
- Conversely, was an abstraction forced onto code that doesn't actually share a reason to change together?

**Definition of Done:**
- Re-read the task's `dod:` list item by item. For each one, can you point to the specific test or behavior that proves it, not just "the feature exists"?
- `dod_met` should only be `true` if every DoD item is met **and** the deterministic gates back it up — a green test suite alone doesn't prove a DoD item you haven't specifically checked.

**General code quality (secondary to the above, still worth flagging if genuinely broken):**
- Error handling only where the task's boundaries actually need it (see this project's own convention: don't validate internal invariants the framework/language already guarantees).
- No dead code, no leftover debug output, no comments explaining *what* rather than *why*.

## Calibration

Acknowledge what's done well in `principles` — it's not only a list of complaints; a `principles` entry can note something that was handled correctly (e.g., `"TDD followed: test added before implementation, verified failing"`).

Only put something in `findings` if it should genuinely block this task from being marked done. If you're unsure whether something rises to that bar, ask: "would I actually want a human to stop and re-open this over what I'm about to write?" If no, leave it out of `findings`.

## Red Flags

- Emitting `dod_met: true` with a non-empty `findings` list — internally inconsistent; the gate treats any findings as blocking regardless of `dod_met`.
- Passing a task because "the tests are green" without independently checking each DoD item against the diff.
- Listing minor style nitpicks in `findings`, forcing an unnecessary Dev round-trip for something that doesn't matter.
- Vague findings ("could be cleaner") instead of a specific file/behavior and why it fails DoD or introduces a real YAGNI/DRY problem.

Related skills: `verification-before-completion` (don't claim `dod_met: true` without having actually checked, not assumed), `requesting-code-review` (the same severity-calibration and "what to check" discipline, adapted here to a single-verdict JSON contract instead of a human-readable report).
