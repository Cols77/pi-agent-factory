# Design: Human-Review Loop — never drop the human

**Date:** 2026-07-27
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Problem (root cause, evidence-backed)

`run_task` (runner.py) has a single loop `for i in range(max_review_cycles)`:
`dev → validation → review(LLM) → (only if the LLM review PASSES) → human-review`.

When the human rejects with a comment, the reject sets `feedback` and `continue`s.
The next iteration runs dev (applies the comment) and then the **LLM review
re-gates**. If the LLM returns `changes-requested`, the human is **not**
consulted (human-review only opens on an LLM PASS); the loop keeps churning
dev↔review on the LLM's terms, sharing the single `max_review_cycles` budget,
until it runs out and **escalates silently** — cutting the human out.

Observed on task T-032: human reject at 14:53 → dev pass 15:16 → review
`changes-requested` 15:19 → escalated (session-review 15:24), with no second
human-review. From the user's seat this looks like a hang: no re-review, no
close. (The run did not deadlock — it escalated.)

## 2. Decision

Chosen behavior (user): **re-review by the LLM, but never drop the human.**
- The LLM still reviews every round.
- Each human round gets a **fresh** LLM budget (a picky reviewer can't burn the
  human's budget).
- When the LLM keeps requesting changes, control still **returns to the human**
  (with the outstanding findings) to approve/close/reject — never a silent
  escalate.
- `--auto` (no human) is unchanged: it still escalates on LLM exhaustion.

## 3. Design — nest the loop into human-rounds × LLM-cycles

Restructure `run_task`'s review section into two nested loops:

- **Inner loop** (`max_review_cycles`, existing budget): `dev → validation →
  review`. Repeats until the LLM review **passes** (`break`) or the budget is
  exhausted. `dev` ESCALATE and the `already_done` first-pass dev-skip behave as
  today; the very first dev attempt is the only one `already_done` skips.
- **Outer loop** (`max_human_rounds`, NEW, default 3): after the inner loop,
  **always surface to the human** (when `human_review is not None`), whether or
  not the LLM passed:
  - handoff `"waiting for you to review the diff"` when the LLM passed;
  - handoff `"reviewer couldn't confirm -- outstanding: <findings> (approve to
    accept, reject to send back)"` when the inner budget exhausted without a
    pass.
  - **approve** → `commit_all` + report approved + `TaskResult "completed"`.
  - **reject** → report `changes-requested`, `feedback =
    format_review_feedback(comments)`, and loop the **outer** round (fresh inner
    budget). After the first human round, `already_done` is cleared (dev now runs
    normally) and the "already complete" banner no longer applies.
- **`--auto`** (`human_review is None`): run the inner loop once; if the LLM
  passed → complete; else → escalate (today's behavior). The outer loop runs
  once.
- **Escalate** only when the outer human-round budget is exhausted (the human
  rejected `max_human_rounds` times) or `--auto` never passed. Escalation is
  therefore always preceded by an explicit human decision in interactive mode.

`run_task` gains `max_human_rounds: int = 3`. `run_next` keeps calling with the
default; no CLI flag added (YAGNI).

## 4. Preserved behavior (existing tests must still pass)

The happy-path report sequence is unchanged, so these hold:
- approve → `commit_all` + `completed`.
- a single reject → dev retry → LLM pass → human approve → completed
  (`human-review` states `[blocked, changes-requested, blocked, approved]`).
- the blocked report still carries `start_commit` (and `already_done` /
  `deliverables` for an already-done first round).
- `--auto` with an LLM pass still completes; with no pass still escalates.

## 5. New behavior (new tests)

1. **Reject → LLM keeps requesting changes → still returns to the human.** After
   a human reject, if the LLM review returns `changes-requested` for the whole
   inner budget, a second `human-review` still opens with a "reviewer couldn't
   confirm" handoff; approving there completes the task. (The T-032 fix.)
2. **Fresh inner budget per human round** (a reject resets the LLM cycle count).
3. **Escalate only after `max_human_rounds` human rejects**, never from the LLM
   silently, in interactive mode.
4. **`--auto` unchanged**: LLM never passes → escalate, no human surfaced.

## 6. Out of scope

- The stale `review-decision.json` files under `.factory-transcripts/<id>/` are
  artifacts of runs that were killed/ended while blocked (each run uses a unique
  transcript dir, so a stale file never affects a later run) — not a live bug;
  no fix here.
- Broader "increment F" workflow control (pause/steer/takeover) remains deferred.
