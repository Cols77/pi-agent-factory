# factory-watch — Pi extension

Launches and observes the factory orchestrator from inside an interactive
`pi` session. Loads in *your own* session (not the orchestrator's spawned
sub-agent sessions, which load `scope-guard` instead).

## Commands

- `/factory` — reads the session's currently active model (`ctx.model`), runs
  `uv run python -m factory.orchestrator run --provider <provider> --model <id>`
  detached, and polls `sessions/.factory-status.json` (written by the
  orchestrator, see Plan A) once a second, rendering it via a widget. Refuses
  to start a second run while `sessions/.factory-run.lock` shows a live PID.
- `/factory-stop` — reads the lock file's PID and terminates it: a forceful
  process-tree kill on Windows (`taskkill /PID <pid> /T /F` — a non-forceful
  `/T` alone is unreliable for plain console processes on Windows, so this
  skips straight to force), or `SIGTERM` to the process group followed by
  `SIGKILL` after a few seconds if still alive on POSIX.

## No new IPC

Everything here reads files Plan A's orchestrator already writes
(`sessions/.factory-status.json`, `sessions/.factory-run.lock`) — no sockets,
no named pipes.

## Load into Pi

```
pi --extension pi-ext/factory-watch/src/index.ts
```
Then type `/factory` in the session.

## Test

```
npm --prefix pi-ext/factory-watch run typecheck
npm --prefix pi-ext/factory-watch test
```

## Verification limits

`ctx.ui.*` calls are no-ops in `-p`/print mode (per Pi's own docs), so the
*logic* here (spawning, file reads, process control) is verifiable
headlessly, but the actual *rendered widget* can only be seen in a real
interactive session. See this plan's Task 6 for what was and wasn't
automated.
