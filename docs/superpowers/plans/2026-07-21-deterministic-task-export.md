# Deterministic Task Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make task export from plans deterministic (code-driven, not model-driven) after `/plan` sessions end, add an interactive mark-done loop, and fix the fenced-code-block false-match bug in `plan_to_tasks.py`.

**Architecture:** The `/plan` handler records a timestamp before the session, then after the session resolves it scans for new plan files and runs `plan_to_tasks` via `spawnSync`. A mark-done picker loop lets the user mark already-implemented tasks as done. A new `set-status` CLI subcommand exposes `ledger.set_status()`. On the Python side, `parse_plan_tasks` strips fenced code blocks before regex matching.

**Tech Stack:** Python 3 (`python-frontmatter`, `argparse`), TypeScript/vitest (`node:child_process`, `node:fs`), no new dependencies.

## Global Constraints

- Every task ends green (`uv run pytest -m unit -q`, `npm --prefix pi-ext/factory-watch run typecheck`, `npm --prefix pi-ext/factory-watch test`, as applicable to what the task touched) and is committed.
- Python: `from __future__ import annotations` at the top of every new/modified module, matching every existing file in `src/factory/orchestrator/`.
- TypeScript: strict mode, NodeNext, matching `pi-ext/factory-watch/tsconfig.json` (unchanged).
- No changes to `pi-ext/scope-guard/`.

Full design: `docs/superpowers/specs/2026-07-21-deterministic-task-export-design.md`.

---

## File Structure

```
src/factory/orchestrator/
  plan_to_tasks.py        # modified: strip fenced code blocks before regex
  __main__.py             # modified: add set-status subcommand

tests/unit/
  test_plan_to_tasks.py   # modified: add code-fence stripping tests

tests/unit/orchestrator/
  test_main.py            # modified: add set-status tests

pi-ext/factory-watch/src/
  process-control.ts      # modified: add buildPlanToTasksCommand, buildSetStatusCommand
  skill-prompt.ts         # modified: update seed prompt (drop soft instruction)
  index.ts                # modified: /plan handler gains post-session export + mark-done loop

pi-ext/factory-watch/test/
  process-control.test.ts   # modified: add tests for new command builders
  skill-prompt.test.ts      # modified: verify new prompt text
  handler.test.ts           # modified: add post-session export + mark-done tests
```

---

### Task 1: Strip fenced code blocks in `plan_to_tasks.py`

**Files:**
- Modify: `src/factory/orchestrator/plan_to_tasks.py`
- Test: `tests/unit/test_plan_to_tasks.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `parse_plan_tasks` now ignores `### Task N:` inside fenced code blocks. Signature and return type unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_plan_to_tasks.py`:

```python
PLAN_TASK_INSIDE_CODE_BLOCK = """\
# Some Plan

```python
### Task 1: Fake Task In Code Block

**Files:**
- Create: `src/fake.py`

**Interfaces:**
- Produces: `fake_func() -> None`.
```

### Task 1: Real Task Outside Code Block

**Files:**
- Create: `src/real.py`

**Interfaces:**
- Produces: `real_func() -> None`.
"""

PLAN_TASK_INSIDE_TILDE_BLOCK = """\
~~~python
### Task 1: Fake Task In Tilde Block

**Files:**
- Create: `src/fake.py`
~~~

### Task 1: Real Task Outside Tilde Block

**Files:**
- Create: `src/real.py`

**Interfaces:**
- Produces: `real_func() -> None`.
"""


def test_task_inside_backtick_code_block_is_ignored():
    tasks = parse_plan_tasks(PLAN_TASK_INSIDE_CODE_BLOCK)
    assert len(tasks) == 1
    assert tasks[0].title == "Real Task Outside Code Block"


def test_task_inside_tilde_code_block_is_ignored():
    tasks = parse_plan_tasks(PLAN_TASK_INSIDE_TILDE_BLOCK)
    assert len(tasks) == 1
    assert tasks[0].title == "Real Task Outside Tilde Block"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_plan_to_tasks.py -v`
Expected: FAIL -- `PLAN_TASK_INSIDE_CODE_BLOCK` is not defined (or the test finds 2 tasks instead of 1 if the fixtures are added but the parser isn't fixed yet).

- [ ] **Step 3: Implement fenced-code-block stripping**

In `src/factory/orchestrator/plan_to_tasks.py`, add the regex and update `parse_plan_tasks`:

Add after the existing `_PRODUCES_LINE` line:

```python
_CODE_FENCE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~", re.MULTILINE)
```

Replace the body of `parse_plan_tasks`:

```python
def parse_plan_tasks(text: str) -> list[ParsedPlanTask]:
    """Parse every `### Task N: Title` section out of a writing-plans-format
    plan document. Pure: no file I/O, no side effects. Returns an empty list
    if no task sections are found -- callers decide whether that's an error.
    Fenced code blocks (``` or ~~~) are stripped before matching so that
    ### Task N: headers inside code examples (e.g., test fixtures) are
    not treated as real task sections.
    """
    stripped = _CODE_FENCE.sub("", text)
    headers = list(_TASK_HEADER.finditer(stripped))
    tasks: list[ParsedPlanTask] = []
    for i, m in enumerate(headers):
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(stripped)
        chunk = stripped[start:end]

        files_match = _FILES_BLOCK.search(chunk)
        files_block = files_match.group(1).strip() if files_match else ""
        produces = [p.strip() for p in _PRODUCES_LINE.findall(chunk)]

        tasks.append(
            ParsedPlanTask(
                number=int(m.group(1)),
                title=m.group(2).strip(),
                files_block=files_block,
                produces=produces,
            )
        )
    return tasks
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/test_plan_to_tasks.py -v`
Expected: all pass (9 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/plan_to_tasks.py tests/unit/test_plan_to_tasks.py
git commit -m "fix: strip fenced code blocks before parsing task sections in plan_to_tasks"
```

---

### Task 2: `set-status` CLI subcommand in `__main__.py`

**Files:**
- Modify: `src/factory/orchestrator/__main__.py`
- Test: `tests/unit/orchestrator/test_main.py`

**Interfaces:**
- Consumes: `ledger.set_status()`, `ledger.load_tasks()`, `ledger.get_task()`, `ledger.TaskNotFoundError`.
- Produces: `factory.orchestrator set-status <task-id> <status>` CLI subcommand.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/orchestrator/test_main.py`:

```python
def test_main_set_status_changes_task_status(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "T-001-a.md").write_text(
        "---\nid: T-001\ntitle: Example task\nstatus: todo\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["factory.orchestrator", "set-status", "T-001", "done", "--repo", str(tmp_path)])
    main()

    updated = frontmatter.load(str(tasks_dir / "T-001-a.md"))
    assert updated["status"] == "done"


def test_main_set_status_not_found_exits_1(tmp_path, monkeypatch, capsys):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    monkeypatch.setattr(sys, "argv", ["factory.orchestrator", "set-status", "T-999", "done", "--repo", str(tmp_path)])
    with pytest.raises(SystemExit):
        main()

    assert "T-999" in capsys.readouterr().err
```

Add the import `import frontmatter` at the top of `tests/unit/orchestrator/test_main.py` if not already present.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_main.py -v`
Expected: FAIL -- `invalid choice: 'set-status'`.

- [ ] **Step 3: Implement `set-status` subcommand**

In `src/factory/orchestrator/__main__.py`, update the argparse section and add the handler.

Replace:

```python
    parser.add_argument("command", choices=["run", "list"])
```

with:

```python
    parser.add_argument("command", choices=["run", "list", "set-status"])
```

After the `if args.command == "list":` block (the `return` at its end), add before the `run` logic:

```python
    if args.command == "set-status":
        from factory.orchestrator.ledger import TaskNotFoundError, get_task, load_tasks, set_status

        tasks = load_tasks(repo_root / "tasks")
        task = get_task(tasks, args.task_id)
        if task is None:
            print(f"error: task not found: {args.task_id}", file=sys.stderr)
            raise SystemExit(1)
        set_status(task, args.new_status)
        return
```

Add `import sys` at the top if not already present (it is already imported via `argparse` usage but needs to be explicit).

Add the two new positional arguments to the parser, right after the `--json` argument line. However, since argparse positional args apply to all subcommands and `set-status` needs `task_id` and `new_status`, use subparsers or add them as optional with `nargs` conditionally. Simplest approach matching existing style: add them as optional args and validate in the handler.

Add after the `--json` line:

```python
    parser.add_argument("--task-id", default=None, help="Task id for set-status command")
    parser.add_argument("--new-status", default=None, help="New status for set-status command")
```

Then update the handler to use `args.task_id` and `args.new_status`:

```python
    if args.command == "set-status":
        from factory.orchestrator.ledger import TaskNotFoundError, get_task, load_tasks, set_status

        if args.task_id is None or args.new_status is None:
            print("usage: factory.orchestrator set-status --task-id <id> --new-status <status>", file=sys.stderr)
            raise SystemExit(1)
        tasks = load_tasks(repo_root / "tasks")
        task = get_task(tasks, args.task_id)
        if task is None:
            print(f"error: task not found: {args.task_id}", file=sys.stderr)
            raise SystemExit(1)
        set_status(task, args.new_status)
        return
```

Update the test to use the `--task-id`/`--new-status` flag style:

```python
def test_main_set_status_changes_task_status(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "T-001-a.md").write_text(
        "---\nid: T-001\ntitle: Example task\nstatus: todo\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["factory.orchestrator", "set-status", "--task-id", "T-001", "--new-status", "done", "--repo", str(tmp_path)])
    main()

    updated = frontmatter.load(str(tasks_dir / "T-001-a.md"))
    assert updated["status"] == "done"


def test_main_set_status_not_found_exits_1(tmp_path, monkeypatch, capsys):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    monkeypatch.setattr(sys, "argv", ["factory.orchestrator", "set-status", "--task-id", "T-999", "--new-status", "done", "--repo", str(tmp_path)])
    with pytest.raises(SystemExit):
        main()

    assert "T-999" in capsys.readouterr().err
```

- [ ] **Step 4: Run to pass**

Run: `uv run pytest tests/unit/orchestrator/test_main.py -v`
Expected: all pass (4 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/__main__.py tests/unit/orchestrator/test_main.py
git commit -m "feat: set-status CLI subcommand for changing task status"
```

---

### Task 3: New command builders in `process-control.ts`

**Files:**
- Modify: `pi-ext/factory-watch/src/process-control.ts`
- Test: `pi-ext/factory-watch/test/process-control.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `buildPlanToTasksCommand(planFile: string, cwd: string): Command`; `buildSetStatusCommand(taskId: string, status: string, cwd: string): Command`.

- [ ] **Step 1: Write the failing tests**

Add to `pi-ext/factory-watch/test/process-control.test.ts`:

```typescript
import { buildPlanToTasksCommand, buildSetStatusCommand } from "../src/process-control.js";

describe("buildPlanToTasksCommand", () => {
  test("builds the plan_to_tasks invocation with the given plan file and repo", () => {
    const cmd = buildPlanToTasksCommand("docs/superpowers/plans/my-plan.md", "/repo");
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual([
      "run", "python", "-m", "factory.orchestrator.plan_to_tasks",
      "docs/superpowers/plans/my-plan.md",
      "--repo", "/repo",
    ]);
  });
});

describe("buildSetStatusCommand", () => {
  test("builds the set-status invocation with task id, status, and repo", () => {
    const cmd = buildSetStatusCommand("T-001", "done", "/repo");
    expect(cmd.bin).toBe("uv");
    expect(cmd.args).toEqual([
      "run", "python", "-m", "factory.orchestrator", "set-status",
      "--task-id", "T-001",
      "--new-status", "done",
      "--repo", "/repo",
    ]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix pi-ext/factory-watch test -- --run 2>&1`
Expected: FAIL -- `buildPlanToTasksCommand` is not exported.

- [ ] **Step 3: Implement**

Add to `pi-ext/factory-watch/src/process-control.ts`:

```typescript
export function buildPlanToTasksCommand(planFile: string, cwd: string): Command {
  return {
    bin: "uv",
    args: ["run", "python", "-m", "factory.orchestrator.plan_to_tasks", planFile, "--repo", cwd],
  };
}

export function buildSetStatusCommand(taskId: string, status: string, cwd: string): Command {
  return {
    bin: "uv",
    args: [
      "run", "python", "-m", "factory.orchestrator", "set-status",
      "--task-id", taskId,
      "--new-status", status,
      "--repo", cwd,
    ],
  };
}
```

- [ ] **Step 4: Run to pass**

Run: `npm --prefix pi-ext/factory-watch test -- --run 2>&1`
Expected: all pass.

- [ ] **Step 5: Run typecheck**

Run: `npm --prefix pi-ext/factory-watch run typecheck 2>&1`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/process-control.ts pi-ext/factory-watch/test/process-control.test.ts
git commit -m "feat: buildPlanToTasksCommand and buildSetStatusCommand in process-control"
```

---

### Task 4: Update seed prompt — drop soft `plan_to_tasks` instruction

**Files:**
- Modify: `pi-ext/factory-watch/src/skill-prompt.ts`
- Test: `pi-ext/factory-watch/test/skill-prompt.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: updated `buildPlanSeedPrompt` with deterministic-export instruction instead of soft "run plan_to_tasks" instruction.

- [ ] **Step 1: Write the failing test**

In `pi-ext/factory-watch/test/skill-prompt.test.ts`, update the existing test to verify the new text and absence of the old text:

Replace:

```typescript
  test("includes every skill block, the plan_to_tasks override instructions, and the topic", () => {
    const prompt = buildPlanSeedPrompt("add battery-aware RTB", ["<skill1/>", "<skill2/>"]);
    expect(prompt).toContain("<skill1/>");
    expect(prompt).toContain("<skill2/>");
    expect(prompt).toContain("factory.orchestrator.plan_to_tasks");
    expect(prompt).toContain("Topic: add battery-aware RTB");
  });
```

with:

```typescript
  test("includes every skill block, the deterministic-export instruction, and the topic", () => {
    const prompt = buildPlanSeedPrompt("add battery-aware RTB", ["<skill1/>", "<skill2/>"]);
    expect(prompt).toContain("<skill1/>");
    expect(prompt).toContain("<skill2/>");
    expect(prompt).toContain("exported automatically");
    expect(prompt).not.toContain("factory.orchestrator.plan_to_tasks");
    expect(prompt).toContain("Topic: add battery-aware RTB");
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix pi-ext/factory-watch test -- --run 2>&1`
Expected: FAIL -- prompt contains "factory.orchestrator.plan_to_tasks" and does not contain "exported automatically".

- [ ] **Step 3: Implement**

In `pi-ext/factory-watch/src/skill-prompt.ts`, replace the instructions array:

```typescript
  const instructions = [
    "You're in plan-time for this repo's dev factory. Use the loaded `brainstorming` skill on the topic below.",
    "When brainstorming reaches its handoff to `writing-plans`, proceed into `writing-plans` as usual; save the plan under `docs/superpowers/plans/`.",
    "Once the plan is saved under `docs/superpowers/plans/`, tasks are exported automatically — do not run plan_to_tasks yourself. Actual execution happens later via /factory-run.",
  ].join("\n\n");
```

- [ ] **Step 4: Run to pass**

Run: `npm --prefix pi-ext/factory-watch test -- --run 2>&1`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/skill-prompt.ts pi-ext/factory-watch/test/skill-prompt.test.ts
git commit -m "feat: replace soft plan_to_tasks instruction with deterministic-export notice"
```

---

### Task 5: Post-session auto-export + mark-done loop in `/plan` handler

**Files:**
- Modify: `pi-ext/factory-watch/src/index.ts`
- Test: `pi-ext/factory-watch/test/handler.test.ts`

**Interfaces:**
- Consumes: `buildPlanToTasksCommand`, `buildSetStatusCommand` (Task 3), `buildListCommand`, `buildListJsonCommand` (existing), `formatTaskOption`, `parseTaskIdFromOption` (existing), `readdirSync`, `statSync` (existing in doc-lister pattern).
- Produces: `/plan` handler with post-session export + mark-done picker loop.

- [ ] **Step 1: Write the failing tests**

Add to `pi-ext/factory-watch/test/handler.test.ts`. These tests mock `spawnSync` to simulate the plan_to_tasks and set-status CLI calls, and verify the widget refresh, notifications, and picker invocations.

```typescript
  test("/plan auto-exports tasks from new plan files after session ends", async () => {
    const { commands } = capture();
    const planDir = mkdtempSync(join(tmpdir(), "factory-plan-export-"));
    mkdirSync(join(planDir, "docs", "superpowers", "plans"), { recursive: true });
    mkdirSync(join(planDir, ".pi", "skills", "brainstorming"), { recursive: true });
    mkdirSync(join(planDir, ".pi", "skills", "writing-plans"), { recursive: true });
    writeFileSync(join(planDir, ".pi", "skills", "brainstorming", "SKILL.md"), "---\nname: brainstorming\n---\nbrainstorming content");
    writeFileSync(join(planDir, ".pi", "skills", "writing-plans", "SKILL.md"), "---\nname: writing-plans\n---\nwriting-plans content");

    // Simulate: plan_to_tasks outputs "created: T-001, T-002"
    // Then list --json returns the new tasks
    let spawnCallCount = 0;
    vi.mocked(spawnSync).mockImplementation((() => {
      spawnCallCount++;
      // First call: plan_to_tasks for the new plan
      if (spawnCallCount === 1) {
        return { status: 0, stdout: "created: T-001, T-002\n", stderr: "" };
      }
      // Second call: list --json to refresh widget
      if (spawnCallCount === 2) {
        return {
          status: 0,
          stdout: JSON.stringify([
            { id: "T-001", title: "First", status: "todo" },
            { id: "T-002", title: "Second", status: "todo" },
          ]),
          stderr: "",
        };
      }
      return { status: 0, stdout: "", stderr: "" };
    }) as any);

    const newSession = vi.fn(async () => ({ cancelled: false }));
    const ctx = fakeCtx({ cwd: planDir, newSession });
    await commands.get("plan")!.handler("my feature", ctx);

    expect(spawnSync).toHaveBeenCalled();
    // At least one plan_to_tasks call and one list call happened
    const calls = vi.mocked(spawnSync).mock.calls;
    const planToTasksCalls = calls.filter((c: any[]) =>
      c[1] && Array.isArray(c[1]) && c[1].some?.((a: string) => a?.includes?.("plan_to_tasks"))
    );
    expect(planToTasksCalls.length).toBeGreaterThanOrEqual(1);
  });

  test("/plan skips export when session is cancelled", async () => {
    const { commands } = capture();
    const newSession = vi.fn(async () => ({ cancelled: true }));
    const ctx = fakeCtx({ cwd: REPO_ROOT, newSession });
    await commands.get("plan")!.handler("my feature", ctx);

    // spawnSync should not have been called for plan_to_tasks after cancel
    const calls = vi.mocked(spawnSync).mock.calls;
    const planToTasksCalls = calls.filter((c: any[]) =>
      c[1] && Array.isArray(c[1]) && c[1].some?.((a: string) => a?.includes?.("plan_to_tasks"))
    );
    expect(planToTasksCalls.length).toBe(0);
  });
```

Add imports at the top of the test file:

```typescript
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix pi-ext/factory-watch test -- --run 2>&1`
Expected: FAIL -- the `/plan` handler doesn't call `spawnSync` for `plan_to_tasks` after the session.

- [ ] **Step 3: Implement the post-session export logic**

In `pi-ext/factory-watch/src/index.ts`, add imports at the top:

```typescript
import { readdirSync, readFileSync, statSync } from "node:fs";
```

Replace the existing `readFileIfExists` and the `import { openSync, readFileSync } from "node:fs"` with a unified import:

```typescript
import { openSync, readFileSync, readdirSync, statSync } from "node:fs";
```

Remove the now-duplicate `import { openSync, readFileSync } from "node:fs";` line.

Update the import from `process-control`:

```typescript
import { buildListCommand, buildListJsonCommand, buildPlanToTasksCommand, buildRunCommand, buildSetStatusCommand, buildWindowsKillArgs } from "./process-control.js";
```

Replace the `/plan` handler:

```typescript
  pi.registerCommand("plan", {
    description: "Start an interactive planning session (brainstorming -> writing-plans)",
    handler: async (args: string, ctx: ExtCommandCtx) => {
      const topic = args.trim();
      if (topic === "") {
        ctx.ui.notify("usage: /plan <topic>", "error");
        return;
      }

      const { skills } = loadSkills({
        cwd: ctx.cwd,
        agentDir: join(homedir(), ".pi", "agent"),
        skillPaths: [],
        includeDefaults: true,
      });

      const skillBlocks: string[] = [];
      for (const name of PLAN_SKILL_NAMES) {
        const skill = skills.find((s) => s.name === name);
        if (skill === undefined) {
          ctx.ui.notify(`/plan: skill not found: ${name}`, "error");
          return;
        }
        const content = readFileSync(skill.filePath, "utf-8");
        const body = stripFrontmatter(content).trim();
        skillBlocks.push(buildSkillBlock({ name: skill.name, location: skill.filePath, body }));
      }

      const seedText = buildPlanSeedPrompt(topic, skillBlocks);
      const beforeMs = Date.now();
      const { cancelled } = await ctx.newSession({
        withSession: async (session: ReplacedSessionCtx) => {
          await session.sendUserMessage(seedText, { deliverAs: "followUp" });
        },
      });

      if (cancelled) return;

      // --- Post-session deterministic export ---
      const plansDir = join(ctx.cwd, "docs", "superpowers", "plans");
      let planFiles: string[];
      try {
        planFiles = readdirSync(plansDir).filter((f) => f.endsWith(".md"));
      } catch {
        planFiles = [];
      }

      const newPlans = planFiles
        .map((f) => ({ file: f, path: join(plansDir, f), mtimeMs: statSync(join(plansDir, f)).mtimeMs }))
        .filter((p) => p.mtimeMs > beforeMs);

      if (newPlans.length === 0) {
        ctx.ui.notify("no new plan files found", "info");
        return;
      }

      const allCreatedIds: string[] = [];
      for (const plan of newPlans) {
        const cmd = buildPlanToTasksCommand(plan.path, ctx.cwd);
        const result = spawnSync(cmd.bin, cmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
        if (result.status !== 0) {
          ctx.ui.notify(`plan_to_tasks failed for ${plan.file}: ${result.stderr || "unknown error"}`, "error");
          continue;
        }
        const match = (result.stdout as string).match(/^created: (.+)$/m);
        if (match) {
          const ids = match[1]!.split(",").map((s: string) => s.trim()).filter(Boolean);
          allCreatedIds.push(...ids);
        }
      }

      // Refresh the task board widget
      const listCmd = buildListCommand();
      const listResult = spawnSync(listCmd.bin, listCmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
      if (listResult.status === 0) {
        const lines = (listResult.stdout as string).split(/\r?\n/).filter((line: string) => line.length > 0);
        ctx.ui.setWidget("factory-tasks", lines);
      }

      if (allCreatedIds.length === 0) {
        ctx.ui.notify("no new tasks created", "info");
        return;
      }

      ctx.ui.notify(`exported ${allCreatedIds.join(", ")} from ${newPlans.map((p) => p.file).join(", ")}`, "info");

      // --- Mark-done loop ---
      const markedDone: string[] = [];
      let remaining = [...allCreatedIds];

      while (remaining.length > 0) {
        const options = remaining.map((id: string) => `${id}  (mark done)`);
        const selected = await ctx.ui.select("Mark which task as done? (cancel to stop)", options);
        if (selected === undefined) break;

        const taskId = selected.split(/\s+/)[0]!;
        const setStatusCmd = buildSetStatusCommand(taskId, "done", ctx.cwd);
        const setResult = spawnSync(setStatusCmd.bin, setStatusCmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
        if (setResult.status !== 0) {
          ctx.ui.notify(`set-status failed for ${taskId}: ${setResult.stderr || "unknown error"}`, "error");
          continue;
        }
        markedDone.push(taskId);
        remaining = remaining.filter((id) => id !== taskId);
      }

      if (markedDone.length > 0) {
        ctx.ui.notify(`${markedDone.join(", ")} marked done`, "info");
      }

      // Final widget refresh
      const finalListResult = spawnSync(listCmd.bin, listCmd.args, { cwd: ctx.cwd, encoding: "utf-8" });
      if (finalListResult.status === 0) {
        const lines = (finalListResult.stdout as string).split(/\r?\n/).filter((line: string) => line.length > 0);
        ctx.ui.setWidget("factory-tasks", lines);
      }
    },
  });
```

The mark-done loop has only task ids (no full `TaskSummary` objects), so it formats
picker options directly as `"${id}  (mark done)"` and extracts the id from the
selected option by taking the first whitespace-delimited token:

- [ ] **Step 4: Run typecheck**

Run: `npm --prefix pi-ext/factory-watch run typecheck 2>&1`
Expected: no errors.

- [ ] **Step 5: Run tests**

Run: `npm --prefix pi-ext/factory-watch test -- --run 2>&1`
Expected: all pass.

- [ ] **Step 6: Run the full gate**

Run: `uv run python scripts/gates/all.py; echo "exit=$?"`
Expected: exit=0.

- [ ] **Step 7: Commit**

```bash
git add pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat: deterministic post-session task export and mark-done loop in /plan"
```
