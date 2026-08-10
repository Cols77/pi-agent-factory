# Review Browser Task Context and Focusable Panes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the browser code-review page show what the task was supposed to accomplish — the chain from requirement down to the plan section the implementer worked from — in panes the reviewer can collapse and zoom.

**Architecture:** The review page becomes a consumer of the system-navigator loaders that already exist (`loadSystemStory`, `loadSystemReverse`, `loadTraceGraph`) rather than a new query layer. The only new Python data is one additive `plan_section` field on `query_story`'s existing dict. On the TypeScript side, `system_context`'s composition is lifted into a shared function, and two new pure modules handle the chain walk and the pane-state reducer.

**Tech Stack:** Python 3.12 (`uv`, pytest, `frontmatter`, jsonschema), TypeScript ESM (vitest, typebox), plain inline HTML/CSS/JS served from `node:http`.

**Spec:** `docs/superpowers/specs/2026-08-10-review-browser-task-context-design.md`

## Global Constraints

- Python tests carry `pytestmark = pytest.mark.unit`. Run with `uv run pytest`.
- TypeScript tests are vitest, run from `pi-ext/factory-watch` with `npm test`. Typecheck with `npm run typecheck`.
- TS imports of local modules use the `.js` extension (ESM), even from `.ts` sources.
- No server data may reach the review page through `innerHTML` except HTML produced by `renderMarkdown`, which escapes its source. Everything else uses `createTextNode`.
- Persistence helpers in `review-surface.ts` are best-effort and never throw.
- The `### Task N:` grammar has exactly one owner: `factory.orchestrator.plan_to_tasks.parse_plan_tasks`. Do not reimplement it in TypeScript.
- Every new context source is optional. A failure in any of them must still leave the review approvable.
- `src/factory/schemas/system_response.schema.json` sets `additionalProperties: false` on `story`. Any new field there requires a schema change in the same commit.

---

### Task 1: Ledger tasks carry `source_plan` and `source_task`

`factory.system.story` reads task metadata through `ledger.Task`, which today drops `source_plan` and `source_task`. Task 3 needs both. Reading them here — rather than re-parsing the task file in `story.py` — follows the reasoning `story.py`'s own docstring gives for `satisfies`: the ledger is the one place task frontmatter is parsed.

**Files:**
- Modify: `src/factory/orchestrator/ledger.py:11-47`
- Test: `tests/unit/orchestrator/test_ledger.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ledger.Task.source_plan: str | None` and `ledger.Task.source_task: int | None`, both defaulting to `None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/orchestrator/test_ledger.py` (create the file with `from pathlib import Path`, `import pytest`, `from factory.orchestrator import ledger`, `pytestmark = pytest.mark.unit` if it does not exist):

```python
def _write_task(tasks_dir: Path, text: str) -> None:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "T-001-x.md").write_text(text, encoding="utf-8")


def test_task_carries_source_plan_and_source_task(tmp_path):
    _write_task(
        tmp_path / "tasks",
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n- d\n"
        "source_plan: docs/superpowers/plans/p.md\nsource_task: 3\n---\nbody\n",
    )

    task = ledger.load_tasks(tmp_path / "tasks")[0]

    assert task.source_plan == "docs/superpowers/plans/p.md"
    assert task.source_task == 3


def test_task_without_source_fields_defaults_to_none(tmp_path):
    _write_task(tmp_path / "tasks", "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n- d\n---\nbody\n")

    task = ledger.load_tasks(tmp_path / "tasks")[0]

    assert task.source_plan is None
    assert task.source_task is None


def test_non_integer_source_task_becomes_none(tmp_path):
    _write_task(
        tmp_path / "tasks",
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n- d\nsource_task: not-a-number\n---\nbody\n",
    )

    assert ledger.load_tasks(tmp_path / "tasks")[0].source_task is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/orchestrator/test_ledger.py -v`
Expected: FAIL with `AttributeError: 'Task' object has no attribute 'source_plan'`

- [ ] **Step 3: Add the fields to the dataclass**

In `src/factory/orchestrator/ledger.py`, extend the `Task` dataclass (currently ending at line 19):

```python
@dataclass
class Task:
    id: str
    title: str
    status: str
    dod: list[str]
    body: str
    path: Path
    satisfies: list[str] = field(default_factory=list)
    # Read here rather than re-parsed in factory.system.story, for the same
    # reason `satisfies` is: the ledger is the one place task frontmatter is
    # parsed. A task written before these fields existed simply has None.
    source_plan: str | None = None
    source_task: int | None = None
```

- [ ] **Step 4: Populate them in `_parse`**

In the same file, insert before the `return Task(` on line 39:

```python
    source_plan_value = meta.get("source_plan")
    source_plan = str(source_plan_value) if source_plan_value else None
    # A hand-edited task file can carry anything here. A non-integer is not a
    # section number, so it is absent rather than an error: the plan section is
    # optional context, never a gate.
    try:
        source_task = int(meta["source_task"]) if meta.get("source_task") is not None else None
    except (TypeError, ValueError):
        source_task = None
```

and add to the `Task(...)` call:

```python
        source_plan=source_plan,
        source_task=source_task,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/orchestrator/test_ledger.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full unit suite for regressions**

Run: `uv run pytest tests/unit -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/factory/orchestrator/ledger.py tests/unit/orchestrator/test_ledger.py
git commit -m "feat(ledger): carry source_plan and source_task on Task"
```

---

### Task 2: `parse_plan_tasks` ignores fenced code blocks and carries section bodies

This closes the open task `T-020`. It is a prerequisite, not cleanup: `parse_plan_tasks` currently finds 19 sections in `docs/superpowers/plans/2026-07-20-factory-plan-and-run.md` for 16 real tasks, numbered `[1,2,3,4,5,6,7,1,2,1,8,...]`, because a markdown fixture inside a code fence carries its own `### Task 1:` headers. Fenced content is masked with spaces rather than removed so that every character offset stays aligned and sections can still be sliced out of the original text — which keeps real fenced code inside the section body, where the reviewer needs to see it.

**Files:**
- Modify: `src/factory/orchestrator/plan_to_tasks.py:11-57`
- Test: `tests/unit/test_plan_to_tasks.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ParsedPlanTask.body: str` — the raw section text between one `### Task N:` header and the next, stripped. `parse_plan_tasks(text: str) -> list[ParsedPlanTask]` keeps its existing signature and its `number`, `title`, `files_block`, `produces` fields unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_plan_to_tasks.py`:

`````python
PLAN_WITH_FENCED_FIXTURE = """\
### Task 1: Real Task

**Files:**
- Create: `src/a.py`

**Interfaces:**
- Produces: `do_a() -> None`.

```markdown
### Task 1: Fixture Inside A Fence
### Task 2: Another Fixture
```

### Task 2: Second Real Task

**Files:**
- Create: `src/b.py`

**Interfaces:**
- Produces: `do_b() -> None`.
"""


def test_task_headers_inside_a_fence_are_not_sections():
    tasks = parse_plan_tasks(PLAN_WITH_FENCED_FIXTURE)
    assert [t.number for t in tasks] == [1, 2]
    assert [t.title for t in tasks] == ["Real Task", "Second Real Task"]


def test_fenced_content_stays_in_the_section_body():
    tasks = parse_plan_tasks(PLAN_WITH_FENCED_FIXTURE)
    assert "### Task 1: Fixture Inside A Fence" in tasks[0].body
    assert "```markdown" in tasks[0].body


def test_body_stops_at_the_next_section():
    tasks = parse_plan_tasks(PLAN_WITH_FENCED_FIXTURE)
    assert "Second Real Task" not in tasks[0].body
    assert "`src/b.py`" in tasks[1].body


def test_tilde_fences_are_masked_too():
    text = "### Task 1: Real\n\n~~~\n### Task 9: Fake\n~~~\n"
    assert [t.number for t in parse_plan_tasks(text)] == [1]


def test_files_block_and_produces_survive_masking():
    tasks = parse_plan_tasks(PLAN_WITH_FENCED_FIXTURE)
    assert "Create: `src/a.py`" in tasks[0].files_block
    assert tasks[0].produces == ["`do_a() -> None`."]
`````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_plan_to_tasks.py -v`
Expected: FAIL — `test_task_headers_inside_a_fence_are_not_sections` gets `[1, 1, 2, 2]`, and the body tests fail with `AttributeError: 'ParsedPlanTask' object has no attribute 'body'`

- [ ] **Step 3: Add the masking helper**

In `src/factory/orchestrator/plan_to_tasks.py`, after the `_ID_RE` definition on line 14:

```python
def _mask_fenced_blocks(text: str) -> str:
    """Blank out fenced code block contents, preserving every character
    offset and every newline so that slices taken against the ORIGINAL text
    stay aligned. A plan legitimately embeds plan-shaped markdown in a fence
    (a test fixture, an example); those `### Task N:` lines are content, not
    sections, and matching them produces phantom tasks (T-020).
    """
    out: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else None
        if fence is None:
            if marker is None:
                out.append(line)
            else:
                fence = marker
                out.append(" " * len(line))
            continue
        out.append(" " * len(line))
        # Only a matching marker closes the fence, so ``` inside a ~~~ block
        # (and vice versa) does not end it early.
        if marker == fence:
            fence = None
    return "\n".join(out)
```

- [ ] **Step 4: Add `body` to the dataclass and match against the masked text**

Extend `ParsedPlanTask` (line 19):

```python
@dataclass
class ParsedPlanTask:
    number: int
    title: str
    files_block: str
    produces: list[str]
    body: str = ""
```

Replace the first two lines of `parse_plan_tasks`'s loop setup (line 38) so headers come from the masked text while chunks come from the original:

```python
    headers = list(_TASK_HEADER.finditer(_mask_fenced_blocks(text)))
```

and add `body=chunk.strip(),` to the `ParsedPlanTask(...)` construction.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_plan_to_tasks.py -v`
Expected: PASS (all, including the pre-existing tests)

- [ ] **Step 6: Verify against the real plan that exposed the bug**

Run:

```bash
uv run python -c "
from pathlib import Path
from factory.orchestrator.plan_to_tasks import parse_plan_tasks
t = parse_plan_tasks(Path('docs/superpowers/plans/2026-07-20-factory-plan-and-run.md').read_text(encoding='utf-8'))
print(len(t), [x.number for x in t])
"
```

Expected: `16 [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]` — sixteen sections, strictly ascending, no duplicates. Before this task it printed 19 with duplicated numbers.

- [ ] **Step 7: Mark T-020 done and commit**

There is no `set-status` subcommand — `factory.orchestrator` exposes only `run`
and `list` — so use `ledger.set_status`, which rewrites the task's frontmatter
in place:

```bash
uv run python -c "
from pathlib import Path
from factory.orchestrator import ledger
tasks = ledger.load_tasks(Path('tasks'))
ledger.set_status(ledger.get_task(tasks, 'T-020'), 'done')
"
git add src/factory/orchestrator/plan_to_tasks.py tests/unit/test_plan_to_tasks.py tasks/T-020-*.md
git commit -m "fix(plan-to-tasks): ignore task headers inside fenced blocks, carry section bodies

Closes T-020. parse_plan_tasks found 19 sections in the 2026-07-20 plan for
16 real tasks because a fenced markdown fixture carries its own '### Task 1:'
headers, which made source_task ambiguous."
```

---

### Task 3: `query_story` returns the resolved plan section

**Files:**
- Modify: `src/factory/system/story.py`
- Modify: `src/factory/schemas/system_response.schema.json` (the `properties.story` block)
- Modify: `tests/unit/system/_fixtures.py:58-66,120-135`
- Test: `tests/unit/system/test_story.py`

**Interfaces:**
- Consumes: `ledger.Task.source_plan`, `ledger.Task.source_task` (Task 1); `parse_plan_tasks(...) -> list[ParsedPlanTask]` with `.body` (Task 2).
- Produces: `query_story(...)["plan_section"]` — either `None` or `{"plan_path": str, "heading": str, "body": str}` — and `query_story(...)["task"]["dod"]: list[str]`.

The `dod` addition is not incidental. `query_story`'s `task` dict is
`{id, title, status}` only (`story.py:229-232`), and `storyTask` in the schema
is `additionalProperties: false`, so the definition of done — the most direct
statement of what the task was supposed to accomplish — is not reachable
through the navigator today. The ledger already parses it.

- [ ] **Step 1: Extend the task fixture to write source fields**

In `tests/unit/system/_fixtures.py`, change the `_TASK` template (line 58) to:

```python
_TASK = """---
id: {id}
title: "{title}"
status: {status}
dod:
  - done
{satisfies}{source}---
body
"""
```

and the plain `write_task` builder (line 120) to:

```python
def write_task(
    tasks_dir: Path,
    task_id: str,
    *,
    title: str = "Task title",
    status: str = "todo",
    satisfies: list[str] | None = None,
    source_plan: str | None = None,
    source_task: int | None = None,
) -> Path:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"{task_id}-slug.md"
    satisfies_block = f"satisfies: {json.dumps(satisfies)}\n" if satisfies else ""
    source_block = ""
    if source_plan:
        source_block += f"source_plan: {source_plan}\n"
    if source_task is not None:
        source_block += f"source_task: {source_task}\n"
    path.write_text(
        _TASK.format(
            id=task_id, title=title, status=status,
            satisfies=satisfies_block, source=source_block,
        ),
        encoding="utf-8",
    )
    return path
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/system/test_story.py`:

```python
_PLAN_TEXT = """\
# A Plan

### Task 1: First Component

Build the first thing.

### Task 2: Second Component

Build the second thing.
"""


def _write_plan_file(repo_root, name="p.md", text=_PLAN_TEXT):
    plans = repo_root / "docs" / "superpowers" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / name).write_text(text, encoding="utf-8")
    return f"docs/superpowers/plans/{name}"


def test_plan_section_resolves_by_title(tmp_path, write_task):
    plan_ref = _write_plan_file(tmp_path)
    # source_task deliberately disagrees with the title: title must win, so a
    # plan whose numbering shifted still resolves to the right section.
    write_task(tmp_path, "T-001", title="Second Component", source_plan=plan_ref, source_task=1)

    section = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))["plan_section"]

    assert section["heading"] == "Task 2: Second Component"
    assert section["plan_path"] == plan_ref
    assert "Build the second thing." in section["body"]


def test_plan_section_falls_back_to_source_task_number(tmp_path, write_task):
    plan_ref = _write_plan_file(tmp_path)
    write_task(tmp_path, "T-001", title="Renamed Since", source_plan=plan_ref, source_task=2)

    section = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))["plan_section"]

    assert section["heading"] == "Task 2: Second Component"


def test_plan_section_is_none_without_source_plan(tmp_path, write_task):
    write_task(tmp_path, "T-001", title="No Plan")

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    assert result["plan_section"] is None


def test_plan_section_is_none_when_the_plan_file_is_missing(tmp_path, write_task):
    write_task(tmp_path, "T-001", title="X", source_plan="docs/superpowers/plans/gone.md",
               source_task=1)

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    assert result["plan_section"] is None


def test_plan_section_is_none_when_no_section_matches(tmp_path, write_task):
    plan_ref = _write_plan_file(tmp_path)
    write_task(tmp_path, "T-001", title="Nowhere In The Plan", source_plan=plan_ref, source_task=9)

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    assert result["plan_section"] is None


def test_plan_section_validates_against_the_response_schema(tmp_path, write_task):
    plan_ref = _write_plan_file(tmp_path)
    write_task(tmp_path, "T-001", title="First Component", source_plan=plan_ref, source_task=1)

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    validate_against(result, _STORY_SCHEMA)


def test_task_carries_its_definition_of_done(tmp_path, write_task):
    write_task(tmp_path, "T-001", title="X")

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))

    # The fixture template writes a single `- done` dod entry.
    assert result["task"]["dod"] == ["done"]
    validate_against(result, _STORY_SCHEMA)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/system/test_story.py -v`
Expected: FAIL with `KeyError: 'plan_section'`

- [ ] **Step 4: Implement the resolver**

In `src/factory/system/story.py`, add the import beside the existing `from factory.orchestrator import ledger`:

```python
from factory.orchestrator.plan_to_tasks import parse_plan_tasks
```

and add this function above `query_story`:

```python
def _plan_section(repo_root: Path, task: ledger.Task) -> dict | None:
    """The `### Task N:` section of the task's source plan -- the steps the
    implementer actually worked from, which the task file itself only points
    at.

    Resolved by title first and by `source_task` number second: until T-020
    landed, a plan's fenced fixtures produced duplicate section numbers, and a
    plan whose sections were reordered after export still names its task the
    same. `parse_plan_tasks` stays the one owner of the `### Task N:` grammar.

    Returns None -- never raises -- for a task with no `source_plan`, a plan
    file that cannot be read, or a plan with no matching section. The section
    is optional review context, never a gate.
    """
    if not task.source_plan:
        return None
    try:
        text = (repo_root / task.source_plan).read_text(encoding="utf-8")
    except OSError:
        return None
    sections = parse_plan_tasks(text)
    match = next((s for s in sections if s.title.strip() == task.title.strip()), None)
    if match is None and task.source_task is not None:
        match = next((s for s in sections if s.number == task.source_task), None)
    if match is None:
        return None
    return {
        "plan_path": task.source_plan,
        "heading": f"Task {match.number}: {match.title}",
        "body": match.body,
    }
```

Then add to `query_story`'s returned dict — both the new top-level field and
`dod` on the existing `task` block:

```python
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "dod": task.dod,
        },
        ...
        "plan_section": _plan_section(repo_root, task),
```

- [ ] **Step 5: Extend the response schema**

In `src/factory/schemas/system_response.schema.json`, add `"dod"` to
`$defs.storyTask` — both to its `required` array and its `properties`, since it
sets `additionalProperties: false`:

```json
"dod": {
  "description": "The task's definition of done, as recorded in its frontmatter and parsed by the ledger.",
  "type": "array",
  "items": { "type": "string" }
}
```

Then, inside `properties.story`, add `"plan_section"` to the `required` array and add to its `properties`:

```json
"plan_section": {
  "description": "The source plan's `### Task N:` section for this task, or null when the task declares no source_plan, the plan file is unreadable, or no section matches.",
  "oneOf": [
    { "type": "null" },
    {
      "type": "object",
      "additionalProperties": false,
      "required": ["plan_path", "heading", "body"],
      "properties": {
        "plan_path": { "type": "string", "minLength": 1 },
        "heading": { "type": "string", "minLength": 1 },
        "body": { "type": "string" }
      }
    }
  ]
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/system/ -v`
Expected: PASS — including the pre-existing story and CLI tests, which validate against the same schema

- [ ] **Step 7: Run the full unit suite**

Run: `uv run pytest tests/unit -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/factory/system/story.py src/factory/schemas/system_response.schema.json \
        tests/unit/system/test_story.py tests/unit/system/_fixtures.py
git commit -m "feat(system): return the resolved plan section from query_story"
```

---

### Task 4: Extract `buildSystemContext` from the `system_context` tool

The review server needs the same graph-plus-freshness-plus-evidence composition the tool already performs, and it needs the loaded graph itself for Task 5's walk. Lifting the body out of `execute` gives both callers one implementation and saves the review server a second `loadTraceGraph` subprocess.

**Files:**
- Create: `pi-ext/factory-watch/src/system-context.ts`
- Modify: `pi-ext/factory-watch/src/system-context-tools.ts:60-121`
- Test: `pi-ext/factory-watch/test/system-context.test.ts`

**Interfaces:**
- Consumes: `loadTraceGraph`, `loadTaskEvidence`, `runPreflight` (existing).
- Produces:
  - `unknownSource(source: string, error: string): Record<string, unknown>` — the moved `unknown()` helper.
  - `buildSystemContext(cwd: string, id: string, deps: SystemContextDeps): SystemContextResult`
  - `interface SystemContextDeps { graph: typeof loadTraceGraph; taskEvidence: typeof loadTaskEvidence; preflight: typeof runPreflight }`
  - `interface SystemContextResult { context: Record<string, unknown>; graph: TraceGraph | null }`

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/system-context.test.ts`:

```typescript
import { describe, expect, test } from "vitest";
import { buildSystemContext } from "../src/system-context.js";
import type { TraceGraph } from "../src/trace-cli.js";

const GRAPH: TraceGraph = {
  nodes: [
    { id: "T-001", kind: "task", title: "A task", path: "tasks/T-001-a.md", exempt: false, deferred: null },
    { id: "plan:p.md", kind: "plan", title: "A plan", path: "docs/superpowers/plans/p.md", exempt: false, deferred: null },
  ],
  edges: [{ src: "T-001", dst: "plan:p.md", kind: "source_plan" }],
  gaps: [],
  validation: {},
  health: { percent: 0, satisfied: 0, expected: 0, dangling: 0, deferred: 0, proposed: 0, classes: [] },
};

// The fakes keep their inferred object types; the `as never` cast belongs at
// each call site. Casting the literal itself would type `deps` as `never`,
// and a `never` cannot be spread — `{ ...deps }` below would not compile.
const deps = {
  graph: () => ({ ok: true as const, graph: GRAPH }),
  taskEvidence: () => ({ ok: true as const, value: { runs: [] } }),
  preflight: () => ({ ok: true as const, value: { findings: [] } }),
};

describe("buildSystemContext", () => {
  test("returns the node, its edges, and its neighbours", () => {
    const { context } = buildSystemContext("/repo", "T-001", deps as never);
    expect((context.node as { id: string }).id).toBe("T-001");
    expect(context.edges).toHaveLength(1);
    expect((context.neighbours as { id: string }[]).map((n) => n.id)).toEqual(["plan:p.md"]);
  });

  test("also returns the loaded graph so callers need not reload it", () => {
    const { graph } = buildSystemContext("/repo", "T-001", deps as never);
    expect(graph?.nodes).toHaveLength(2);
  });

  test("reports an unknown source rather than throwing when the graph fails", () => {
    const failing = { ...deps, graph: () => ({ ok: false as const, error: "uv missing" }) };
    const { context, graph } = buildSystemContext("/repo", "T-001", failing as never);
    expect(context.status).toBe("unknown");
    expect(context.source).toBe("trace");
    expect(graph).toBeNull();
  });

  test("reports an unknown source for an id that is not in the graph", () => {
    const { context } = buildSystemContext("/repo", "T-999", deps as never);
    expect(context.status).toBe("unknown");
    expect(String(context.error)).toContain("T-999");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd pi-ext/factory-watch && npm test -- system-context`
Expected: FAIL — cannot resolve `../src/system-context.js`

- [ ] **Step 3: Create the module**

Create `pi-ext/factory-watch/src/system-context.ts`, moving the logic currently inside `system_context`'s `execute` (`system-context-tools.ts:86-119`) verbatim:

```typescript
import { loadTraceGraph } from "./trace-cli.js";
import type { TraceGraph } from "./trace-cli.js";
import { loadTaskEvidence, runPreflight } from "./evidence-client.js";

export interface SystemContextDeps {
  graph: typeof loadTraceGraph;
  taskEvidence: typeof loadTaskEvidence;
  preflight: typeof runPreflight;
}

export interface SystemContextResult {
  context: Record<string, unknown>;
  // The graph the composition already loaded. Returned so a caller that needs
  // the full node/edge set (the review server's chain walk) does not spawn a
  // second `uv run` for data this call already has in hand.
  graph: TraceGraph | null;
}

export function unknownSource(source: string, error: string): Record<string, unknown> {
  return {
    status: "unknown",
    source,
    error,
    instruction: "Missing evidence is unknown. Do not infer or manufacture it.",
  };
}

export function buildSystemContext(
  cwd: string,
  id: string,
  deps: SystemContextDeps,
): SystemContextResult {
  const graphResult = deps.graph(cwd);
  if (!graphResult.ok) {
    return { context: unknownSource("trace", graphResult.error), graph: null };
  }
  const graph = graphResult.graph;
  const node = graph.nodes.find((item) => item.id === id);
  if (node === undefined) {
    return { context: unknownSource("trace", `node not found: ${id}`), graph };
  }
  const edges = graph.edges.filter((edge) => edge.src === id || edge.dst === id);
  const neighbourIds = new Set(
    edges.flatMap((edge) => [edge.src, edge.dst]).filter((each) => each !== id),
  );
  const neighbours = graph.nodes.filter((item) => neighbourIds.has(item.id));
  const taskEvidence = node.kind === "task" ? deps.taskEvidence(cwd, id) : null;
  const freshness = node.kind === "task" ? deps.preflight(cwd, id) : null;
  return {
    graph,
    context: {
      node,
      edges,
      neighbours,
      freshness: freshness === null
        ? { status: "not-applicable", reason: "freshness is task-scoped" }
        : freshness.ok ? freshness.value : unknownSource("preflight", freshness.error),
      evidence: taskEvidence === null
        ? { status: "not-applicable", reason: "implementation evidence is task-scoped" }
        : taskEvidence.ok
          ? { runs: taskEvidence.value.runs.map((run) => ({
              run_id: run.run_id,
              outcome: run.outcome,
              start_commit: run.start_commit,
              result_commit: run.result_commit,
            })) }
          : unknownSource("evidence", taskEvidence.error),
      provenance: "recorded and deterministically derived project data only",
    },
  };
}
```

- [ ] **Step 4: Make the tool a thin caller**

In `pi-ext/factory-watch/src/system-context-tools.ts`, delete the local `unknown()` function (lines 60-67) and replace `systemContext`'s `execute` body with:

```typescript
      return result(buildSystemContext(ctx.cwd, params.id, deps).context);
```

Add `import { buildSystemContext, unknownSource } from "./system-context.js";` and replace every remaining `unknown(` call in the file with `unknownSource(`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd pi-ext/factory-watch && npm test`
Expected: PASS — including the existing `system-context-tools` tests, unchanged

- [ ] **Step 6: Typecheck**

Run: `cd pi-ext/factory-watch && npm run typecheck`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add pi-ext/factory-watch/src/system-context.ts \
        pi-ext/factory-watch/src/system-context-tools.ts \
        pi-ext/factory-watch/test/system-context.test.ts
git commit -m "refactor(factory-watch): extract buildSystemContext from the system_context tool"
```

---

### Task 5: `walkIntentChain` — the requirement-to-task chain

Pure: it walks a graph already in memory, so it needs no subprocess and no filesystem.

**Files:**
- Create: `pi-ext/factory-watch/src/review-intent.ts`
- Test: `pi-ext/factory-watch/test/review-intent.test.ts`

**Interfaces:**
- Consumes: `TraceGraph`, `TraceNode`, `TraceNodeKind`, `TraceEdgeKind` from `./trace-cli.js`.
- Produces:
  - `interface ReviewChainNode { id: string; kind: TraceNodeKind; title: string; path: string }`
  - `interface IntentChain { chain: ReviewChainNode[]; stopsAt: string | null }`
  - `walkIntentChain(graph: TraceGraph, taskId: string): IntentChain`

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/review-intent.test.ts`:

```typescript
import { describe, expect, test } from "vitest";
import { walkIntentChain } from "../src/review-intent.js";
import type { TraceEdge, TraceGraph, TraceNode } from "../src/trace-cli.js";

function node(id: string, kind: TraceNode["kind"], title: string): TraceNode {
  return { id, kind, title, path: `${id}.md`, exempt: false, deferred: null };
}

function graphOf(nodes: TraceNode[], edges: TraceEdge[]): TraceGraph {
  return {
    nodes, edges, gaps: [], validation: {},
    health: { percent: 0, satisfied: 0, expected: 0, dangling: 0, deferred: 0, proposed: 0, classes: [] },
  };
}

const FULL = graphOf(
  [
    node("T-001", "task", "A task"),
    node("plan:p.md", "plan", "A plan"),
    node("spec:s.md", "spec", "A spec"),
    node("SR-014", "sr", "A requirement"),
    node("BR-002", "br", "A business requirement"),
  ],
  [
    { src: "T-001", dst: "plan:p.md", kind: "source_plan" },
    { src: "plan:p.md", dst: "spec:s.md", kind: "spec_ref" },
    { src: "T-001", dst: "SR-014", kind: "satisfies" },
    { src: "SR-014", dst: "BR-002", kind: "upstream" },
  ],
);

describe("walkIntentChain", () => {
  test("orders a complete chain from business requirement down to task", () => {
    const { chain, stopsAt } = walkIntentChain(FULL, "T-001");
    expect(chain.map((n) => n.id)).toEqual(["BR-002", "SR-014", "spec:s.md", "plan:p.md", "T-001"]);
    expect(stopsAt).toBeNull();
  });

  test("reports satisfies as the stop when the task links no requirement", () => {
    const graph = graphOf(FULL.nodes, FULL.edges.filter((e) => e.kind !== "satisfies" && e.kind !== "upstream"));
    const { chain, stopsAt } = walkIntentChain(graph, "T-001");
    expect(chain.map((n) => n.id)).toEqual(["spec:s.md", "plan:p.md", "T-001"]);
    expect(stopsAt).toBe("satisfies");
  });

  test("reports source_plan as the stop when the requirement side is complete", () => {
    const graph = graphOf(FULL.nodes, FULL.edges.filter((e) => e.kind !== "source_plan" && e.kind !== "spec_ref"));
    const { chain, stopsAt } = walkIntentChain(graph, "T-001");
    expect(chain.map((n) => n.id)).toEqual(["BR-002", "SR-014", "T-001"]);
    expect(stopsAt).toBe("source_plan");
  });

  test("an edge pointing at a node that does not exist counts as unresolved", () => {
    const graph = graphOf(
      [node("T-001", "task", "A task")],
      [{ src: "T-001", dst: "plan:gone.md", kind: "source_plan" }],
    );
    const { chain, stopsAt } = walkIntentChain(graph, "T-001");
    expect(chain.map((n) => n.id)).toEqual(["T-001"]);
    expect(stopsAt).toBe("satisfies");
  });

  test("an unknown task id yields an empty chain stopping at task", () => {
    expect(walkIntentChain(FULL, "T-999")).toEqual({ chain: [], stopsAt: "task" });
  });

  test("a single-edge hop reports no alternatives", () => {
    const { chain } = walkIntentChain(FULL, "T-001");
    expect(chain.every((n) => n.alternatives === 0)).toBe(true);
  });

  test("a second satisfies edge is counted, not silently dropped", () => {
    const graph = graphOf(
      [...FULL.nodes, node("SR-020", "sr", "Another requirement")],
      [...FULL.edges, { src: "T-001", dst: "SR-020", kind: "satisfies" }],
    );
    const { chain } = walkIntentChain(graph, "T-001");
    const sr = chain.find((n) => n.id === "SR-014");
    expect(sr?.alternatives).toBe(1);
    // The chain still shows one requirement; the count is how the reviewer
    // learns a second one exists.
    expect(chain.filter((n) => n.kind === "sr")).toHaveLength(1);
  });

  test("a second spec_ref edge is counted on the spec it resolved to", () => {
    const graph = graphOf(
      [...FULL.nodes, node("spec:other.md", "spec", "Another spec")],
      [...FULL.edges, { src: "plan:p.md", dst: "spec:other.md", kind: "spec_ref" }],
    );
    const { chain } = walkIntentChain(graph, "T-001");
    expect(chain.find((n) => n.id === "spec:s.md")?.alternatives).toBe(1);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd pi-ext/factory-watch && npm test -- review-intent`
Expected: FAIL — cannot resolve `../src/review-intent.js`

- [ ] **Step 3: Implement the walk**

Create `pi-ext/factory-watch/src/review-intent.ts`:

```typescript
import type { TraceEdgeKind, TraceGraph, TraceNode, TraceNodeKind } from "./trace-cli.js";

export interface ReviewChainNode {
  id: string;
  kind: TraceNodeKind;
  title: string;
  path: string;
  // How many FURTHER edges of the same kind left the same source. A task may
  // declare several `satisfies` and a plan may reference several specs, but the
  // chain shows one line per hop. Without this count the reviewer would be
  // shown a partial chain with no sign anything was omitted -- the exact
  // failure this pane exists to prevent. 0 in the ordinary single-edge case.
  alternatives: number;
}

export interface IntentChain {
  chain: ReviewChainNode[];
  stopsAt: string | null;
}

// The order hops are reported as missing. Fixed rather than derived from the
// display order, so `stopsAt` names a cause and not merely the topmost blank
// row: an absent `upstream` is only interesting once `satisfies` resolved.
const HOP_PRECEDENCE = ["satisfies", "upstream", "source_plan", "spec_ref"] as const;

interface Hop {
  node: TraceNode | undefined;
  alternatives: number;
}

function toChainNode(node: TraceNode, alternatives: number): ReviewChainNode {
  return { id: node.id, kind: node.kind, title: node.title, path: node.path, alternatives };
}

/** Walk the two branches `factory.trace.model.extract_edges` actually writes:
 *
 *     task --satisfies--> SR --upstream--> BR
 *     task --source_plan--> plan --spec_ref--> spec
 *
 * Returns the resolved hops ordered BR -> SR -> spec -> plan -> task, and the
 * first hop that did not resolve. An edge whose destination has no node is
 * unresolved: the walk never guesses past a hop it could not follow, it stops
 * and says where -- the discipline `factory.system.reverse` states for its own
 * `stops_at`. Pure: no I/O, the graph is already loaded.
 */
export function walkIntentChain(graph: TraceGraph, taskId: string): IntentChain {
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const task = byId.get(taskId);
  if (task === undefined) return { chain: [], stopsAt: "task" };

  const NONE: Hop = { node: undefined, alternatives: 0 };

  // Collect every candidate rather than taking the first: the count of the ones
  // not shown is what the chain reports as "+N more".
  const hop = (src: string, kind: TraceEdgeKind): Hop => {
    const edges = graph.edges.filter((each) => each.src === src && each.kind === kind);
    const first = edges[0];
    return {
      node: first === undefined ? undefined : byId.get(first.dst),
      alternatives: Math.max(0, edges.length - 1),
    };
  };

  const sr = hop(taskId, "satisfies");
  const br = sr.node === undefined ? NONE : hop(sr.node.id, "upstream");
  const plan = hop(taskId, "source_plan");
  const spec = plan.node === undefined ? NONE : hop(plan.node.id, "spec_ref");

  const resolved: Record<(typeof HOP_PRECEDENCE)[number], Hop> = {
    satisfies: sr, upstream: br, source_plan: plan, spec_ref: spec,
  };
  const stopsAt = HOP_PRECEDENCE.find((hopName) => resolved[hopName].node === undefined) ?? null;

  // The task itself was not reached through an edge, so it has no alternatives.
  const chain = [br, sr, spec, plan, { node: task, alternatives: 0 }]
    .filter((each): each is { node: TraceNode; alternatives: number } => each.node !== undefined)
    .map((each) => toChainNode(each.node, each.alternatives));
  return { chain, stopsAt };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd pi-ext/factory-watch && npm test -- review-intent`
Expected: PASS (5 tests)

- [ ] **Step 5: Typecheck and commit**

Run: `cd pi-ext/factory-watch && npm run typecheck`
Expected: no errors

```bash
git add pi-ext/factory-watch/src/review-intent.ts pi-ext/factory-watch/test/review-intent.test.ts
git commit -m "feat(factory-watch): add walkIntentChain for the review context chain"
```

---

### Task 6: `review-layout.ts` — the pane-state reducer

Pure, so the focus model is tested without a browser.

**Files:**
- Create: `pi-ext/factory-watch/src/review-layout.ts`
- Test: `pi-ext/factory-watch/test/review-layout.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `type PaneId = "context" | "tree" | "diff" | "comments"`
  - `interface LayoutState { collapsed: PaneId[]; zoomed: PaneId | null }`
  - `const PANE_ORDER: readonly PaneId[]`, `const DEFAULT_LAYOUT: LayoutState`
  - `togglePane(state: LayoutState, pane: PaneId): LayoutState`
  - `zoomPane(state: LayoutState, pane: PaneId): LayoutState`
  - `restoreLayout(state: LayoutState): LayoutState`
  - `columnTemplate(state: LayoutState): string`
  - `normalizeLayout(raw: unknown): LayoutState`

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/review-layout.test.ts`:

```typescript
import { describe, expect, test } from "vitest";
import {
  DEFAULT_LAYOUT, columnTemplate, normalizeLayout, restoreLayout, togglePane, zoomPane,
} from "../src/review-layout.js";

describe("columnTemplate", () => {
  test("the default gives every pane its natural width", () => {
    expect(columnTemplate(DEFAULT_LAYOUT)).toBe("1.2fr 240px 2fr 320px");
  });

  test("a collapsed pane becomes a rail and the rest keep their widths", () => {
    expect(columnTemplate(togglePane(DEFAULT_LAYOUT, "tree"))).toBe("1.2fr 28px 2fr 320px");
  });

  test("a zoomed pane takes the window and the rest collapse to zero", () => {
    expect(columnTemplate(zoomPane(DEFAULT_LAYOUT, "context"))).toBe("1fr 0px 0px 0px");
  });

  test("zoom overrides collapse without discarding it", () => {
    const state = zoomPane(togglePane(DEFAULT_LAYOUT, "tree"), "diff");
    expect(columnTemplate(state)).toBe("0px 0px 1fr 0px");
    expect(columnTemplate(restoreLayout(state))).toBe("1.2fr 28px 2fr 320px");
  });
});

describe("togglePane", () => {
  test("toggling twice returns to the default", () => {
    const state = togglePane(togglePane(DEFAULT_LAYOUT, "comments"), "comments");
    expect(state.collapsed).toEqual([]);
  });

  test("collapsing every pane is allowed and reversible", () => {
    let state = DEFAULT_LAYOUT;
    for (const pane of ["context", "tree", "diff", "comments"] as const) {
      state = togglePane(state, pane);
    }
    expect(columnTemplate(state)).toBe("28px 28px 28px 28px");
  });
});

describe("zoomPane", () => {
  test("zooming the already-zoomed pane restores", () => {
    const state = zoomPane(zoomPane(DEFAULT_LAYOUT, "diff"), "diff");
    expect(state.zoomed).toBeNull();
  });
});

describe("normalizeLayout", () => {
  test("unknown pane ids are dropped", () => {
    expect(normalizeLayout({ collapsed: ["tree", "nope"], zoomed: "bogus" }))
      .toEqual({ collapsed: ["tree"], zoomed: null });
  });

  test("junk falls back to the default", () => {
    expect(normalizeLayout(null)).toEqual(DEFAULT_LAYOUT);
    expect(normalizeLayout("garbage")).toEqual(DEFAULT_LAYOUT);
    expect(normalizeLayout({ collapsed: "tree" })).toEqual(DEFAULT_LAYOUT);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd pi-ext/factory-watch && npm test -- review-layout`
Expected: FAIL — cannot resolve `../src/review-layout.js`

- [ ] **Step 3: Implement the reducer**

Create `pi-ext/factory-watch/src/review-layout.ts`:

```typescript
export type PaneId = "context" | "tree" | "diff" | "comments";

export const PANE_ORDER: readonly PaneId[] = ["context", "tree", "diff", "comments"];

export interface LayoutState {
  collapsed: PaneId[];
  zoomed: PaneId | null;
}

export const DEFAULT_LAYOUT: LayoutState = { collapsed: [], zoomed: null };

const RAIL = "28px";
const NATURAL: Record<PaneId, string> = {
  context: "1.2fr",
  tree: "240px",
  diff: "2fr",
  comments: "320px",
};

function isPaneId(value: unknown): value is PaneId {
  return typeof value === "string" && (PANE_ORDER as readonly string[]).includes(value);
}

export function togglePane(state: LayoutState, pane: PaneId): LayoutState {
  const collapsed = state.collapsed.includes(pane)
    ? state.collapsed.filter((each) => each !== pane)
    : [...state.collapsed, pane];
  return { ...state, collapsed };
}

/** Zooming the already-zoomed pane restores, so the same key both enters and
 * leaves focus. Collapse state is kept, not cleared: leaving zoom must return
 * the reviewer to the layout they built, not to the default. */
export function zoomPane(state: LayoutState, pane: PaneId): LayoutState {
  return { ...state, zoomed: state.zoomed === pane ? null : pane };
}

export function restoreLayout(state: LayoutState): LayoutState {
  return { ...state, zoomed: null };
}

export function columnTemplate(state: LayoutState): string {
  if (state.zoomed !== null) {
    return PANE_ORDER.map((pane) => (pane === state.zoomed ? "1fr" : "0px")).join(" ");
  }
  return PANE_ORDER.map((pane) => (state.collapsed.includes(pane) ? RAIL : NATURAL[pane])).join(" ");
}

/** Coerce a persisted or posted layout into a valid one. The stored file is
 * hand-editable and the POST body is client input; neither may put an unknown
 * pane id into a CSS template. */
export function normalizeLayout(raw: unknown): LayoutState {
  if (raw === null || typeof raw !== "object") return DEFAULT_LAYOUT;
  const value = raw as { collapsed?: unknown; zoomed?: unknown };
  if (value.collapsed !== undefined && !Array.isArray(value.collapsed)) return DEFAULT_LAYOUT;
  return {
    collapsed: (value.collapsed ?? []).filter(isPaneId),
    zoomed: isPaneId(value.zoomed) ? value.zoomed : null,
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd pi-ext/factory-watch && npm test -- review-layout`
Expected: PASS (9 tests)

- [ ] **Step 5: Typecheck and commit**

Run: `cd pi-ext/factory-watch && npm run typecheck`
Expected: no errors

```bash
git add pi-ext/factory-watch/src/review-layout.ts pi-ext/factory-watch/test/review-layout.test.ts
git commit -m "feat(factory-watch): add the review pane layout reducer"
```

---

### Task 7: Persist the layout beside the surface preference

`localStorage` cannot be used: `server.listen(0)` (`review-server.ts:153`) binds a random port, so every review is a new origin and the layout would silently reset each time.

**Files:**
- Modify: `pi-ext/factory-watch/src/review-surface.ts:34-49`
- Test: `pi-ext/factory-watch/test/review-surface.test.ts`

**Interfaces:**
- Consumes: `LayoutState`, `DEFAULT_LAYOUT`, `normalizeLayout` from `./review-layout.js` (Task 6).
- Produces: `readLayoutPref(cwd: string): LayoutState`, `writeLayoutPref(cwd: string, state: LayoutState): void`.

- [ ] **Step 1: Write the failing test**

Append to `pi-ext/factory-watch/test/review-surface.test.ts` (reuse the file's existing tmpdir helper; the snippet below creates its own if there is none):

```typescript
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DEFAULT_LAYOUT } from "../src/review-layout.js";
import { readLayoutPref, writeLayoutPref, readSurfacePref, writeSurfacePref } from "../src/review-surface.js";

describe("layout preference", () => {
  test("round-trips through the surface preference file", () => {
    const cwd = mkdtempSync(join(tmpdir(), "layout-"));
    writeLayoutPref(cwd, { collapsed: ["tree"], zoomed: "diff" });
    expect(readLayoutPref(cwd)).toEqual({ collapsed: ["tree"], zoomed: "diff" });
  });

  test("does not disturb the surface preference stored in the same file", () => {
    const cwd = mkdtempSync(join(tmpdir(), "layout-"));
    writeSurfacePref(cwd, "browser");
    writeLayoutPref(cwd, { collapsed: ["comments"], zoomed: null });
    expect(readSurfacePref(cwd)).toBe("browser");
  });

  test("a missing file yields the default layout", () => {
    expect(readLayoutPref(mkdtempSync(join(tmpdir(), "layout-")))).toEqual(DEFAULT_LAYOUT);
  });

  test("a corrupt stored layout yields the default rather than throwing", () => {
    const cwd = mkdtempSync(join(tmpdir(), "layout-"));
    mkdirSync(join(cwd, "sessions"), { recursive: true });
    writeFileSync(join(cwd, "sessions", ".factory-review-surface.json"),
      '{"layout":{"collapsed":["bogus"],"zoomed":"nope"}}', "utf-8");
    expect(readLayoutPref(cwd)).toEqual(DEFAULT_LAYOUT);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd pi-ext/factory-watch && npm test -- review-surface`
Expected: FAIL — `readLayoutPref` is not exported

- [ ] **Step 3: Implement the helpers**

In `pi-ext/factory-watch/src/review-surface.ts`, add the import and the two functions after `writeSurfacePref`:

```typescript
import { DEFAULT_LAYOUT, normalizeLayout } from "./review-layout.js";
import type { LayoutState } from "./review-layout.js";

// Stored under its own "layout" key in the same file the surface preference
// uses. localStorage is not an option: the review server binds port 0, so
// every review is a new origin and a browser-stored layout would silently
// reset each time.
export function readLayoutPref(cwd: string): LayoutState {
  try {
    const raw = JSON.parse(readFileSync(surfacePrefPath(cwd), "utf-8")) as Record<string, unknown>;
    return normalizeLayout(raw["layout"]);
  } catch {
    return DEFAULT_LAYOUT;
  }
}

export function writeLayoutPref(cwd: string, state: LayoutState): void {
  try {
    const path = surfacePrefPath(cwd);
    mkdirSync(dirname(path), { recursive: true });
    let existing: Record<string, unknown> = {};
    try {
      existing = JSON.parse(readFileSync(path, "utf-8")) as Record<string, unknown>;
    } catch {
      existing = {};
    }
    existing["layout"] = normalizeLayout(state);
    writeFileSync(path, JSON.stringify(existing), "utf-8");
  } catch {
    // best-effort; a failed write just means we don't remember the layout
  }
}
```

Note: `readSurfacePref` casts the parsed file to `Record<string, string>`, which
stops being true once the file holds a nested `layout` object. Widen it to
`Record<string, unknown>`.

Do **not** coerce the value with `String(...)` where it reads
`raw["surface"] ?? raw["review"]`. `value === "browser"` type-checks against an
`unknown` under `--strict` with no cast, and `String(value) === "browser"` would
be strictly looser: a hand-edited `"surface": ["browser"]` stringifies to
`"browser"` and would start selecting the browser surface, where the strict
comparison correctly falls through to `"terminal"`. Widening the cast must not
widen what counts as a valid preference.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd pi-ext/factory-watch && npm test -- review-surface`
Expected: PASS — including the existing surface-preference tests

- [ ] **Step 5: Typecheck and commit**

Run: `cd pi-ext/factory-watch && npm run typecheck`
Expected: no errors

```bash
git add pi-ext/factory-watch/src/review-surface.ts pi-ext/factory-watch/test/review-surface.test.ts
git commit -m "feat(factory-watch): persist the review pane layout server-side"
```

---

### Task 8: Compose the intent into `ReviewPageData` and add the two endpoints

**Files:**
- Modify: `pi-ext/factory-watch/src/review-server.ts`
- Modify: `pi-ext/factory-watch/src/system-cli.ts:239-246` (add `plan_section` to `SystemStory`)
- Modify: `pi-ext/factory-watch/src/index.ts:198-204` (pass `cwd` to the server)
- Test: `pi-ext/factory-watch/test/review-server.test.ts`

**Interfaces:**
- Consumes: `walkIntentChain` (Task 5), `buildSystemContext` (Task 4), `readLayoutPref` (Task 7), `loadSystemStory`/`loadSystemReverse` (existing).
- Produces:
  - `interface ReviewIntent { chain: ReviewChainNode[]; stopsAt: string | null; planSection: { planPath: string; heading: string; html: string } | null; dod: string[]; status: string; requirements: string[] }`
  - `ReviewPageData` gains `intent: ReviewIntent | null` and `layout: LayoutState`.
  - `buildReviewPageData(cwd, startCommit, files, opts)` — `opts` gains optional `deps?: Partial<ReviewPageDeps>`.
  - `startReviewServer(data, opts: { cwd: string; reverse?: typeof loadSystemReverse; writeLayout?: typeof writeLayoutPref })`.

- [ ] **Step 1: Add `plan_section` and `dod` to the story types**

In `pi-ext/factory-watch/src/system-cli.ts`, add `dod: string[];` to the
existing `StoryTask` interface (matching the `storyTask` schema change from
Task 3), then extend the interface at line 239:

```typescript
export interface StoryPlanSection {
  plan_path: string;
  heading: string;
  body: string;
}

export interface SystemStory {
  scope: StoryScopeRef;
  task: StoryTask;
  runs: StoryRun[];
  requirements: string[];
  // The `### Task N:` section of the task's source plan -- the steps the
  // implementer worked from. Null when the task declares no source_plan, the
  // plan is unreadable, or no section matches.
  plan_section: StoryPlanSection | null;
  degraded: boolean;
  degraded_reasons: string[];
}
```

- [ ] **Step 2: Write the failing tests**

Append to `pi-ext/factory-watch/test/review-server.test.ts`:

```typescript
import { walkIntentChain } from "../src/review-intent.js";

const STORY_OK = {
  ok: true as const,
  value: {
    scope: { kind: "task", ref: "task:T-001" },
    task: { id: "T-001", title: "A task", status: "in-review", dod: ["ships"] },
    runs: [], requirements: ["sr:SR-014"],
    plan_section: { plan_path: "docs/superpowers/plans/p.md", heading: "Task 1: A task", body: "Do the thing." },
    degraded: false, degraded_reasons: [],
  },
};

const CONTEXT_OK = {
  context: {},
  graph: {
    nodes: [
      { id: "T-001", kind: "task", title: "A task", path: "tasks/T-001-a.md", exempt: false, deferred: null },
      { id: "plan:p.md", kind: "plan", title: "A plan", path: "docs/superpowers/plans/p.md", exempt: false, deferred: null },
    ],
    edges: [{ src: "T-001", dst: "plan:p.md", kind: "source_plan" }],
    gaps: [], validation: {},
    health: { percent: 0, satisfied: 0, expected: 0, dangling: 0, deferred: 0, proposed: 0, classes: [] },
  },
};

// No cast on the literal: `as never` here would type `okDeps` as `never`, and
// a `never` cannot be spread — every `{ ...okDeps }` below would fail to
// compile. Cast at the call site instead.
const okDeps = {
  story: () => STORY_OK,
  context: () => CONTEXT_OK,
  layout: () => ({ collapsed: [], zoomed: null }),
};

describe("buildReviewPageData intent", () => {
  test("carries the chain, the DoD and the rendered plan section", () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: okDeps as never });
    expect(data.intent?.chain.map((n) => n.id)).toEqual(["plan:p.md", "T-001"]);
    expect(data.intent?.stopsAt).toBe("satisfies");
    expect(data.intent?.dod).toEqual(["ships"]);
    expect(data.intent?.planSection?.html).toContain("Do the thing.");
  });

  test("a failing story leaves the page renderable without an intent", () => {
    const deps = { ...okDeps, story: () => ({ ok: false, error: "uv missing" }) };
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: deps as never });
    expect(data.intent).toBeNull();
    expect(data.files).toEqual(FILES);
  });

  test("a failing graph keeps the plan section and empties the chain", () => {
    const deps = { ...okDeps, context: () => ({ context: {}, graph: null }) };
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: deps as never });
    expect(data.intent?.chain).toEqual([]);
    expect(data.intent?.planSection?.heading).toBe("Task 1: A task");
  });

  test("a null plan section still yields a usable intent", () => {
    const story = { ...STORY_OK, value: { ...STORY_OK.value, plan_section: null } };
    const deps = { ...okDeps, story: () => story };
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: deps as never });
    expect(data.intent?.planSection).toBeNull();
    expect(data.intent?.dod).toEqual(["ships"]);
  });
});

describe("review server endpoints", () => {
  test("/api/why returns the reverse walk for a file", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: okDeps as never });
    const reverse = () => ({ ok: true as const, value: { scope: { kind: "file", ref: "file:a.ts" }, paths: [], degraded: false, degraded_reasons: [] } });
    const srv = await startReviewServer(data, { cwd: "/repo", reverse: reverse as never });
    const res = await fetch(`${srv.url}/api/why?file=a.ts`);
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ scope: { ref: "file:a.ts" } });
    srv.close();
  });

  test("/api/why reports the reason instead of failing the pane", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: okDeps as never });
    const reverse = () => ({ ok: false as const, error: "no manifest" });
    const srv = await startReviewServer(data, { cwd: "/repo", reverse: reverse as never });
    const body = await (await fetch(`${srv.url}/api/why?file=a.ts`)).json();
    expect(body).toMatchObject({ status: "unknown", source: "reverse" });
    srv.close();
  });

  test("/api/layout persists a posted layout", async () => {
    const data = buildReviewPageData("/repo", "abc", FILES, { taskId: "T-001", deps: okDeps as never });
    const written: unknown[] = [];
    const srv = await startReviewServer(data, {
      cwd: "/repo",
      writeLayout: ((_cwd: string, state: unknown) => { written.push(state); }) as never,
    });
    await fetch(`${srv.url}/api/layout`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ collapsed: ["tree"], zoomed: null }),
    });
    expect(written).toEqual([{ collapsed: ["tree"], zoomed: null }]);
    srv.close();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd pi-ext/factory-watch && npm test -- review-server`
Expected: FAIL — `data.intent` is undefined and `startReviewServer` takes one argument

- [ ] **Step 4: Add the types and the intent composition**

In `pi-ext/factory-watch/src/review-server.ts`, add the imports:

```typescript
import { walkIntentChain } from "./review-intent.js";
import type { ReviewChainNode } from "./review-intent.js";
import { buildSystemContext } from "./system-context.js";
import { unknownSource } from "./system-context.js";
import { loadSystemStory, loadSystemReverse } from "./system-cli.js";
import { readLayoutPref, writeLayoutPref } from "./review-surface.js";
import { DEFAULT_LAYOUT, normalizeLayout } from "./review-layout.js";
import type { LayoutState } from "./review-layout.js";
```

and the types:

```typescript
export interface ReviewIntent {
  chain: ReviewChainNode[];
  stopsAt: string | null;
  planSection: { planPath: string; heading: string; html: string } | null;
  // status and dod are duplicated with ReviewTaskContext on purpose: these come
  // from query_story through the ledger, those come from reading the task file
  // directly. The pane prefers these and falls back to those, which is what
  // keeps the panel useful when the navigator is unavailable. A divergence
  // between them is worth seeing, so they are not merged.
  dod: string[];
  status: string;
  requirements: string[];
}

export interface ReviewPageDeps {
  story: typeof loadSystemStory;
  context: typeof buildSystemContext;
  layout: typeof readLayoutPref;
}
```

Extend `ReviewPageData` with `intent: ReviewIntent | null;` and `layout: LayoutState;`.

Add the builder above `buildReviewPageData`:

```typescript
function buildIntent(cwd: string, taskId: string, deps: ReviewPageDeps): ReviewIntent | null {
  const story = deps.story(cwd, `task:${taskId}`);
  if (!story.ok) return null; // navigator unavailable -- the task file panel still renders

  const graph = deps.context(cwd, taskId, defaultSystemContextDeps).graph;
  const walked = graph === null ? { chain: [], stopsAt: null } : walkIntentChain(graph, taskId);
  const section = story.value.plan_section;
  return {
    chain: walked.chain,
    stopsAt: walked.stopsAt,
    planSection: section === null ? null : {
      planPath: section.plan_path,
      heading: section.heading,
      // renderMarkdown escapes its source before emitting markup -- the same
      // trusted renderer the task panel and /review-plans already use.
      html: renderMarkdown(section.body).html,
    },
    dod: story.value.task.dod,
    status: story.value.task.status,
    requirements: story.value.requirements,
  };
}
```

Define `defaultSystemContextDeps` beside it, importing the three loaders the
extracted composition takes:

```typescript
import { loadTraceGraph } from "./trace-cli.js";
import { loadTaskEvidence, runPreflight } from "./evidence-client.js";
import type { SystemContextDeps } from "./system-context.js";

const defaultSystemContextDeps: SystemContextDeps = {
  graph: loadTraceGraph,
  taskEvidence: loadTaskEvidence,
  preflight: runPreflight,
};
```

In `buildReviewPageData`, resolve deps and add the two fields:

```typescript
  const resolved: ReviewPageDeps = {
    story: opts.deps?.story ?? loadSystemStory,
    context: opts.deps?.context ?? buildSystemContext,
    layout: opts.deps?.layout ?? readLayoutPref,
  };
```

then `intent: buildIntent(cwd, opts.taskId, resolved),` and `layout: resolved.layout(cwd),`.

- [ ] **Step 5: Add the endpoints**

Change `startReviewServer`'s signature to
`startReviewServer(data: ReviewPageData, opts: { cwd: string; reverse?: typeof loadSystemReverse; writeLayout?: typeof writeLayoutPref })`
and add these handlers before the final `404`:

```typescript
      if (req.method === "GET" && url.startsWith("/api/why")) {
        const file = new URL(url, "http://127.0.0.1").searchParams.get("file") ?? "";
        const reverse = (opts.reverse ?? loadSystemReverse)(opts.cwd, `file:${file}`);
        res.writeHead(200, { "content-type": "application/json" });
        // A file with no recorded evidence is the normal case for a new file.
        // It is reported as unknown, never as a failed pane.
        res.end(JSON.stringify(reverse.ok ? reverse.value : unknownSource("reverse", reverse.error)));
        return;
      }
      if (req.method === "POST" && url === "/api/layout") {
        let state: LayoutState = DEFAULT_LAYOUT;
        try {
          state = normalizeLayout(JSON.parse(await readBody(req)));
        } catch {
          state = DEFAULT_LAYOUT;
        }
        (opts.writeLayout ?? writeLayoutPref)(opts.cwd, state);
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
        return;
      }
```

- [ ] **Step 6: Update the callers**

`opts` is deliberately **required**, not optional. `cwd` has no safe default:
falling back to `process.cwd()` would serve `/api/why` and `/api/layout` from
whatever directory the process happens to be in, which inside a git worktree is
a different repository — a wrong answer that still looks like a working
feature. A caller that cannot supply `cwd` should fail to compile.

In `pi-ext/factory-watch/src/index.ts:204`, change the call to:

```typescript
              const srv = await startReviewServer(pageData, { cwd: ctx.cwd });
```

Three pre-existing tests in `pi-ext/factory-watch/test/review-server.test.ts`
call `startReviewServer(data)` with one argument and will no longer compile.
Add the second argument to each, changing nothing else — not their assertions,
their names, or their fixtures:

```typescript
    const srv = await startReviewServer(data, { cwd: "/repo" });
```

This is a mechanical call-site update forced by a deliberate signature change,
which is the one edit to a pre-existing test this plan sanctions. Weakening or
retargeting an existing assertion is still forbidden.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd pi-ext/factory-watch && npm test -- review-server`
Expected: PASS — including the four pre-existing `buildReviewPageData` and `startReviewServer` tests, whose assertions are unchanged

- [ ] **Step 8: Full suite and typecheck**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: PASS, no type errors

- [ ] **Step 9: Commit**

```bash
git add pi-ext/factory-watch/src/review-server.ts pi-ext/factory-watch/src/system-cli.ts \
        pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/review-server.test.ts
git commit -m "feat(factory-watch): compose the review intent and serve /api/why and /api/layout"
```

---

### Task 9: Render the intent pane and the collapsible, zoomable layout

**Files:**
- Modify: `pi-ext/factory-watch/src/review-html.ts` (whole file)
- Test: `pi-ext/factory-watch/test/review-html.test.ts`

**Interfaces:**
- Consumes: `ReviewPageData.intent` and `.layout` (Task 8); `columnTemplate`, `PANE_ORDER` semantics (Task 6) — reimplemented inline in the page script, since the served page cannot import modules.
- Produces: `renderReviewHtml(): string`, unchanged signature.

- [ ] **Step 1: Write the failing test**

Create `pi-ext/factory-watch/test/review-html.test.ts`:

```typescript
import { describe, expect, test } from "vitest";
import { renderReviewHtml } from "../src/review-html.js";

describe("renderReviewHtml", () => {
  const html = renderReviewHtml();

  test("declares all four panes", () => {
    for (const pane of ["context", "tree", "diff", "comments"]) {
      expect(html).toContain(`data-pane="${pane}"`);
    }
  });

  test("gives every pane a collapse control", () => {
    expect(html.match(/class="pane-toggle"/g) ?? []).toHaveLength(4);
  });

  test("drives the grid from a column template rather than a fixed one", () => {
    expect(html).not.toContain("grid-template-columns: 240px 1fr 320px");
    expect(html).toContain("gridTemplateColumns");
  });

  test("no longer caps the task context at 35vh", () => {
    expect(html).not.toContain("35vh");
  });

  test("posts layout changes to the server rather than using localStorage", () => {
    expect(html).toContain("/api/layout");
    expect(html).not.toContain("localStorage");
  });

  test("fetches per-file provenance lazily from /api/why", () => {
    expect(html).toContain("/api/why?file=");
  });

  test("renders the fan-out marker so a partial chain is never silent", () => {
    // walkIntentChain counts the requirements and specs it did not show. A page
    // that computes that count and never renders it leaves the reviewer looking
    // at one of two satisfied requirements with no sign the second exists --
    // precisely the failure the count was added to prevent.
    expect(html).toMatch(/n\.alternatives/);
    expect(html).toContain("more)");
  });

  test("the only non-clearing innerHTML assignment is the rendered plan section", () => {
    // renderMarkdown output is the sole trusted HTML on this page; every other
    // server value must reach the DOM through createTextNode.
    const assignments = html.match(/innerHTML = (?!'')[^;\n]+/g) ?? [];
    expect(assignments).toEqual(["innerHTML = intent.planSection.html"]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd pi-ext/factory-watch && npm test -- review-html`
Expected: FAIL — no `data-pane` attributes, `35vh` still present

- [ ] **Step 3: Replace the stylesheet and body**

In `pi-ext/factory-watch/src/review-html.ts`, replace the `<style>` block's layout rules and the `<body>` markup with:

```html
<style>
  :root { color-scheme: light dark; }
  body { font: 13px/1.5 ui-monospace, monospace; margin: 0; display: grid;
         grid-template-rows: auto auto 1fr; height: 100vh; }
  #panes { display: grid; grid-template-columns: 1.2fr 240px 2fr 320px; overflow: hidden; }
  .pane { display: flex; flex-direction: column; overflow: hidden; border-left: 1px solid #8884; }
  .pane-head { display: flex; align-items: center; gap: 4px; padding: 2px 4px;
               border-bottom: 1px solid #8884; font-size: 11px; opacity: .8; user-select: none; }
  .pane-toggle { cursor: pointer; border: 0; background: none; font: inherit; padding: 0 2px; }
  .pane-body { overflow: auto; padding: 8px; flex: 1; }
  .pane.collapsed .pane-body, .pane.zoomed-out { display: none; }
  .pane.collapsed .pane-label { writing-mode: vertical-rl; }
  .row { white-space: pre-wrap; padding-left: 18px; position: relative; }
  .row.add { background: rgba(0,200,0,.12); }
  .row.del { background: rgba(220,0,0,.12); }
  .row.hunk { color: #6ab; }
  .row .plus { position: absolute; left: 2px; cursor: pointer; opacity: 0; }
  .row:hover .plus { opacity: .6; }
  .row .plus:hover { opacity: 1; }
  .banner { color: #c80; padding: 4px 8px; }
  .guide { padding: 4px 8px; border-bottom: 1px solid #8884; white-space: pre-wrap;
           font-size: 12px; opacity: .9; }
  .guide:empty { display: none; }
  .chain li { list-style: none; }
  .chain .hop { opacity: .75; font-size: 11px; }
  .stops { color: #c80; font-size: 11px; margin: 4px 0; }
  #tree .file { cursor: pointer; padding: 2px 4px; white-space: nowrap; }
  #tree .file.active { background: #8884; }
  .why { font-size: 11px; opacity: .8; padding: 2px 8px; border-bottom: 1px solid #8884; }
  .plan pre { overflow: auto; padding: 6px; background: #8882; }
  .plan code { background: #8882; }
  button { font: inherit; margin: 4px 4px 0 0; }
  .cmt { border: 1px solid #8884; padding: 4px; margin: 4px 0; }
</style>
```

```html
<body>
  <div class="banner" id="banner"></div>
  <div class="guide" id="guide"></div>
  <div id="panes">
    <section class="pane" data-pane="context">
      <div class="pane-head"><button class="pane-toggle">&#9662;</button>
        <span class="pane-label">1 Task context</span></div>
      <div class="pane-body" id="context"></div>
    </section>
    <section class="pane" data-pane="tree">
      <div class="pane-head"><button class="pane-toggle">&#9662;</button>
        <span class="pane-label">2 Files</span></div>
      <div class="pane-body" id="tree"></div>
    </section>
    <section class="pane" data-pane="diff">
      <div class="pane-head"><button class="pane-toggle">&#9662;</button>
        <span class="pane-label">3 Diff</span></div>
      <div class="why" id="why"></div>
      <div class="pane-body" id="diff"></div>
    </section>
    <section class="pane" data-pane="comments">
      <div class="pane-head"><button class="pane-toggle">&#9662;</button>
        <span class="pane-label">4 Review</span></div>
      <div class="pane-body">
        <div><strong>Comments (<span id="count">0</span>)</strong></div>
        <div style="opacity:.7;font-size:11px;margin:2px 0 8px;">hover a diff line, click + to comment</div>
        <div id="cmts"></div>
        <hr>
        <button id="approve">Approve</button>
        <button id="reject">Reject</button>
        <div id="done" hidden>Decision sent — you can close this tab.</div>
      </div>
    </section>
  </div>
```

- [ ] **Step 4: Add the layout controller to the page script**

Insert into the page's `<script>`, after `const data = await (await fetch('/api/review')).json();`:

```javascript
  const PANES = ['context', 'tree', 'diff', 'comments'];
  const RAIL = '28px';
  const NATURAL = { context: '1.2fr', tree: '240px', diff: '2fr', comments: '320px' };
  let layout = data.layout || { collapsed: [], zoomed: null };

  function applyLayout() {
    const grid = document.getElementById('panes');
    grid.style.gridTemplateColumns = layout.zoomed
      ? PANES.map(p => p === layout.zoomed ? '1fr' : '0px').join(' ')
      : PANES.map(p => layout.collapsed.includes(p) ? RAIL : NATURAL[p]).join(' ');
    for (const el of document.querySelectorAll('.pane')) {
      const id = el.dataset.pane;
      el.classList.toggle('collapsed', !layout.zoomed && layout.collapsed.includes(id));
      el.classList.toggle('zoomed-out', Boolean(layout.zoomed) && layout.zoomed !== id);
    }
    fetch('/api/layout', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(layout),
    }).catch(() => {}); // a failed write just means we don't remember it
  }

  for (const el of document.querySelectorAll('.pane')) {
    el.querySelector('.pane-toggle').onclick = () => {
      const id = el.dataset.pane;
      layout.collapsed = layout.collapsed.includes(id)
        ? layout.collapsed.filter(p => p !== id)
        : layout.collapsed.concat([id]);
      applyLayout();
    };
  }
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    const index = ['1', '2', '3', '4'].indexOf(e.key);
    if (index >= 0) { const p = PANES[index]; layout.zoomed = layout.zoomed === p ? null : p; applyLayout(); }
    else if (e.key === 'Escape') { layout.zoomed = null; applyLayout(); }
    else if (e.key === '?') { alert('1-4 zoom a pane, Esc restores, click a pane header to collapse it'); }
  });
  applyLayout();
```

- [ ] **Step 5: Replace `renderTask` with `renderContext`**

Replace the existing `renderTask` function and its call with:

```javascript
  // Intent first: what this change was supposed to accomplish, then the task
  // file as a fallback for when the navigator is unavailable.
  function renderContext() {
    const box = document.getElementById('context');
    box.innerHTML = '';
    const line = (text, cls) => {
      const d = document.createElement('div');
      if (cls) d.className = cls;
      d.appendChild(document.createTextNode(text));
      box.appendChild(d);
      return d;
    };
    const intent = data.intent;
    if (intent && intent.chain.length) {
      const list = document.createElement('ul');
      list.className = 'chain';
      intent.chain.forEach((n, depth) => {
        const item = document.createElement('li');
        // A hop with further candidates says so. Showing one of two satisfied
        // requirements with no marker is the partial picture this pane exists
        // to prevent.
        const more = n.alternatives ? '  (+' + n.alternatives + ' more)' : '';
        item.appendChild(document.createTextNode('  '.repeat(depth) + n.kind + ' · ' + n.id + ' — ' + n.title + more));
        list.appendChild(item);
      });
      box.appendChild(list);
    }
    if (intent && intent.stopsAt) {
      line('stops at: ' + intent.stopsAt + ' (nothing recorded links further up)', 'stops');
    }
    const task = data.task;
    if (task) line(task.id + ' — ' + task.title);
    const status = (intent && intent.status) || (task && task.status) || 'unknown';
    line('status: ' + status + (task ? ' · ' + task.path : ''));

    const dod = (intent && intent.dod.length ? intent.dod : (task ? task.dod : [])) || [];
    if (dod.length) {
      line('Definition of done:');
      const list = document.createElement('ul');
      dod.forEach((item) => {
        const row = document.createElement('li');
        row.appendChild(document.createTextNode(item));
        list.appendChild(row);
      });
      box.appendChild(list);
    }
    if (intent && intent.planSection) {
      line('From plan · ' + intent.planSection.heading + ' · ' + intent.planSection.planPath);
      const body = document.createElement('div');
      body.className = 'plan';
      // renderMarkdown escaped this server-side; it is the only trusted HTML here.
      body.innerHTML = intent.planSection.html;
      box.appendChild(body);
    } else {
      line('(no plan section resolved for this task)', 'stops');
    }
  }
  renderContext();
```

- [ ] **Step 6: Fetch per-file provenance on file click**

Add this function and call it at the end of `renderTree`'s click handler (`el.onclick = () => { active = f.path; renderAll(); showWhy(f.path); }`):

```javascript
  const whyCache = {};
  async function showWhy(path) {
    const box = document.getElementById('why');
    box.textContent = 'why this file: …';
    if (!(path in whyCache)) {
      try {
        whyCache[path] = await (await fetch('/api/why?file=' + encodeURIComponent(path))).json();
      } catch (err) {
        whyCache[path] = { status: 'unknown', error: String(err) };
      }
    }
    const value = whyCache[path];
    if (value.status === 'unknown') { box.textContent = 'why this file: unknown (' + value.error + ')'; return; }
    const paths = value.paths || [];
    box.textContent = paths.length === 0
      ? 'why this file: no recorded evidence names it'
      : 'why this file: ' + paths.map(p => (p.task_id || '?') + (p.stops_at ? ' (stops at ' + p.stops_at + ')' : '')).join(', ');
  }
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd pi-ext/factory-watch && npm test -- review-html`
Expected: PASS (8 tests)

- [ ] **Step 8: Full suite, typecheck, and manual verification**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: PASS, no type errors

Then verify by hand — this is the deliverable, and no unit test proves it reads well:

1. Start a review through `/factory-watch` on a task in `human-review`, choosing the Browser surface.
2. Confirm the context pane shows the chain, the DoD, and the plan section prose — not a `Full steps: …` pointer.
3. Collapse each pane by clicking its header; confirm the others reflow.
4. Press `1`, then `Esc`; confirm the context pane fills the window and returns.
5. Click a second file; confirm the "why this file" line updates.
6. Close the tab, re-run the review, confirm the collapsed panes came back.

- [ ] **Step 9: Commit**

```bash
git add pi-ext/factory-watch/src/review-html.ts pi-ext/factory-watch/test/review-html.test.ts
git commit -m "feat(factory-watch): show task intent and collapsible panes in the browser review"
```

---

## Verification

After Task 9, the whole suite must pass from a clean state:

```bash
uv run pytest tests/unit -q
cd pi-ext/factory-watch && npm test && npm run typecheck
```

The manual checks in Task 9 Step 8 are required; the layout and readability of the pane are the point of this work and no unit test covers them.
