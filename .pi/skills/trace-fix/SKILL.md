---
name: trace-fix
description: Close traceability gaps one at a time — judge which requirement a task actually satisfies by reading statements, propose it with your reasoning, and let the trace tools perform every write.
---

# Trace fix

Use this when the human wants to improve traceability health: linking tasks to the
system requirements they satisfy, plans to the specs they implement, tasks to the
plans they came from, or recording an honest exemption or deferral where no link
belongs.

## What you own, and what you do not

You own **one judgment per gap**: which candidate genuinely matches, and why.

You do **not** own validation, writing, or deciding when the work is finished.
Those belong to the `trace_*` tools. That split is deliberate — a gate that
trusted your account of your own progress would be worthless.

You **do** own which gap to work. `trace_next` returns every pending gap; the
focused one is a default ordering, not a queue.

## Steps

1. **Get a gap.** Call `trace_next`. It returns the gap, the node's excerpt, every
   pending gap, and **every** candidate with its full statement. Pass `node_id` to
   focus a specific one — related gaps are often easier to judge together, even
   though you still confirm them one at a time.
2. **Judge by meaning.** Candidates are ordered by shared-term overlap. That is a
   lexical hint, not a verdict — a task titled "Bug Capture" and a requirement about
   preempting patrol may share no vocabulary and still be the right pair, while two
   documents that both say "system" and "detection" may be unrelated. Read the
   statements. Consider every candidate, not just the top few.
3. **Propose, then wait.** Tell the human the gap, your recommended candidate, and
   the reasoning — what the task actually does, and why that satisfies that
   requirement's statement. If nothing fits, say so; a wrong link is worse than an
   honest deferral. Do not call a write tool before they answer.
4. **Record their decision**, then return to step 1:
   - `trace_link` with `satisfies` — note `node_id` is always the **task** id, even
     when the gap was reported against the requirement
   - `trace_link` with `spec` — for a plan implementing a spec
   - `trace_link` with `source_plan` — for a task that declares no plan
   - `trace_exempt` — no requirement applies (tasks and plans only)
   - `trace_defer` — discussed, needs more time
5. **Run the gate.** Call `trace_check` and report its output verbatim, including
   any gaps still pending.

## Rules

- **Never edit `satisfies:`, `trace_exempt:` or `trace_deferred:` by hand.** The
  tools verify that a link target exists; a hand-written link can create the
  dangling reference they would have refused.
- **Never assert a gap is handled without having called the tool.** `trace_check`
  re-derives everything from disk and will contradict you.
- **A deferral needs a real reason.** "Needs more time" alone is not one — record
  what has to happen before it can be resolved.
- **Requirements cannot be exempted.** An SR that no task satisfies and no run
  validates is a real gap. Defer it instead.
- **Excerpts and summaries may be clipped.** When one ends with a `[truncated …]`
  marker, read the file it names before judging. A task's `dod` block is often the
  part that falls off the end.
- **Some gaps do not close by linking.** An unvalidated or stale requirement closes
  by running validation; a dangling upstream closes by fixing the reference or
  creating the target. Deferring those records them, it does not resolve them.
- **Do not batch.** One gap, one proposal, one confirmation.
