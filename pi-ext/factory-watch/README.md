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
  - Without `--auto` (the default): spawns the orchestrator **detached**,
    with stdio fully closed, starts the background status-widget poll, and
    opens the in-session **mission control** dashboard (see below) --
    `q` closes the dashboard back to the chat while the run and the
    background poll keep going; `/factory-watch` reopens it later. When the
    orchestrator's automated review passes, it blocks on human review by
    writing a `human-review` pipeline entry with `node_state: "blocked"` and
    a `start_commit` to `sessions/.factory-status.json`; the dashboard shows
    "HUMAN REVIEW NEEDED" and pressing Enter on that row opens the review
    overlay (file-list summary + full diff drill-down, `c` to comment, `e`
    to edit, `a`/`r` to approve/reject). The decision is written atomically
    to `sessions/.factory-transcripts/<session-id>/review-decision.json`,
    which the orchestrator's `FileHumanReviewGate` (Python side) polls for.
    This is the human-in-the-loop path.
  - With `--auto`: reproduces the original fully-automated behavior
    unchanged -- detached spawn, no stdin/stdout piping, no review gate, no
    mission control dashboard, polls `sessions/.factory-status.json`
    (written by the orchestrator, see Plan A) once a second and renders it
    via a widget.
- `/factory-run [--auto] [task-id]` — runs the exact same pipeline `/factory`
  does, targeting one specific task (`status: todo` only) instead of
  whichever the orchestrator would pick next: with no task id, lists todo
  tasks via `factory.orchestrator list --json` and shows an interactive
  picker; with a task id, skips straight to
  `uv run python -m factory.orchestrator run --provider <provider> --model
  <id> --task <task-id>`. Like `/factory`, `--auto` picks the detached,
  dashboard-less `launchAndWatch` path and its absence spawns the
  orchestrator and opens the in-session mission control dashboard.
- `/factory-watch` — reopens the in-session mission control dashboard against
  whatever `sessions/.factory-status.json` currently holds, without spawning
  a new orchestrator run. Notifies "no factory run to watch" if that file
  doesn't exist yet. This is how you get back into mission control (and
  service a pending human review) after closing it with `q`.
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
- `/clear` — wipes the conversation and drops into a fresh, empty context,
  matching Claude Code's `/clear` (no confirmation). Implemented via Pi's
  `ctx.newSession()`; the previous session file stays saved on disk.

## Mission control

`/factory` and `/factory-run` (without `--auto`), and `/factory-watch`, open
mission control **in-session** via `ctx.ui.custom` -- a modal overlay driven
by `MissionControlDashboard`, not a second terminal window. It polls the same
`sessions/.factory-status.json` the running orchestrator writes and re-renders
live while open. It shows all 5 pipeline stages (context-gather, dev,
validation, review, human-review) with the currently-running one highlighted,
handoff messages as each stage completes, and a `blocked -- waiting for you
to review the diff` state if the run reaches human-review.

Selecting a row and pressing Enter dispatches an action, handled by an
action-dispatch loop (`runMissionControl` in `index.ts`) around the overlay:
- agent rows (context-gather, dev, review) open a read-only, scrollable
  transcript view of that session (`SessionTranscriptView`); `o` pops the
  same session out into a real `pi --session <id>` window, `q` closes back to
  the dashboard.
- validation opens that run's `sim-gate.log` in a scrollable markdown view.
- human-review (once a `start_commit` exists and the node is blocked) runs
  the review overlay in place (`runReviewLoop`) -- review is Enter-driven
  only, never auto-opened.
- `q` on the dashboard itself closes mission control back to the chat; the
  status widget keeps updating in the background (via
  `startBackgroundWidgetPoll`) and flags "human review needed" until you
  run `/factory-watch` to reopen it.

### Unblocking a stuck developer

When the developer node exhausts its retries with unit tests still red, mission
control shows `⚠ DEV STUCK` and the widget shows `⚠ dev stuck — /factory-watch
to pair`. To unblock:

1. Open `/factory-watch`, select the **developer** row, and press **Enter**.
   A new terminal window opens in the exact dev `pi` session that got stuck.
2. Pair with the agent until unit tests pass; let it finish (committing its
   work is natural but not required).
3. Close the window and re-run the task (`/factory-run <task>`). The factory
   detects the work is done (`already_done` routing), skips the dev node, and
   runs validation → review → done.

If the work isn't actually finished on re-run, the context-gatherer won't mark
it done, the dev node runs again, and it may escalate again — pair and re-run
as needed. The factory run is never held open waiting on you.

## No new IPC

This reads the status/lock files Plan A's orchestrator already writes
(`sessions/.factory-status.json`, `sessions/.factory-run.lock`) and writes
the human-review decision back to
`sessions/.factory-transcripts/<session-id>/review-decision.json`, which the
orchestrator polls for — plain files, no sockets, no named pipes.

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
