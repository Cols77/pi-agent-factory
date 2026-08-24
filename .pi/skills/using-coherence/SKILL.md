---
name: using-coherence
description: Route "what should I do next" to the right coherence workflow — read /using-coherence's ranked status menu and point at the command that actually resolves each outcome. Reference only; performs no writes itself.
---

# Using coherence

`/using-coherence` (`pi-ext/factory-watch/src/coherence-command.ts`) prints one
deterministic menu: `coherence status --json`'s probe lines, worst outcome
first, each with the exact resolve command Python already built. This skill
is the routing table for that menu — it tells a human or an agent which
*workflow* a given outcome belongs to. It does not run anything, write
anything, or decide anything on the register, the trace graph, or any file.
The resolve commands printed by `/using-coherence` itself, and the workflows
below, hold all write authority; this document holds none.

## What you own, and what you do not

You own **orientation**: given an outcome name from the menu, which skill or
command is the one that actually clears it. You do not own judgement about
*whether* to clear it, what a fix should say, or any mutation — those belong
to the workflow the table below points at (`\doctor`, `\trace-fix`, the
`coherence`/`factory` CLIs), never to this file.

## Routing table

| Outcome (worst → best) | What it means | Where it resolves |
| --- | --- | --- |
| `interrupted_run` | A factory run stopped mid-pipeline with an open checkpoint. | `factory.orchestrator run-state inspect <run-id>` (printed `resolve_cmd`) — inspect, then resume or close the run via the orchestrator's own recovery path. Not a coherence write. |
| `probe_error` | One of `coherence status`'s own probes crashed. | Read the summary for the failing probe's name, then run that probe's own CLI directly (e.g. `coherence trace check`, `coherence register check`) to see the real error outside the aggregator. |
| `failing_gate` | `coherence trace check`, `coherence register check`, or the membership `--gate` failed. | Run the printed `resolve_cmd` yourself to see the full report, then close the specific gap it names — a missing `satisfies` edge via `\trace-fix`, an invalid requirement via `\doctor`, or an unbundled artifact via `coherence navigate membership`. |
| `stale_audit` | The newest coverage-review run recorded an SR whose checksum has since drifted. | `coherence audit run <feature>` (printed `resolve_cmd`) — re-run the audit for that feature; do not hand-edit `checksum_state`. |
| `proposed_backlog` | A declared feature has never been audited. | `coherence audit run <feature>` (printed `resolve_cmd`), or `\doctor` first if the feature's requirements themselves are still thin. |
| `nothing_pending` | Every probe is clean. | Nothing to route — `/using-coherence` reflects this back as the primary line. |

## How to use this table

1. Run `/using-coherence`. Its top line names the worst outcome and its
   `resolve_cmd`; the numbered menu beneath it, headed by "not that? pick
   from the menu", lists every other probe's outcome in the same worst-first
   order.
2. Look up the outcome name (not the free-text summary) in the table above.
3. Hand off to the named workflow. If it is a `resolve_cmd`, that command is
   already fully substituted — run it as printed, never re-typed or
   concatenated with another command.
4. If a probe's outcome is not in this table, that is this table falling
   behind `src/coherence/status.py`'s `_PRECEDENCE` tuple — treat it as
   needing attention (never as clean) and fix the table, not the assumption.

## Rules

- **Never write on this skill's own authority.** Every mutation in the table
  above happens inside the workflow it names, driven by that workflow's own
  tools — this file only names which workflow to open.
- **Never re-rank the menu.** `coherence status` already computed
  worst-first precedence; this table routes by outcome name, it does not
  re-decide which outcome is worse.
- **Never invent a resolve command.** If `resolve_cmd` is absent for a line,
  route to the workflow's own read path (e.g. run the probe's CLI directly),
  not to a guessed command.
