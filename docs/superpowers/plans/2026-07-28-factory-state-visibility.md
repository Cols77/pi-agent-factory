# Factory State Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the factory's real state legible — per-node activity descriptions in mission control, and a task picker that never hides a started-but-unfinished task and shows where its last run stopped.

**Architecture:** All derived from data the orchestrator already has: the streamed `snippet` per running node, the manifest's file list, and a new per-task mirror of the status record. No agent prompt changes, no LLM/token cost. Python writes; the TS pi-extension (`factory-watch`) displays.

**Tech Stack:** Python 3 (orchestrator, `uv`/`pytest`/`ruff`), TypeScript (`pi-ext/factory-watch`, `vitest`/`tsc`).

## Global Constraints

- **Best-effort telemetry:** status and per-task-mirror writes must NEVER raise into the orchestrator run. Reuse the existing `_atomic_write_json` tolerance (swallow `OSError`, warn, continue).
- **No agent/prompt changes, no token cost.** Display only.
- **Windows repo.** The Bash tool is Git Bash. Run TS from `pi-ext/factory-watch/`: `npx vitest run <file>` and `npx tsc --noEmit`. Do NOT run the full `npx vitest run` suite — a known-flaky `mission-control-review.ts` "usage:" test fails intermittently under concurrency and is unrelated.
- **Python checks:** `uv run python -m pytest <targets> -q` and `uv run ruff check src/factory/orchestrator/`.
- **Per-task mirror path:** `sessions/.factory-runs/<task_id>.json`, added to `.gitignore` (runtime artifact).
- **Hide tasks by `status == "done"` only** — never by file presence.
- Commit each task; append the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/factory/orchestrator/nodes.py` | `_summarize_manifest` → file-basename summary (Task 1) |
| `src/factory/orchestrator/runner.py` | `run_next` auto-pick no longer filters by `deliverables_exist` (Task 2) |
| `src/factory/orchestrator/status.py` | `FileStatusReporter` mirrors each write per task (Task 3) |
| `src/factory/orchestrator/run_state.py` (new) | `read_last_run(repo_root, task_id)` (Task 4) |
| `src/factory/orchestrator/__main__.py` | `list --json` adds `last_run` per task (Task 5) |
| `.gitignore` | ignore `sessions/.factory-runs/` (Task 3) |
| `pi-ext/factory-watch/src/status-format.ts` | `snippet` on `MissionControlRow` (Task 6) |
| `pi-ext/factory-watch/src/mission-control-dashboard.ts` | render snippet line for running rows (Task 7) |
| `pi-ext/factory-watch/src/task-picker.ts` | `last_run` on `TaskSummary`; `humanizeAge`; annotated `formatTaskOption` (Task 8) |
| `pi-ext/factory-watch/src/index.ts` | picker filter hides by status only (Task 8) |

---

### Task 1: Context-gatherer summary lists file basenames

**Files:**
- Modify: `src/factory/orchestrator/nodes.py` (`_summarize_manifest`, lines 25-34)
- Test: `tests/unit/orchestrator/test_nodes_context_dev.py`

**Interfaces:**
- Produces: `_summarize_manifest(manifest: dict | None) -> str` — unchanged signature; richer string. Flows unchanged into the context-gather `pass` report's `handoff` (`→ dev: <this>`) and `summary`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/orchestrator/test_nodes_context_dev.py`:

```python
def test_summarize_manifest_lists_basenames_and_coherence():
    m = {"context": {"source_files": ["src/a/rtb.py", "src/waypoint.py", "nav.py"]},
         "coherence": {"proven": True}}
    assert _summarize_manifest(m) == "provided: rtb.py, waypoint.py, nav.py · coherence proven"


def test_summarize_manifest_truncates_over_three_files():
    m = {"context": {"source_files": ["a.py", "b.py", "c.py", "d.py", "e.py"]},
         "coherence": {"proven": True}}
    assert _summarize_manifest(m) == "provided: a.py, b.py, c.py (+2) · coherence proven"


def test_summarize_manifest_no_files_and_unproven():
    assert _summarize_manifest({"context": {}, "coherence": {}}) == "no source files · coherence unproven"


def test_summarize_manifest_none():
    assert _summarize_manifest(None) == "no manifest"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_nodes_context_dev.py -k summarize_manifest -q`
Expected: FAIL (current output is `"3 files, coherence=yes"` form).

- [ ] **Step 3: Implement**

Replace `_summarize_manifest` in `nodes.py` with:

```python
def _summarize_manifest(manifest: dict | None) -> str:
    """One-line manifest summary for the handoff/summary status: the actual file
    basenames the context gatherer provided, plus coherence."""
    if manifest is None:
        return "no manifest"
    ctx = manifest.get("context", {})
    raw = ctx.get("source_files", [])
    files = raw if isinstance(raw, list) else []
    coherence = "coherence proven" if manifest.get("coherence", {}).get("proven") else "coherence unproven"
    if not files:
        return f"no source files · {coherence}"
    names = [Path(str(p)).name for p in files]
    shown = ", ".join(names[:3])
    if len(names) > 3:
        shown += f" (+{len(names) - 3})"
    return f"provided: {shown} · {coherence}"
```

(`Path` is already imported at `nodes.py:3`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/orchestrator/test_nodes_context_dev.py -q && uv run ruff check src/factory/orchestrator/nodes.py`
Expected: PASS, ruff clean. (The pre-existing `test_context_gatherer_*` assertion at line ~192 compares against `_summarize_manifest(manifest)` itself, so it stays green.)

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/nodes.py tests/unit/orchestrator/test_nodes_context_dev.py
git commit -m "feat: context-gatherer summary lists provided file basenames"
```

---

### Task 2: `run_next` auto-pick no longer hides tasks by file presence

**Files:**
- Modify: `src/factory/orchestrator/runner.py` (`run_next`, the `else` auto-pick branch, ~lines 245-250)
- Test: `tests/unit/orchestrator/test_run_next.py`

**Interfaces:**
- Consumes: `next_todo(tasks)` (ledger, unchanged).
- Produces: `run_next` auto-pick returns the first `status == "todo"` task regardless of whether its deliverables exist on disk. The explicit `--task` path is unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/orchestrator/test_run_next.py` (reuse the file's `_repo`/`_scripts` helpers; a todo task whose Create file already exists must still be picked). Model on the existing run_next tests:

```python
def test_auto_pick_selects_todo_task_even_if_deliverables_exist(tmp_path):
    repo = _repo(tmp_path)
    # T-001's body declares Create: src/x.py, which _repo already created on disk.
    (repo / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\n- Create: `src/x.py`\n",
        encoding="utf-8")
    backend = FakeAgentBackend(_scripts())
    result = run_next(repo, backend, FakeGateRunner([0, 0, 0]), status=FakeStatusReporter())
    # It must run the task (not return None / "no todo tasks") despite src/x.py existing.
    assert result is not None
```

(If `_scripts`/`FakeGateRunner` arity differs in this file, match the existing passing tests' call shape — do not invent new fakes.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_run_next.py -k deliverables_exist -q`
Expected: FAIL — today the `deliverables_exist` filter drops T-001, so `run_next` returns `None`.

- [ ] **Step 3: Implement**

In `runner.py`, the auto-pick branch currently reads:

```python
    else:
        # Skip tasks whose Create:/Test: deliverables already exist on disk --
        # their work is already done, so they shouldn't be auto-picked as "next".
        task = next_todo([t for t in tasks if not deliverables_exist(t.body, repo_root)])
        if task is None:
            return None
```

Replace with:

```python
    else:
        # Pick the next todo task by STATUS only. A task whose Create:/Test:
        # deliverables happen to exist on disk is NOT necessarily complete (it may
        # have stopped at dev-fail with files committed); hiding it here silently
        # swallows unfinished work. Genuinely-done work is handled at run time by
        # the context-gatherer's already-done routing, which verifies via the gates.
        task = next_todo(tasks)
        if task is None:
            return None
```

Remove the now-unused `deliverables_exist` import if nothing else in `runner.py` uses it (check: `parse_deliverables` is still used; `deliverables_exist` is not after this change — remove it from the `from factory.orchestrator.deliverables import ...` line, keeping `parse_deliverables`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/orchestrator/test_run_next.py -q && uv run ruff check src/factory/orchestrator/runner.py`
Expected: PASS, ruff clean (no unused-import warning).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/runner.py tests/unit/orchestrator/test_run_next.py
git commit -m "fix: factory-run auto-pick hides tasks by status, not file presence"
```

---

### Task 3: `FileStatusReporter` mirrors each write to a per-task file

**Files:**
- Modify: `src/factory/orchestrator/status.py` (`FileStatusReporter.report`, after the primary write at ~line 168)
- Modify: `.gitignore`
- Test: `tests/unit/orchestrator/test_status.py`

**Interfaces:**
- Produces: after every `FileStatusReporter.report(...)`, the same `record` dict is also written to `self.path.parent / ".factory-runs" / f"{task_id}.json"`, best-effort. This is the mirror `read_last_run` (Task 4) consumes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/orchestrator/test_status.py`:

```python
def test_report_mirrors_record_to_per_task_file(tmp_path):
    path = tmp_path / "sessions" / ".factory-status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    reporter.report(task_id="T-037", node="dev", node_state="fail", attempt=3, max_attempts=3,
                    handoff="unit tests still red", outcome="escalated")
    mirror = tmp_path / "sessions" / ".factory-runs" / "T-037.json"
    assert mirror.exists()
    rec = json.loads(mirror.read_text(encoding="utf-8"))
    assert rec["task_id"] == "T-037"
    assert rec["current_node"] == "dev"
    assert rec["current_state"] == "fail"
    assert rec["pipeline"][0]["handoff"] == "unit tests still red"


def test_report_mirror_write_failure_does_not_raise(tmp_path):
    # Best-effort: a failing mirror write must not abort the run, and the primary
    # status file must still be written.
    path = tmp_path / "sessions" / ".factory-status.json"
    reporter = FileStatusReporter(path=path, session_id="s1")
    # Make the mirror dir path a FILE so mkdir(parents=True) under it raises.
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / ".factory-runs").write_text("x", encoding="utf-8")
    reporter.report(task_id="T-1", node="dev", node_state="running", attempt=1, max_attempts=3)  # must not raise
    assert path.exists()  # primary write still happened
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_status.py -k mirror -q`
Expected: FAIL — no mirror file is written yet.

- [ ] **Step 3: Implement**

In `status.py`, at the end of `FileStatusReporter.report`, the method currently finishes with:

```python
        record = {
            "session_id": self.session_id,
            "task_id": task_id,
            "current_node": node,
            "current_state": node_state,
            "pipeline": self._pipeline,
            "started_at": self.started_at,
            "updated_at": _now(),
        }
        _atomic_write_json(self.path, record)
```

Append, immediately after the `_atomic_write_json(self.path, record)` line, a best-effort mirror write:

```python
        # Mirror the record to a per-task file so a stopped/killed run's state
        # survives the next run overwriting the single global status slot. The
        # picker reads these to show where each task last stopped. Best-effort:
        # _atomic_write_json already swallows OSError and warns, never raising.
        mirror_path = self.path.parent / ".factory-runs" / f"{task_id}.json"
        _atomic_write_json(mirror_path, record)
```

(`_atomic_write_json` already does `path.parent.mkdir(parents=True, exist_ok=True)` inside a try and prints a warning instead of raising on failure — so the mirror-dir-is-a-file case is swallowed.)

- [ ] **Step 4: Add the gitignore entry**

Append to `.gitignore` (after the existing `sessions/.factory-*` runtime-artifact block from the earlier cleanup):

```
sessions/.factory-runs/
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/orchestrator/test_status.py -q && uv run ruff check src/factory/orchestrator/status.py`
Expected: PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/status.py tests/unit/orchestrator/test_status.py .gitignore
git commit -m "feat: mirror status to a per-task file so stopped runs survive"
```

---

### Task 4: `read_last_run` extracts a task's last stop-point

**Files:**
- Create: `src/factory/orchestrator/run_state.py`
- Test: `tests/unit/orchestrator/test_run_state.py`

**Interfaces:**
- Consumes: the mirror file shape written in Task 3 (`current_node`, `current_state`, `pipeline[]`, `updated_at`).
- Produces: `read_last_run(repo_root: Path, task_id: str) -> dict | None` returning
  `{"node", "state", "outcome", "handoff", "updated_at"}` or `None` when the mirror
  is missing or unreadable/corrupt.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/orchestrator/test_run_state.py`:

```python
import json
import pytest
from factory.orchestrator.run_state import read_last_run

pytestmark = pytest.mark.unit


def _write_mirror(repo_root, task_id, record):
    d = repo_root / "sessions" / ".factory-runs"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")


def test_read_last_run_returns_stop_point_with_reason(tmp_path):
    _write_mirror(tmp_path, "T-037", {
        "task_id": "T-037", "current_node": "dev", "current_state": "fail",
        "updated_at": "2026-07-28T11:08:16Z",
        "pipeline": [
            {"node": "context-gather", "node_state": "pass", "handoff": "→ dev", "outcome": None},
            {"node": "dev", "node_state": "fail", "handoff": "unit tests still red", "outcome": "escalated"},
        ],
    })
    assert read_last_run(tmp_path, "T-037") == {
        "node": "dev", "state": "fail", "outcome": "escalated",
        "handoff": "unit tests still red", "updated_at": "2026-07-28T11:08:16Z",
    }


def test_read_last_run_none_when_missing(tmp_path):
    assert read_last_run(tmp_path, "T-999") is None


def test_read_last_run_none_on_corrupt_file(tmp_path):
    d = tmp_path / "sessions" / ".factory-runs"
    d.mkdir(parents=True)
    (d / "T-1.json").write_text("{not json", encoding="utf-8")
    assert read_last_run(tmp_path, "T-1") is None


def test_read_last_run_handoff_none_when_no_matching_entry(tmp_path):
    _write_mirror(tmp_path, "T-2", {
        "task_id": "T-2", "current_node": "dev", "current_state": "running",
        "updated_at": "t", "pipeline": [],
    })
    got = read_last_run(tmp_path, "T-2")
    assert got == {"node": "dev", "state": "running", "outcome": None, "handoff": None, "updated_at": "t"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_run_state.py -q`
Expected: FAIL — `run_state` module does not exist.

- [ ] **Step 3: Implement**

Create `src/factory/orchestrator/run_state.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


def read_last_run(repo_root: Path, task_id: str) -> dict | None:
    """Read a task's per-task status mirror (written by FileStatusReporter) and
    return a compact stop-point: {node, state, outcome, handoff, updated_at}.
    Returns None if the mirror is missing or unreadable/corrupt (best-effort)."""
    path = repo_root / "sessions" / ".factory-runs" / f"{task_id}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    node = record.get("current_node")
    pipeline = record.get("pipeline", [])
    if not isinstance(pipeline, list):
        pipeline = []
    # Reason: the handoff on the current node's own pipeline entry.
    handoff = None
    for entry in pipeline:
        if isinstance(entry, dict) and entry.get("node") == node:
            handoff = entry.get("handoff")
    # Outcome: the last non-null outcome recorded across the pipeline.
    outcome = None
    for entry in pipeline:
        if isinstance(entry, dict) and entry.get("outcome"):
            outcome = entry["outcome"]
    return {
        "node": node,
        "state": record.get("current_state"),
        "outcome": outcome,
        "handoff": handoff,
        "updated_at": record.get("updated_at"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/orchestrator/test_run_state.py -q && uv run ruff check src/factory/orchestrator/run_state.py`
Expected: PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/run_state.py tests/unit/orchestrator/test_run_state.py
git commit -m "feat: read_last_run extracts a task's last stop-point from its mirror"
```

---

### Task 5: `list --json` includes each task's `last_run`

**Files:**
- Modify: `src/factory/orchestrator/__main__.py` (the `list` command, ~lines 48-60)
- Test: `tests/unit/orchestrator/test_main.py`

**Interfaces:**
- Consumes: `read_last_run(repo_root, task_id)` (Task 4).
- Produces: each object in `list --json` output gains `"last_run": <dict|null>` alongside `id/title/status/already_done`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/orchestrator/test_main.py` (model on the existing `list --json` test; if none, invoke the CLI the way the file's other tests do). A minimal test that drives the module's `main` for the `list --json` command and asserts `last_run` is present:

```python
def test_list_json_includes_last_run(tmp_path, capsys, monkeypatch):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-1.md").write_text(
        "---\nid: T-1\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    d = tmp_path / "sessions" / ".factory-runs"
    d.mkdir(parents=True)
    (d / "T-1.json").write_text(json.dumps({
        "task_id": "T-1", "current_node": "dev", "current_state": "fail", "updated_at": "t",
        "pipeline": [{"node": "dev", "node_state": "fail", "handoff": "red", "outcome": "escalated"}],
    }), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["factory", "--repo", str(tmp_path), "list", "--json"])
    main()
    out = json.loads(capsys.readouterr().out)
    t1 = next(t for t in out if t["id"] == "T-1")
    assert t1["last_run"]["state"] == "fail"
    assert t1["last_run"]["handoff"] == "red"
```

(Match the file's existing import of `main`/`sys` and how it invokes the CLI; if `test_main.py` invokes via `subprocess`, follow that style instead and assert on parsed stdout.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/unit/orchestrator/test_main.py -k last_run -q`
Expected: FAIL — `last_run` key absent.

- [ ] **Step 3: Implement**

In `__main__.py`, add the import near the other orchestrator imports:

```python
from factory.orchestrator.run_state import read_last_run
```

Change the `list --json` dict comprehension (currently emitting `id/title/status/already_done`) to add `last_run`:

```python
            print(json.dumps([
                {
                    "id": t.id, "title": t.title, "status": t.status,
                    "already_done": deliverables_exist(t.body, repo_root),
                    "last_run": read_last_run(repo_root, t.id),
                }
                for t in tasks
            ]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/orchestrator/test_main.py -q && uv run ruff check src/factory/orchestrator/__main__.py`
Expected: PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/__main__.py tests/unit/orchestrator/test_main.py
git commit -m "feat: list --json includes each task's last-run stop-point"
```

---

### Task 6: `snippet` on `MissionControlRow`

**Files:**
- Modify: `pi-ext/factory-watch/src/status-format.ts` (`MissionControlRow` + `formatMissionControlRows`, lines 148-172)
- Test: `pi-ext/factory-watch/test/status-format.test.ts`

**Interfaces:**
- Produces: `MissionControlRow` gains `snippet: string | null`; `formatMissionControlRows` sets it from the entry. Consumed by the dashboard (Task 7).

- [ ] **Step 1: Update the existing exact-match test + add a snippet test**

In `test/status-format.test.ts`, the `formatMissionControlRows` "shows every stage" test asserts an exact `toEqual` on each row object (lines ~185-191). Add `snippet: null` to every expected row object there (context-gather, dev, validation, review, human-review) so it still matches once the field exists. Then add:

```typescript
test("carries the snippet from a running entry", () => {
  const record: StatusRecord = {
    session_id: "s1", task_id: "T-1", current_node: "dev", current_state: "running",
    pipeline: [
      { node: "dev", node_state: "running", attempt: 1, max_attempts: 3, snippet: "grepping for advance_waypoint", outcome: null, handoff: null, updated_at: "t" },
    ],
    started_at: "t", updated_at: "t",
  };
  const rows = formatMissionControlRows(record, ["dev"]);
  expect(rows[0]!.snippet).toBe("grepping for advance_waypoint");
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `pi-ext/factory-watch/`): `npx vitest run test/status-format.test.ts`
Expected: FAIL — `snippet` not on `MissionControlRow`; the updated exact-match test also fails until the field is populated.

- [ ] **Step 3: Implement**

In `status-format.ts`, add `snippet` to the interface:

```typescript
export interface MissionControlRow {
  node: string;
  label: string;
  state: string;
  handoff: string | null;
  sessionId: string | null;
  summary: string | null;
  startCommit: string | null;
  snippet: string | null;
}
```

And populate it in `formatMissionControlRows`'s returned object:

```typescript
      snippet: entry?.snippet ?? null,
```

- [ ] **Step 4: Run tests + typecheck**

Run (from `pi-ext/factory-watch/`): `npx vitest run test/status-format.test.ts && npx tsc --noEmit`
Expected: PASS, tsc clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/status-format.ts pi-ext/factory-watch/test/status-format.test.ts
git commit -m "feat: carry the live snippet on MissionControlRow"
```

---

### Task 7: Dashboard renders the live snippet for running rows

**Files:**
- Modify: `pi-ext/factory-watch/src/mission-control-dashboard.ts` (`render`, lines 63-70)
- Test: `pi-ext/factory-watch/test/mission-control-dashboard.test.ts`

**Interfaces:**
- Consumes: `MissionControlRow.snippet` (Task 6).
- Produces: for a row whose `state === "running"` with a non-empty snippet, `render` emits one extra line showing the snippet's last non-empty line, truncated to the panel width.

- [ ] **Step 1: Write the failing test**

Add to `test/mission-control-dashboard.test.ts` (it already imports `MissionControlDashboard` and has a running `dev` entry in `RECORD`; use a record whose dev entry has a snippet):

```typescript
test("renders the live snippet under a running row", () => {
  const record = { ...RECORD, pipeline: [
    { node: "dev", node_state: "running", attempt: 1, max_attempts: 3, snippet: "grepping for advance_waypoint", outcome: null, handoff: null, updated_at: "t" },
  ] } as typeof RECORD;
  const lines = new MissionControlDashboard(record, () => {}).render(80).join("\n");
  expect(lines).toContain("grepping for advance_waypoint");
});

test("does not render a snippet for a non-running row", () => {
  const record = { ...RECORD, pipeline: [
    { node: "dev", node_state: "pass", attempt: 1, max_attempts: 3, snippet: "should not show", outcome: null, handoff: "→ validation", updated_at: "t" },
  ] } as typeof RECORD;
  const lines = new MissionControlDashboard(record, () => {}).render(80).join("\n");
  expect(lines).not.toContain("should not show");
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `pi-ext/factory-watch/`): `npx vitest run test/mission-control-dashboard.test.ts`
Expected: FAIL — no snippet line rendered.

- [ ] **Step 3: Implement**

In `mission-control-dashboard.ts` `render`, inside the `formatMissionControlRows(...).forEach((row, i) => {...})` body, after the `handoff` line and before/around the `summary` block, add:

```typescript
      if (row.state === "running" && row.snippet) {
        const last = row.snippet.split("\n").map((s) => s.trim()).filter(Boolean).pop() ?? "";
        if (last) {
          const max = Math.max(1, width - 6);
          const shown = last.length > max ? last.slice(0, max - 1) + "…" : last;
          lines.push(`    … ${shown}`);
        }
      }
```

- [ ] **Step 4: Run tests + typecheck**

Run (from `pi-ext/factory-watch/`): `npx vitest run test/mission-control-dashboard.test.ts && npx tsc --noEmit`
Expected: PASS, tsc clean.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/mission-control-dashboard.ts pi-ext/factory-watch/test/mission-control-dashboard.test.ts
git commit -m "feat: mission control shows the live snippet under a running node"
```

---

### Task 8: Picker shows run-state and stops hiding by file presence

**Files:**
- Modify: `pi-ext/factory-watch/src/task-picker.ts`
- Modify: `pi-ext/factory-watch/src/index.ts` (the filter + empty-state notice, lines 344-351)
- Test: `pi-ext/factory-watch/test/task-picker.test.ts`

**Interfaces:**
- Consumes: `list --json`'s per-task `last_run` and `already_done` (Task 5); `secondsAgo` (status-format).
- Produces: `TaskSummary` gains `last_run?: LastRun | null`; `humanizeAge(seconds): string`; `formatTaskOption(task, now?)` renders a single annotated line. `index.ts` filters by `status === "todo"` only.

- [ ] **Step 1: Write the failing tests**

Replace/extend `test/task-picker.test.ts`:

```typescript
import { describe, expect, test } from "vitest";
import { formatTaskOption, parseTaskIdFromOption, humanizeAge } from "../src/task-picker.js";

const NOW = new Date("2026-07-28T13:08:16Z");

describe("humanizeAge", () => {
  test("boundaries", () => {
    expect(humanizeAge(30)).toBe("just now");
    expect(humanizeAge(5 * 60)).toBe("5m ago");
    expect(humanizeAge(2 * 3600)).toBe("2h ago");
    expect(humanizeAge(3 * 86400)).toBe("3d ago");
  });
});

describe("formatTaskOption", () => {
  test("clean todo with no run history", () => {
    expect(formatTaskOption({ id: "T-036", title: "ScriptedPerception", status: "todo" }, NOW)).toBe(
      "T-036  ScriptedPerception",
    );
  });

  test("annotates a stopped task with node/state, age and reason", () => {
    const line = formatTaskOption({
      id: "T-037", title: "DirectiveExecutor", status: "todo",
      last_run: { node: "dev", state: "fail", outcome: "escalated", handoff: "unit tests still red", updated_at: "2026-07-28T11:08:16Z" },
    }, NOW);
    expect(line).toBe("T-037  DirectiveExecutor  — ⚠ stopped: dev fail (2h ago): unit tests still red");
  });

  test("omits the reason clause when handoff is null", () => {
    const line = formatTaskOption({
      id: "T-5", title: "X", status: "todo",
      last_run: { node: "review", state: "changes-requested", outcome: null, handoff: null, updated_at: "2026-07-28T13:07:16Z" },
    }, NOW);
    expect(line).toBe("T-5  X  — ⚠ stopped: review changes-requested (just now)");
  });

  test("annotates a done-outside-factory task when deliverables exist but no run history", () => {
    expect(formatTaskOption({ id: "T-29", title: "Foo", status: "todo", already_done: true }, NOW)).toBe(
      "T-29  Foo  — deliverables present (will route to review)",
    );
  });
});

describe("parseTaskIdFromOption", () => {
  test("recovers the id from an annotated option", () => {
    expect(parseTaskIdFromOption("T-037  DirectiveExecutor  — ⚠ stopped: dev fail (2h ago): unit tests still red")).toBe("T-037");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `pi-ext/factory-watch/`): `npx vitest run test/task-picker.test.ts`
Expected: FAIL — `humanizeAge` and the annotation logic don't exist.

- [ ] **Step 3: Implement the picker**

Replace `task-picker.ts` with:

```typescript
import { secondsAgo } from "./status-format.js";

export interface LastRun {
  node: string | null;
  state: string | null;
  outcome: string | null;
  handoff: string | null;
  updated_at: string | null;
}

export interface TaskSummary {
  id: string;
  title: string;
  status: string;
  // True when the task's Create:/Test: deliverables already exist on disk
  // (orchestrator's `list --json` computes this). Used only to ANNOTATE a task
  // with no run history as likely-done -- never to hide it.
  already_done?: boolean;
  // The task's last factory run stop-point, or null if it never ran.
  last_run?: LastRun | null;
}

export function humanizeAge(seconds: number): string {
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function formatTaskOption(task: TaskSummary, now: Date = new Date()): string {
  const base = `${task.id}  ${task.title}`;
  const lr = task.last_run;
  if (lr && lr.node && lr.state) {
    const age = lr.updated_at ? ` (${humanizeAge(secondsAgo(lr.updated_at, now))})` : "";
    const reason = lr.handoff ? `: ${lr.handoff}` : "";
    return `${base}  — ⚠ stopped: ${lr.node} ${lr.state}${age}${reason}`;
  }
  if (task.already_done) {
    return `${base}  — deliverables present (will route to review)`;
  }
  return base;
}

export function parseTaskIdFromOption(option: string): string {
  const [id] = option.split(/\s+/);
  return id!;
}
```

- [ ] **Step 4: Implement the filter fix in `index.ts`**

Change the filter and empty-state notice (currently lines 344-348):

```typescript
        // Hide tasks whose Create:/Test: deliverables already exist -- their
        // work is already done, so don't suggest them for execution.
        const todoTasks = tasks.filter((t) => t.status === "todo" && !t.already_done);
        if (todoTasks.length === 0) {
          ctx.ui.notify("no runnable todo tasks (already-done tasks are hidden)", "info");
          return;
        }
```

to:

```typescript
        // Show every todo task. A task is hidden only when its ledger status is
        // "done" -- never because its files exist on disk (that would swallow a
        // started-but-unfinished task). Run-state is surfaced via formatTaskOption.
        const todoTasks = tasks.filter((t) => t.status === "todo");
        if (todoTasks.length === 0) {
          ctx.ui.notify("no todo tasks", "info");
          return;
        }
```

- [ ] **Step 5: Run tests + typecheck**

Run (from `pi-ext/factory-watch/`): `npx vitest run test/task-picker.test.ts && npx tsc --noEmit`
Expected: PASS, tsc clean.

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/task-picker.ts pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/task-picker.test.ts
git commit -m "feat: task picker shows run-state and stops hiding by file presence"
```

---

## Final verification

- [ ] **Python:** `uv run python -m pytest tests/unit/orchestrator/ -q` → all pass; `uv run ruff check src/factory/orchestrator/` → clean.
- [ ] **TS:** from `pi-ext/factory-watch/`, run each touched test file (`status-format`, `mission-control-dashboard`, `task-picker`) plus `npx tsc --noEmit` → all pass. (Avoid the full `vitest run` suite — the known-flaky `mission-control-review` "usage:" test.)
- [ ] **Manual E2E (optional, live):** re-run the factory; confirm `factory-run` now lists T-037 annotated with its `dev fail` stop-point, the mission-control dashboard shows a live snippet line under a running node, and the context-gatherer row's summary lists provided file basenames.
