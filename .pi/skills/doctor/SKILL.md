---
name: doctor
description: Turn prose specs into system requirements — read the specs, judge which claims are falsifiable requirements, propose them one at a time, and let the doctor tools perform every write.
---

# Doctor

Use this when a project's behaviour is described in its specs but not recorded in
its requirements register — a project being onboarded, or one whose specs have
moved ahead of its requirements.

## What you own, and what you do not

You own **the judgement**: which claims in the prose are requirements, how many
are in a passage, whether the register already covers one, how a statement should
read, when the pass is done, and what a metric task says.

You do **not** own id assignment, frontmatter, or the scorer lookup. Those are
mechanical, and they fail silently when done by hand — a colliding `SR-004`, or
YAML the register rejects long after you wrote it.

This split is narrower than the one in `\trace-fix`, and deliberately so. That
loop works over a finite gap set on disk, so its tools can tell it when the work
is finished. Yours works over prose, where "have we captured every behaviour" is
not computable. **You decide when the pass is complete**, and you say what you
based that on.

## Steps

1. **Get the register state.** Call `factory doctor context`. It gives you every
   requirement with its statement, source and state, the declared harnesses, and
   which metrics are actually implemented.
2. **Read the specs yourself**, in full, with your own file tools. The context
   command lists their paths and deliberately does not summarise, rank or excerpt
   them — a heuristic that decided which prose reached you would cap what you can
   find.
3. **Judge.** A requirement is a claim a measurement could contradict. "The
   navigation system shall preempt patrol within 5s of a shark detection" is one.
   "The system should be responsive" is not. A single heading may hold three
   requirements or none — the register, not the document structure, tells you what
   is already covered.
4. **Propose one.** Give the human the statement you would record, the passage it
   came from, and why you read it as falsifiable. If an existing requirement
   already covers the ground, say so instead of minting a near-duplicate.
5. **Wait.** One proposal, one confirmation. Never batch approvals, and do not
   call a write tool before they answer.
6. **On accept**, `factory doctor mint --source <spec path> --title ...
   --statement ... --domain ...`. Then return to step 4.
7. **When the human wants a requirement bound**, `factory doctor promote SR-NNN
   --harness ... --experiment ... --metric ... --assert ...`. Propose the harness,
   experiment and metric name; let the human choose the threshold.
8. **If promote reports the metric is NOT implemented**, propose a task that
   implements it in the target repo's scorers module, with a real definition of
   done. On accept, `factory doctor task --satisfies SR-NNN --title ... --dod ...`.
9. **Say when you believe the pass is complete**, and what you based it on — which
   specs you read, and what you deliberately did not record as a requirement.

## Rules

- **Never hand-write a requirement or task file.** `mint`, `promote` and `task`
  produce frontmatter the register can parse; hand-authored YAML is discovered as
  broken much later, by something else.
- **Never invent an assertion threshold.** Propose the metric, ask for the number.
  It is a product decision, and an agent-invented number that looks authoritative
  in the register is worse than an obvious hole.
- **A proposed requirement is not a failure.** Recording one whose measurement is
  undecided is the honest state, and it does not block the gate.
- **Do not link tasks to requirements here.** `\trace-fix` already does that, with
  ranked candidates over the existing graph. This skill only mints what does not
  yet exist.
- **Step 9 is a claim, not a gate.** `factory trace check` remains the gate, and
  re-derives everything from disk.
