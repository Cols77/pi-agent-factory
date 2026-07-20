# Design: Interactive Planning and Targeted Execution for the Dev Factory

**Date:** 2026-07-20
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)

---

## 1. Context & Framing

The dev factory (Plans 1-4, all complete and merged/on `build/factory-watch-ext`)
already has `pi-ext/factory-watch/` (`/factory`, `/factory-stop`, `/factory-tasks`)
for launching and watching the deterministic Python orchestrator
(`src/factory/orchestrator/`) from inside an interactive `pi` session, and 8
vendored skills under `.pi/skills/` backing the orchestrator's sub-agent roles
(`ROLE_SKILLS` in `roles.py`).

Two gaps remain, both against the original design
(`docs/superpowers/specs/2026-07-16-deterministic-agent-dev-factory-design.md`):

1. **Plan-time has no command surface.** §3/§6 of that design deliberately keep
   brainstorm → spec → plan **human-in-the-loop**, using the existing
   **superpowers** `brainstorming`/`writing-plans` skills — but today those
   skills aren't vendored at all, and there's no way to enter that workflow
   from inside a `pi` session the way `/factory` enters build-time.
2. **`/factory` can only run "whatever's next."** `run_next` always picks
   `next_todo(tasks)` — there's no way to say "run *this* task."

Separately, verification work on the existing 8 skills
(commit `bb77fb3` and the follow-up live check) surfaced that pi's own
`<available_skills>` mechanism is a **soft** path: skills are advertised by
name/location, and it's up to the model's own judgment whether to fetch the
content via a `read` tool call. That happened to work in a manual test, but
it's not a guarantee, and it's exactly what this repo's own Core Principle 4
already rules out for agent skill loading: *"Skills are loaded by role, not
chosen by the model... fixed skill manifest injected at spawn."* This spec
fixes that gap everywhere it currently exists, not just for the new work.

### 1.1 Goals

- `/plan <topic>` — an interactive, human-in-the-loop planning session inside
  `pi`, using the real `brainstorming`/`writing-plans` skills, ending with
  `tasks/T-*.md` files the factory can pick up (no manual authoring step).
- `/factory-run [task-id]` — run the orchestrator against one specific task,
  picked either by inline id or an interactive picker, instead of always
  "whatever's next."
- **Deterministic ("hard") skill loading everywhere**, replacing the
  advertise-and-hope-the-model-reads-it pattern: both the new `/plan` command
  and the existing sub-agent roles (`Context-Gatherer`/`Dev`/`Validation`/
  `Review`/`Session-Writer`) get full skill content injected into their
  prompt/message by our own code, not left to model discretion.

### 1.2 Non-Goals

- **Not rebuilding plan-time as a factory node.** `/plan` is a live dialogue
  with a human (you), the same shape as this conversation, not an autonomous
  sub-agent — matching the original design's explicit human-in-the-loop
  intent for plan-time. There is no `/plan-auto`.
- **Not a task queue.** `/factory-run` targets exactly one task per
  invocation, same single-lock/single-status-file model `/factory` already
  uses. Running several tasks unattended in sequence is a separate,
  later concern if it's ever needed.
- **Not relaxing the ledger's `todo`-only precondition.** `/factory-run`
  can only target a task whose `status` is `todo` — same precondition
  `next_todo` already enforces for `/factory`. Re-running a `rejected`/
  `escalated`/`done` task by id is out of scope here.
- **Not a robust general Markdown parser.** `scripts/plan_to_tasks.py` (§3.3)
  parses exactly the `writing-plans` skill's own standard task-section
  format. Plans that don't follow that shape aren't a supported input.

---

## 2. Architecture Overview

```
YOUR PI SESSION (interactive, factory-watch extension)
======================================================

 1. You type:
    /plan add battery-aware RTB logic
        |
        v
    factory-watch reads .pi/skills/{brainstorming,writing-plans}/SKILL.md
    (via pi's real loadSkills()+stripFrontmatter -- the "hard-load" pattern,
    see Diagram B)
    builds one seed message = [skill blocks] + [instructions] + [topic]
    injects it into a FRESH session, which triggers a real model turn
        |
        v
    +-------------------------------------------------+
    |   YOU + MODEL TALK (brainstorming -> writing-    |
    |   plans), exactly like this conversation          |
    +-------------------------------------------------+
        |
        v
    writing-plans saves:
      docs/superpowers/specs/2026-07-20-<name>-design.md
      docs/superpowers/plans/2026-07-20-<name>.md
        |
        v
    seed prompt's override kicks in instead of writing-plans' normal
    "execute now?" handoff:
      uv run python scripts/plan_to_tasks.py <plan-file>
        |
        v
    tasks/T-004.md, tasks/T-005.md, ...   (status: todo, deterministically
                                            parsed from the plan's
                                            ### Task N: sections)

 2. You type:
    /factory-tasks                    (existing, unchanged)
        |
        v
    widget shows the board, now including T-004/T-005

 3. You type:
    /factory-run                      (new -- no id given)
        |
        v
    factory-watch runs `orchestrator list --json`, filters status=="todo",
    shows ctx.ui.select() picker; you pick T-004
        |
        v
    spawns, detached:
      uv run python -m factory.orchestrator run
        --provider <session's active provider> --model <session's active model>
        --task T-004
    same spawn+poll+widget mechanics /factory already has
        |
        v
    +---------------------------------------------------------+
    | ORCHESTRATOR (headless, background process)              |
    |  ledger.get_task(tasks, "T-004")  --- not found/not-todo |
    |       |                            --> error status,     |
    |       v  found + todo               shown in widget      |
    |  run_task(...) same pipeline as always:                  |
    |   Context-Gatherer -> Dev -> Validation -> Review          |
    |   each: fresh `pi -p` sub-agent, prompt built by           |
    |   compose_prompt() -- see Diagram B for its skill loading  |
    +---------------------------------------------------------+
        |
        v
    tasks/T-004.md status -> done (or rejected/escalated)
    sessions/<id>.session.json written
```

**Diagram B — the "hard skill loading" pattern, two implementations of one idea:**

```
Same principle both places: never advertise-and-hope; always read the
skill file yourself and inject its full content into the prompt.

+-----------------------------------+   +------------------------------------+
| TS SIDE -- pi-ext/factory-watch/  |   | PYTHON SIDE -- orchestrator/        |
| used by: /plan                    |   | used by: every sub-agent node       |
|                                    |   | (Context-Gatherer, Dev, ...)        |
|                                    |   |                                      |
| loadSkills({cwd: ctx.cwd, ...})   |   | python-frontmatter.load(path)       |
|   (pi's own exported resolver)    |   |   (already a dependency, already    |
| readFileSync(skill.filePath)      |   |    used in ledger.py)               |
| stripFrontmatter(content)         |   | .content  (body, frontmatter        |
|   (pi's own exported helper)      |   |  already stripped)                  |
|                                    |   |                                      |
|          v                        |   |          v                            |
| <skill name="brainstorming"       |   | <skill name="test-driven-           |
|   location="...">                 |   |   development" location="...">      |
|  ...full SKILL.md body...         |   |  ...full SKILL.md body...           |
| </skill>                          |   | </skill>                            |
|                                    |   |  (one block per skill in            |
|          v                        |   |   ROLE_SKILLS[role], concatenated)  |
| session.sendUserMessage(          |   |          v                            |
|   skillBlocks + instructions      |   | compose_prompt() embeds these       |
|   + topic, {deliverAs:"followUp"} |   | blocks instead of bare              |
| )  -> real model turn, guaranteed |   | "- skill-name" bullets              |
|    to have seen full content      |   |          v                            |
|                                    |   | pi_backend._build_command(prompt)   |
|                                    |   | -> `pi -p "<full prompt>"`          |
|                                    |   |   subprocess, guaranteed to have    |
|                                    |   |   seen full content too             |
+-----------------------------------+   +------------------------------------+

Both: skill's SKILL.md gets `disable-model-invocation: true` -- hidden from
pi's own <available_skills> soft-advertise list, reachable only through the
code paths above.
```

---

## 3. Components

### 3.1 Vendored skills: `brainstorming`, `writing-plans`

Vendored under `.pi/skills/brainstorming/SKILL.md` and
`.pi/skills/writing-plans/SKILL.md`, from the local superpowers plugin
install, adapted the same way the existing 8 were: content kept faithful,
Claude-Code-specific mechanics dropped where there's no `pi` equivalent —
concretely, `brainstorming`'s "Visual Companion" section (a browser-based
mockup tool with no analog here) is removed rather than adapted, and any
reference to dispatching a separate Task/Agent-tool subagent is reworded to
describe the single-session dialogue `/plan` actually runs.

**All 10 vendored skills** (the existing 8 + these 2) get
`disable-model-invocation: true` added to their frontmatter. Every one of
them is now loaded by our own code (§3.2, §3.4) — none of them need to be
reachable via the soft `<available_skills>` path.

### 3.2 `/plan` command (`pi-ext/factory-watch/`)

`pi.registerCommand("plan", { handler: async (topic, ctx) => {...} })`.
If `topic` is empty, `ctx.ui.notify("usage: /plan <topic>", "error")` and
return — inline topic is required (per design decision; there is no
"prime and chat" mode).

**Seed-prompt construction** (pure function `buildPlanSeedPrompt(topic,
skillBlocks: string[]): string`, unit-tested with fixture skill-block
strings so it never needs a real filesystem or pi runtime in tests):

1. Resolve `brainstorming` and `writing-plans` via pi's real
   `loadSkills({ cwd: ctx.cwd, agentDir: path.join(os.homedir(), ".pi",
   "agent"), skillPaths: [], includeDefaults: true })` (exported from
   `@earendil-works/pi-coding-agent`).
2. For each, `readFileSync(skill.filePath, "utf-8")`, `stripFrontmatter(...)`
   (also exported from the package), wrap as
   `` <skill name="${skill.name}" location="${skill.filePath}">\nReferences are relative to ${skill.baseDir}.\n\n${body}\n</skill> `` —
   byte-identical in shape to what pi's own native `/skill:name` expansion
   produces.
3. Concatenate both blocks, then append fixed orchestration instructions:
   - You're in plan-time for this repo's dev factory. Use the loaded
     `brainstorming` skill on the topic below.
   - When brainstorming reaches its handoff to `writing-plans`, proceed into
     `writing-plans` as usual; save the plan under `docs/superpowers/plans/`.
   - Override `writing-plans`' own "Execution Handoff" step: once the plan is
     saved, do **not** offer subagent-driven or inline execution. Instead
     run `uv run python scripts/plan_to_tasks.py <plan-file>` and report the
     task ids it created. Actual execution happens later via `/factory-run`.
   - Topic: `<topic>`
4. `ctx.newSession({ withSession: async (session) => { await
   session.sendUserMessage(seedText, { deliverAs: "followUp" }); } })` — a
   **fresh** session (not a fork of the current one), so the dialogue starts
   clean rather than inheriting whatever was in the session before `/plan`
   was typed.

### 3.3 `scripts/plan_to_tasks.py` — plan.md -> ledger parser

CLI: `uv run python scripts/plan_to_tasks.py <plan-file> [--repo .]`.

Parses each `### Task N: [Component Name]` section (writing-plans' standard
format — confirmed against both the skill's own template and this repo's
existing plans under `docs/superpowers/plans/`) into one `tasks/T-*.md`:

| Ledger field | Derived from |
|---|---|
| `id` | Next unused `T-NNN` (3-digit, zero-padded), scanned across every existing `tasks/*.md`'s `id` frontmatter field — never just the current plan's own numbering — so ids never collide across multiple `/plan` runs. |
| filename | `tasks/T-{NNN}-{slug of Component Name}.md`, matching the existing `T-001-example.md` convention. |
| `title` | The task header's `[Component Name]`, verbatim. |
| `status` | Always `todo`. |
| `dod` | Each line under that task's `**Interfaces:** Produces:` bullet (one dod list item per such line), plus one fixed trailing item: `"All steps in this task complete; tests/gates pass; committed"`. If no `Produces:` line is found, just the fixed item. |
| `body` | The task's `**Files:**` block, reproduced verbatim, followed by a blank line and `Full steps: docs/superpowers/plans/<plan-file-basename>.md, Task N.` — the actual code/commands stay in the plan file, not duplicated (the Dev sub-agent's context manifest already loads the plan as context, per the existing `context_manifest` schema in the 2026-07-16 design, §7). |
| extra frontmatter | `source_plan: docs/superpowers/plans/<basename>.md`, `source_task: N` (integer) — used only for idempotency (below), ignored by `ledger.py`'s parser like any other unrecognized frontmatter key. |

**Idempotency:** before creating a task, the script checks whether any
existing `tasks/*.md` already has that exact `(source_plan, source_task)`
pair, and skips creating a duplicate if so. Re-running the parser on a plan
you already parsed is a safe no-op.

**Failure mode:** a plan with zero `### Task N:` sections found -> exit code
1, message to stderr, no files written (no partial output).

### 3.4 Sub-agent skill hard-loading (`src/factory/orchestrator/`)

New `factory/orchestrator/skills.py`:

```python
def load_skill_block(skills_dir: Path, name: str) -> str:
    """Read .pi/skills/<name>/SKILL.md, strip frontmatter, wrap in the same
    <skill> block shape pi's own native /skill:name expansion produces.
    Raises FileNotFoundError if the skill directory/file doesn't exist --
    a role naming a skill that isn't vendored is a hard configuration
    error, not something to silently degrade past."""
```
implemented with `python-frontmatter` (already a dependency, already used
identically in `ledger.py`): `post = frontmatter.load(path); body =
post.content`.

`prompts.py`'s `compose_prompt` replaces:
```python
lines.append("## Loaded skills")
for skill in ROLE_SKILLS[role]:
    lines.append(f"- {skill}")
```
with a call to `load_skill_block(skills_dir, skill)` per skill in
`ROLE_SKILLS[role]`, inlining the full blocks in place of the bare bullet
list. `compose_prompt` gains a `skills_dir: Path` parameter (its callers in
`nodes.py` already have `repo_root` in scope to compute `repo_root /
".pi" / "skills"`).

**Known impact:** existing tests in `tests/unit/orchestrator/` that assert
`compose_prompt`'s exact bare-bullet output need updating to expect the new
`<skill>` blocks instead — an expected consequence of this change, not a
regression to work around.

### 3.5 Orchestrator: targeted `run --task` / `list --json`

`ledger.py` additions:
```python
def get_task(tasks: list[Task], task_id: str) -> Task | None:
    return next((t for t in tasks if t.id == task_id), None)

class TaskNotFoundError(RuntimeError):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"task not found: {task_id}")
        self.task_id = task_id

class TaskNotTodoError(RuntimeError):
    def __init__(self, task_id: str, status: str) -> None:
        super().__init__(f"task {task_id} is not todo (status: {status})")
        self.task_id = task_id
        self.status = status
```
(mirrors `lock.py`'s existing `AlreadyRunningError` shape.)

`runner.py`'s `run_next` gains `task_id: str | None = None`. When given: look
up via `get_task`; raise `TaskNotFoundError`/`TaskNotTodoError` if missing or
not `status == "todo"` (both are already caught for free by `__main__.py`'s
existing `except Exception as exc: status.report(node_state="error", ...);
raise` block around `run_next` — no new error-plumbing needed there).

`__main__.py`:
- `run` subcommand gains `--task <id>`, passed through to `run_next`.
- `list` subcommand gains `--json`: prints
  `json.dumps([{"id": t.id, "title": t.title, "status": t.status} for t in
  load_tasks(...)])` instead of the human-readable board. The existing
  plain-text `list` output (used by `/factory-tasks`'s widget) is unchanged.

### 3.6 `/factory-run` command (`pi-ext/factory-watch/`)

- `buildRunCommand(provider, modelId, taskId?)` — extends the existing pure
  function with an optional third argument, appending `["--task", taskId]`
  when given. Existing 2-argument call sites/tests keep passing unchanged.
- `buildListJsonCommand(): Command` — new pure function, mirrors
  `buildListCommand` but adds `--json`.
- `formatTaskOption(task: {id, title}): string` -> `` `${id}  ${title}` `` and
  `parseTaskIdFromOption(option: string): string` -> the first
  whitespace-delimited token — pure, unit-tested, so id-recovery from a
  picker string isn't buried untested in the handler.
- `pi.registerCommand("factory-run", { handler: async (args, ctx) => {...}
  } })`:
  - If `args.trim()` is non-empty, use it directly as the task id.
  - Otherwise: `spawnSync` `list --json`, `JSON.parse` the output, filter to
    `status === "todo"`. If empty, `ctx.ui.notify("no todo tasks", "info")`
    and stop (no spawn) — a small UX improvement over `/factory`'s today,
    which spawns unconditionally and relies on the orchestrator's own
    fast-exit. If non-empty, `ctx.ui.select("Run which task?",
    tasks.map(formatTaskOption))`; if the user cancels (`undefined`
    returned), stop with no action.
  - Reuses `/factory`'s existing "already running" lock-check and its
    spawn+poll+widget mechanics — pulled into small shared internal helpers
    used by both commands rather than duplicated a second time (DRY within
    the file this work is already touching). Exact internal file
    organization (more functions in `index.ts` vs. splitting into e.g.
    `run-command.ts`/`task-picker.ts`) is a plan-level decision, not a
    spec-level one.

---

## 4. Error Handling

- **Bad task id to `/factory-run <id>`** (typo, wrong status): surfaces the
  same way any other orchestrator crash already does — `TaskNotFoundError`/
  `TaskNotTodoError` gets caught by `__main__.py`'s existing top-level
  handler, written to the status file as `node_state: "error"`, and shown in
  the widget `/factory-run` is already polling. No new TS-side error path
  needed.
- **`plan_to_tasks.py` run twice on the same plan:** idempotent no-op (§3.3).
- **`plan_to_tasks.py` given a plan with no `### Task N:` sections:** hard
  failure, exit 1, nothing written (§3.3).
- **`/plan` called with no topic:** rejected immediately by the command
  handler before any session/turn is created.
- **A `ROLE_SKILLS` entry names a skill that isn't vendored:**
  `load_skill_block` raises `FileNotFoundError`, surfacing as a hard crash
  of that sub-agent node (caught by the same top-level orchestrator handler
  as any other node exception) rather than silently falling back to a bare
  skill name.
- **`/factory-run` picker with zero todo tasks:** notify, no spawn (§3.6).
- **`/factory-run` picker cancelled:** no-op, no notify needed.

---

## 5. Deliberately Out of Scope for v1

- **No queue/batch execution** (confirmed non-goal, §1.2).
- **No re-running non-todo tasks by id** (confirmed non-goal, §1.2).
- **No general Markdown plan parser** — `plan_to_tasks.py` only understands
  `writing-plans`' own standard task-section shape.
- **No fork-based `/plan`** (preserving prior session context) — always a
  fresh session; can revisit later if it turns out users want to carry
  context in.
- **No changes to `/factory`'s zero-arg behavior** — it keeps running
  "whatever's next" unconditionally, unchanged; the new "no todo tasks ->
  notify without spawning" UX improvement is specific to `/factory-run`'s
  picker path, not retrofitted onto `/factory`.

---

## 6. Testing Strategy

- **`plan_to_tasks.py`**: pure parsing function (fixture plan.md strings in,
  expected `Task`-shaped records out) tested in isolation from file I/O; a
  thin CLI wrapper tested separately for the write-files/idempotency/
  failure-exit-code behavior, following this repo's existing
  Protocol+Fake/pure-function-plus-thin-wiring pattern used throughout
  `src/factory/orchestrator/`.
- **`load_skill_block`**: unit tests with fixture `SKILL.md` files (valid
  frontmatter+body, and a missing-file case asserting `FileNotFoundError`).
- **`compose_prompt`**: existing tests updated to assert the new `<skill>`
  block shape; add a case per role confirming all of that role's
  `ROLE_SKILLS` appear.
- **`get_task`/`TaskNotFoundError`/`TaskNotTodoError`/`run_next(task_id=...)`**:
  direct unit tests (found+todo, found+wrong-status, not-found), same style
  as the existing `next_todo`/`run_next` tests.
- **TypeScript**: `buildPlanSeedPrompt`, `buildRunCommand` (3-arg form),
  `buildListJsonCommand`, `formatTaskOption`/`parseTaskIdFromOption` — pure
  functions, vitest-covered, following `scope-guard`/`factory-watch`'s
  existing precedent exactly. `/plan` and `/factory-run`'s thin wiring
  (`ctx.newSession`, `ctx.ui.select`, `spawn`/`spawnSync`) stays thin and
  isn't the primary test surface.
- **Required manual verification** (same category as Plan 4's Task 6): a
  real `/plan <topic>` run watched end-to-end (does the seed message
  actually contain full skill content, does the model follow brainstorming
  -> writing-plans -> the over­ridden handoff correctly), and a real
  `/factory-run` picker run confirming task-targeting actually constrains
  which task executes. Cannot be fully proven by unit tests alone.

---

## 7. Cross-Plan Dependencies

Consumes, unchanged: `pi-ext/factory-watch/`'s existing spawn+poll+widget
mechanics and lock/status file contracts (Plan 4), the orchestrator's
existing `run_next`/node-executor pipeline (Plan 3), and the
`context_manifest` schema's existing `"plan"` context field (2026-07-16
design, §7), which is how `tasks/T-*.md` files generated here already flow
into a Dev sub-agent's loaded context without any schema change.

If `writing-plans`' own task-section format ever changes shape upstream (a
new superpowers release), `plan_to_tasks.py`'s parser (§3.3) needs updating
to match — nothing here enforces that at compile time, matching this
repo's existing acknowledged limitation for the KB/session schemas (see the
2026-07-16 design's own cross-dependency note on Plan A's status/lock file
shapes).
