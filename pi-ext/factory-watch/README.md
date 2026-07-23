# factory-watch — Pi extension

Launches and observes the factory orchestrator from inside an interactive
`pi` session. Loads in *your own* session (not the orchestrator's spawned
sub-agent sessions, which load `scope-guard` instead).

## Commands

- `/factory [--auto]` — reads the session's currently active model
  (`ctx.model`), runs
  `uv run python -m factory.orchestrator run --provider <provider> --model <id>`,
  and watches its progress. Refuses to start a second run while
  `sessions/.factory-run.lock` shows a live PID.
  - Without `--auto` (the default): spawns the orchestrator **non-detached**
    with piped stdio. When the orchestrator's automated review passes, it
    writes a `review_pending` JSON line to stdout and blocks on stdin for a
    decision; this extension opens a review overlay (file-list summary +
    full diff drill-down, `c` to comment, `e` to edit, `a`/`r` to
    approve/reject) and writes the decision back to the child's stdin. This
    is the human-in-the-loop path.
  - With `--auto`: reproduces the original fully-automated behavior
    unchanged -- detached spawn, no stdin/stdout piping, no review gate,
    polls `sessions/.factory-status.json` (written by the orchestrator, see
    Plan A) once a second and renders it via a widget.
  - Either way, once the run is launched this also opens a **mission
    control** terminal window (see below).
- `/factory-run [--auto] [task-id]` — runs the exact same pipeline `/factory`
  does, targeting one specific task (`status: todo` only) instead of
  whichever the orchestrator would pick next: with no task id, lists todo
  tasks via `factory.orchestrator list --json` and shows an interactive
  picker; with a task id, skips straight to
  `uv run python -m factory.orchestrator run --provider <provider> --model
  <id> --task <task-id>`. Like `/factory`, `--auto` picks the detached
  `launchAndWatch` path and its absence picks the foreground
  `launchInteractiveReview` human-review path, and either way a mission
  control window opens alongside the run.
- `/factory-stop` — reads the lock file's PID and terminates it: a forceful
  process-tree kill on Windows (`taskkill /PID <pid> /T /F` — a non-forceful
  `/T` alone is unreliable for plain console processes on Windows, so this
  skips straight to force), or `SIGTERM` to the process group followed by
  `SIGKILL` after a few seconds if still alive on POSIX.
- `/factory-tasks` — shows the task ledger, grouped by status, as a widget.
- `/review-plans` — lists every file under `docs/superpowers/specs/`,
  `docs/superpowers/plans/`, and `tasks/T-*.md` (newest first, labeled
  `[spec]`/`[plan]`/`[task]`; task labels show `id -- title (status)`),
  and opens the picked one in a scrollable, real-markdown-rendered view
  (`pi-tui`'s own `Markdown` component, not a raw-text dump). Task
  frontmatter is reformatted into a clean header instead of shown as raw
  YAML. Keys: Up/Down/PageUp/PageDown/Home/End to scroll, `q` or Escape
  to close.
- `/plan <topic>` — starts a fresh session seeded with the real, full content
  of the vendored `brainstorming`/`writing-plans` skills (hard-loaded via
  Pi's own exported `loadSkills`/`stripFrontmatter`, not the soft
  advertise-and-hope-the-model-reads-it path) plus the topic. Ends with
  `uv run python -m factory.orchestrator.plan_to_tasks <plan-file>`
  deterministically turning the saved plan into `tasks/T-*.md` files, ready
  for `/factory-run`.

## Mission control

Both `/factory` and `/factory-run` open a second terminal window (via
`spawnTerminalWindow`) running the standalone `mission-control-dashboard.ts`
entry point, pointed at the same `sessions/.factory-status.json` the running
orchestrator writes. It shows all 5 pipeline stages (context-gather, dev,
validation, review, human-review) with the currently-running one
highlighted, handoff messages as each stage completes, and a `blocked --
waiting for you to review the diff` state if the run reaches human-review.
Selecting a row and pressing Enter dispatches by stage: agent rows
(context-gather, dev, review) open the real `pi --session <id>` in a new
window; validation opens a window tailing that run's `sim-gate.log`; and
human-review (once a startCommit exists) opens `mission-control-review.ts`
to browse the actual changed files. These windows are purely observational
(review browsing aside) -- closing them does not affect the run.

## No new IPC

Everything here reads files Plan A's orchestrator already writes
(`sessions/.factory-status.json`, `sessions/.factory-run.lock`) — no sockets,
no named pipes.

## Hard skill loading

`/plan` never relies on the model choosing to read a skill file. It reads
`.pi/skills/brainstorming/SKILL.md` and `.pi/skills/writing-plans/SKILL.md`
itself (via Pi's own exported `loadSkills`/`stripFrontmatter`) and injects
their full content into the seed message -- the same `<skill name="..."
location="...">` shape Pi's native `/skill:name` expansion produces. The
orchestrator's sub-agent roles do the equivalent on the Python side
(`factory/orchestrator/skills.py`'s `load_skill_block`, used by
`compose_prompt`). All 10 vendored skills are marked
`disable-model-invocation: true` in their frontmatter -- they're never meant
to be reachable any other way.

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
