# Already-Done Task Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `factory-run` is given a task whose work already exists, context-gather recognizes it and routes to review (skipping dev, still running validation) for a clean human-confirmed close, instead of rejecting.

**Architecture:** A new `NodeOutcome.ALREADY_DONE` emitted by `run_context_gatherer` (from an `already_done` flag in the agent's manifest) makes `run_task` skip only the dev node on the first review-loop pass. Validation and review still run, so completion still requires the sim gate + review gates to pass. In interactive mode the existing human-review approval is the confirmation; its diff shows the *implementing* commits for the task's deliverables (not the empty `start_commit..HEAD` range), under an "already complete" banner.

**Tech Stack:** Python 3 (orchestrator, `uv`/`pytest`), TypeScript (pi extension, `node`/`vitest`), git.

## Global Constraints

- Python tests: `uv run python -m pytest <path> -v`. Mark unit tests with `pytestmark = pytest.mark.unit`.
- TS tests: from `pi-ext/factory-watch/`, `npx vitest run <path>`. Typecheck: `npx tsc --noEmit`.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- `.ts` relative imports in files also loaded via `node <file>.ts` (review-overlay.ts, review-diff.ts, mission-control-*.ts) MUST use `.ts` specifiers; files imported only under vitest (index.ts, status-format.ts) use `.js` specifiers. Follow the specifier already used by the file you edit.
- No `additionalProperties: false` on the manifest schema — extra fields like `already_done` are already tolerated; no schema change.
- `Task` dataclass signature: `Task(id, title, status, dod, body, path)`.

---

### Task 1: `NodeOutcome.ALREADY_DONE` + context-gather detection

**Files:**
- Modify: `src/factory/orchestrator/types.py` (add enum member)
- Modify: `src/factory/orchestrator/nodes.py` (`run_context_gatherer` detection branch)
- Modify: `src/factory/orchestrator/roles.py` (`ROLE_PROMPTS[CONTEXT_GATHERER]` instruction)
- Test: `tests/unit/orchestrator/test_nodes_context_dev.py`

**Interfaces:**
- Produces: `NodeOutcome.ALREADY_DONE` (value `"already-done"`); `run_context_gatherer(...)` returns `(NodeOutcome.ALREADY_DONE, manifest, NodeEvent("context-gather", "already-done", attempt))` when `manifest.get("already_done")` is truthy.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/orchestrator/test_nodes_context_dev.py`:

```python
def test_context_gatherer_already_done(tmp_path):
    write_skill_stubs(tmp_path)
    m = _manifest(tmp_path)
    m["already_done"] = True
    m["already_done_reason"] = "deliverables exist and match the DoD"
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.ALREADY_DONE
    assert manifest is not None
    assert ev.result == "already-done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_nodes_context_dev.py::test_context_gatherer_already_done -v`
Expected: FAIL — `AttributeError: ALREADY_DONE` (enum member missing).

- [ ] **Step 3: Add the enum member**

In `src/factory/orchestrator/types.py`, extend `NodeOutcome`:

```python
class NodeOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REJECT = "reject"
    CHANGES = "changes-requested"
    ESCALATE = "escalate"
    ALREADY_DONE = "already-done"
```

- [ ] **Step 4: Add the detection branch in `run_context_gatherer`**

In `src/factory/orchestrator/nodes.py`, inside `run_context_gatherer`, immediately after `manifest = result.output` and BEFORE the `if manifest.get("reject"):` block:

```python
        manifest = result.output
        if manifest.get("already_done"):
            reason = manifest.get("already_done_reason") or "task deliverables already exist"
            status.report(
                task_id=task.id, node="context-gather", node_state="already-done",
                attempt=attempt, max_attempts=max_attempts,
                handoff="→ review: task appears already complete",
                session_id=result.session_id, summary=reason,
            )
            return (
                NodeOutcome.ALREADY_DONE,
                manifest,
                NodeEvent("context-gather", "already-done", attempt, {}),
            )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run python -m pytest tests/unit/orchestrator/test_nodes_context_dev.py -v`
Expected: PASS (new test passes; existing `test_context_gatherer_pass`/`_reject` unaffected).

- [ ] **Step 6: Add the prompt instruction**

In `src/factory/orchestrator/roles.py`, replace the `ROLE_PROMPTS[AgentRole.CONTEXT_GATHERER]` string with:

```python
    AgentRole.CONTEXT_GATHERER: (
        "You verify that spec, plan, prior session, and this task are coherent and "
        "that context is complete. Emit ONLY a context manifest as a fenced ```json block "
        "matching the context_manifest schema. If you cannot prove coherence, set "
        "coherence.proven=false and populate reject.\n"
        "FIRST, before anything else: check whether this task's deliverables (the "
        "`Create:`/`Modify:`/`Test:` paths in the task body) already exist and satisfy "
        "the Definition of Done. Read files with the read/view tool — NOT with bash (bash "
        "is disabled for your role). If the work already appears complete, add "
        "`\"already_done\": true` and a one-line `\"already_done_reason\"` to the manifest "
        "JSON; coherence need not be proven in that case."
    ),
```

- [ ] **Step 7: Run the full node + prompt test suite**

Run: `uv run python -m pytest tests/unit/orchestrator/ -v`
Expected: PASS (no regressions).

- [ ] **Step 8: Commit**

```bash
git add src/factory/orchestrator/types.py src/factory/orchestrator/nodes.py src/factory/orchestrator/roles.py tests/unit/orchestrator/test_nodes_context_dev.py
git commit -m "feat: context-gather emits ALREADY_DONE when a task's work already exists"
```

---

### Task 2: `parse_deliverables` helper

**Files:**
- Create: `src/factory/orchestrator/deliverables.py`
- Test: `tests/unit/orchestrator/test_deliverables.py`

**Interfaces:**
- Produces: `parse_deliverables(task_body: str) -> list[str]` — returns the backticked paths from `Create:`/`Modify:`/`Test:` lines, in order, de-duplicated.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/orchestrator/test_deliverables.py`:

```python
import pytest
from factory.orchestrator.deliverables import parse_deliverables

pytestmark = pytest.mark.unit

BODY = """- Create: `src/drone/interfaces.py`
- Create: `src/drone/fake_flight_controller.py`
- Test: `tests/unit/drone/test_interfaces.py`

Full steps: docs/plan.md, Task 1."""


def test_parses_create_and_test_paths():
    assert parse_deliverables(BODY) == [
        "src/drone/interfaces.py",
        "src/drone/fake_flight_controller.py",
        "tests/unit/drone/test_interfaces.py",
    ]


def test_parses_modify_lines_and_dedupes():
    body = "- Modify: `a.py`\n- Test: `a.py`\n- prose line, ignored"
    assert parse_deliverables(body) == ["a.py"]


def test_ignores_bodies_without_deliverables():
    assert parse_deliverables("just some prose\nno paths here") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_deliverables.py -v`
Expected: FAIL — `ModuleNotFoundError: factory.orchestrator.deliverables`.

- [ ] **Step 3: Implement the helper**

Create `src/factory/orchestrator/deliverables.py`:

```python
from __future__ import annotations

import re

# Matches lines like "- Create: `path`", "- Modify: `path`", "- Test: `path`"
# (case-insensitive verb, optional leading list marker/whitespace).
_LINE = re.compile(r"^\s*[-*]?\s*(?:create|modify|test)\s*:\s*`([^`]+)`", re.IGNORECASE)


def parse_deliverables(task_body: str) -> list[str]:
    """Extract deliverable file paths from a task body's Create/Modify/Test
    lines, in order of appearance, de-duplicated."""
    out: list[str] = []
    seen: set[str] = set()
    for line in task_body.splitlines():
        m = _LINE.match(line)
        if m:
            path = m.group(1).strip()
            if path and path not in seen:
                seen.add(path)
                out.append(path)
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/unit/orchestrator/test_deliverables.py -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/deliverables.py tests/unit/orchestrator/test_deliverables.py
git commit -m "feat: parse_deliverables helper for task Create/Modify/Test paths"
```

---

### Task 3: `run_task` routing + status `already_done`/`deliverables` fields

**Files:**
- Modify: `src/factory/orchestrator/status.py` (`report()` signatures + entry dict on all four implementers)
- Modify: `src/factory/orchestrator/runner.py` (`run_task` routing)
- Test: `tests/unit/orchestrator/test_run_next.py`, `tests/unit/orchestrator/test_status.py`

**Interfaces:**
- Consumes: `NodeOutcome.ALREADY_DONE` (Task 1); `parse_deliverables` (Task 2).
- Produces: on the already-done human-review block, the `human-review` pipeline entry carries `already_done: true` and `deliverables: [...]`. `report()` gains keyword args `already_done: bool = False` and `deliverables: list[str] | None = None`.

- [ ] **Step 1: Write the failing status test**

Add to `tests/unit/orchestrator/test_status.py`:

```python
def test_report_records_already_done_and_deliverables(tmp_path):
    path = tmp_path / "status.json"
    reporter = FileStatusReporter(path=path, session_id="run-1")
    reporter.report(task_id="T-1", node="human-review", node_state="blocked",
                    attempt=1, max_attempts=1, start_commit="abc",
                    already_done=True, deliverables=["src/x.py", "tests/test_x.py"])
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["pipeline"][0]
    assert entry["already_done"] is True
    assert entry["deliverables"] == ["src/x.py", "tests/test_x.py"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_status.py::test_report_records_already_done_and_deliverables -v`
Expected: FAIL — `TypeError: report() got an unexpected keyword argument 'already_done'`.

- [ ] **Step 3: Add the params to all four `report()` implementers**

In `src/factory/orchestrator/status.py`, add these two keyword-only params (after `start_commit`) to the `report` method of `StatusReporter` (Protocol), `NullStatusReporter`, `FileStatusReporter`, and `FakeStatusReporter`:

```python
        already_done: bool = False,
        deliverables: list[str] | None = None,
```

In `FileStatusReporter.report`, add to the `entry` dict (before `"updated_at"`):

```python
            "already_done": already_done,
            "deliverables": deliverables or [],
```

In `FakeStatusReporter.report`, add to the appended dict:

```python
                "already_done": already_done,
                "deliverables": deliverables or [],
```

(`NullStatusReporter` and the Protocol just need the signature; no body change.)

- [ ] **Step 4: Run the status test to verify it passes**

Run: `uv run python -m pytest tests/unit/orchestrator/test_status.py -v`
Expected: PASS (new + existing, including the sticky-field tests).

- [ ] **Step 5: Write the failing routing tests**

Add to `tests/unit/orchestrator/test_run_next.py` (reuse the file's existing imports/fixtures for `run_task`, `FakeAgentBackend`, `FakeGateRunner`, `FakeStatusReporter`, `FakeHumanReviewGate`, `Task`; if a helper below isn't already imported there, add the import). These assert routing off `ALREADY_DONE`:

```python
def test_already_done_skips_dev_runs_validation_and_review(tmp_path):
    write_skill_stubs(tmp_path)
    task = Task("T-1", "t", "todo", ["c"], "- Create: `src/x.py`", Path("t"))
    m = {"task_id": "T-1", "generated_by": "context-gatherer",
         "generated_at": "2026-07-16T14:32:10Z",
         "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
         "context": {"task": "tasks/T-1.md", "source_files": [], "skills": []},
         "reject": None, "already_done": True}
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "T-1.md").write_text("dod", encoding="utf-8")
    backend = FakeAgentBackend({
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)],
        # dev MUST NOT be consumed on the already-done first pass; a review PASS
        # payload closes the task before any dev call.
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    })
    gates = FakeGateRunner({"sim": [0], "full": [0]})
    status = FakeStatusReporter()
    result = run_task(tmp_path, backend, gates, status=status, task=task)
    nodes = [c["node"] for c in status.calls]
    assert "validation" in nodes           # validation ran
    assert result.outcome == "completed"    # review PASS closed it
    # dev never reported (skipped on the already-done first pass)
    assert "dev" not in nodes
```

(If `run_task`'s signature in this file's existing tests differs — e.g. it is called via `run_next` — mirror that call convention instead; the assertion set stays the same.)

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_run_next.py::test_already_done_skips_dev_runs_validation_and_review -v`
Expected: FAIL — currently `ALREADY_DONE` is treated by `run_task`'s `if c_outcome == REJECT or manifest is None` guard as *not* reject (falls through), then dev runs on the first pass, consuming/needing a dev script; the assertion `"dev" not in nodes` fails.

- [ ] **Step 7: Implement the routing in `run_task`**

In `src/factory/orchestrator/runner.py`, in `run_task`, after the context-gather call and its reject guard, add the flag; then guard the dev call and the human-review report. Concretely:

After `_report_node(status, task.id, c_ev, c_ev.attempts)` (the non-reject context-gather report), add:

```python
    already_done = c_outcome == NodeOutcome.ALREADY_DONE
```

Change the dev call at the top of the `for` loop from:

```python
    for _ in range(max_review_cycles):
        iterations += 1

        d_outcome, d_ev = run_dev(...)
        events.append(d_ev)
        if d_outcome == NodeOutcome.ESCALATE:
            ...
        _report_node(status, task.id, d_ev, max_dev_iters)
```

to (skip dev only on the already-done first pass):

```python
    for i in range(max_review_cycles):
        iterations += 1

        if not (already_done and i == 0):
            d_outcome, d_ev = run_dev(
                backend, gates, task, manifest, kb_entries, repo_root, max_dev_iters, feedback,
                transcript_dir=transcript_dir, status=status,
            )
            events.append(d_ev)
            if d_outcome == NodeOutcome.ESCALATE:
                _report_node(status, task.id, d_ev, max_dev_iters, outcome="escalated")
                return TaskResult(task.id, task.title, "escalated", iterations, events, False, manifest)
            _report_node(status, task.id, d_ev, max_dev_iters)
```

Validation and review below stay exactly as they are (validation always runs). Finally, in the review-PASS + human-review block, pass the already-done metadata to the "blocked" report. Change:

```python
                status.report(
                    task_id=task.id, node="human-review", node_state="blocked",
                    attempt=1, max_attempts=1, handoff="waiting for you to review the diff",
                    start_commit=start_commit,
                )
```

to:

```python
                status.report(
                    task_id=task.id, node="human-review", node_state="blocked",
                    attempt=1, max_attempts=1,
                    handoff=("task appears already complete — approve to mark done"
                             if already_done else "waiting for you to review the diff"),
                    start_commit=start_commit,
                    already_done=already_done,
                    deliverables=parse_deliverables(task.body) if already_done else [],
                )
```

Add the import at the top of `runner.py`:

```python
from factory.orchestrator.deliverables import parse_deliverables
```

- [ ] **Step 8: Add the self-correct + auto-mode tests**

Add to `tests/unit/orchestrator/test_run_next.py`:

```python
def test_already_done_but_sim_fails_falls_through_to_dev(tmp_path):
    write_skill_stubs(tmp_path)
    task = Task("T-1", "t", "todo", ["c"], "- Create: `src/x.py`", Path("t"))
    m = {"task_id": "T-1", "generated_by": "context-gatherer",
         "generated_at": "2026-07-16T14:32:10Z",
         "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
         "context": {"task": "tasks/T-1.md", "source_files": [], "skills": []},
         "reject": None, "already_done": True}
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "T-1.md").write_text("dod", encoding="utf-8")
    backend = FakeAgentBackend({
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)],
        AgentRole.DEV: [AgentResult(True, {})],  # consumed on iteration 2
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    })
    # sim fails first pass -> loop back; unit green so dev passes; sim green 2nd pass
    gates = FakeGateRunner({"sim": [1, 0], "unit": [0], "full": [0]})
    status = FakeStatusReporter()
    result = run_task(tmp_path, backend, gates, status=status, task=task)
    nodes = [c["node"] for c in status.calls]
    assert "dev" in nodes               # dev ran on the self-correct pass
    assert result.outcome == "completed"
```

- [ ] **Step 9: Run the routing tests to verify they pass**

Run: `uv run python -m pytest tests/unit/orchestrator/test_run_next.py -v`
Expected: PASS (both new tests + existing).

- [ ] **Step 10: Run the whole orchestrator suite**

Run: `uv run python -m pytest tests/unit/orchestrator/ -v`
Expected: PASS (no regressions).

- [ ] **Step 11: Commit**

```bash
git add src/factory/orchestrator/status.py src/factory/orchestrator/runner.py tests/unit/orchestrator/test_run_next.py tests/unit/orchestrator/test_status.py
git commit -m "feat: run_task routes ALREADY_DONE to review (skip dev, keep validation) with human-review metadata"
```

---

### Task 4: TS status types — `already_done` + `deliverables`

**Files:**
- Modify: `pi-ext/factory-watch/src/status-format.ts` (`PipelineEntry` interface)
- Test: `pi-ext/factory-watch/test/status-format.test.ts`

**Interfaces:**
- Produces: `PipelineEntry.already_done?: boolean` and `PipelineEntry.deliverables?: string[]`, readable off a parsed status record.

- [ ] **Step 1: Write the failing test**

Add to `pi-ext/factory-watch/test/status-format.test.ts` (match the file's existing import style):

```typescript
test("parseStatus surfaces already_done and deliverables on a pipeline entry", () => {
  const raw = JSON.stringify({
    session_id: "s1", task_id: "T-1", current_node: "human-review", current_state: "blocked",
    started_at: "t", updated_at: "t",
    pipeline: [{
      node: "human-review", node_state: "blocked", attempt: 1, max_attempts: 1,
      snippet: "", outcome: null, handoff: null, updated_at: "t",
      already_done: true, deliverables: ["src/x.py"],
    }],
  });
  const rec = parseStatus(raw)!;
  expect(rec.pipeline[0]!.already_done).toBe(true);
  expect(rec.pipeline[0]!.deliverables).toEqual(["src/x.py"]);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run (from `pi-ext/factory-watch/`): `npx vitest run test/status-format.test.ts`
Expected: FAIL — `tsc`/type error: `already_done` does not exist on `PipelineEntry` (the test reads properties the interface doesn't declare).

- [ ] **Step 3: Add the optional fields**

In `pi-ext/factory-watch/src/status-format.ts`, add to the `PipelineEntry` interface (after `start_commit?`):

```typescript
  already_done?: boolean;
  deliverables?: string[];
```

- [ ] **Step 4: Run the test + typecheck to verify pass**

Run: `npx vitest run test/status-format.test.ts && npx tsc --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/status-format.ts pi-ext/factory-watch/test/status-format.test.ts
git commit -m "feat: PipelineEntry carries already_done + deliverables"
```

---

### Task 5: `review-diff.ts` implementing-diff functions

**Files:**
- Modify: `pi-ext/factory-watch/src/review-diff.ts`
- Test: `pi-ext/factory-watch/test/review-diff.integration.test.ts`

**Interfaces:**
- Consumes: `FileStat` (existing, in review-diff.ts).
- Produces:
  - `computeImplementingFiles(cwd: string, deliverables: string[]): FileStat[]` — for each deliverable path, the numstat/status of the last commit that touched it.
  - `computeImplementingFileDiffText(cwd: string, file: string): string` — the patch of the last commit that touched `file`, restricted to that file.

- [ ] **Step 1: Write the failing integration test**

Add to `pi-ext/factory-watch/test/review-diff.integration.test.ts` (it already builds a temp git repo; reuse its helper for making commits — mirror the existing setup in that file). New cases:

```typescript
test("computeImplementingFiles reports the last commit's stats for each deliverable", () => {
  // repo: commit a.py (added), then commit b.py (added). Deliverables [a.py, b.py].
  const files = computeImplementingFiles(repo, ["a.py", "b.py"]);
  const paths = files.map((f) => f.path).sort();
  expect(paths).toEqual(["a.py", "b.py"]);
  expect(files.every((f) => f.added > 0)).toBe(true);
});

test("computeImplementingFileDiffText returns the adding commit's patch for a file", () => {
  const text = computeImplementingFileDiffText(repo, "a.py");
  expect(text).toContain("a.py");
  expect(text).toMatch(/^\+/m); // has added lines
});
```

(Import both new functions at the top of the test file alongside the existing `computeReviewFiles` import.)

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run test/review-diff.integration.test.ts`
Expected: FAIL — `computeImplementingFiles is not a function` / import error.

- [ ] **Step 3: Implement the functions**

Append to `pi-ext/factory-watch/src/review-diff.ts`:

```typescript
// The "implementing diff" for an already-done task: for each deliverable,
// the last commit that touched it (that file only). Used instead of the
// start_commit..working-tree range, which is empty when the work was
// committed before the run started.
export function computeImplementingFiles(cwd: string, deliverables: string[]): FileStat[] {
  const out: FileStat[] = [];
  for (const file of deliverables) {
    // -1: last commit touching the path; --numstat --format= : just the stat line.
    const numstat = spawnSync(
      "git", ["log", "-1", "--numstat", "--format=", "--", file],
      { cwd, encoding: "utf-8" },
    );
    const stats = parseDiffStat(numstat.stdout);
    const nameStatus = spawnSync(
      "git", ["log", "-1", "--name-status", "--format=", "--", file],
      { cwd, encoding: "utf-8" },
    );
    const statuses = parseNameStatus(nameStatus.stdout);
    for (const entry of stats) {
      out.push({ ...entry, status: statuses.get(entry.path) ?? entry.status });
    }
  }
  return out;
}

export function computeImplementingFileDiffText(cwd: string, file: string): string {
  const result = spawnSync(
    "git", ["log", "-1", "-p", "--format=", "--", file],
    { cwd, encoding: "utf-8" },
  );
  return result.stdout;
}
```

`parseNameStatus` is currently module-private; if TypeScript reports it unused-after-export or the function needs to be reachable, it already exists in this file — no change beyond calling it. (It is defined above `computeReviewFiles`.)

- [ ] **Step 4: Run the test + typecheck to verify pass**

Run: `npx vitest run test/review-diff.integration.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/review-diff.ts pi-ext/factory-watch/test/review-diff.integration.test.ts
git commit -m "feat: implementing-diff computation for already-done deliverables"
```

---

### Task 6: Wire already-done review — banner + implementing diff

**Files:**
- Modify: `pi-ext/factory-watch/src/review-overlay.ts` (`ReviewOverlay` mode/banner; `runReviewLoop` opts)
- Modify: `pi-ext/factory-watch/src/index.ts` (`launchInteractiveReview` branch)
- Test: `pi-ext/factory-watch/test/review-overlay.test.ts`, `pi-ext/factory-watch/test/handler.test.ts`

**Interfaces:**
- Consumes: `computeImplementingFiles`, `computeImplementingFileDiffText` (Task 5); `PipelineEntry.already_done`/`deliverables` (Task 4).
- Produces: `runReviewLoop(ui, cwd, taskId, startCommit, files, opts?)` where `opts?: { implementing?: boolean; banner?: string }`. When `implementing` is true, per-file diffs use `computeImplementingFileDiffText` and the summary shows `banner`.

- [ ] **Step 1: Write the failing overlay test**

Add to `pi-ext/factory-watch/test/review-overlay.test.ts` (match its existing construction of `ReviewOverlay`; it passes `(files, comments, tui, cwd, startCommit, onAction)` — add the two new trailing args):

```typescript
test("ReviewOverlay renders the banner and uses the implementing diff when in implementing mode", () => {
  const files = [{ path: "a.py", status: "A" as const, added: 3, removed: 0 }];
  const overlay = new ReviewOverlay(
    files, new Map(), { terminal: { rows: 20 } }, "/repo", "", () => {},
    { implementing: true, banner: "This task appears already complete" },
  );
  const summary = overlay.render(80).join("\n");
  expect(summary).toContain("This task appears already complete");
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run test/review-overlay.test.ts`
Expected: FAIL — constructor takes 6 args, not 8 (type/arity error), and the banner text is absent.

- [ ] **Step 3: Extend `ReviewOverlay`**

In `pi-ext/factory-watch/src/review-overlay.ts`:

Add the implementing-diff import to the existing `./review-diff.ts` import line:

```typescript
import { computeFileDiffText, computeImplementingFileDiffText } from "./review-diff.ts";
```

Add two fields and two constructor params (explicit assignment, matching the file's no-parameter-properties rule):

```typescript
  private readonly implementing: boolean;
  private readonly banner: string;
```

Constructor — add trailing params `opts` and assign:

```typescript
  constructor(
    files: FileStat[],
    comments: Map<string, string>,
    tui: TuiLike,
    cwd: string,
    startCommit: string,
    onAction: (action: ReviewAction) => void,
    opts: { implementing?: boolean; banner?: string } = {},
  ) {
    this.files = files;
    this.comments = comments;
    this.tui = tui;
    this.cwd = cwd;
    this.startCommit = startCommit;
    this.onAction = onAction;
    this.implementing = opts.implementing ?? false;
    this.banner = opts.banner ?? "";
  }
```

In `diffLinesFor`, choose the diff source:

```typescript
      const diffText = this.implementing
        ? computeImplementingFileDiffText(this.cwd, file.path)
        : computeFileDiffText(this.cwd, this.startCommit, file.path);
```

In `render`, at the top of the `summary` branch, prepend the banner when set:

```typescript
    if (this.view.mode === "summary") {
      const lines: string[] = [];
      if (this.banner) {
        lines.push(this.banner, "");
      }
      lines.push(`Task: ${this.files.length} files changed`, "");
      this.files.forEach((f, i) => {
        const prefix = i === this.selectedIndex ? "> " : "  ";
        lines.push(prefix + formatStatLine(f, this.comments.has(f.path)));
      });
      lines.push("", "↑↓ select  Enter open  c comment  e edit  a approve  r reject");
      return lines;
    }
```

- [ ] **Step 4: Thread `opts` through `runReviewLoop`**

Change `runReviewLoop`'s signature and the `ReviewOverlay` construction inside it:

```typescript
export async function runReviewLoop(
  ui: UiApi,
  cwd: string,
  taskId: string,
  startCommit: string,
  files: FileStat[],
  opts: { implementing?: boolean; banner?: string } = {},
): Promise<ReviewDecisionResult> {
  const comments = new Map<string, string>();

  for (;;) {
    const action = await ui.custom<ReviewAction>((tui, _theme, _keybindings, done) => {
      return new ReviewOverlay(files, comments, tui, cwd, startCommit, done, opts) as unknown as ReturnType<
        Parameters<UiApi["custom"]>[0]
      >;
    });
    // ... rest unchanged ...
```

- [ ] **Step 5: Run overlay test + typecheck**

Run: `npx vitest run test/review-overlay.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 6: Write the failing handler test**

Add to `pi-ext/factory-watch/test/handler.test.ts` a case asserting that when the polled human-review entry has `already_done`, the extension computes implementing files from the deliverables. Mock `computeImplementingFiles` and `runReviewLoop` (match the file's existing vi.mock style for `review-diff`/`review-overlay`):

```typescript
test("/factory-run already-done human-review uses the implementing diff + banner", async () => {
  // Arrange a status file whose human-review entry is blocked + already_done,
  // with deliverables, using the harness this file already uses to drive the
  // launchInteractiveReview poll. Then assert:
  expect(computeImplementingFiles).toHaveBeenCalledWith(expect.any(String), ["src/x.py"]);
  expect(runReviewLoop).toHaveBeenCalledWith(
    expect.any(Object), expect.any(String), "T-1", expect.any(String),
    expect.any(Array),
    expect.objectContaining({ implementing: true }),
  );
});
```

(Model the status-file/poll arrangement on the existing "detects a blocked human-review" test in this file; reuse its fixtures rather than inventing new ones.)

- [ ] **Step 7: Run it to verify it fails**

Run: `npx vitest run test/handler.test.ts`
Expected: FAIL — the branch doesn't exist; `computeImplementingFiles` is never called and `runReviewLoop` is called without `implementing`.

- [ ] **Step 8: Implement the branch in `launchInteractiveReview`**

In `pi-ext/factory-watch/src/index.ts`, add the import:

```typescript
import { computeReviewFiles, computeImplementingFiles } from "./review-diff.js";
```

In the review poll, where it currently builds `files` and calls `runReviewLoop`, branch on the entry's `already_done`:

```typescript
          const startCommit = hrEntry.start_commit;
          const taskId = record.task_id;
          const sessionId = record.session_id;
          reviewInFlightForTask = taskId;
          const alreadyDone = hrEntry.already_done === true;
          const files = alreadyDone
            ? computeImplementingFiles(ctx.cwd, hrEntry.deliverables ?? [])
            : computeReviewFiles(ctx.cwd, startCommit);
          const opts = alreadyDone
            ? { implementing: true, banner: "This task appears already complete — approve to mark it done, reject to re-run it." }
            : {};
          void runReviewLoop(ctx.ui, ctx.cwd, taskId, startCommit, files, opts).then((decision) => {
            writeReviewDecision(reviewDecisionPath(ctx.cwd, sessionId), decision);
          });
```

- [ ] **Step 9: Run handler test + typecheck**

Run: `npx vitest run test/handler.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 10: Run the full TS suite**

Run: `npx vitest run`
Expected: PASS (no regressions).

- [ ] **Step 11: Commit**

```bash
git add pi-ext/factory-watch/src/review-overlay.ts pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/review-overlay.test.ts pi-ext/factory-watch/test/handler.test.ts
git commit -m "feat: already-done human-review shows the implementing diff under an 'already complete' banner"
```

---

## Final verification

- [ ] **Full Python suite:** `uv run python -m pytest tests/unit/orchestrator/ -v` → all pass.
- [ ] **Full TS suite + typecheck:** from `pi-ext/factory-watch/`, `npx vitest run && npx tsc --noEmit` → all pass.
- [ ] **Manual end-to-end (optional, live):** in a fresh `pif` session, `/factory-run T-029` → context-gather emits already-done → validation runs → review → human-review shows the implementing diff of `0d4634b` under the banner → approve → T-029 marked `done`.
