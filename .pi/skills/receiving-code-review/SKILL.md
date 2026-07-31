---
name: receiving-code-review
description: Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verification, not performative agreement or blind implementation
disable-model-invocation: true
---

# Code Review Reception

## Overview

Code review requires technical evaluation, not emotional performance.

**Core principle:** Verify before implementing. Ask before assuming. Technical correctness over social comfort.

## The Response Pattern

```
WHEN receiving code review feedback:

1. READ: Complete feedback without reacting
2. UNDERSTAND: Restate the requirement in your own words (or ask)
3. VERIFY: Check against codebase reality
4. EVALUATE: Technically sound for THIS codebase?
5. RESPOND: Technical acknowledgment or reasoned pushback
6. IMPLEMENT: One item at a time, test each
```

## Forbidden Responses

**NEVER:** "You're absolutely right!", "Great point!", "Let me implement that now" (before verification).

**INSTEAD:** restate the technical requirement, ask clarifying questions, push back with technical reasoning if wrong, or just start working (actions over words).

## Handling Unclear Feedback

```
IF any item is unclear:
  STOP - do not implement anything yet
  ASK for clarification on unclear items

WHY: items may be related. Partial understanding = wrong implementation.
```

**Example:** feedback covers 6 items, 4 are clear, 2 are not.
- WRONG: implement the 4 clear ones now, ask about the other 2 later.
- RIGHT: "I understand items 1,2,3,6. Need clarification on 4 and 5 before proceeding."

## Handling External Review Feedback

```
BEFORE implementing:
  1. Check: Technically correct for THIS codebase?
  2. Check: Breaks existing functionality?
  3. Check: Reason for the current implementation?
  4. Check: Works on all platforms/versions this project targets?
  5. Check: Does the reviewer understand the full context?

IF suggestion seems wrong:
  Push back with technical reasoning

IF can't easily verify:
  Say so: "I can't verify this without [X]. Should I [investigate/ask/proceed]?"

IF it conflicts with a prior architectural decision:
  Stop and flag it rather than silently overriding.
```

Be skeptical of external feedback, but check carefully before dismissing it.

## YAGNI Check for "Professional" Features

```
IF reviewer suggests "implementing properly":
  grep codebase for actual usage

  IF unused: flag it - "This isn't called anywhere. Remove it (YAGNI)?"
  IF used: implement properly
```

If a feature isn't needed, don't add it just because a reviewer suggested "doing it properly."

## Implementation Order

```
FOR multi-item feedback:
  1. Clarify anything unclear FIRST
  2. Then implement in this order:
     - Blocking issues (breaks, security)
     - Simple fixes (typos, imports)
     - Complex fixes (refactoring, logic)
  3. Test each fix individually
  4. Verify no regressions
```

## When To Push Back

Push back when: the suggestion breaks existing functionality, the reviewer lacks full context, it violates YAGNI (unused feature), it's technically incorrect for this stack, legacy/compatibility reasons exist, or it conflicts with a prior architectural decision.

**How:** use technical reasoning, not defensiveness. Ask specific questions. Reference working tests/code.

## Acknowledging Correct Feedback

```
GOOD: "Fixed. [Brief description of what changed]"
GOOD: "Good catch - [specific issue]. Fixed in [location]."
GOOD: [Just fix it and show the diff]

BAD: "You're absolutely right!" / "Great point!" / "Thanks for catching that!"
```

**Why no thanks:** actions speak. Just fix it. The diff itself shows you heard the feedback.

## Gracefully Correcting Your Own Pushback

If you pushed back and were wrong:
```
GOOD: "You were right - I checked [X] and it does [Y]. Implementing now."
BAD: long apology, defending why you pushed back, over-explaining
```

State the correction factually and move on.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Performative agreement | State the requirement or just act |
| Blind implementation | Verify against codebase first |
| Batch without testing | One at a time, test each |
| Assuming the reviewer is right | Check if it breaks things |
| Avoiding pushback | Technical correctness > comfort |
| Partial implementation | Clarify all items first |
| Can't verify, proceed anyway | State the limitation, ask for direction |

## The Bottom Line

**External feedback = suggestions to evaluate, not orders to follow.**

Verify. Question. Then implement. No performative agreement. Technical rigor always.
