# Governed-execution plugin for Hermes

This directory is a project-local Hermes adapter for SR-034/SR-049's governed
execution driver. It gives a human working from a Hermes session the same
surface Codex's `.agents/skills/governed-execution/SKILL.md` and Claude
Code's `.claude/commands/governed-execution.md` give their own hosts: inspect
what is legal for a named run and task, dispatch a task, watch progress, and
relay an explicit human `retry`/`defer`/`block` decision. It is a host
adapter only -- no local execution state, no lifecycle interpretation, no
second journal, no gate interpretation, no retry loop of its own.

**Python/Coherence is authoritative.** Stage order, revisions, attempts, gate
results, hashes, evidence, the fixer budget and every human decision live in
`coherence.execution.cli`. This plugin transports arguments in and renders
JSON out. A human must explicitly authorize retry, defer, block, or
downstream handoff -- this plugin never originates one of those and never
grants consent on the human's behalf.

Unlike `.hermes/plugins/coherence-plan/` (a purely read-only adapter -- it
only ever renders a planning projection), this plugin can also call
`dispatch-task` and `resolve-human`: the same two mutating verbs Codex's
skill and Claude Code's command already expose. It is still a thin adapter:
neither mutating verb is invoked without first asking the backend whether
that verb is currently legal.

## Prerequisites

- Hermes Agent with project-plugin discovery support.
- Python 3.11 or newer for this repository.
- `uv` on `PATH`.
- A checkout of this repository with its Coherence environment available to
  `uv run coherence`.
- Either run Hermes with this repository as its working directory, or make
  the checkout discoverable to this plugin: set `COHERENCE_PROJECT_ROOT`,
  set `COHERENCE_REPO_ROOT`, or write the checkout path into a `repo_root.txt`
  marker beside `plugin.py`.

Every backend call is an argv-only subprocess invocation of the form:

```text
uv run coherence execution <command> ... --project-root <project-root> --json
```

No shell command string is ever built, and a run ID or task ID containing
path separators, whitespace, shell syntax, or other characters outside the
safe identifier grammar is rejected before any subprocess runs.

## Command grammar

```text
/governed-execution legal-actions <run-id> <task-id>
/governed-execution dispatch-task <run-id> <task-id>
/governed-execution resolve-human <run-id> <task-id> <request-sha256> <decision-id> retry|defer|block <response words...>
/governed-execution stream-progress <run-id>
```

Both the run id and the task id must be supplied by the caller and must match
`[A-Za-z0-9][A-Za-z0-9._-]*`, the same grammar Codex's skill and Claude
Code's command document. This plugin never infers a run id, a task id, or the
current state from the working directory, recent history, a Kanban card, or
another session; a missing or unsafe identifier is rejected -- with a usage
message -- before any backend call. Every argument is passed to the backend
as separate argv values, never one interpolated string.

## 1. Ask the backend what is legal

```text
uv run coherence execution legal-actions --run-id <run-id> --task-id <task-id> --project-root <root> --json
```

is always called before `dispatch-task` or `resolve-human`. That response is
the only host transition projection this plugin trusts: it renders the
projection as returned and forwards only the backend-returned action from
`legal_next_actions`. `dispatch-task` and `resolve-human` are refused --
without a second subprocess call -- whenever the current projection does not
name them.

| `state` | What it means | What this plugin will forward |
| --- | --- | --- |
| `ready` | No pending decision, no recorded handoff | `dispatch-task`, `stream-progress` |
| `needs_input` | A durable human-decision request is pending | `resolve-human`, `stream-progress` |
| `completed` | The canonical `handoff` stage is recorded | render the handoff |
| `escalated` / `blocked` | A human deferred or blocked the run | render the reason |

`denied_write_count` is visibility only: it is rendered, never treated as a
failure or a blocker.

## 2. Dispatch, only when the projection says so

```text
uv run coherence execution dispatch-task <task-id> --run-id <run-id> --project-root <root> --json
```

is only forwarded to the backend when the `legal-actions` gate above named
`dispatch-task` in `legal_next_actions` -- only the backend-returned action is
ever forwarded. Progress is read the same way:

```text
uv run coherence execution stream-progress <run-id> --project-root <root> --json
```

## 3. `needs_input` is rendered, never answered

When `state` is `needs_input`, the projection -- including the exact
`request_sha256`, the request's reason, and the allowed `retry`/`defer`/
`block` choices -- is rendered exactly as the backend returned it. This
plugin never answers the request itself. A human must choose, and that
choice must be supplied to this plugin's own `resolve-human` entrypoint as an
explicit argument:

```text
uv run coherence execution resolve-human --run-id <run-id> --task-id <task-id> --request-sha256 <hash> --decision-id <id> --decision retry|defer|block --response <human words> --decided-by human --json
```

This plugin never infers a decision from a Hermes Kanban `done` card, a
model's own claim that work is finished, or anything else it can observe --
only from the `retry`/`defer`/`block` word the caller types as this command's
own argument. A repeated identical decision is an idempotent replay; a
conflicting, stale, or already-consumed decision is rejected by the backend
and that rejection is shown verbatim, never worked around.

## 4. Stop at the handoff

Every projection and handoff carries `starts_automatically: false`. That is a
hard stop: this plugin never starts implementation, never adopts a
requirement, and never starts a downstream workflow, merge, or push because a
run completed. Consent, requirement adoption, and downstream handoff are
human-only decisions this plugin does not make.

## What this plugin never does

- **Never retry** a failed stage on its own; a retry is a human decision the
  backend records.
- **Never invoke a worker process** (an agent, a test command, a fixer)
  directly; the driver owns every lane.
- **Never interpret a gate** result, a test failure, or a review finding as
  pass/fail; the backend already decided.
- **Never write a second journal**, checkpoint, status file, or any
  host-local lifecycle state; the Coherence run journal is the only state
  path.
- **Never reproduce the driver loop** in this file, in `plugin.py`, or in any
  prompt a Hermes session builds from it.
- Never infer a transition from a Kanban `done` card or from a model's own
  claim that work is finished.
- Never register a flaky test on a human's behalf: `coherence execution
  flaky-register` requires `--decided-by human` and is not exposed by this
  plugin at all.

## Project root resolution

The backend is invoked with an explicit `--project-root`, resolved in this
order (identical to `.hermes/plugins/coherence-plan/`'s own resolution):

1. `COHERENCE_PROJECT_ROOT`, when set.
2. The current working directory, when it is itself a checkout (it contains
   `pyproject.toml` and `src/coherence`).
3. A checkout located via `COHERENCE_REPO_ROOT`, or a `repo_root.txt` file
   written beside `plugin.py`, or `plugin.py`'s own location when it is
   installed inside a checkout.
4. The current working directory, as a last resort.

Unlike `coherence-plan`'s plugin, this plugin never loads a Python module
from the located checkout -- it only tells the CLI subprocess which directory
to run against -- so "the checkout" here means only "a directory carrying
`pyproject.toml` and `src/coherence`".

A checkout that cannot be located, an unreadable or missing `uv`/`coherence`
executable, and a non-zero CLI exit outside its own canonical `0`/`1` pair are
all rendered as `execution blocked: ...`. Nothing here raises into the Hermes
host.

## Explicit opt-in activation

Project-local plugins are disabled by default. Enable this plugin only for a
trusted checkout and only for the Hermes process being started:

```bash
HERMES_ENABLE_PROJECT_PLUGINS=true hermes
```

On PowerShell, use a process-scoped environment variable instead:

```powershell
$env:HERMES_ENABLE_PROJECT_PLUGINS = "true"
hermes
```

This does not edit `~/.hermes/config.yaml`, enable a persistent user plugin,
or modify any Hermes profile.

## Authority and boundaries

- Coherence owns every execution projection, hash, gate result, and human
  decision record.
- This plugin renders the backend's exact state, reason, and pending request;
  it does not soften, reinterpret, or replace any of them with a host-local
  status.
- Hermes provides presentation and the surrounding conversation only.
- This plugin never grants consent, never starts implementation, and never
  starts a downstream workflow, merge, or push.
- Hermes configuration is not changed or automatically enabled by this
  project-local package.

For a clean handoff, `starts_automatically: false` remains mandatory. A human
must choose any next action through an appropriate authorized workflow, and
that workflow must revalidate the current Coherence state before acting.
