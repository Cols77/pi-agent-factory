# Design: Trace-fix Field of View

Date: 2026-08-06
Status: Approved (brainstorming) — ready for implementation planning
Builds on: `2026-08-03-trace-model-and-cli.md`, `2026-08-03-trace-fix-workflow.md`
Related: `2026-08-06-requirement-doctor-design.md` §8 owns the `sr_unvalidated`
split; this design does not touch gap kinds.

## 1. Problem

The `\trace-fix` loop states a principle at `propose.py:99`:

> Ranking only ORDERS the list. It is never truncated: a lexical heuristic must
> not get to decide which links are reachable, or a correct match phrased in
> different vocabulary becomes unpickable.

It then applies that principle to candidates and breaks it three other ways. Plan
1 recorded the largest one as an intention (`2026-08-03-trace-model-and-cli.md`,
line 1582): *"This is the deterministic half of the `\trace-fix` loop: it decides
which gap and which candidates exist. The LLM decides which candidate is right."*

Deciding **which gap** is the same class of act as deciding which candidates are
reachable, and it is done by a hardcoded constant.

### 1.1 The loop shows one gap and hides the rest

`next_gap` (`propose.py:107-120`) iterates pending gaps and returns the first.
The order is `_KIND_ORDER` (`gaps.py:22`) then node id (`gaps.py:93`). The agent
receives `pending_total` — a bare integer — and no list.

`task_no_sr` is order 0 and `sr_unsatisfied` is order 3. They are the same missing
link seen from opposite ends. An agent that could see the pending set might notice
that three tasks all implement one requirement and reason about them together;
instead it meets each task cold, and the ordering constant guarantees it never
sees the requirement side until every task side is dispositioned.

The skill's **"Do not batch — one gap, one proposal, one confirmation"** rule is
correct: batched approval is rubber-stamping. But the implementation conflated
*visibility* with *commit granularity*. The whole list can be visible while
confirmations stay one at a time.

### 1.2 Half the gap kinds have no remedy in the toolset

`_POOL_KIND` (`propose.py:25`) covers four kinds. `GapKind` (`gaps.py:9-18`)
declares eight. For `sr_unvalidated`, `sr_stale`, `dangling_upstream` and
`task_plan_missing`, `candidates` is empty and `trace-tool-format.ts:21` renders:

> Candidates: no candidates exist for this gap kind. Defer it, or exempt it if it
> is a task or plan that legitimately has nothing to link to.

The exempt advice is correctly conditioned. But for a requirement, exempt is
refused outright at `write.py:66`, so **defer is the only legal move** — and
`registerTraceTools` (`trace-tools.ts:148`) registers exactly five tools:
`trace_next`, `trace_link`, `trace_exempt`, `trace_defer`, `trace_check`. None
runs validation.

So an `sr_unvalidated` that one `factory validate` would clear is recorded as
"discussed, needs more time", and `trace check` passes on deferrals. The gate goes
green on gaps that were fixable by a command the agent had no way to reach.
Deferral has become a pressure valve.

### 1.3 Content is truncated silently

`_EXCERPT_CHARS = 1200` and `_SUMMARY_CHARS = 400` (`propose.py:21-22`). The
candidate *list* is complete; every entry in it is clipped, with no marker and no
affordance to get more (`propose.py:118`, `propose.py:69`, `propose.py:76`).

A task's `dod` block — the content that most directly states what it satisfies —
can fall off the end of a 1200-character excerpt. Nothing in `SKILL.md` or
`skill-prompt.ts` tells the agent it may simply open the file.

## 2. What is deliberately not changed

- **`trace check` stays stateless and gate-shaped.** Re-deriving every gap and
  disposition from disk is correct: a gate that trusted the agent's account of its
  own progress would be worthless. That reasoning holds for a gate. It does not
  transfer to what the agent is allowed to look at.
- **Candidate ranking and non-truncation.** `_terms`, the stopword list and the
  score ordering are all fine, because the list they order is never cut.
- **The "lexical hint, not a verdict" warning**, repeated at four surfaces —
  `propose.py:99`, `trace-tools.ts:29`, `trace-tool-format.ts:28`,
  `skill-prompt.ts:24`. Saying it once would be an intention; saying it at every
  surface the model reads makes it operative. Keep all four.
- **Gap kinds.** The `sr_unvalidated` conflation is real but is fixed by the
  doctor design §8, which needs the same distinction for its proposed state. One
  change, not two.
- **"Do not batch."** One confirmation at a time survives unchanged.

## 3. Change A — show the whole pending set

`Proposal` gains a field listing every pending gap: `node_id`, `kind`, `detail`.
`pending_total` stays for compatibility with the existing test at plan 1 line 1675.

`trace_next` gains an optional `node_id` parameter. Absent, it behaves exactly as
today and focuses the first gap in `_KIND_ORDER`. Given, it focuses that gap
instead. An unknown or non-pending id is refused with the reason, and nothing is
written.

`formatProposal` renders the full list beneath the focused proposal, under a
heading that states plainly that the agent may take any of them and that the
ordering is a default, not a queue.

The three prompt surfaces change together: `SKILL.md` step 1, `skill-prompt.ts:23`
(which currently says the tools own enumeration), and the assertion in
`test/skill-prompt.test.ts:37`.

**Why this is the highest-value change:** it is one field and one format function,
and it removes the only place where a constant decides what the agent is permitted
to consider.

## 4. Change B — honest guidance for the candidate-less kinds

`formatProposal`'s empty-candidate branch becomes per-kind:

| kind | guidance |
|---|---|
| `sr_unvalidated`, `sr_stale` | Closed by running validation, not by linking. Neither `trace_link` nor `trace_exempt` applies. Defer only if validation genuinely cannot be run yet, and record why. |
| `dangling_upstream` | The target does not exist. Fix the reference or create the missing requirement; deferral records the dangle, it does not resolve it. |
| `task_plan_missing` | `source_plan` points at a file that is not there. Correct it with `trace_link --source-plan`, or exempt the task if it legitimately has no plan. |

`sr_unvalidated` and `sr_stale` are the two kinds the toolset cannot act on at all.
Two options, and this design takes the second:

1. Register a `trace_validate` tool wrapping `factory validate`.
2. State in the guidance and the skill that these close outside this loop.

Option 2, because validation needs a declared harness, a scenario and a scorer;
against a repo with no `.factory/factory.yaml` — the drone repo's state today — a
`trace_validate` tool would fail every time and teach the agent to defer anyway.
The doctor design's `sr_unvalidatable` kind makes that condition legible, at which
point a validate tool becomes worth revisiting. Reaching for the tool first would
be building the button before the thing it is supposed to fix.

## 5. Change C — mark truncation and name the escape hatch

Where `_read(...)[:_EXCERPT_CHARS]` or `[:_SUMMARY_CHARS]` actually cuts, append a
marker naming the full path:

```
…[truncated at 1200 chars — read docs/superpowers/plans/2026-07-21-....md for the full text]
```

`Node.path` is already on the node, so the path is available at every truncation
point. When the text fits, nothing is appended and output is unchanged.

`SKILL.md` gains one line: excerpts and summaries may be clipped, and reading the
file directly is expected when the excerpt is not enough to judge.

The limits themselves stay. They exist to keep a proposal readable, which is a
reasonable default — the defect was that a clipped excerpt was indistinguishable
from a complete one.

## 6. Testing strategy

**Python (`-m unit`):**
- `Proposal` carries every pending gap, and the count matches `pending_total`
- the focused gap is unchanged when no id is requested — guards the existing
  ordering behaviour
- requesting a specific pending gap focuses it and returns the same full list
- requesting an unknown or already-dispositioned id is refused, and nothing is
  written
- an excerpt over the limit ends with the marker and names the node's real path
- an excerpt under the limit is byte-identical to today

**TypeScript (`npm test`):**
- `formatProposal` renders the pending list and labels the ordering as a default
- each of the four candidate-less kinds renders its own guidance, and neither
  `sr_unvalidated` nor `sr_stale` suggests `trace_exempt`
- `trace_next` forwards `node_id` when given and omits it when not
- `skill-prompt.ts` no longer claims the tools own enumeration

## 7. Non-goals

- Any change to `trace check`, to gap kinds, or to health arithmetic.
- Batched approval, auto-linking, or any path that writes without a confirmation.
- A `trace_validate` tool — see §4.
- Changing the ranking heuristic or the truncation limits.
- Anything in the doctor loop; these two designs share no code beyond `Proposal`.
