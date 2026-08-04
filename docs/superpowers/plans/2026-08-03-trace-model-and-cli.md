# Traceability Model and `factory trace` CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `src/factory/trace/` — a Python package that derives the artifact graph (requirements, specs, plans, tasks) from declared frontmatter only, reports traceability gaps and a health score, writes gap dispositions, and enforces a stateless completion gate.

**Architecture:** Pure functions over a repo root, in the shape of the existing `src/factory/requirements/` and `src/factory/validation/` packages: dataclasses + logic modules + an `argparse` `cli.py` + `__main__.py`. All writes go through `python-frontmatter`, exactly as `src/factory/polish/routing.py:41-46` already does, so this repo never grows a second frontmatter serializer. This package is the single source of truth for traceability rules; the TypeScript viewer (separate plan) consumes its `--json` output and holds no rules of its own.

**Tech Stack:** Python 3.11–3.12, `python-frontmatter`, `argparse`, `pytest`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-03-review-plans-browser-and-trace-health-design.md`
- **Declared edges only.** An edge exists only if it is written on disk. Never infer an edge from filename, date, or title similarity. (Spec §4.2)
- Every test module must set `pytestmark = pytest.mark.unit` — `pyproject.toml` sets `addopts = "-m unit"`, so unmarked tests silently do not run.
- Every source and test file starts with `from __future__ import annotations`.
- ruff line-length is 100.
- Tests live in `tests/unit/trace/` and that directory needs an `__init__.py` (matches `tests/unit/requirements/`).
- No new third-party dependencies. `python-frontmatter` is already in `[project].dependencies`.
- `[tool.setuptools.packages.find] where = ["src"]` discovers `factory.trace` automatically — do not edit `pyproject.toml`.
- Run tests with `uv run pytest`.

---

### Task 1: Node loading

**Files:**
- Create: `src/factory/trace/__init__.py` (empty)
- Create: `src/factory/trace/model.py`
- Create: `tests/unit/trace/__init__.py` (empty)
- Test: `tests/unit/trace/test_model_nodes.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `NodeKind`, `Node`, `load_nodes(root: Path) -> list[Node]`.
  - `Node(id: str, kind: NodeKind, title: str, path: Path, exempt: bool, deferred: str | None)`
  - ID scheme, used by every later task: `SR-001`, `BR-002`, `T-047` for frontmatter-identified artifacts; `plan:<filename>` and `spec:<filename>` for files that carry no id.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/__init__.py` as an empty file, then `tests/unit/trace/test_model_nodes.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.model import load_nodes

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_sr_task_plan_and_spec_nodes(tmp_path):
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\nid: SR-001\ntitle: Preempt patrol\nstatement: s\ndomain: behavioral\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n\nbody\n",
    )
    _write(
        tmp_path / "tasks" / "T-047-bug-capture.md",
        "---\nid: T-047\ntitle: Bug Capture\nstatus: done\ndod: []\n---\n\nbody\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "plans" / "p1.md", "# Sim Testbench Plan\n\nbody\n")
    _write(tmp_path / "docs" / "superpowers" / "specs" / "s1.md", "# Sim Design\n\nbody\n")

    nodes = {n.id: n for n in load_nodes(tmp_path)}

    assert nodes["SR-001"].kind == "sr"
    assert nodes["SR-001"].title == "Preempt patrol"
    assert nodes["T-047"].kind == "task"
    assert nodes["T-047"].title == "Bug Capture"
    assert nodes["plan:p1.md"].kind == "plan"
    assert nodes["plan:p1.md"].title == "Sim Testbench Plan"
    assert nodes["spec:s1.md"].kind == "spec"
    assert nodes["spec:s1.md"].title == "Sim Design"


def test_malformed_task_degrades_to_filename_instead_of_raising(tmp_path):
    _write(tmp_path / "tasks" / "T-099-broken.md", "---\nnot: valid: yaml: at all\n")

    nodes = {n.id: n for n in load_nodes(tmp_path)}

    assert nodes["T-099-broken.md"].kind == "task"
    assert nodes["T-099-broken.md"].title == "T-099-broken.md"


def test_reads_exempt_and_deferred_dispositions(tmp_path):
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Infra\nstatus: done\ndod: []\ntrace_exempt: true\n---\n",
    )
    _write(
        tmp_path / "tasks" / "T-002.md",
        '---\nid: T-002\ntitle: Later\nstatus: todo\ndod: []\n'
        'trace_deferred: "needs SR split"\n---\n',
    )

    nodes = {n.id: n for n in load_nodes(tmp_path)}

    assert nodes["T-001"].exempt is True
    assert nodes["T-001"].deferred is None
    assert nodes["T-002"].exempt is False
    assert nodes["T-002"].deferred == "needs SR split"


def test_missing_directories_yield_no_nodes(tmp_path):
    assert load_nodes(tmp_path) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/trace/test_model_nodes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.trace'`

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/trace/__init__.py` as an empty file, then `src/factory/trace/model.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import frontmatter

NodeKind = Literal["br", "sr", "spec", "plan", "task"]

_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind
    title: str
    path: Path
    exempt: bool = False
    deferred: str | None = None


def _load_post(path: Path) -> frontmatter.Post | None:
    # A malformed artifact must degrade to a filename-labelled node, never crash the
    # whole graph -- same contract doc-lister.ts:26 already honours on the TS side.
    try:
        return frontmatter.load(str(path))
    except Exception:
        return None


def _disposition(meta: dict) -> tuple[bool, str | None]:
    exempt = bool(meta.get("trace_exempt", False))
    deferred = meta.get("trace_deferred")
    return exempt, str(deferred) if deferred else None


def _first_heading(text: str, fallback: str) -> str:
    match = _HEADING_RE.search(text)
    return match.group(1).strip() if match else fallback


def _id_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    if post is None or "id" not in post.metadata:
        return Node(id=path.name, kind=kind, title=path.name, path=path)
    exempt, deferred = _disposition(post.metadata)
    return Node(
        id=str(post.metadata["id"]),
        kind=kind,
        title=str(post.metadata.get("title", path.name)),
        path=path,
        exempt=exempt,
        deferred=deferred,
    )


def _file_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    body = post.content if post is not None else path.read_text(encoding="utf-8")
    meta = post.metadata if post is not None else {}
    exempt, deferred = _disposition(meta)
    return Node(
        id=f"{kind}:{path.name}",
        kind=kind,
        title=_first_heading(body, path.name),
        path=path,
        exempt=exempt,
        deferred=deferred,
    )


def _glob(root: Path, *parts: str, pattern: str) -> list[Path]:
    directory = root.joinpath(*parts)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(pattern))


def load_nodes(root: Path) -> list[Node]:
    nodes: list[Node] = []
    for path in _glob(root, "requirements", pattern="SR-*.md"):
        nodes.append(_id_node(path, "sr"))
    for path in _glob(root, "requirements", pattern="BR-*.md"):
        nodes.append(_id_node(path, "br"))
    for path in _glob(root, "tasks", pattern="T-*.md"):
        nodes.append(_id_node(path, "task"))
    for path in _glob(root, "docs", "superpowers", "plans", pattern="*.md"):
        nodes.append(_file_node(path, "plan"))
    for path in _glob(root, "docs", "superpowers", "specs", pattern="*.md"):
        nodes.append(_file_node(path, "spec"))
    return nodes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/trace/test_model_nodes.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/factory/trace/ tests/unit/trace/
git commit -m "feat(trace): load artifact nodes from declared frontmatter

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Edge extraction

**Files:**
- Modify: `src/factory/trace/model.py` (append `EdgeKind`, `Edge`, `extract_edges`)
- Test: `tests/unit/trace/test_model_edges.py`

**Interfaces:**
- Consumes: `Node`, `load_nodes` from Task 1.
- Produces: `EdgeKind = Literal["source_plan", "satisfies", "upstream", "spec_ref"]`,
  `Edge(src: str, dst: str, kind: EdgeKind)`,
  `extract_edges(root: Path, nodes: list[Node]) -> list[Edge]`.
  `dst` may name a node that does not exist — dangling references are detected in Task 3, not silently dropped here.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/test_model_edges.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.model import Edge, extract_edges, load_nodes

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _edges(tmp_path: Path) -> list[Edge]:
    return extract_edges(tmp_path, load_nodes(tmp_path))


def test_task_declares_source_plan_and_satisfies(tmp_path):
    _write(
        tmp_path / "tasks" / "T-012.md",
        "---\nid: T-012\ntitle: t\nstatus: done\ndod: []\n"
        "source_plan: docs/superpowers/plans/p1.md\nsatisfies:\n- SR-001\n---\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "plans" / "p1.md", "# P\n")

    edges = _edges(tmp_path)

    assert Edge("T-012", "plan:p1.md", "source_plan") in edges
    assert Edge("T-012", "SR-001", "satisfies") in edges


def test_scalar_satisfies_is_accepted_as_single_edge(tmp_path):
    _write(
        tmp_path / "tasks" / "T-013.md",
        "---\nid: T-013\ntitle: t\nstatus: todo\ndod: []\nsatisfies: SR-002\n---\n",
    )

    assert Edge("T-013", "SR-002", "satisfies") in _edges(tmp_path)


def test_sr_upstream_edge_is_kept_even_when_target_is_missing(tmp_path):
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n"
        "upstream:\n- BR-002\n---\n",
    )

    assert Edge("SR-001", "BR-002", "upstream") in _edges(tmp_path)


def test_plan_spec_edge_comes_from_a_literal_path_in_the_body(tmp_path):
    _write(
        tmp_path / "docs" / "superpowers" / "plans" / "p1.md",
        "# Plan\n\nSee docs/superpowers/specs/2026-07-30-design.md for context.\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "specs" / "2026-07-30-design.md", "# Spec\n")

    assert Edge("plan:p1.md", "spec:2026-07-30-design.md", "spec_ref") in _edges(tmp_path)


def test_similar_filenames_alone_never_create_an_edge(tmp_path):
    # The core invariant: a plan and a spec sharing a date and stem are NOT linked
    # unless the plan actually writes the path. Spec section 4.2.
    _write(tmp_path / "docs" / "superpowers" / "plans" / "2026-07-30-sim.md", "# Sim Plan\n")
    _write(tmp_path / "docs" / "superpowers" / "specs" / "2026-07-30-sim-design.md", "# Sim Spec\n")

    assert [e for e in _edges(tmp_path) if e.kind == "spec_ref"] == []


def test_duplicate_references_produce_one_edge(tmp_path):
    _write(
        tmp_path / "docs" / "superpowers" / "plans" / "p1.md",
        "# P\n\ndocs/superpowers/specs/s1.md and again docs/superpowers/specs/s1.md\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "specs" / "s1.md", "# S\n")

    assert len([e for e in _edges(tmp_path) if e.kind == "spec_ref"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/trace/test_model_edges.py -v`
Expected: FAIL — `ImportError: cannot import name 'Edge' from 'factory.trace.model'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/factory/trace/model.py`:

```python
EdgeKind = Literal["source_plan", "satisfies", "upstream", "spec_ref"]

_SPEC_REF_RE = re.compile(r"docs/superpowers/specs/([A-Za-z0-9._-]+\.md)")


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: EdgeKind


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def extract_edges(root: Path, nodes: list[Node]) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[Edge] = set()

    def add(edge: Edge) -> None:
        if edge not in seen:
            seen.add(edge)
            edges.append(edge)

    for node in nodes:
        if node.kind in ("task", "sr", "br"):
            post = _load_post(node.path)
            if post is None:
                continue
            meta = post.metadata
            source_plan = meta.get("source_plan")
            if source_plan:
                add(Edge(node.id, f"plan:{Path(str(source_plan)).name}", "source_plan"))
            for sr_id in _as_list(meta.get("satisfies")):
                add(Edge(node.id, sr_id, "satisfies"))
            for upstream_id in _as_list(meta.get("upstream")):
                add(Edge(node.id, upstream_id, "upstream"))
        elif node.kind == "plan":
            post = _load_post(node.path)
            body = post.content if post is not None else node.path.read_text(encoding="utf-8")
            for filename in _SPEC_REF_RE.findall(body):
                add(Edge(node.id, f"spec:{filename}", "spec_ref"))

    return edges
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS — 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/factory/trace/model.py tests/unit/trace/test_model_edges.py
git commit -m "feat(trace): extract declared edges only, never inferred

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Validation status join

**Files:**
- Create: `src/factory/trace/validation_status.py`
- Test: `tests/unit/trace/test_validation_status.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `SrState = Literal["passed", "failed", "error", "never_validated"]`,
  `SrStatus(id, state, stale, metric, value, assert_expr, trials, declared_trials, artifacts, error)`,
  `load_validation(root: Path) -> dict[str, SrStatus]` keyed by SR id.
  Reads `validation/validation-report.json`, whose entry shape is written by
  `src/factory/validation/report.py:46-59`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/test_validation_status.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from factory.trace.validation_status import load_validation

pytestmark = pytest.mark.unit


def _report(tmp_path: Path, entries: list[dict]) -> None:
    path = tmp_path / "validation" / "validation-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"requirements": entries}), encoding="utf-8")


def test_passing_entry(tmp_path):
    _report(
        tmp_path,
        [{
            "id": "SR-001", "domain": "behavioral", "metric": "preemption_success_rate",
            "value": 1.0, "assert": ">= 0.90", "passed": True, "trials": 3,
            "declared_trials": 3, "stale": False, "artifacts": ["traces/shark.json"],
        }],
    )

    status = load_validation(tmp_path)["SR-001"]

    assert status.state == "passed"
    assert status.stale is False
    assert status.value == 1.0
    assert status.assert_expr == ">= 0.90"
    assert status.trials == 3
    assert status.declared_trials == 3
    assert status.artifacts == ["traces/shark.json"]


def test_failing_entry(tmp_path):
    _report(tmp_path, [{"id": "SR-002", "passed": False, "stale": False}])

    assert load_validation(tmp_path)["SR-002"].state == "failed"


def test_harness_error_entry_is_its_own_state(tmp_path):
    _report(tmp_path, [{"id": "SR-003", "error": "unknown harness: bogus"}])

    status = load_validation(tmp_path)["SR-003"]

    assert status.state == "error"
    assert status.error == "unknown harness: bogus"


def test_stale_is_orthogonal_to_passed(tmp_path):
    # The dangerous state: green earned against a statement that has since changed.
    _report(tmp_path, [{"id": "SR-004", "passed": True, "stale": True}])

    status = load_validation(tmp_path)["SR-004"]

    assert status.state == "passed"
    assert status.stale is True


def test_missing_report_yields_empty_map_not_an_error(tmp_path):
    assert load_validation(tmp_path) == {}


def test_unreadable_report_yields_empty_map(tmp_path):
    path = tmp_path / "validation" / "validation-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert load_validation(tmp_path) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/trace/test_validation_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.trace.validation_status'`

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/trace/validation_status.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SrState = Literal["passed", "failed", "error", "never_validated"]

REPORT_RELPATH = ("validation", "validation-report.json")


@dataclass(frozen=True)
class SrStatus:
    id: str
    state: SrState
    stale: bool = False
    metric: str | None = None
    value: float | None = None
    assert_expr: str | None = None
    trials: int | None = None
    declared_trials: int | None = None
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None


def report_path(root: Path) -> Path:
    return root.joinpath(*REPORT_RELPATH)


def _entry_state(entry: dict) -> SrState:
    if entry.get("error"):
        return "error"
    return "passed" if entry.get("passed") else "failed"


def load_validation(root: Path) -> dict[str, SrStatus]:
    # A missing or unreadable report means "nothing has been validated", which is
    # never_validated for every SR -- not failed. Spec section 5.
    try:
        raw = json.loads(report_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    statuses: dict[str, SrStatus] = {}
    for entry in raw.get("requirements", []):
        req_id = str(entry.get("id", ""))
        if not req_id:
            continue
        value = entry.get("value")
        statuses[req_id] = SrStatus(
            id=req_id,
            state=_entry_state(entry),
            stale=bool(entry.get("stale", False)),
            metric=entry.get("metric"),
            value=float(value) if isinstance(value, (int, float)) else None,
            assert_expr=entry.get("assert"),
            trials=entry.get("trials"),
            declared_trials=entry.get("declared_trials"),
            artifacts=[str(a) for a in entry.get("artifacts", [])],
            error=entry.get("error"),
        )
    return statuses
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS — 16 passed

- [ ] **Step 5: Commit**

```bash
git add src/factory/trace/validation_status.py tests/unit/trace/test_validation_status.py
git commit -m "feat(trace): join validation report to SR ids in five states

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Gap detection and dispositions

**Files:**
- Create: `src/factory/trace/gaps.py`
- Test: `tests/unit/trace/test_gaps.py`

**Interfaces:**
- Consumes: `Node`, `Edge` (Task 1-2), `SrStatus` (Task 3).
- Produces: `GapKind`, `Disposition`, `Gap(node_id, kind, detail, disposition)`,
  `find_gaps(nodes, edges, validation) -> list[Gap]`.
  `GapKind = Literal["task_no_sr", "task_plan_missing", "plan_no_spec", "dangling_upstream", "sr_unsatisfied", "sr_unvalidated", "sr_stale"]`
  `Disposition = Literal["pending", "exempt", "deferred"]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/test_gaps.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.gaps import find_gaps
from factory.trace.model import Edge, Node
from factory.trace.validation_status import SrStatus

pytestmark = pytest.mark.unit


def _task(node_id: str, *, exempt: bool = False, deferred: str | None = None) -> Node:
    return Node(node_id, "task", node_id, Path(f"tasks/{node_id}.md"), exempt, deferred)


def _sr(node_id: str) -> Node:
    return Node(node_id, "sr", node_id, Path(f"requirements/{node_id}.md"))


def _plan(name: str) -> Node:
    return Node(f"plan:{name}", "plan", name, Path(f"docs/superpowers/plans/{name}"))


def _kinds(gaps, node_id: str) -> set[str]:
    return {g.kind for g in gaps if g.node_id == node_id}


def test_task_without_satisfies_is_a_gap(tmp_path):
    gaps = find_gaps([_task("T-001")], [], {})

    assert "task_no_sr" in _kinds(gaps, "T-001")


def test_task_source_plan_pointing_at_missing_file_is_a_gap():
    nodes = [_task("T-001")]
    edges = [Edge("T-001", "plan:gone.md", "source_plan")]

    assert "task_plan_missing" in _kinds(find_gaps(nodes, edges, {}), "T-001")


def test_plan_without_a_spec_reference_is_a_gap():
    assert "plan_no_spec" in _kinds(find_gaps([_plan("p1.md")], [], {}), "plan:p1.md")


def test_dangling_upstream_is_a_gap():
    nodes = [_sr("SR-001")]
    edges = [Edge("SR-001", "BR-002", "upstream")]

    assert "dangling_upstream" in _kinds(find_gaps(nodes, edges, {}), "SR-001")


def test_sr_absent_from_report_is_unvalidated_not_failed():
    kinds = _kinds(find_gaps([_sr("SR-001")], [], {}), "SR-001")

    assert "sr_unvalidated" in kinds


def test_passing_but_stale_sr_is_a_gap():
    validation = {"SR-001": SrStatus("SR-001", "passed", stale=True)}
    kinds = _kinds(find_gaps([_sr("SR-001")], [], validation), "SR-001")

    assert "sr_stale" in kinds
    assert "sr_unvalidated" not in kinds


def test_sr_with_no_satisfying_task_is_a_gap():
    assert "sr_unsatisfied" in _kinds(find_gaps([_sr("SR-001")], [], {}), "SR-001")


def test_satisfied_task_and_sr_produce_no_link_gaps():
    nodes = [_task("T-001"), _sr("SR-001")]
    edges = [Edge("T-001", "SR-001", "satisfies")]

    gaps = find_gaps(nodes, edges, {})

    assert "task_no_sr" not in _kinds(gaps, "T-001")
    assert "sr_unsatisfied" not in _kinds(gaps, "SR-001")


def test_exempt_task_gap_is_reported_with_exempt_disposition():
    gaps = [g for g in find_gaps([_task("T-001", exempt=True)], [], {}) if g.kind == "task_no_sr"]

    assert [g.disposition for g in gaps] == ["exempt"]


def test_deferred_task_gap_carries_the_reason_as_detail():
    nodes = [_task("T-001", deferred="needs an SR split first")]

    gaps = [g for g in find_gaps(nodes, [], {}) if g.kind == "task_no_sr"]

    assert gaps[0].disposition == "deferred"
    assert "needs an SR split first" in gaps[0].detail


def test_an_sr_cannot_exempt_itself_even_if_the_file_declares_it():
    # Spec 4.4: a requirement no task satisfies and no run validates is a real
    # gap, never an exception. A hand-edited SR must not be able to opt out.
    node = Node("SR-001", "sr", "SR-001", Path("requirements/SR-001.md"), exempt=True)

    gaps = [g for g in find_gaps([node], [], {}) if g.kind == "sr_unsatisfied"]

    assert gaps[0].disposition == "pending"


def test_gap_order_is_deterministic():
    nodes = [_task("T-002"), _task("T-001"), _plan("b.md"), _plan("a.md")]

    first = [(g.node_id, g.kind) for g in find_gaps(nodes, [], {})]
    second = [(g.node_id, g.kind) for g in find_gaps(list(reversed(nodes)), [], {})]

    assert first == second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/trace/test_gaps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.trace.gaps'`

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/trace/gaps.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from factory.trace.model import Edge, Node
from factory.trace.validation_status import SrStatus

GapKind = Literal[
    "task_no_sr",
    "task_plan_missing",
    "plan_no_spec",
    "dangling_upstream",
    "sr_unsatisfied",
    "sr_unvalidated",
    "sr_stale",
]

Disposition = Literal["pending", "exempt", "deferred"]

_KIND_ORDER: dict[str, int] = {
    "task_no_sr": 0,
    "plan_no_spec": 1,
    "sr_unsatisfied": 2,
    "sr_unvalidated": 3,
    "sr_stale": 4,
    "dangling_upstream": 5,
    "task_plan_missing": 6,
}


@dataclass(frozen=True)
class Gap:
    node_id: str
    kind: GapKind
    detail: str
    disposition: Disposition = "pending"


def _disposition_of(node: Node) -> tuple[Disposition, str]:
    # SRs are deliberately not exemptable (spec 4.4). Deferral is still allowed --
    # an SR may legitimately need more time -- but it can never be waived outright.
    if node.exempt and node.kind not in ("sr", "br"):
        return "exempt", "declared trace_exempt"
    if node.deferred:
        return "deferred", f"deferred: {node.deferred}"
    return "pending", ""


def find_gaps(
    nodes: list[Node], edges: list[Edge], validation: dict[str, SrStatus]
) -> list[Gap]:
    by_id = {n.id: n for n in nodes}
    gaps: list[Gap] = []

    def add(node: Node, kind: GapKind, detail: str) -> None:
        disposition, note = _disposition_of(node)
        gaps.append(Gap(node.id, kind, f"{detail} ({note})" if note else detail, disposition))

    out = {n.id: [e for e in edges if e.src == n.id] for n in nodes}
    satisfied_srs = {e.dst for e in edges if e.kind == "satisfies"}

    for node in nodes:
        node_edges = out[node.id]
        if node.kind == "task":
            if not any(e.kind == "satisfies" for e in node_edges):
                add(node, "task_no_sr", "task declares no satisfies")
            for edge in node_edges:
                if edge.kind == "source_plan" and edge.dst not in by_id:
                    add(node, "task_plan_missing", f"source_plan target missing: {edge.dst}")
        elif node.kind == "plan":
            if not any(e.kind == "spec_ref" for e in node_edges):
                add(node, "plan_no_spec", "plan references no spec")
        elif node.kind == "sr":
            if node.id not in satisfied_srs:
                add(node, "sr_unsatisfied", "no task declares satisfies for this SR")
            status = validation.get(node.id)
            if status is None or status.state == "never_validated":
                add(node, "sr_unvalidated", "absent from validation report")
            elif status.stale:
                add(node, "sr_stale", "result predates a change to statement or binding")

        for edge in node_edges:
            if edge.kind == "upstream" and edge.dst not in by_id:
                add(node, "dangling_upstream", f"upstream target missing: {edge.dst}")

    gaps.sort(key=lambda g: (_KIND_ORDER[g.kind], g.node_id))
    return gaps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS — 28 passed

- [ ] **Step 5: Commit**

```bash
git add src/factory/trace/gaps.py tests/unit/trace/test_gaps.py
git commit -m "feat(trace): detect gaps with frontmatter-declared dispositions

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Health score

**Files:**
- Create: `src/factory/trace/health.py`
- Test: `tests/unit/trace/test_health.py`

**Interfaces:**
- Consumes: `Gap`, `find_gaps` (Task 4), `Node` (Task 1).
- Produces: `ClassHealth(name, satisfied, expected, exempt)`,
  `Health(classes, satisfied, expected, dangling, deferred)` with a `percent` property,
  `compute_health(nodes: list[Node], gaps: list[Gap]) -> Health`.
  Slot classes, in order: `"task->plan"`, `"task->SR"`, `"plan->spec"`, `"SR satisfied"`, `"SR validated"`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/test_health.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.gaps import Gap
from factory.trace.health import compute_health
from factory.trace.model import Node

pytestmark = pytest.mark.unit


def _task(node_id: str) -> Node:
    return Node(node_id, "task", node_id, Path(f"tasks/{node_id}.md"))


def _sr(node_id: str) -> Node:
    return Node(node_id, "sr", node_id, Path(f"requirements/{node_id}.md"))


def _by_name(health) -> dict[str, object]:
    return {c.name: c for c in health.classes}


def test_no_gaps_is_full_health():
    health = compute_health([_task("T-001")], [])

    assert health.percent == 100
    assert health.expected == 2  # one source_plan slot + one satisfies slot


def test_pending_gap_consumes_a_slot():
    gaps = [Gap("T-001", "task_no_sr", "d", "pending")]

    health = compute_health([_task("T-001")], gaps)

    assert _by_name(health)["task->SR"].satisfied == 0
    assert health.percent == 50


def test_exempt_gap_removes_the_slot_so_100_stays_reachable():
    gaps = [Gap("T-001", "task_no_sr", "d", "exempt")]

    health = compute_health([_task("T-001")], gaps)

    assert _by_name(health)["task->SR"].expected == 0
    assert _by_name(health)["task->SR"].exempt == 1
    assert health.percent == 100


def test_deferred_gap_still_counts_against_the_score():
    # Deferring is honest, not free -- it must not inflate the number.
    gaps = [Gap("T-001", "task_no_sr", "d", "deferred")]

    health = compute_health([_task("T-001")], gaps)

    assert _by_name(health)["task->SR"].satisfied == 0
    assert health.deferred == 1
    assert health.percent == 50


def test_dangling_references_are_counted_but_not_scored():
    gaps = [Gap("SR-001", "dangling_upstream", "d", "pending")]

    health = compute_health([_sr("SR-001")], gaps)

    assert health.dangling == 1
    assert _by_name(health)["SR satisfied"].expected == 1


def test_upstream_is_never_an_expected_slot():
    # A top-level SR legitimately has no parent; penalising that would be wrong.
    health = compute_health([_sr("SR-001")], [])

    assert "SR upstream" not in _by_name(health)
    assert _by_name(health)["SR validated"].expected == 1


def test_empty_repo_is_100_percent_not_a_division_error():
    assert compute_health([], []).percent == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/trace/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.trace.health'`

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/trace/health.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from factory.trace.gaps import Gap
from factory.trace.model import Node

# Which gap kind consumes which slot class. dangling_upstream and
# task_plan_missing are defects, not unfilled slots, so they are counted
# separately and never folded into the percentage. Spec section 4.5.
_SLOT_OF_GAP: dict[str, str] = {
    "task_no_sr": "task->SR",
    "plan_no_spec": "plan->spec",
    "sr_unsatisfied": "SR satisfied",
    "sr_unvalidated": "SR validated",
}

_CLASS_ORDER = ["task->plan", "task->SR", "plan->spec", "SR satisfied", "SR validated"]

_SLOTS_PER_NODE: dict[str, list[str]] = {
    "task": ["task->plan", "task->SR"],
    "plan": ["plan->spec"],
    "sr": ["SR satisfied", "SR validated"],
}


@dataclass(frozen=True)
class ClassHealth:
    name: str
    satisfied: int
    expected: int
    exempt: int


@dataclass(frozen=True)
class Health:
    classes: list[ClassHealth]
    satisfied: int
    expected: int
    dangling: int
    deferred: int

    @property
    def percent(self) -> int:
        if self.expected == 0:
            return 100
        return round(100 * self.satisfied / self.expected)


def compute_health(nodes: list[Node], gaps: list[Gap]) -> Health:
    expected = {name: 0 for name in _CLASS_ORDER}
    unfilled = {name: 0 for name in _CLASS_ORDER}
    exempt = {name: 0 for name in _CLASS_ORDER}

    for node in nodes:
        for slot in _SLOTS_PER_NODE.get(node.kind, []):
            expected[slot] += 1

    dangling = 0
    deferred = 0
    for gap in gaps:
        if gap.kind in ("dangling_upstream", "task_plan_missing"):
            dangling += 1
            continue
        if gap.disposition == "deferred":
            deferred += 1
        slot = _SLOT_OF_GAP.get(gap.kind)
        if slot is None:
            continue
        if gap.disposition == "exempt":
            expected[slot] -= 1
            exempt[slot] += 1
        else:
            unfilled[slot] += 1

    # sr_stale has no slot of its own: an SR is only counted once for validation,
    # and a stale result already fails to satisfy the "SR validated" slot.
    for gap in gaps:
        if gap.kind == "sr_stale" and gap.disposition != "exempt":
            unfilled["SR validated"] += 1

    classes = [
        ClassHealth(name, max(0, expected[name] - unfilled[name]), expected[name], exempt[name])
        for name in _CLASS_ORDER
    ]
    return Health(
        classes=classes,
        satisfied=sum(c.satisfied for c in classes),
        expected=sum(c.expected for c in classes),
        dangling=dangling,
        deferred=deferred,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS — 35 passed

- [ ] **Step 5: Commit**

```bash
git add src/factory/trace/health.py tests/unit/trace/test_health.py
git commit -m "feat(trace): unweighted health score with exemptions removing slots

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Graph assembly and `status` / `graph` CLI

**Files:**
- Create: `src/factory/trace/graph.py`
- Create: `src/factory/trace/cli.py`
- Create: `src/factory/trace/__main__.py`
- Test: `tests/unit/trace/test_cli_status.py`

**Interfaces:**
- Consumes: `load_nodes`, `extract_edges`, `load_validation`, `find_gaps`, `compute_health`.
- Produces: `build_graph(root: Path) -> Graph` where
  `Graph(nodes, edges, gaps, validation, health)`; `graph_to_dict(graph) -> dict`;
  `cmd_status(root) -> str`; `cmd_graph(root) -> dict`; `main(argv) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/test_cli_status.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from factory.trace.cli import cmd_graph, cmd_status, main

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _repo(tmp_path: Path) -> Path:
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Thing\nstatus: done\ndod: []\n"
        "source_plan: docs/superpowers/plans/p1.md\n---\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "plans" / "p1.md", "# Plan One\n")
    return tmp_path


def test_status_reports_percent_and_gap_count(tmp_path):
    text = cmd_status(_repo(tmp_path))

    assert "task->plan" in text
    assert "%" in text
    assert "task declares no satisfies" in text


def test_graph_dict_is_json_serialisable_and_has_the_expected_keys(tmp_path):
    data = cmd_graph(_repo(tmp_path))

    json.dumps(data)  # must not raise
    assert set(data) == {"nodes", "edges", "gaps", "validation", "health"}
    assert {"id": "T-001", "kind": "task"}.items() <= data["nodes"][0].items()


def test_main_graph_json_prints_parsable_json(tmp_path, capsys):
    exit_code = main(["graph", "--project-root", str(_repo(tmp_path)), "--json"])

    assert exit_code == 0
    assert "nodes" in json.loads(capsys.readouterr().out)


def test_main_status_on_empty_repo_exits_zero(tmp_path, capsys):
    assert main(["status", "--project-root", str(tmp_path)]) == 0
    assert "100%" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/trace/test_cli_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.trace.cli'`

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/trace/graph.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from factory.trace.gaps import Gap, find_gaps
from factory.trace.health import Health, compute_health
from factory.trace.model import Edge, Node, extract_edges, load_nodes
from factory.trace.validation_status import SrStatus, load_validation


@dataclass(frozen=True)
class Graph:
    nodes: list[Node]
    edges: list[Edge]
    gaps: list[Gap]
    validation: dict[str, SrStatus]
    health: Health


def build_graph(root: Path) -> Graph:
    nodes = load_nodes(root)
    edges = extract_edges(root, nodes)
    validation = load_validation(root)
    gaps = find_gaps(nodes, edges, validation)
    return Graph(nodes, edges, gaps, validation, compute_health(nodes, gaps))


def graph_to_dict(graph: Graph) -> dict:
    return {
        "nodes": [{**asdict(n), "path": str(n.path)} for n in graph.nodes],
        "edges": [asdict(e) for e in graph.edges],
        "gaps": [asdict(g) for g in graph.gaps],
        "validation": {k: asdict(v) for k, v in graph.validation.items()},
        "health": {
            "percent": graph.health.percent,
            "satisfied": graph.health.satisfied,
            "expected": graph.health.expected,
            "dangling": graph.health.dangling,
            "deferred": graph.health.deferred,
            "classes": [asdict(c) for c in graph.health.classes],
        },
    }
```

Create `src/factory/trace/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.trace.graph import build_graph, graph_to_dict


def cmd_graph(root: Path) -> dict:
    return graph_to_dict(build_graph(root))


def cmd_status(root: Path) -> str:
    graph = build_graph(root)
    health = graph.health
    lines = [f"traceability health: {health.percent}%  ({health.satisfied}/{health.expected} slots)"]
    for cls in health.classes:
        suffix = f"  [{cls.exempt} exempt]" if cls.exempt else ""
        lines.append(f"  {cls.name:<14} {cls.satisfied}/{cls.expected}{suffix}")
    lines.append(f"  dangling refs  {health.dangling}")
    lines.append(f"  deferred       {health.deferred}")
    pending = [g for g in graph.gaps if g.disposition == "pending"]
    lines.append("")
    lines.append(f"gaps: {len(graph.gaps)} ({len(pending)} pending)")
    for gap in graph.gaps:
        mark = {"pending": "!", "deferred": "~", "exempt": "-"}[gap.disposition]
        lines.append(f"  {mark} {gap.node_id:<24} {gap.kind:<18} {gap.detail}")
    return "\n".join(lines)


def _add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=Path("."), type=Path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-trace")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status")
    _add_root(p_status)

    p_graph = sub.add_parser("graph")
    _add_root(p_graph)
    p_graph.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "status":
        print(cmd_status(args.project_root))
    elif args.cmd == "graph":
        print(json.dumps(cmd_graph(args.project_root), indent=2))
    return 0
```

Create `src/factory/trace/__main__.py`:

```python
from __future__ import annotations

import sys

from factory.trace.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS — 39 passed

- [ ] **Step 5: Run it against this repo for real**

Run: `uv run python -m factory.trace status`
Expected: a health line plus a gap list. `task->SR` reads `0/45` and `plan->spec` reads roughly `10/26` — the numbers recorded in spec §4.5. If `task->SR` is not `0/45`, stop: either the repo changed or edge extraction is wrong.

- [ ] **Step 6: Commit**

```bash
git add src/factory/trace/graph.py src/factory/trace/cli.py src/factory/trace/__main__.py tests/unit/trace/test_cli_status.py
git commit -m "feat(trace): assemble graph and add status/graph CLI commands

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Disposition and link writers

**Files:**
- Create: `src/factory/trace/write.py`
- Modify: `src/factory/trace/cli.py` (add `link`, `exempt`, `defer` subcommands)
- Test: `tests/unit/trace/test_write.py`

**Interfaces:**
- Consumes: `load_nodes` (Task 1).
- Produces:
  - `link_satisfies(root: Path, task_id: str, sr_id: str) -> Path`
  - `link_spec(root: Path, plan_id: str, spec_filename: str) -> Path`
  - `set_exempt(root: Path, node_id: str, reason: str) -> Path`
  - `set_deferred(root: Path, node_id: str, reason: str) -> Path`
  - All raise `LookupError` for an unknown node and `ValueError` for a missing link target.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/test_write.py`:

```python
from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
from factory.trace.write import link_satisfies, link_spec, set_deferred, set_exempt

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _repo(tmp_path: Path) -> Path:
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Thing\nstatus: todo\ndod: []\n---\n\nbody\n",
    )
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "plans" / "p1.md", "# Plan One\n\nbody\n")
    _write(tmp_path / "docs" / "superpowers" / "specs" / "s1.md", "# Spec One\n")
    return tmp_path


def test_link_satisfies_writes_the_edge_and_preserves_the_body(tmp_path):
    root = _repo(tmp_path)

    path = link_satisfies(root, "T-001", "SR-001")

    post = frontmatter.load(str(path))
    assert post["satisfies"] == ["SR-001"]
    assert post["title"] == "Thing"
    assert "body" in post.content


def test_link_satisfies_is_idempotent(tmp_path):
    root = _repo(tmp_path)

    link_satisfies(root, "T-001", "SR-001")
    path = link_satisfies(root, "T-001", "SR-001")

    assert frontmatter.load(str(path))["satisfies"] == ["SR-001"]


def test_link_satisfies_refuses_a_missing_requirement(tmp_path):
    # A confirmed link must never create a fresh dangling reference. Spec section 6.4.
    root = _repo(tmp_path)

    with pytest.raises(ValueError, match="SR-999"):
        link_satisfies(root, "T-001", "SR-999")


def test_link_spec_appends_a_literal_path_the_reader_will_parse(tmp_path):
    root = _repo(tmp_path)

    path = link_spec(root, "plan:p1.md", "s1.md")

    assert "docs/superpowers/specs/s1.md" in path.read_text(encoding="utf-8")


def test_link_spec_refuses_a_missing_spec(tmp_path):
    root = _repo(tmp_path)

    with pytest.raises(ValueError, match="gone.md"):
        link_spec(root, "plan:p1.md", "gone.md")


def test_set_exempt_and_set_deferred_write_frontmatter(tmp_path):
    root = _repo(tmp_path)

    set_exempt(root, "T-001", "tooling task, no SR applies")
    post = frontmatter.load(str(root / "tasks" / "T-001.md"))
    assert post["trace_exempt"] is True
    assert post["trace_exempt_reason"] == "tooling task, no SR applies"

    set_deferred(root, "T-001", "needs an SR split")
    post = frontmatter.load(str(root / "tasks" / "T-001.md"))
    assert post["trace_deferred"] == "needs an SR split"


def test_set_deferred_on_a_plan_that_has_no_frontmatter(tmp_path):
    root = _repo(tmp_path)

    path = set_deferred(root, "plan:p1.md", "spec not written yet")

    post = frontmatter.load(str(path))
    assert post["trace_deferred"] == "spec not written yet"
    assert "# Plan One" in post.content


def test_set_exempt_refuses_a_requirement(tmp_path):
    # Spec 4.4: SRs are not exemptable. Defer them instead.
    with pytest.raises(ValueError, match="cannot be exempted"):
        set_exempt(_repo(tmp_path), "SR-001", "inconvenient")


def test_unknown_node_raises(tmp_path):
    with pytest.raises(LookupError):
        set_exempt(_repo(tmp_path), "T-404", "nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/trace/test_write.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.trace.write'`

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/trace/write.py`:

```python
from __future__ import annotations

from pathlib import Path

import frontmatter

from factory.trace.model import Node, load_nodes


def _node(root: Path, node_id: str) -> Node:
    for node in load_nodes(root):
        if node.id == node_id:
            return node
    raise LookupError(f"unknown node: {node_id}")


def _node_path(root: Path, node_id: str) -> Path:
    return _node(root, node_id).path


def _update_meta(path: Path, **fields: object) -> Path:
    post = frontmatter.load(str(path))
    for key, value in fields.items():
        post[key] = value
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def link_satisfies(root: Path, task_id: str, sr_id: str) -> Path:
    if not (root / "requirements" / f"{sr_id}.md").is_file():
        raise ValueError(f"no such requirement: {sr_id}")
    path = _node_path(root, task_id)
    post = frontmatter.load(str(path))
    existing = post.metadata.get("satisfies") or []
    if isinstance(existing, str):
        existing = [existing]
    current = [str(s) for s in existing]
    if sr_id not in current:
        current.append(sr_id)
    return _update_meta(path, satisfies=current)


def link_spec(root: Path, plan_id: str, spec_filename: str) -> Path:
    if not (root / "docs" / "superpowers" / "specs" / spec_filename).is_file():
        raise ValueError(f"no such spec: {spec_filename}")
    path = _node_path(root, plan_id)
    reference = f"docs/superpowers/specs/{spec_filename}"
    text = path.read_text(encoding="utf-8")
    if reference not in text:
        suffix = "" if text.endswith("\n") else "\n"
        text = f"{text}{suffix}\nSpec: {reference}\n"
        path.write_text(text, encoding="utf-8")
    return path


def set_exempt(root: Path, node_id: str, reason: str) -> Path:
    node = _node(root, node_id)
    if node.kind in ("sr", "br"):
        raise ValueError(f"{node_id} cannot be exempted; defer it instead")
    return _update_meta(node.path, trace_exempt=True, trace_exempt_reason=reason)


def set_deferred(root: Path, node_id: str, reason: str) -> Path:
    return _update_meta(_node_path(root, node_id), trace_deferred=reason)
```

- [ ] **Step 4: Wire the subcommands into `cli.py`**

In `src/factory/trace/cli.py`, add the import below the existing `from factory.trace.graph import ...`:

```python
from factory.trace.write import link_satisfies, link_spec, set_deferred, set_exempt
```

Then, inside `main`, insert these parsers immediately before `args = parser.parse_args(argv)`:

```python
    p_link = sub.add_parser("link")
    _add_root(p_link)
    p_link.add_argument("node_id")
    p_link.add_argument("--satisfies", metavar="SR-###")
    p_link.add_argument("--spec", metavar="FILENAME")

    p_exempt = sub.add_parser("exempt")
    _add_root(p_exempt)
    p_exempt.add_argument("node_id")
    p_exempt.add_argument("--reason", required=True)

    p_defer = sub.add_parser("defer")
    _add_root(p_defer)
    p_defer.add_argument("node_id")
    p_defer.add_argument("--reason", required=True)
```

And add these branches immediately before `return 0`:

```python
    elif args.cmd == "link":
        if not args.satisfies and not args.spec:
            parser.error("link requires --satisfies or --spec")
        try:
            if args.satisfies:
                print(link_satisfies(args.project_root, args.node_id, args.satisfies))
            if args.spec:
                print(link_spec(args.project_root, args.node_id, args.spec))
        except (LookupError, ValueError) as exc:
            print(f"error: {exc}")
            return 2
    elif args.cmd == "exempt":
        try:
            print(set_exempt(args.project_root, args.node_id, args.reason))
        except (LookupError, ValueError) as exc:
            print(f"error: {exc}")
            return 2
    elif args.cmd == "defer":
        try:
            print(set_deferred(args.project_root, args.node_id, args.reason))
        except LookupError as exc:
            print(f"error: {exc}")
            return 2
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS — 48 passed

- [ ] **Step 6: Commit**

```bash
git add src/factory/trace/write.py src/factory/trace/cli.py tests/unit/trace/test_write.py
git commit -m "feat(trace): deterministic writers for links, exemptions and deferrals

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: `next` — deterministic gap enumeration with ranked candidates

**Files:**
- Create: `src/factory/trace/propose.py`
- Modify: `src/factory/trace/cli.py` (add `next` subcommand)
- Test: `tests/unit/trace/test_propose.py`

**Interfaces:**
- Consumes: `build_graph` (Task 6), `Gap` (Task 4), `Node` (Task 1).
- Produces: `Candidate(id, title, summary, shared_terms, score)`,
  `Proposal(gap, node_title, node_excerpt, pending_total, candidates)`,
  `next_gap(root: Path) -> Proposal | None`, `proposal_to_dict(proposal) -> dict`.
- This is the deterministic half of the `/trace-fix` loop: it decides *which* gap
  and *which candidates exist*. The LLM decides which candidate is right.
- **Never truncate the candidate list.** Ranking orders it for convenience;
  truncating would let a lexical heuristic decide which links are reachable at all,
  and a correct match whose vocabulary differs would become unpickable. Every
  candidate carries its `summary` — the requirement's actual statement — because a
  shared-term count is not something a reader can reason semantically about.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/test_propose.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.propose import next_gap, proposal_to_dict

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sr(tmp_path: Path, sr_id: str, statement: str) -> None:
    _write(
        tmp_path / "requirements" / f"{sr_id}.md",
        f"---\nid: {sr_id}\ntitle: {sr_id} title\nstatement: {statement}\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
    )


def test_returns_none_when_nothing_is_pending(tmp_path):
    assert next_gap(tmp_path) is None


def test_proposes_the_first_pending_gap_with_candidates(tmp_path):
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Preempt patrol on shark detection\nstatus: todo\ndod: []\n---\n"
        "\nThe navigation system must preempt patrol when a shark is detected.\n",
    )
    _sr(tmp_path, "SR-001", "navigation shall preempt patrol when a shark is detected")
    _sr(tmp_path, "SR-002", "battery telemetry shall be published every second")

    proposal = next_gap(tmp_path)

    assert proposal is not None
    assert proposal.gap.node_id == "T-001"
    assert proposal.gap.kind == "task_no_sr"
    assert proposal.candidates[0].id == "SR-001"
    assert proposal.candidates[0].score > proposal.candidates[-1].score


def test_every_candidate_is_returned_never_truncated(tmp_path):
    # A lexical ranker must not decide which links are reachable. A correct match
    # whose vocabulary differs would otherwise be unpickable.
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod: []\n---\n\nbody\n",
    )
    for n in range(1, 13):
        _sr(tmp_path, f"SR-{n:03d}", f"requirement number {n}")

    assert len(next_gap(tmp_path).candidates) == 12


def test_candidate_carries_the_statement_not_just_a_term_count(tmp_path):
    # The consumer reasons semantically, which a shared-term count cannot support.
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Preempt patrol\nstatus: todo\ndod: []\n---\n\nshark detected\n",
    )
    _sr(tmp_path, "SR-001", "preempt patrol when a shark is detected")

    candidate = next_gap(tmp_path).candidates[0]

    assert candidate.summary == "preempt patrol when a shark is detected"
    assert "shark" in candidate.shared_terms


def test_pending_total_is_reported(tmp_path):
    for task_id in ("T-001", "T-002", "T-003"):
        _write(
            tmp_path / "tasks" / f"{task_id}.md",
            f"---\nid: {task_id}\ntitle: t\nstatus: todo\ndod: []\n---\n",
        )

    assert next_gap(tmp_path).pending_total == 3


def test_deferred_and_exempt_gaps_are_skipped(tmp_path):
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: A\nstatus: todo\ndod: []\ntrace_exempt: true\n---\n",
    )
    _write(
        tmp_path / "tasks" / "T-002.md",
        '---\nid: T-002\ntitle: B\nstatus: todo\ndod: []\ntrace_deferred: "later"\n---\n',
    )

    assert next_gap(tmp_path) is None


def test_ordering_is_stable_across_calls(tmp_path):
    for task_id in ("T-003", "T-001", "T-002"):
        _write(
            tmp_path / "tasks" / f"{task_id}.md",
            f"---\nid: {task_id}\ntitle: t\nstatus: todo\ndod: []\n---\n",
        )

    assert next_gap(tmp_path).gap.node_id == next_gap(tmp_path).gap.node_id == "T-001"


def test_proposal_dict_is_json_serialisable(tmp_path):
    import json

    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod: []\n---\n\nbody\n",
    )

    json.dumps(proposal_to_dict(next_gap(tmp_path)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/trace/test_propose.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.trace.propose'`

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/trace/propose.py`:

```python
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

import frontmatter

from factory.trace.gaps import Gap
from factory.trace.graph import build_graph
from factory.trace.model import Node

_WORD_RE = re.compile(r"[a-z]{4,}")

_STOPWORDS = frozenset({
    "shall", "must", "with", "when", "that", "this", "then", "from", "into",
    "than", "them", "they", "will", "have", "been", "were", "some", "such",
    "task", "plan", "spec", "should", "which", "while", "after", "before",
})

_EXCERPT_CHARS = 1200
_SUMMARY_CHARS = 400


@dataclass(frozen=True)
class Candidate:
    id: str
    title: str
    summary: str
    shared_terms: list[str]
    score: int


@dataclass(frozen=True)
class Proposal:
    gap: Gap
    node_title: str
    node_excerpt: str
    pending_total: int
    candidates: list[Candidate]


def _terms(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _summary_of(node: Node) -> str:
    # An SR's statement is the thing a reader actually needs in order to judge a
    # match; for everything else the first prose line is the closest equivalent.
    try:
        post = frontmatter.load(str(node.path))
        statement = post.metadata.get("statement")
        if statement:
            return str(statement)[:_SUMMARY_CHARS]
        body = post.content
    except Exception:
        body = _read(node.path)
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:_SUMMARY_CHARS]
    return node.title


def _candidates_for(gap: Gap, node: Node, nodes: list[Node]) -> list[Candidate]:
    if gap.kind == "task_no_sr":
        pool = [n for n in nodes if n.kind == "sr"]
    elif gap.kind == "plan_no_spec":
        pool = [n for n in nodes if n.kind == "spec"]
    elif gap.kind == "sr_unsatisfied":
        pool = [n for n in nodes if n.kind == "task"]
    else:
        return []

    source_terms = _terms(f"{node.title}\n{_read(node.path)}")
    candidates = [
        Candidate(
            id=other.id,
            title=other.title,
            summary=_summary_of(other),
            shared_terms=sorted(source_terms & _terms(f"{other.title}\n{_read(other.path)}")),
            score=len(source_terms & _terms(f"{other.title}\n{_read(other.path)}")),
        )
        for other in pool
    ]
    # Ranking only ORDERS the list. It is never truncated: a lexical heuristic must
    # not get to decide which links are reachable, or a correct match phrased in
    # different vocabulary becomes unpickable.
    # Deterministic: score descending, then id ascending. Never a random tiebreak.
    candidates.sort(key=lambda c: (-c.score, c.id))
    return candidates


def next_gap(root: Path) -> Proposal | None:
    graph = build_graph(root)
    by_id = {n.id: n for n in graph.nodes}
    pending = [g for g in graph.gaps if g.disposition == "pending"]
    for gap in pending:
        node = by_id.get(gap.node_id)
        if node is None:
            continue
        return Proposal(
            gap=gap,
            node_title=node.title,
            node_excerpt=_read(node.path)[:_EXCERPT_CHARS],
            pending_total=len(pending),
            candidates=_candidates_for(gap, node, graph.nodes),
        )
    return None


def proposal_to_dict(proposal: Proposal) -> dict:
    return {
        "gap": asdict(proposal.gap),
        "node_title": proposal.node_title,
        "node_excerpt": proposal.node_excerpt,
        "pending_total": proposal.pending_total,
        "candidates": [asdict(c) for c in proposal.candidates],
    }
```

- [ ] **Step 4: Wire the `next` subcommand into `cli.py`**

Add the import beside the other `factory.trace` imports:

```python
from factory.trace.propose import next_gap, proposal_to_dict
```

Add the parser immediately before `args = parser.parse_args(argv)`:

```python
    p_next = sub.add_parser("next")
    _add_root(p_next)
    p_next.add_argument("--json", action="store_true")
```

Add the branch immediately before `return 0`:

```python
    elif args.cmd == "next":
        proposal = next_gap(args.project_root)
        if proposal is None:
            print(json.dumps({"gap": None}) if args.json else "no pending gaps")
            return 0
        if args.json:
            print(json.dumps(proposal_to_dict(proposal), indent=2))
        else:
            print(
                f"{proposal.gap.node_id}  {proposal.gap.kind}  {proposal.gap.detail}"
                f"  ({proposal.pending_total} pending)"
            )
            for candidate in proposal.candidates:
                print(f"  {candidate.id:<12} {candidate.title}")
                print(f"    {candidate.summary}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS — 56 passed

- [ ] **Step 6: Commit**

```bash
git add src/factory/trace/propose.py src/factory/trace/cli.py tests/unit/trace/test_propose.py
git commit -m "feat(trace): deterministic gap enumeration with ranked candidates

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: `check` — the stateless completion gate

**Files:**
- Modify: `src/factory/trace/cli.py` (add `cmd_check` and the `check` subcommand)
- Test: `tests/unit/trace/test_cli_check.py`

**Interfaces:**
- Consumes: `build_graph` (Task 6), the disposition writers (Task 7).
- Produces: `cmd_check(root: Path) -> tuple[str, int]` — report text and exit code.
  Exit `1` when any gap is `pending`; exit `0` when every gap is linked, exempt, or
  deferred. The gate re-derives everything from disk on every call and consults no
  session log, so a model cannot satisfy it by asserting the work was done.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/test_cli_check.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.cli import cmd_check, main
from factory.trace.write import set_deferred, set_exempt

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _task(tmp_path: Path, task_id: str) -> None:
    _write(
        tmp_path / "tasks" / f"{task_id}.md",
        f"---\nid: {task_id}\ntitle: t\nstatus: todo\ndod: []\n"
        "source_plan: docs/superpowers/plans/p1.md\n---\n",
    )


def _plan(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs" / "superpowers" / "plans" / "p1.md",
        "# P\n\ndocs/superpowers/specs/s1.md\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "specs" / "s1.md", "# S\n")


def test_pending_gap_fails_the_gate(tmp_path):
    _task(tmp_path, "T-001")
    _plan(tmp_path)

    text, code = cmd_check(tmp_path)

    assert code == 1
    assert "T-001" in text
    assert "pending" in text


def test_exempting_every_gap_passes_the_gate(tmp_path):
    _task(tmp_path, "T-001")
    _plan(tmp_path)
    set_exempt(tmp_path, "T-001", "tooling")

    text, code = cmd_check(tmp_path)

    assert code == 0
    assert "0 pending" in text


def test_deferring_passes_the_gate_but_is_reported_as_a_warning(tmp_path):
    _task(tmp_path, "T-001")
    _plan(tmp_path)
    set_deferred(tmp_path, "T-001", "needs an SR split")

    text, code = cmd_check(tmp_path)

    assert code == 0
    assert "deferred" in text
    assert "needs an SR split" in text


def test_empty_repo_passes(tmp_path):
    assert cmd_check(tmp_path)[1] == 0


def test_main_check_propagates_the_exit_code(tmp_path, capsys):
    _task(tmp_path, "T-001")
    _plan(tmp_path)

    assert main(["check", "--project-root", str(tmp_path)]) == 1
    assert "pending" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/trace/test_cli_check.py -v`
Expected: FAIL — `ImportError: cannot import name 'cmd_check' from 'factory.trace.cli'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/factory/trace/cli.py`, after `cmd_status`:

```python
def cmd_check(root: Path) -> tuple[str, int]:
    # Stateless by design: every gap and every disposition is re-derived from disk,
    # so the gate cannot be satisfied by a claim that the work was done. Spec 6.3.
    graph = build_graph(root)
    pending = [g for g in graph.gaps if g.disposition == "pending"]
    deferred = [g for g in graph.gaps if g.disposition == "deferred"]
    exempt = [g for g in graph.gaps if g.disposition == "exempt"]

    lines = [
        f"traceability health: {graph.health.percent}%",
        f"{len(pending)} pending, {len(deferred)} deferred, {len(exempt)} exempt",
    ]
    if pending:
        lines.append("")
        lines.append("undiscussed gaps (the gate fails on these):")
        for gap in pending:
            lines.append(f"  ! {gap.node_id:<24} {gap.kind:<18} {gap.detail}")
    if deferred:
        lines.append("")
        lines.append("deferred — discussed, still open:")
        for gap in deferred:
            lines.append(f"  ~ {gap.node_id:<24} {gap.kind:<18} {gap.detail}")
    return "\n".join(lines), (1 if pending else 0)
```

Add the parser immediately before `args = parser.parse_args(argv)`:

```python
    p_check = sub.add_parser("check")
    _add_root(p_check)
```

Add the branch immediately before `return 0`:

```python
    elif args.cmd == "check":
        text, code = cmd_check(args.project_root)
        print(text)
        return code
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS — 61 passed

- [ ] **Step 5: Verify the whole suite and the linters still pass**

Run: `uv run pytest`
Expected: PASS — the full unit suite, no regressions.

Run: `uv run ruff check src/factory/trace tests/unit/trace`
Expected: `All checks passed!`

Run: `uv run pyright src/factory/trace`
Expected: `0 errors`

- [ ] **Step 6: Verify the gate really fails on this repo**

Run: `uv run python -m factory.trace check; echo "exit=$?"`
Expected: `exit=1`, with 45 `task_no_sr` entries listed as pending. A `0` here means gap detection is broken — this repo has known pending gaps (spec §4.5).

- [ ] **Step 7: Commit**

```bash
git add src/factory/trace/cli.py tests/unit/trace/test_cli_check.py
git commit -m "feat(trace): stateless check gate failing on undiscussed gaps

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## What this plan deliberately does not build

- **The browser viewer** (`md-render.ts`, `docs-server.ts`, `docs-html.ts`,
  `graph-layout.ts`, `/review-plans --browser`) — plan 2. It consumes
  `factory trace graph --json` and holds no traceability rules.
- **The `/trace-fix` workflow** — plan 3. It registers five tools (`trace_next`,
  `trace_link`, `trace_exempt`, `trace_defer`, `trace_check`) over these CLI
  commands, so the model reasons over the candidates while the tools do the
  enumerating, validating and writing.
- **Gap prevention** — gating `factory-run` on a task closing with no `satisfies:`,
  and teaching `writing-plans` to emit a spec key. Deliberately out of scope per
  spec §9; it changes orchestrator and skill behaviour.

**Note for plan 2:** Task 7's `set_exempt`/`set_deferred` can add frontmatter to
plan files that previously had none. `md-render.ts` must therefore strip frontmatter
before rendering a plan, not just a task.
