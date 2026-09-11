# Coherence planning plugin for Hermes

This directory is a project-local, read-only Hermes adapter for the Coherence
planning workflow. It presents the backend's current legal actions and block
reason for a named planning run. Coherence remains the authority for planning
state, hashes, gates, DecisionFiles, consent, adoption, and the handoff.

The adapter does not perform adoption, accept warnings, run gates, materialize
Kanban work, or start implementation or any other downstream workflow. It does
not infer actions from conversation history, model output, Hermes session state,
or Kanban state.

## Prerequisites

- Hermes Agent with project-plugin discovery support.
- Python 3.11 or newer for this repository.
- `uv` on `PATH`.
- A checkout of this repository with its Coherence environment available to
  `uv run coherence`.
- Either run Hermes with this repository as its working directory, or make the
  checkout discoverable by the plugin itself so it can load the shared adapter:
  set `COHERENCE_REPO_ROOT`, write the checkout path into a `repo_root.txt`
  marker beside `plugin.py`, or install the plugin inside the checkout. An
  out-of-tree install needs one of these; setting only
  `COHERENCE_PROJECT_ROOT` is not enough, because that variable chooses the
  `--project-root` passed to the backend and does not make the shared adapter
  loadable (see "Project root resolution" below).

The backend command used by the adapter is an argv-only subprocess invocation:

```text
uv run coherence plan legal-actions --project-root <project-root> --run-id <run-id> --json
```

The adapter passes no shell command string and rejects a run ID containing path
separators, whitespace, shell syntax, or other characters outside its safe
run-ID grammar before invoking the backend.

## Where the shared logic comes from

The safety-critical logic lives in
`src/coherence/planning/legal_actions_adapter.py`, shared with every other host
adapter. This plugin loads that module **by file path** rather than with
`import coherence.planning.legal_actions_adapter`.

The package import would first execute `coherence/planning/__init__.py`, which
eagerly imports the whole planning chain (`bootstrap` → `check` → `model` →
`semantic` → `serialization` → `python-frontmatter`). A host process that only
*wants to render a projection* would then need this project's full runtime
installed in its own interpreter, on a matching Python version. The adapter
module itself imports only the standard library, so loading it directly keeps
the host's environment untouched while still executing this repository's source
verbatim. There is no second copy of the logic to drift.

## Project root resolution

The backend is invoked with an explicit `--project-root`, resolved in this
order:

1. `COHERENCE_PROJECT_ROOT`, when set.
2. The current working directory, when it is itself a checkout (it contains
   `pyproject.toml` and `src/coherence`). This keeps the ordinary "run Hermes
   from the repository" path — and `Path.cwd()` — unchanged.
3. The checkout that owns the shared adapter, when the working directory is
   not a checkout. This is what lets a host started elsewhere (a user-level
   plugin install, for example) query this project anyway.
4. The current working directory, as a last resort.

Step 3 locates the checkout from `COHERENCE_REPO_ROOT`, else a `repo_root.txt`
file written beside this plugin by an install that lives outside the checkout,
else this file's own location when it is installed inside a checkout. Every
candidate is used only if it actually carries
`src/coherence/planning/legal_actions_adapter.py` — the override included — so a
misconfigured override falls through to the next candidate instead of failing
at the load.

A checkout that cannot be located, and an adapter that cannot be loaded from a
located checkout (missing, unreadable, or not even parseable source, or a file
that does not expose the adapter's API), are both rendered as a
`planning blocked: ...` string; neither raises into the host.

| Variable | Meaning |
|---|---|
| `COHERENCE_REPO_ROOT` | The checkout holding `src/coherence/planning/legal_actions_adapter.py`; used only when that file is actually there |
| `COHERENCE_PROJECT_ROOT` | The `--project-root` passed to the backend |

`repo_root.txt` is not ordinary configuration. It selects which Python source
file the Hermes host process *executes* when `/coherence-plan` runs, so it
carries the same trust level as `plugin.py` itself: a file that only a trusted
writer can modify, and that must be write-protected accordingly. This plugin
adds no hashing or pinning of the path it reads — the file system it is read
from is the trust boundary.

## Explicit opt-in activation

Project-local plugins are disabled by default. Enable this plugin only for a
trusted checkout and only for the Hermes process you are starting:

```bash
HERMES_ENABLE_PROJECT_PLUGINS=true hermes
```

On PowerShell, use a process-scoped environment variable instead:

```powershell
$env:HERMES_ENABLE_PROJECT_PLUGINS = "true"
hermes
```

This does not edit `~/.hermes/config.yaml`, enable a persistent user plugin,
or modify any Hermes profile. Close the process or clear the environment
variable to return to the default disabled behavior. Do not use
`hermes --ignore-rules` for this test: that option also disables project
plugins.

After Hermes starts in the repository, the command registered by this package
is:

```text
/coherence-plan <run-id>
```

The namespace is intentional. This package does not claim the bare `/plan`
name and does not replace another host's `/plan` command. If a host presents a
guided `/plan` entrypoint, it must still use a named run and the backend legal-
actions projection; this plugin itself only exposes `/coherence-plan`.

## Named run lifecycle

Run IDs identify durable planning state and must be reused when resuming. A
new run is started explicitly through Coherence, not implicitly by invoking the
Hermes adapter:

```bash
uv run coherence plan start \
  --project-root . \
  --run-id run-001 \
  --prompt "Describe the planning request here" \
  --json

uv run coherence plan resume \
  --project-root . \
  --run-id run-001 \
  --json
```

`start` creates the named run and fails if that run already exists. `resume`
reconstructs and validates the existing named run; it does not create a second
run. If an interrupted Hermes session is replaced, invoke the adapter again
with the same run ID rather than inventing a new ID:

```text
/coherence-plan run-001
```

The adapter does not call `start`, `resume`, `append`, `resolve`, `finalize`,
or any other mutating planning operation. Use the Coherence CLI or the
approved host workflow for those operations, and re-check legal actions after
any state-changing operation.

## Legal-actions JSON contract

`coherence plan legal-actions --json` returns a JSON object. The adapter
accepts the response only when all authority fields below are valid:

```json
{
  "schema": 1,
  "run_id": "run-001",
  "blocked": true,
  "reason": "SESSION_NOT_READY",
  "legal_next_actions": [],
  "starts_automatically": false
}
```

The `schema` is the integer `1`; `run_id` must exactly equal the requested
named run; `blocked` is a boolean; `reason` is either a string or `null`;
`legal_next_actions` is an array of strings; and `starts_automatically` must
be exactly `false`. The backend may include additional projection fields such
as `state`, `run_identity`, `selected_downstream_workflow`, and its action
registry; the adapter renders only the backend-declared action list and block
reason.

A missing, malformed, stale, contradictory, or automatically-starting
projection is blocked rather than guessed. A failed subprocess or invalid
JSON response is rendered as a planning block and cannot cause a workflow to
start.

Typical output is:

```text
Planning blocked: SESSION_NOT_READY
Legal actions: none
Starts automatically: no
```

For an unblocked response, the same output shape is used:

```text
Planning ready
Legal actions: inspect-handoff
Starts automatically: no
```

The action list is display-only. Seeing an action such as
`create-downstream-session` never authorizes this adapter to execute it.

## Authority and boundaries

- Coherence owns the legal-action projection and all planning truth.
- The adapter renders the backend's exact block reason; it does not soften,
  reinterpret, or replace it with a host-local status.
- Hermes provides presentation and the surrounding conversation only.
- The adapter never grants consent, adopts candidate SRs, changes canonical
  FEAT/SR/bundle files, runs gates, creates a downstream session, or launches
  implementation.
- Hermes configuration is not changed or automatically enabled by this
  project-local package.

For a clean handoff, `starts_automatically: false` remains mandatory. A human
must choose any next action through an appropriate authorized workflow, and
that workflow must revalidate the current Coherence state before acting.
