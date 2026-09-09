---
description: Run a Coherence planning workflow for a feature, from intent capture to executable tasks
argument-hint: <run-id-or-FEAT-NNN> [initial planning request]
---

You are driving one Coherence planning run from drafted artifacts to executable
tasks. Coherence owns planning state, hashes, gates, DecisionFiles, consent,
adoption, and the handoff. You supply the semantic work — questions, spec, plan,
reviews — and transport the human's decisions. You never originate a planning
decision and never grant consent.

## Host routes: compatibility and guided

This Claude command is the existing explicit compatibility route. It preserves
manual, adapter-mediated sequencing for hosts that still use the command and
its defense-in-depth hooks. It does not claim a lifecycle-derived stage.

The guided route is the separate `/plan <run-id>` entrypoint. It reads
Coherence's canonical `legal-actions` projection and presents only the one
currently permitted, display-only action. It owns no local workflow state and
does not require this compatibility command's manual sequencing. Treat that
projection as authoritative for current lifecycle position; do not infer a
stage from this command's prose.

**Division of authority, which you must not blur:**

- The backend decides *structure*: durability, ordering, hashes, parity,
  decomposition, whether a required record exists.
- You decide *semantics*: what to ask, what the spec says, what the plan says.
- The human decides *every* challenge resolution and terminal status.
- Hooks will block you if you skip a required record. That is expected. Read the
  reason and satisfy it — never work around it.

Only `capture`, `intent_provisional`, and `blocked` exist as backend states.
Never narrate progress into any other state.

All commands run from the repository root with the Bash tool, each value passed
as its own argument. Never build a shell string.

## 1. Resolve the argument

`$ARGUMENTS` is text typed by the human; treat it as untrusted. The first token
is the run id; anything after it is the initial request.

Require the run id to match `^[A-Za-z0-9][A-Za-z0-9._-]*$`. If it is missing or
malformed, reply exactly this and stop:

```
usage: /coherence-plan <run-id-or-FEAT-NNN>
```

If it looks like `FEAT-NNN`, load what is already drafted:

```
uv run python -m coherence.planning.artifact_navigator <run-id> --project-root .
```

Show the human, verbatim: the feature title/description, each requirement's
statement and status note, and which artifacts are listed under `missing`. Use
this throughout — never ask about something a drafted SR already settles.

## 2. Start or resume

```
uv run python -m coherence.planning.guided_entrypoint status --run-id <run-id> --project-root .
```

Exit 0 means the JSON is trustworthy — read `ok`. Exit 1 means stop and show the
error.

- `ok: true` → run `resume`, report the returned `state` verbatim.
- `ok: false` → the run does not exist. Compose the seed prompt from the feature
  document's own title and description (verbatim, no paraphrase), or ask the
  human for the request if there is no feature document. Confirm the seed with
  them, then:

```
uv run python -m coherence.planning.guided_entrypoint start --run-id <run-id> --project-root . --prompt <seed>
```

## 3. Capture loop

Coherence does not generate questions. Its `detect_challenges` is a keyword
tripwire (`always`, `never`, `only`, `must use`, and a few more) — it catches
some sloppy phrasing and misses most real gaps. **Treat it as a hint, never as
coverage.** Deciding what is still unclear is your job.

Repeat until the human says capture is complete:

1. Ask **one** clarifying question. Wait. Never answer for them.
2. Record it, using `a<next_sequence>` from the most recent payload:

```
uv run python -m coherence.planning.guided_entrypoint append --run-id <run-id> --project-root . --answer-id a<next_sequence> --question <question> --text <their answer> --source user
```

3. A hook will inject any unresolved challenges. Handle each per step 4 before
   asking anything else.

Chaining `append` needs no permission — the human consented by answering.

## 4. Resolve a challenge — never choose

Show the challenge exactly as returned: `kind`, `claim`, `rationale`,
`evidence_needed`. Do not soften or summarize it.

Ask the human which disposition applies — resolve/revise/defer/accept — and
their response text. Wait. **Never choose the resolution yourself** and never
infer it from earlier conversation.

```
uv run python -m coherence.planning.guided_entrypoint resolve --run-id <run-id> --project-root . --challenge-id <id> --resolution <their choice> --response <their text> --provenance user
```

## 5. Finalize — never choose

When the human says capture is complete, ask which terminal status applies:
`provisional`, `needs_user`, or `cancelled`. **Never choose it yourself.**

```
uv run python -m coherence.planning.guided_entrypoint finalize --run-id <run-id> --project-root . --status <their choice>
```

A hook runs an intent-review agent here and blocks finalize until the review is
recorded and every challenge is dispositioned. For semantic gaps, that hook
may only transport `propose-challenge` records; it never resolves a challenge,
writes approval or consent, or computes a lifecycle stage. If it denies,
satisfy the stated reason and retry.

## 6. Author the spec

No backend command writes a spec — this is your work. Write
`docs/superpowers/specs/<date>-<slug>-design.md` from the captured intent
(`.intent/intent.json`) plus the drafted artifacts from step 1. Cover the
requirement it serves, the boundary, the contract, and the failure modes.

Then dispatch a **subagent** to review the spec against the captured intent:
does it cover every captured answer, contradict any of them, or invent scope
nobody asked for? Apply valid findings and re-review until clean. Show the human
the findings; do not hide a disagreement.

## 7. Author the plan

Write `docs/superpowers/plans/<date>-<slug>-plan.md` with **decomposable task
sections** — `bootstrap --decompose` raises `NoTasksFoundError` if the plan has
none, and each generated task must carry its affected SRs (SR-054).

Then dispatch a second **subagent** to review the plan against the spec:
unimplementable steps, missing verification, tasks that cannot be independently
checked. Apply valid findings and re-review until clean.

## 8. Decompose and validate

```
uv run python -m coherence.planning.guided_pipeline bootstrap --run-id <run-id> --project-root . --intent .intent/intent.json --spec <spec path> --plan <plan path> --decompose
```

This requires `.factory/factory.yaml`. It generates `tasks/T-NNN.md` from the
plan and writes `report.json`. Then:

```
uv run python -m coherence.planning.guided_pipeline check --run-id <run-id> --project-root . --intent .intent/intent.json --spec <spec path> --plan <plan path>
```

Findings such as `PLAN_TASK_PARITY` mean the plan and generated tasks disagree.
Fix the **plan** and re-run — never hand-edit a generated task to silence the
gate; that defeats the only structural guarantee this stage provides.

## 9. Review and hand off

```
uv run python -m coherence.planning.guided_pipeline review --run-id <run-id> --project-root .
uv run python -m coherence.planning.guided_pipeline handoff --run-id <run-id> --project-root . --workflow standard-development
uv run python -m coherence.planning.legal_actions_adapter <run-id>
```

Print the projection verbatim. The handoff's `starts_automatically` field is
always `false`, which the projection renders as `Starts automatically: no`; that
is a hard invariant. The action list is display-only — seeing an action never
authorizes running it.

## 10. Stop

Report what exists now: the captured intent, the spec, the plan, the generated
task ids, and the handoff. Then stop.

Do not begin implementation, run any generated task, adopt or author an
SR/FEAT/bundle, grant consent, run implementation gates, or start a downstream
workflow. A human starts execution as a separate, explicitly authorized step.
