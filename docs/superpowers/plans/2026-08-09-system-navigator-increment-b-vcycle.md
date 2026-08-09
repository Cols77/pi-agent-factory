# System Navigator Increment B — V-Cycle Navigator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/system` a V-cycle navigator — open a task to see how it was implemented, and open a file to walk back to the requirement it serves.

**Architecture:** Two new openable scope kinds (`task:`, `file:`) answered by new Python queries that compose existing loaders. Reverse navigation walks only recorded links: file → `changed_files` → manifest → `task_id` → task → `satisfies` → SR. Where no manifest exists, run history comes from `sessions/*.session.json`, a thinner recorded source. Python computes; TypeScript renders.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, json, jsonschema, pytest; TypeScript, Vitest, jsdom, the existing docs server and `/system` page.

**Spec:** `docs/superpowers/specs/2026-08-09-system-navigator-increment-b-vcycle-design.md`

## Global Constraints

- Claim class ∈ `recorded|derived|synthesized|missing`; freshness ∈ `fresh|stale|degraded|n/a`; `missing` ⟺ `n/a`.
- Freshness is content-based, never mtime-based.
- Scope refs are exact, never fuzzy. Case-sensitive.
- Reverse navigation walks recorded links only — no hop is inferred. An unresolved hop is `missing` and the chain stops there.
- No whole-suite or repo-wide test pass rate.
- Manifests are never reconstructed. No git-derived implementation history.
- A session-record claim cites the session record (`CitationKind.SESSION`), never a manifest. Its `implementation` is `missing`.
- Where a manifest and a session record exist for the same run, the manifest wins and the session record is not read.
- Reuse existing loaders (`factory.evidence.manifests`, `factory.trace.model`, `factory.orchestrator.ledger`, `factory.requirements.register`). No parallel parsing rules.
- Python computes, TypeScript renders. No interpretation in the browser.
- `/system` stays opt-in.
- No new claim classes.

## Verification discipline

`pyproject.toml` sets `addopts = "-m unit"`. Integration commands must pass `-m 'unit or integration'` or they collect nothing and exit green.

The `rtk` proxy has been observed misreporting pytest collection counts. Run anything collection-sensitive as `rtk proxy uv run pytest ...`.

**Fixtures must be built through real writers.** Use `factory.evidence.manifests.write_run_manifest` for manifests and the real ledger/register parsers for their artifacts. A hand-rolled dict that merely resembles a manifest is what let an earlier task ship a query reading a storage layout no producer writes — its tests passed because the fixtures encoded the same wrong assumption as the code.

---

## File Structure

**Create:**
- `src/factory/system/refs.py` — namespace mapping between trace ids, register ids and scope refs
- `src/factory/system/sessions.py` — the session-record evidence source
- `src/factory/system/story.py` — task implementation story query
- `src/factory/system/reverse.py` — reverse navigation query
- `tests/unit/system/test_refs.py`
- `tests/unit/system/test_sessions.py`
- `tests/unit/system/test_story.py`
- `tests/unit/system/test_reverse.py`
- `tests/integration/system/test_vcycle.py`
- `pi-ext/factory-watch/test/system-page-vcycle.test.ts`

**Modify:**
- `src/factory/system/models.py` — add `CitationKind.SESSION`
- `src/factory/system/queries.py` — extend `parse_scope_ref`, add implementation aggregates to `query_brief`
- `src/factory/system/cli.py` — add `story` and `reverse` subcommands
- `src/factory/schemas/system_response.schema.json` — add `story` and `reverse` members
- `pi-ext/factory-watch/src/system-cli.ts` — client wrappers
- `pi-ext/factory-watch/src/system-page.ts` — render the new views
- `pi-ext/factory-watch/src/docs-server.ts` — routes
- `pi-ext/factory-watch/src/system-context-tools.ts` — extend the existing PIF tools; do NOT add a registration surface

---

## Task 1: Namespace mapping and the new scope kinds

Trace node ids are `spec:<basename>`; `satisfies` edges name a bare `SR-146`; navigator refs are `spec:<path>` and `sr:SR-146`. These namespaces have never met and the mismatch has been parked twice. Reverse navigation makes them meet, so it gets one mapping function with a test per direction.

**Files:**
- Create: `src/factory/system/refs.py`
- Create: `tests/unit/system/test_refs.py`
- Modify: `src/factory/system/queries.py` (`_SCOPE_KINDS`, `parse_scope_ref` docstring)

**Interfaces:**
- Produces: `sr_ref_from_trace_id(raw: str) -> str | None`, `task_ref_from_trace_id(raw: str) -> str | None`, `trace_id_for_task(task_id: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from factory.system.refs import sr_ref_from_trace_id, task_ref_from_trace_id, trace_id_for_task

pytestmark = pytest.mark.unit


def test_bare_sr_id_from_a_satisfies_edge_becomes_a_scope_ref():
    assert sr_ref_from_trace_id("SR-146") == "sr:SR-146"


def test_an_already_prefixed_sr_ref_is_returned_unchanged():
    assert sr_ref_from_trace_id("sr:SR-146") == "sr:SR-146"


def test_an_unmappable_value_is_none_never_guessed():
    assert sr_ref_from_trace_id("") is None
    assert sr_ref_from_trace_id("not-an-sr") is None
    assert sr_ref_from_trace_id("SR-") is None


def test_task_trace_ids_map_both_directions():
    assert task_ref_from_trace_id("task:T-059") == "task:T-059"
    assert task_ref_from_trace_id("T-059") == "task:T-059"
    assert trace_id_for_task("T-059") == "task:T-059"
    assert trace_id_for_task("task:T-059") == "task:T-059"


def test_mapping_is_case_sensitive():
    assert sr_ref_from_trace_id("sr-146") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/system/test_refs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.system.refs'`

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

import re

# Trace `satisfies` edges name a bare `SR-146`; navigator scope refs are
# `sr:SR-146`. One mapping, in one place, so no call site invents its own.
_SR_ID = re.compile(r"^SR-\d+$")
_TASK_ID = re.compile(r"^T-\d+$")


def sr_ref_from_trace_id(raw: str) -> str | None:
    """`SR-146` or `sr:SR-146` -> `sr:SR-146`. Anything else -> None."""
    value = raw.strip()
    if value.startswith("sr:"):
        value = value[len("sr:"):]
    return f"sr:{value}" if _SR_ID.match(value) else None


def task_ref_from_trace_id(raw: str) -> str | None:
    """`T-059` or `task:T-059` -> `task:T-059`. Anything else -> None."""
    value = raw.strip()
    if value.startswith("task:"):
        value = value[len("task:"):]
    return f"task:{value}" if _TASK_ID.match(value) else None


def trace_id_for_task(task_id: str) -> str:
    """The trace node id for a task ledger id."""
    return task_id if task_id.startswith("task:") else f"task:{task_id}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk proxy uv run pytest tests/unit/system/test_refs.py -v`
Expected: PASS

- [ ] **Step 5: Allow `task:` and `file:` as scopes**

In `src/factory/system/queries.py`, extend `_SCOPE_KINDS` to `("bundle", "sr", "task", "file")` and update `parse_scope_ref`'s error message to `"expected bundle:<id>, sr:<id>, task:<id> or file:<path>"`. Update its docstring: task and file are now openable per design §3.1.

Add to `tests/unit/system/test_queries.py`:

```python
def test_task_and_file_are_now_openable_scopes():
    assert parse_scope_ref("task:T-059").kind == "task"
    assert parse_scope_ref("file:src/drone/planning/reactive.py").kind == "file"


def test_spec_and_plan_are_still_not_openable_scopes():
    with pytest.raises(ScopeKindError):
        parse_scope_ref("spec:docs/superpowers/specs/x.md")
```

- [ ] **Step 6: Run the suite and static checks**

Run: `rtk proxy uv run pytest tests/unit/system -q && uv run pyright && uv run ruff check src tests`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/factory/system/refs.py tests/unit/system/test_refs.py src/factory/system/queries.py tests/unit/system/test_queries.py
git commit -m "feat(system): map trace ids to scope refs and open task/file scopes"
```

---

## Task 2: Session records as a second evidence source

Manifests only exist from 2026-08-09. `sessions/*.session.json` is a recorded artifact written by each run and is the only surviving history for everything earlier. It is thinner: no commit range, no changed files, no patch.

**Files:**
- Create: `src/factory/system/sessions.py`
- Create: `tests/unit/system/test_sessions.py`
- Modify: `src/factory/system/models.py` (add `SESSION = "session"` to `CitationKind`)

**Interfaces:**
- Consumes: `CitationKind.SESSION`
- Produces: `SessionRun` dataclass with fields `run_id: str`, `task_id: str`, `started_at: str | None`, `ended_at: str | None`, `outcome: str`, `nodes: list[dict]`, `dod_met: bool | None`, `path: Path`; and `load_session_runs(repo_root: Path, task_id: str) -> list[SessionRun]`

- [ ] **Step 1: Write the failing test**

```python
import json
import pytest
from factory.system.sessions import SessionRun, load_session_runs

pytestmark = pytest.mark.unit


def _write_session(repo_root, session_id, task_id, outcome, dod_met=True):
    sessions = repo_root / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "started_at": "2026-08-06T20:00:00Z",
        "ended_at": "2026-08-06T20:30:00Z",
        "git": {"branch": "main", "head": "a" * 40},
        "tasks": [{
            "task_id": task_id,
            "title": "Some task",
            "outcome": outcome,
            "iterations": 1,
            "commits": [],
            "dod": {"met": dod_met},
            "nodes": [{"node": "dev", "result": "pass", "attempts": 1, "extra": {}}],
        }],
    }
    path = sessions / f"{session_id}.session.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_only_runs_for_the_requested_task(tmp_path):
    _write_session(tmp_path, "2026-08-06T20-00-00Z", "T-055", "completed")
    _write_session(tmp_path, "2026-08-06T21-00-00Z", "T-056", "rejected")

    runs = load_session_runs(tmp_path, "T-055")

    assert [r.task_id for r in runs] == ["T-055"]
    assert runs[0].outcome == "completed"
    assert runs[0].run_id == "2026-08-06T20-00-00Z"
    assert runs[0].dod_met is True


def test_rejected_and_escalated_runs_are_kept(tmp_path):
    _write_session(tmp_path, "s1", "T-055", "rejected", dod_met=False)
    _write_session(tmp_path, "s2", "T-055", "escalated", dod_met=False)

    outcomes = sorted(r.outcome for r in load_session_runs(tmp_path, "T-055"))

    assert outcomes == ["escalated", "rejected"], "failed attempts are part of the story"


def test_absent_sessions_directory_returns_no_runs_and_does_not_raise(tmp_path):
    assert load_session_runs(tmp_path, "T-055") == []


def test_an_unreadable_session_record_is_skipped_not_fatal(tmp_path):
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "broken.session.json").write_text("{not json", encoding="utf-8")
    _write_session(tmp_path, "good", "T-055", "completed")

    assert [r.run_id for r in load_session_runs(tmp_path, "T-055")] == ["good"]


def test_runs_are_ordered_by_recorded_start_time(tmp_path):
    _write_session(tmp_path, "later", "T-055", "completed")
    path = _write_session(tmp_path, "earlier", "T-055", "completed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["started_at"] = "2026-08-01T00:00:00Z"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert [r.run_id for r in load_session_runs(tmp_path, "T-055")] == ["earlier", "later"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/system/test_sessions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.system.sessions'`

- [ ] **Step 3: Add the citation kind**

In `src/factory/system/models.py`, add `SESSION = "session"` to `CitationKind`. Add the same value to the `citation.kind` enum in `src/factory/schemas/system_claim.schema.json` and in `system_response.schema.json`'s inlined `citation` `$def` — both, or they diverge, which cost an earlier task a review round.

- [ ] **Step 4: Write the implementation**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionRun:
    """One task-run as recorded in sessions/*.session.json.

    Thinner than an evidence manifest by nature: it has no commit range, no
    changed files and no patch, because none was recorded. Callers must render
    `implementation` as `missing` rather than deriving it from `git.head`.
    """

    run_id: str
    task_id: str
    started_at: str | None
    ended_at: str | None
    outcome: str
    nodes: list[dict]
    dod_met: bool | None
    path: Path


def load_session_runs(repo_root: Path, task_id: str) -> list[SessionRun]:
    """Recorded runs for one task, oldest first. Never raises on bad input."""
    sessions_dir = repo_root / "sessions"
    if not sessions_dir.is_dir():
        return []
    runs: list[SessionRun] = []
    for path in sorted(sessions_dir.glob("*.session.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        for entry in payload.get("tasks") or []:
            if not isinstance(entry, dict) or entry.get("task_id") != task_id:
                continue
            dod = entry.get("dod")
            runs.append(
                SessionRun(
                    run_id=str(payload.get("session_id") or path.stem),
                    task_id=task_id,
                    started_at=payload.get("started_at"),
                    ended_at=payload.get("ended_at"),
                    outcome=str(entry.get("outcome") or "unknown"),
                    nodes=list(entry.get("nodes") or []),
                    dod_met=dod.get("met") if isinstance(dod, dict) else None,
                    path=path,
                )
            )
    runs.sort(key=lambda r: (r.started_at or "", r.run_id))
    return runs
```

- [ ] **Step 5: Run the tests and static checks**

Run: `rtk proxy uv run pytest tests/unit/system -q && uv run pyright && uv run ruff check src tests`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/factory/system/sessions.py tests/unit/system/test_sessions.py src/factory/system/models.py src/factory/schemas/system_claim.schema.json src/factory/schemas/system_response.schema.json
git commit -m "feat(system): read session records as a second evidence source"
```

---

## Task 3: Task implementation story

**Files:**
- Create: `src/factory/system/story.py`
- Create: `tests/unit/system/test_story.py`
- Modify: `src/factory/system/cli.py` (add the `story` subcommand)
- Modify: `src/factory/schemas/system_response.schema.json` (add a `story` member)

**Interfaces:**
- Consumes: `load_session_runs`, `sr_ref_from_trace_id`, `trace_id_for_task`
- Produces: `query_story(repo_root: Path, scope: SystemScopeRef) -> dict` returning `{"scope": {...}, "task": {...}, "runs": [...], "requirements": [...], "degraded": bool, "degraded_reasons": [str]}`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from factory.system.models import SystemScopeRef
from factory.system.story import query_story

pytestmark = pytest.mark.unit


def test_manifest_runs_carry_implementation_detail(tmp_path, write_task, write_manifest):
    write_task(tmp_path, "T-059", status="done", satisfies=["SR-146"])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-059"))

    assert result["task"]["id"] == "T-059"
    assert len(result["runs"]) == 1
    run = result["runs"][0]
    assert run["source"] == "manifest"
    assert run["implementation"]["changed_files"] == ["src/a.py"]
    assert result["requirements"] == ["sr:SR-146"]


def test_session_only_runs_report_implementation_missing(tmp_path, write_task, write_session):
    write_task(tmp_path, "T-055", status="done", satisfies=[])
    write_session(tmp_path, "s1", "T-055", "completed")

    run = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-055"))["runs"][0]

    assert run["source"] == "session"
    assert run["implementation"]["kind"] == "missing"
    assert run["implementation"]["freshness"]["state"] == "n/a"
    assert run["citation"]["kind"] == "session"


def test_a_manifest_wins_over_a_session_record_for_the_same_run(tmp_path, write_task,
                                                                write_manifest, write_session):
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="dup", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])
    write_session(tmp_path, "dup", "T-059", "completed")

    runs = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-059"))["runs"]

    assert len(runs) == 1
    assert runs[0]["source"] == "manifest"


def test_a_task_with_no_runs_still_renders_with_history_missing(tmp_path, write_task):
    write_task(tmp_path, "T-070", status="todo", satisfies=["SR-1"])

    result = query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-070"))

    assert result["runs"] == []
    assert result["degraded"] is True
    assert any("no recorded runs" in r for r in result["degraded_reasons"])
    assert result["requirements"] == ["sr:SR-1"]


def test_an_unknown_task_raises_scope_not_found(tmp_path):
    from factory.system.queries import ScopeNotFoundError
    with pytest.raises(ScopeNotFoundError):
        query_story(tmp_path, SystemScopeRef(kind="task", ref="task:T-999"))
```

Add the three fixtures to `tests/unit/system/_fixtures.py`. `write_manifest` MUST call `factory.evidence.manifests.write_run_manifest`; `write_task` MUST produce frontmatter the real ledger parses; `write_session` is the helper from Task 2's test, moved here.

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/system/test_story.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.system.story'`

- [ ] **Step 3: Write the implementation**

`query_story` resolves the task through `factory.orchestrator.ledger.get_task`, raising `ScopeNotFoundError` when absent. It reads manifests via `manifests.list_run_manifests(repo_root / "evidence")` filtered on `task_id`, then adds session runs whose `run_id` is not already covered. Manifest runs cite `CitationKind.MANIFEST`; session runs cite `CitationKind.SESSION` and carry `implementation` as a `missing`/`n/a` claim. Requirements come from the trace `satisfies` edges for `trace_id_for_task(task.id)`, mapped through `sr_ref_from_trace_id` and dropped when unmappable. Runs are ordered by recorded `started_at`, then by citation path — never by array position across documents.

`degraded_reasons` entries are gated behind a real count, exactly as `query_timeline` does: no reason may fire with a count of zero.

- [ ] **Step 4: Run the tests**

Run: `rtk proxy uv run pytest tests/unit/system -q`
Expected: PASS

- [ ] **Step 5: Register the CLI subcommand**

Add `story` beside the existing subcommands in `cli.py`, taking `--scope` and `--json` from the shared `common` parent, and add a `story` member to `system_response.schema.json`. Add to `tests/unit/system/test_cli.py`:

```python
def test_story_subcommand_emits_json_for_a_task_scope(tmp_path, write_task):
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    out = run_cli(["story", "--scope", "task:T-059", "--repo-root", str(tmp_path), "--json"])
    assert json.loads(out)["task"]["id"] == "T-059"
```

- [ ] **Step 6: Run the suite and static checks**

Run: `rtk proxy uv run pytest tests/unit/system -q && uv run pyright && uv run ruff check src tests`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/factory/system/story.py tests/unit/system/test_story.py tests/unit/system/_fixtures.py src/factory/system/cli.py tests/unit/system/test_cli.py src/factory/schemas/system_response.schema.json
git commit -m "feat(system): add the task implementation story query"
```

---

## Task 4: Reverse navigation

**Files:**
- Create: `src/factory/system/reverse.py`
- Create: `tests/unit/system/test_reverse.py`
- Modify: `src/factory/system/cli.py` (add the `reverse` subcommand)
- Modify: `src/factory/schemas/system_response.schema.json` (add a `reverse` member)

**Interfaces:**
- Consumes: `sr_ref_from_trace_id`, `trace_id_for_task`
- Produces: `query_reverse(repo_root: Path, scope: SystemScopeRef) -> dict` returning `{"scope": {...}, "paths": [...], "degraded": bool, "degraded_reasons": [str]}` where each path is `{"file": str, "run": {...}, "task": {...}, "requirements": [...], "stops_at": str | None}`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from factory.system.models import SystemScopeRef
from factory.system.reverse import query_reverse
from factory.system.queries import ScopeNotFoundError

pytestmark = pytest.mark.unit


def test_walks_file_to_run_to_task_to_requirement(tmp_path, write_task, write_manifest):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    write_task(tmp_path, "T-059", status="done", satisfies=["SR-146"])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])

    result = query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:src/a.py"))

    assert len(result["paths"]) == 1
    path = result["paths"][0]
    assert path["run"]["run_id"] == "r1"
    assert path["task"]["id"] == "T-059"
    assert path["requirements"] == ["sr:SR-146"]
    assert path["stops_at"] is None


def test_a_file_no_run_touched_is_missing_not_empty(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "orphan.py").write_text("x = 1\n", encoding="utf-8")

    result = query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:src/orphan.py"))

    assert result["paths"] == []
    assert result["degraded"] is True
    assert any("no recorded run" in r for r in result["degraded_reasons"])


def test_the_chain_stops_where_a_hop_does_not_resolve(tmp_path, write_task, write_manifest):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])

    path = query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:src/a.py"))["paths"][0]

    assert path["requirements"] == []
    assert path["stops_at"] == "satisfies"


def test_one_file_touched_by_several_runs_yields_several_paths(tmp_path, write_task, write_manifest):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="escalated",
                   changed_files=["src/a.py"])
    write_manifest(tmp_path, run_id="r2", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])

    paths = query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:src/a.py"))["paths"]

    assert [p["run"]["run_id"] for p in paths] == ["r1", "r2"], "rework must not be collapsed"


def test_a_path_outside_the_repository_is_refused(tmp_path):
    with pytest.raises(ScopeNotFoundError):
        query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:../../etc/passwd"))


def test_an_exported_guide_is_not_a_navigable_file(tmp_path, write_exported_guide):
    exported = write_exported_guide(tmp_path / "guide.json")
    with pytest.raises(ScopeNotFoundError):
        query_reverse(tmp_path, SystemScopeRef(kind="file", ref=f"file:{exported.name}"))
```

`write_exported_guide` writes a real export via `factory.system.guide.export_guide` so the refusal is tested against the genuine artifact, not a lookalike.

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/system/test_reverse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.system.reverse'`

- [ ] **Step 3: Write the implementation**

`query_reverse` resolves the file ref against the repo root with `.resolve()` **before** the containment check, raising `ScopeNotFoundError` when it escapes, when it does not exist, or when `factory.system.guide.is_exported_guide` reports it as an export. It then scans `manifests.list_run_manifests(repo_root / "evidence")` for manifests whose `implementation.changed_files` contains the repo-relative path, and for each builds one path: run → `task_id` → ledger task → `satisfies` edges mapped through `sr_ref_from_trace_id`.

`stops_at` names the first hop that did not resolve (`"task"` or `"satisfies"`), or `None` when the chain completes. Paths are ordered by the run's recorded `started_at`, then citation path.

Session records are **not** used here: they record no changed files, so they cannot participate in a file-anchored walk.

- [ ] **Step 4: Run the tests**

Run: `rtk proxy uv run pytest tests/unit/system -q`
Expected: PASS

- [ ] **Step 5: Register the CLI subcommand and schema member**

Add `reverse` to `cli.py` and a `reverse` member to `system_response.schema.json`.

- [ ] **Step 6: Run the suite and static checks**

Run: `rtk proxy uv run pytest tests/unit/system -q && uv run pyright && uv run ruff check src tests`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/factory/system/reverse.py tests/unit/system/test_reverse.py src/factory/system/cli.py src/factory/schemas/system_response.schema.json
git commit -m "feat(system): add reverse navigation from a file to its requirements"
```

---

## Task 5: Feature briefing gains implementation, and the integration test

**Files:**
- Modify: `src/factory/system/queries.py` (`query_brief` bundle branch)
- Modify: `tests/unit/system/test_queries.py`
- Create: `tests/integration/system/test_vcycle.py`

**Interfaces:**
- Consumes: `query_story`
- Produces: each bundle `task:` member claim gains `implementation_summary`: `{"runs": int, "latest_outcome": str | None, "changed_file_count": int | None, "latest_validation": str | None}`

- [ ] **Step 1: Write the failing test**

```python
def test_bundle_task_members_carry_an_implementation_summary(tmp_path, write_task,
                                                              write_manifest, write_bundle):
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py", "src/b.py"])
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-059"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))

    member = next(c for c in result["claims"] if "T-059" in c["text"])
    summary = member["implementation_summary"]
    assert summary["runs"] == 1
    assert summary["latest_outcome"] == "completed"
    assert summary["changed_file_count"] == 2


def test_a_task_member_with_no_runs_summarises_as_none_not_zero(tmp_path, write_task,
                                                                write_bundle):
    write_task(tmp_path, "T-070", status="todo", satisfies=[])
    write_bundle(tmp_path / "bundles", "feat", "Feature", ["task:T-070"])

    result = query_brief(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:feat"))
    member = next(c for c in result["claims"] if "T-070" in c["text"])

    assert member["implementation_summary"]["runs"] == 0
    assert member["implementation_summary"]["latest_outcome"] is None
    assert member["implementation_summary"]["changed_file_count"] is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `rtk proxy uv run pytest tests/unit/system/test_queries.py -v -k implementation_summary`
Expected: FAIL — `KeyError: 'implementation_summary'`

- [ ] **Step 3: Write the implementation**

In `query_brief`'s bundle branch, for each resolved `task:` member call `query_story` and attach the summary. The aggregate claim class is `derived` and cites the manifests it came from. `changed_file_count` is `None` — not `0` — when nothing was recorded, so "no runs" never reads as "changed nothing". Add the member's `implementation_summary` to the claim schema.

- [ ] **Step 4: Write the integration test**

`tests/integration/system/test_vcycle.py`, marked `pytestmark = pytest.mark.integration`, builds a temp repo through the real writers and drives the real CLI end to end:

```python
def test_story_and_reverse_agree_about_the_same_run(tmp_path, ...):
    # build task + manifest through the real writers, then:
    story = run_module_cli(tmp_path, ["story", "--scope", "task:T-059", "--json"])
    reverse = run_module_cli(tmp_path, ["reverse", "--scope", "file:src/a.py", "--json"])
    assert story["runs"][0]["run_id"] == reverse["paths"][0]["run"]["run_id"]
```

`run_module_cli` invokes `uv run python -m factory.system` via `subprocess`, mirroring the existing `test_navigator_projection.py` helper.

- [ ] **Step 5: Run unit and integration suites**

Run: `rtk proxy uv run pytest tests/unit/system tests/integration/system -q -m 'unit or integration'`
Expected: PASS, with a non-zero collected count.

- [ ] **Step 6: Commit**

```bash
git add src/factory/system/queries.py tests/unit/system/test_queries.py tests/integration/system/test_vcycle.py src/factory/schemas/system_claim.schema.json
git commit -m "feat(system): summarise implementation per bundle task member"
```

---

## Task 6: Browser rendering for the V-cycle views

**Files:**
- Modify: `pi-ext/factory-watch/src/system-cli.ts` (add `loadSystemStory`, `loadSystemReverse`)
- Modify: `pi-ext/factory-watch/src/docs-server.ts` (add `/api/system/story`, `/api/system/reverse`)
- Modify: `pi-ext/factory-watch/src/system-page.ts` (render the two views)
- Modify: `pi-ext/factory-watch/src/system-context-tools.ts` (extend the existing tools)
- Create: `pi-ext/factory-watch/test/system-page-vcycle.test.ts`

**Interfaces:**
- Consumes: `runJsonCli` from `cli-runner.ts`, `buildSystemCommand` from `system-cli.ts`
- Produces: `loadSystemStory(cwd: string, scope: string): CliResult<SystemStory>`, `loadSystemReverse(cwd: string, scope: string): CliResult<SystemReverse>`

- [ ] **Step 1: Write the failing DOM test**

Extend the existing jsdom harness. Assert on real DOM nodes, never on the generated source string:

```typescript
test("a session-sourced run is visibly distinguished from a manifest run", async () => {
  const dom = await loadPage({ scope: "task:T-055" });
  const rows = dom.window.document.querySelectorAll("#panelStory .run");
  expect(rows.length).toBe(2);
  expect(rows[0].querySelector(".source")?.textContent).toBe("manifest");
  expect(rows[1].querySelector(".source")?.textContent).toBe("session");
  // The session run states its implementation is missing rather than hiding it.
  expect(rows[1].textContent).toContain("missing");
});

test("a reverse path that stops early names the hop it stopped at", async () => {
  const dom = await loadPage({ scope: "file:src/a.py" });
  const path = dom.window.document.querySelector("#panelReverse .path");
  expect(path?.textContent).toContain("satisfies");
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix pi-ext/factory-watch test -- --run system-page-vcycle`
Expected: FAIL — the panels do not exist

- [ ] **Step 3: Add the client wrappers**

Thin shims on `runJsonCli`, no interpretation. Exact command: `uv run python -m factory.system story --scope <ref> --json`.

- [ ] **Step 4: Add the routes**

Exact `pathname ===` matching only, mirroring the existing `/api/system/*` routes so dot-segment traversal still 404s.

- [ ] **Step 5: Render the views**

A Story panel listing runs with a `.source` badge (`manifest` or `session`), outcome, commit range where recorded, and changed files. A Reverse panel listing each path as file → run → task → requirements, naming `stops_at` where the chain stopped. Missing values render plainly and are never hidden. All payload text reaches the DOM via `createTextNode`.

- [ ] **Step 6: Extend the PIF tools**

Add the two queries to `system-context-tools.ts`. Do not create a registration surface.

- [ ] **Step 7: Run the full gates**

Run: `rtk proxy uv run pytest -q -m 'unit or integration' && uv run pyright && uv run ruff check src tests && npm --prefix pi-ext/factory-watch test && npm --prefix pi-ext/factory-watch run typecheck`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add pi-ext/factory-watch/src pi-ext/factory-watch/test
git commit -m "feat(factory-watch): render the task story and reverse navigation views"
```

---

## Plan self-review

**Spec coverage.** §3.1 scope kinds → Task 1. §3.2 namespace mapping → Task 1. §3.3 four-way separation → no code needed; the classes are unchanged. §4.1 task story → Task 3. §4.2 reverse navigation → Task 4. §4.3 briefing aggregates → Task 5. §5 data sources → Tasks 2–5. §6.1 session records → Task 2. §7 failure handling → tested in each of Tasks 2–5. §8 testing discipline → the Verification discipline section and every task's fixtures. §9 security → Task 4 Step 3 and Step 4. §10 non-goals → nothing in the plan builds them. §11 Increment C → out of scope by design.

**Type consistency.** `SessionRun` is defined in Task 2 and consumed in Task 3. `query_story` is defined in Task 3 and consumed in Task 5. `sr_ref_from_trace_id` / `trace_id_for_task` are defined in Task 1 and consumed in Tasks 3 and 4. `CitationKind.SESSION` is added in Task 2 and used in Task 3.

**Known gap carried from the spec.** `manifest.reviews` is empty on `--auto` runs, so the review column of the story view is designed from the schema, not observed data. Task 3 does not test it against a populated `reviews` array because no such manifest exists. Either record one non-`--auto` run before Task 3, or accept that column as unproven until one exists — the executor must raise this rather than fabricate a fixture for it.
