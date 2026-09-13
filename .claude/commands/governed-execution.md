---
description: Drive one named governed execution run through the Python-owned Coherence execution commands
argument-hint: <run-id> <task-id>
---

You are driving one governed execution run (SR-034/SR-049) for the named run ID
and task ID. This command is the Claude Code rendering of exactly the same
contract as Codex's `.agents/skills/governed-execution/SKILL.md`; neither host
may diverge from it.

**Python/Coherence is authoritative.** Stage order, revisions, attempts, gate
results, hashes, evidence, the fixer budget and every human decision live in
Python. You transport arguments in and render JSON out. A human must explicitly
authorize retry, defer, block, or downstream handoff — you never originate one
of those and never grant consent on the human's behalf.

## Required input

`usage: /governed-execution <run-id> <task-id>`

Both identifiers must be supplied by the user and must match
`[A-Za-z0-9][A-Za-z0-9._-]*`. The run ID and the task ID are the only two
identities you are allowed to act on. Never infer a run ID, a task ID, or the
current state from the working directory, recent history, a Kanban card, or
another session. If either argument is missing or unsafe, print the usage line
and stop.

Pass every argument as **separate argv values** (never one interpolated
string), exactly as shown below.

## 1. Ask the backend what is legal

Always run this first, and again after every state-changing operation:

```text
uv run coherence execution legal-actions --run-id <run-id> --task-id <task-id> --project-root <root> --json
```

That projection is the only host transition projection. Render it as returned
and permit only the backend-returned action from `legal_next_actions`. Do not
infer state or actions, do not translate or rename an action, and do not
auto-select one.

- `ready` → `dispatch-task`, `report-worker-result`, `stream-progress`
- `needs_input` → `resolve-human` (the human chooses), `stream-progress`
- `completed` → render the handoff and stop
- `escalated` / `blocked` → render the reason and stop

`denied_write_count` is visibility only: report it, never treat it as a failure
or a blocker.

## 2. Dispatch, only when the projection says so

```text
uv run coherence execution dispatch-task <task-id> --run-id <run-id> --project-root <root> --json
```

Exit `0` is a valid payload, `1` a canonical blocked or escalated result, `2`
invalid input. Forward the structured JSON and the exact blocking reason
verbatim; never soften or summarize a refusal into a success.

Read progress with:

```text
uv run coherence execution stream-progress <run-id> --project-root <root> --json
```

Report a worker lane's own observation — never a verdict — with:

```text
uv run coherence execution report-worker-result --run-id <run-id> --task-id <task-id> --lane <lane> --result pass|fail|error --detail <text> --json
```

## 3. `needs_input` is rendered, never answered

When `state` is `needs_input`, display the exact `request_sha256`, the request's
reason, and the allowed `retry|defer|block` choices. **Never answer the request
yourself.** Ask the human which one they choose, then relay their decision:

```text
uv run coherence execution resolve-human --run-id <run-id> --task-id <task-id> --request-sha256 <hash> --decision-id <id> --decision retry|defer|block --response <human words> --decided-by human --json
```

`retry` runs one more governed attempt, `defer` writes the existing Deferral,
and `block` keeps the run escalated. A repeated identical decision is an
idempotent replay; a conflicting, stale or already-consumed decision is
rejected by the backend — show the rejection, never work around it.

## 4. Stop at the handoff

Every projection and handoff carries `starts_automatically: false`. That is a
hard stop: when you see it, render the handoff and stop. Consent, requirement
adoption, and downstream handoff are **human-only** decisions. Never start
implementation, never adopt a requirement, and never start a downstream
workflow, merge, or push because a run completed.

## What this command never does

- **Never retry** a failed stage on your own; a retry is a human decision the
  backend records.
- **Never invoke a worker process** (an agent, a test command, a fixer) directly;
  the driver owns every lane.
- **Never interpret a gate** result, a test failure, or a review finding as
  pass/fail; the backend already decided.
- **Never write a second journal**, checkpoint, status file, TodoWrite plan, or
  any host-local lifecycle state; the Coherence run journal is the only state
  path.
- **Never reproduce the driver loop** in prose, shell, TypeScript, or model
  instructions.
- Never infer a transition from a Kanban `done` card or from a model's own
  claim that work is finished.
- Never register a flaky test on a human's behalf: `coherence execution
  flaky-register` requires `--decided-by human` and is the human's command.
