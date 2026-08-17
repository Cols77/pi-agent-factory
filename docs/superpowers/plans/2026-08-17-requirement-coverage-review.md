# Requirement Coverage Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `factory.coverage` package — a feature-scoped audit that resolves declared SRs, measures import-graph overlap between binding tests and implementing files, validates per-SR semantic verdicts, classifies coverage state, and gates on dishonest coverage (pass/fail/degraded).

**Architecture:** Three new Python modules (`imports.py`, `scope.py`, `audit.py`, `gate.py`, `report.py`, `cli.py`) under `src/factory/coverage/`, plus two new skills. The deterministic phases (scope resolution, import overlap, consolidation, gate) are all Python; the semantic judgment (Phase 2) is a subagent protocol defined by the vendored skills. CLI verbs: `audit` (Phase 0+1), `verdict` (validate+record), `consolidate` (Phase 3+4), `gate` (re-derive), `report` (human summary).

**Tech Stack:** Python 3.11-3.12, stdlib ast, factory.trace.graph, factory.requirements.register, factory.evidence.manifests, existing fixture patterns.

**Spec ref:** `docs/superpowers/specs/2026-08-17-requirement-coverage-review-design.md`

---

### Task 1: `imports.py` — transitive import resolution and overlap check

**Files:**
- Create: `src/factory/coverage/__init__.py`
- Create: `src/factory/coverage/imports.py`
- Test: `tests/unit/coverage/test_imports.py`

- [ ] **Step 1: Write `__init__.py` (empty)**

```python
# src/factory/coverage/__init__.py
```

- [ ] **Step 2: Write the failing tests for `imports.py`**

```python
# tests/unit/coverage/test_imports.py
from pathlib import Path

import pytest

from factory.coverage.imports import compute_overlap, transitive_imports

pytestmark = pytest.mark.unit


def _tree(root: Path) -> None:
    """A small project with an absolute import chain."""
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "drone").mkdir()
    (root / "src" / "drone" / "__init__.py").write_text("")
    (root / "src" / "drone" / "priority_filter.py").write_text(
        "def preempt():\n    return True\n"
    )
    (root / "tests" / "test_preempt.py").write_text(
        "from drone.priority_filter import preempt\n\ndef test_preempt():\n"
        "    assert preempt()\n"
    )


def test_transitive_imports_reaches_implementation(tmp_path: Path) -> None:
    _tree(tmp_path)
    reached, _ = transitive_imports(tmp_path, tmp_path / "tests" / "test_preempt.py")
    assert (tmp_path / "src" / "drone" / "priority_filter.py") in reached


def test_compute_overlap_true(tmp_path: Path) -> None:
    _tree(tmp_path)
    result = compute_overlap(
        tmp_path, "tests/test_preempt.py", ["src/drone/priority_filter.py"],
    )
    assert result.ok
    assert "src/drone/priority_filter.py" in result.overlap


def test_compute_overlap_false_when_imports_nothing(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_empty.py").write_text(
        "def test_nothing():\n    assert True\n"
    )
    result = compute_overlap(
        tmp_path, "tests/test_empty.py", ["src/drone/priority_filter.py"],
    )
    assert not result.ok
    assert result.overlap == ()


def test_seed_file_is_not_self_overlap(tmp_path: Path) -> None:
    _tree(tmp_path)
    result = compute_overlap(
        tmp_path,
        "tests/test_preempt.py",
        ["src/drone/priority_filter.py", "tests/test_preempt.py"],
    )
    # The test file itself was changed; it must not count as overlap.
    assert result.ok
    assert "tests/test_preempt.py" not in result.overlap
    assert "src/drone/priority_filter.py" in result.overlap


def test_relative_import_resolution(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "a.py").write_text("from . import b\n")
    (tmp_path / "pkg" / "b.py").write_text("X = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_rel.py").write_text(
        "from pkg.a import b\n"
    )
    reached, _ = transitive_imports(tmp_path, tmp_path / "tests" / "test_rel.py")
    assert (tmp_path / "pkg" / "a.py") in reached
    assert (tmp_path / "pkg" / "b.py") in reached


def test_node_id_selection_stripped(tmp_path: Path) -> None:
    _tree(tmp_path)
    result = compute_overlap(
        tmp_path, "tests/test_preempt.py::test_preempt",
        ["src/drone/priority_filter.py"],
    )
    assert result.ok


def test_missing_selection_is_honest_false(tmp_path: Path) -> None:
    result = compute_overlap(tmp_path, "tests/does_not_exist.py", ["x.py"])
    assert not result.ok
    assert result.test_source is None


def test_unresolved_imports_are_honest(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_extern.py").write_text(
        "import numpy\n\ndef test():\n    pass\n"
    )
    result = compute_overlap(tmp_path, "tests/test_extern.py", ["x.py"])
    assert not result.ok
    assert "numpy" in result.unresolved
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/coverage/test_imports.py -v
```
Expected: 8 tests, all fail with ModuleNotFoundError or ImportError.

- [ ] **Step 4: Write `imports.py`**

```python
# src/factory/coverage/imports.py
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class OverlapResult:
    ok: bool
    test_source: str | None
    reached_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    overlap: tuple[str, ...]
    unresolved: tuple[str, ...]


def _import_edges(source: str) -> list[tuple[str, int]]:
    """(module_name, relative_level) pairs from the AST; level 0 = absolute."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    edges: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom) and node.module:
            edges.append((node.module, node.level))
    return edges


def _module_candidates(root: Path, module: str, level: int, origin: Path) -> list[Path]:
    """Candidate files for an import, in resolution order.

    Relative imports are anchored on the importing file's package directory.
    The src/ layout is tried as a second candidate root.
    """
    base = origin.parent if origin is not None else root
    if level > 0:
        for _ in range(level - 1):
            base = base.parent
    parts = module.split(".") if module else []
    if level > 0 and base != root:
        rel = base.relative_to(root)
        parts = list(rel.parts) + parts
    dotted = ".".join(parts)
    rel_path = dotted.replace(".", "/")
    candidates: list[Path] = []
    for anchor in (root, root / "src"):
        candidates.append(anchor / f"{rel_path}.py")
        candidates.append(anchor / rel_path / "__init__.py")
    return candidates


def _resolve_import(root: Path, module: str, level: int, origin: Path) -> Path | None:
    for cand in _module_candidates(root, module, level, origin):
        try:
            if cand.is_file():
                return cand.resolve()
        except OSError:
            continue
    return None


def transitive_imports(root: Path, source_file: Path) -> tuple[set[Path], set[str]]:
    """All project files transitively imported from source_file.

    Returns (reached_files, unresolved_modules). Files outside the project
    root are unresolved and stop the walk. The source_file itself is excluded
    from reached.
    """
    root_resolved = root.resolve()
    reached: set[Path] = set()
    unresolved: set[str] = set()
    seen: set[Path] = set()
    queue: list[Path] = [source_file.resolve()]
    while queue:
        cur = queue.pop(0)
        if cur in seen or not cur.exists():
            continue
        seen.add(cur)
        try:
            text = cur.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for module, level in _import_edges(text):
            resolved = _resolve_import(root, module, level, cur)
            if resolved is None:
                unresolved.add(module)
                continue
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                continue
            if resolved in seen:
                continue
            reached.add(resolved)
            queue.append(resolved)
    # Exclude the seed itself
    reached.discard(source_file.resolve())
    return reached, unresolved


def _norm(p: Path) -> str:
    return p.as_posix().lstrip("./")


def compute_overlap(root: Path, selection: str, changed_files: Iterable[str]) -> OverlapResult:
    """Phase 1: does the binding test selection reach any changed file?

    selection is a pytest selection (path or node id). The leading path is
    resolved relative to the project root; the transitive import closure is
    intersected with changed_files (repo-relative paths).
    """
    changed = tuple(_norm(Path(c)) for c in changed_files)
    if "::" in selection:
        selection = selection.split("::", 1)[0]
    source = root / selection.lstrip("/")
    if not source.exists():
        return OverlapResult(False, None, (), changed, (), ())
    reached, unresolved = transitive_imports(root, source)
    root_resolved = root.resolve()
    reached_rel = tuple(
        sorted(_norm(p.relative_to(root_resolved)) for p in reached)
    )
    overlap = tuple(sorted(set(reached_rel) & set(changed)))
    return OverlapResult(
        ok=bool(overlap),
        test_source=_norm(source),
        reached_files=reached_rel,
        changed_files=changed,
        overlap=overlap,
        unresolved=tuple(sorted(unresolved)),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/coverage/test_imports.py -v
```
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add src/factory/coverage/__init__.py src/factory/coverage/imports.py tests/unit/coverage/test_imports.py
git commit -m "feat(coverage): transitive import resolution and overlap check"
```

---

### Task 2: `scope.py` — feature scope resolution

**Files:**
- Create: `src/factory/coverage/scope.py`
- Test: `tests/unit/coverage/test_scope.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/coverage/test_scope.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.coverage.scope import (
    FeatureScope,
    resolve_feature_scope,
    _latest_validation,
)

pytestmark = pytest.mark.unit


def _manifest(
    *,
    task_id: str,
    run_id: str = "RUN-001",
    start_commit: str = "a" * 40,
    result_commit: str = "b" * 40,
    changed_files: list[str] | None = None,
    validation: list[dict] | None = None,
) -> dict:
    """Minimal valid evidence manifest (required fields from schema)."""
    return {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": task_id,
        "started_at": "2026-08-01T00:00:00Z",
        "ended_at": "2026-08-01T01:00:00Z",
        "start_commit": start_commit,
        "result_commit": result_commit,
        "outcome": "completed",
        "inputs": {
            "task": {"path": f"tasks/{task_id}.md", "sha256": "0" * 64},
            "requirements": [],
            "factory_config_sha256": "0" * 64,
        },
        "implementation": {"changed_files": changed_files or []},
        "dependencies": [],
        "validation": validation or [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }


def _req_file(tmp_path: Path, sid: str, statement: str = "shall do X") -> Path:
    p = tmp_path / "requirements" / f"{sid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    content = f"""---
id: {sid}
title: "Test {sid}"
statement: "{statement}"
domain: behavioral
binding:
  harness: sim-testbench
  experiment: tests/test_{sid}.py
  metric: unit_pass_rate
  trials: 1
  assert: "== 1.0"
checksum: null
---
"""
    p.write_text(content)
    return p


def _feat_file(tmp_path: Path, fid: str, requirements: list[str]) -> Path:
    p = tmp_path / "docs" / "features" / f"{fid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    reqs = ", ".join(requirements)
    content = f"""---
id: {fid}
title: "Test feat"
requirements: [{reqs}]
---
"""
    p.write_text(content)
    return p


def _task_file(tmp_path: Path, tid: str, satisfies: list[str]) -> Path:
    p = tmp_path / "tasks" / f"{tid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    content = f"""---
id: {tid}
title: "Test {tid}"
satisfies: [{', '.join(satisfies)}]
---
Do the work.
"""
    p.write_text(content)
    return p


def test_resolve_scope_empty_feature(tmp_path: Path) -> None:
    _feat_file(tmp_path, "FEAT-001", [])
    scope = resolve_feature_scope(tmp_path, "FEAT-001")
    assert scope.feature_id == "FEAT-001"
    assert scope.declared == ()


def test_resolve_scope_single_sr(tmp_path: Path) -> None:
    _feat_file(tmp_path, "FEAT-001", ["SR-001"])
    _req_file(tmp_path, "SR-001")
    _task_file(tmp_path, "T-001", ["SR-001"])
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "runs").mkdir()
    manifest = _manifest(
        task_id="T-001",
        changed_files=["src/drone/priority_filter.py"],
        validation=[{"requirements": [{"id": "SR-001", "passed": True, "value": 1.0, "assert": "== 1.0", "trials": 1}]}],
    )
    p = evidence_dir / "runs" / "RUN-001.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")

    scope = resolve_feature_scope(tmp_path, "FEAT-001")
    assert "SR-001" in scope.srs
    sr = scope.srs["SR-001"]
    assert sr.checksum_state == "current"
    assert len(sr.tasks) == 1
    assert sr.tasks[0].task_id == "T-001"
    assert "src/drone/priority_filter.py" in sr.tasks[0].changed_files
    assert sr.measurement is not None
    assert sr.measurement["passed"] is True


def test_completeness_declared_not_linked(tmp_path: Path) -> None:
    _feat_file(tmp_path, "FEAT-001", ["SR-001", "SR-002"])
    _req_file(tmp_path, "SR-001")
    _req_file(tmp_path, "SR-002")
    _task_file(tmp_path, "T-001", ["SR-001"])
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "runs").mkdir()
    manifest = _manifest(task_id="T-001")
    (evidence_dir / "runs" / "RUN-001.json").write_text(json.dumps(manifest), encoding="utf-8")

    scope = resolve_feature_scope(tmp_path, "FEAT-001")
    assert any(
        f["kind"] == "declared_not_linked" and f["sr_id"] == "SR-002"
        for f in scope.completeness
    )


def test_declared_not_in_register(tmp_path: Path) -> None:
    _feat_file(tmp_path, "FEAT-001", ["SR-999"])
    scope = resolve_feature_scope(tmp_path, "FEAT-001")
    assert any(f["kind"] == "declared_not_in_register" and f["sr_id"] == "SR-999" for f in scope.completeness)


def test_proposed_requirement_checksum_state(tmp_path: Path) -> None:
    """An SR with no binding is proposed; checksum_state is 'proposed'."""
    _feat_file(tmp_path, "FEAT-001", ["SR-003"])
    p = tmp_path / "requirements" / "SR-003.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("""---
id: SR-003
title: "Proposed"
statement: "shall do Y"
domain: behavioral
---
""")
    scope = resolve_feature_scope(tmp_path, "FEAT-001")
    assert scope.srs["SR-003"].checksum_state == "proposed"


def test_multiple_tasks_per_sr(tmp_path: Path) -> None:
    _feat_file(tmp_path, "FEAT-001", ["SR-001"])
    _req_file(tmp_path, "SR-001")
    _task_file(tmp_path, "T-001", ["SR-001"])
    _task_file(tmp_path, "T-002", ["SR-001"])
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "runs").mkdir()
    (evidence_dir / "runs" / "RUN-001.json").write_text(
        json.dumps(_manifest(task_id="T-001", changed_files=["a.py"])), encoding="utf-8"
    )
    (evidence_dir / "runs" / "RUN-002.json").write_text(
        json.dumps(_manifest(task_id="T-002", changed_files=["b.py"])), encoding="utf-8"
    )
    scope = resolve_feature_scope(tmp_path, "FEAT-001")
    assert len(scope.srs["SR-001"].tasks) == 2
    assert scope.tasks["T-001"].changed_files == ("a.py",)
    assert scope.tasks["T-002"].changed_files == ("b.py",)


def test_latest_validation_empty(tmp_path: Path) -> None:
    assert _latest_validation([], "SR-001") is None


def test_latest_validation_newest_wins(tmp_path: Path) -> None:
    old = _manifest(task_id="T-001",
        validation=[{"requirements": [{"id": "SR-001", "passed": False, "value": 0.0}]}],
    )
    new = _manifest(task_id="T-001",
        validation=[{"requirements": [{"id": "SR-001", "passed": True, "value": 1.0, "assert": "== 1.0", "trials": 1}]}],
    )
    # list_run_manifests returns newest-first; test the helper directly
    result = _latest_validation([new, old], "SR-001")
    assert result is not None
    assert result["passed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/coverage/test_scope.py -v
```
Expected: 8 tests, all fail with ImportError or ModuleNotFoundError.

- [ ] **Step 3: Write `scope.py`**

```python
# src/factory/coverage/scope.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from factory.evidence.manifests import list_run_manifests
from factory.requirements.register import is_checksum_current, load_register
from factory.trace.graph import build_graph


@dataclass(frozen=True)
class TaskScope:
    task_id: str
    changed_files: tuple[str, ...]
    manifests: tuple[str, ...]


@dataclass(frozen=True)
class SrScope:
    sr_id: str
    statement: str
    binding: dict | None
    checksum_state: str  # "current" | "stale" | "proposed"
    tasks: tuple[TaskScope, ...]
    measurement: dict | None
    deferred: bool
    domain: str


@dataclass(frozen=True)
class FeatureScope:
    feature_id: str
    declared: tuple[str, ...]
    contains: tuple[str, ...]
    linked: tuple[str, ...]
    register: tuple[str, ...]
    srs: dict[str, SrScope]
    completeness: tuple[dict, ...]
    tasks: dict[str, TaskScope]


def _latest_validation(manifests: list[dict], sr_id: str) -> dict | None:
    """Newest manifest (already newest-first) that measures this SR."""
    for manifest in manifests:
        results = [
            entry
            for validation in manifest.get("validation") or []
            if isinstance(validation, dict)
            for entry in validation.get("requirements", [])
            if isinstance(entry, dict) and entry.get("id") == sr_id and "passed" in entry
        ]
        if results:
            return results[0]
    return None


def _changed_files_from_manifest(manifest: dict) -> tuple[str, ...]:
    impl = manifest.get("implementation", {})
    if isinstance(impl, dict):
        raw = impl.get("changed_files", [])
        if isinstance(raw, list):
            return tuple(str(f) for f in raw)
    return ()


def _checksum_state(req: object) -> str:
    """Return 'current', 'stale', or 'proposed'."""
    from factory.requirements.register import Requirement
    if not isinstance(req, Requirement):
        return "proposed"
    if req.binding is None:
        return "proposed"
    return "current" if is_checksum_current(req) else "stale"


def _is_deferred(sr_path: Path) -> bool:
    import frontmatter
    try:
        post = frontmatter.load(str(sr_path))
        return bool(post.metadata.get("trace_deferred"))
    except Exception:
        return False


def resolve_feature_scope(root: Path, feat: str) -> FeatureScope:
    """Phase 0: resolve a feature's declared SRs, tasks, and changed files.

    The feat id is e.g. FEAT-001. The corresponding file is
    docs/features/FEAT-001.md.
    """
    feat = feat.upper() if feat.startswith("FEAT-") else feat
    graph = build_graph(root)
    by_id = {n.id: n for n in graph.nodes}

    feat_node = by_id.get(feat)
    if feat_node is None:
        # Degrade gracefully: a feature with no node is an empty scope.
        return FeatureScope(
            feature_id=feat,
            declared=(),
            contains=(),
            linked=(),
            register=(),
            srs={},
            completeness=(),
            tasks={},
        )

    # contains edges from feat → SRs (from frontmatter requirements:)
    contains = tuple(
        sorted(e.dst for e in graph.edges if e.src == feat and e.kind == "contains")
    )
    # declared = same as contains (both come from the feat frontmatter)
    declared = contains

    # Load register for binding/checksum info
    reqs = load_register(root / "requirements")
    req_by_id = {r.id: r for r in reqs}

    # Per-SR: tasks with satisfies edge
    sr_to_tasks: dict[str, list[TaskScope]] = {}
    tasks_by_id: dict[str, TaskScope] = {}
    for edge in graph.edges:
        if edge.kind != "satisfies":
            continue
        sr_id = edge.dst
        if sr_id not in declared:
            continue
        task_id = edge.src
        if task_id not in tasks_by_id:
            manifests = list_run_manifests(root / "evidence", task_id=task_id)
            changed = set()
            manifest_ids: list[str] = []
            for m in manifests:
                changed.update(_changed_files_from_manifest(m))
                manifest_ids.append(m.get("run_id", "?"))
            ts = TaskScope(
                task_id=task_id,
                changed_files=tuple(sorted(changed)),
                manifests=tuple(manifest_ids),
            )
            tasks_by_id[task_id] = ts
        else:
            ts = tasks_by_id[task_id]
        sr_to_tasks.setdefault(sr_id, []).append(ts)

    linked = tuple(sorted(sr_to_tasks.keys()))
    register = tuple(sorted(req_by_id.keys()))

    # Build per-SR scope
    srs: dict[str, SrScope] = {}
    for sr_id in declared:
        req = req_by_id.get(sr_id)
        sr_path = root / "requirements" / f"{sr_id}.md"
        deferred = _is_deferred(sr_path) if sr_path.exists() else False
        manifests = list_run_manifests(root / "evidence", task_id=None)
        # Filter manifests that mention this SR
        sr_manifests = _find_manifests_for_sr(manifests, sr_id)

        srs[sr_id] = SrScope(
            sr_id=sr_id,
            statement=req.statement if req else "(not in register)",
            binding=_binding_dict(req) if req and req.binding else None,
            checksum_state=_checksum_state(req),
            tasks=tuple(sr_to_tasks.get(sr_id, [])),
            measurement=_latest_validation(sr_manifests, sr_id),
            deferred=deferred,
            domain=req.domain if req else "unknown",
        )

    # Completeness findings
    completeness: list[dict] = []
    for sr_id in declared:
        if sr_id not in req_by_id:
            completeness.append({"kind": "declared_not_in_register", "sr_id": sr_id})
        elif sr_id not in linked:
            completeness.append({"kind": "declared_not_linked", "sr_id": sr_id})

    # task-satisfies-undeclared: a task linked to a declared SR also satisfies
    # an undeclared SR
    for edge in graph.edges:
        if edge.kind != "satisfies":
            continue
        if edge.dst in declared:
            continue
        if edge.src in tasks_by_id:
            completeness.append({
                "kind": "task_satisfies_undeclared",
                "sr_id": edge.dst,
                "task_id": edge.src,
            })

    return FeatureScope(
        feature_id=feat,
        declared=declared,
        contains=contains,
        linked=linked,
        register=register,
        srs=srs,
        completeness=tuple(completeness),
        tasks=tasks_by_id,
    )


def _binding_dict(req: object) -> dict | None:
    from factory.requirements.register import Requirement
    if not isinstance(req, Requirement) or req.binding is None:
        return None
    b = req.binding
    return {
        "harness": b.harness,
        "experiment": b.experiment,
        "metric": b.metric,
        "assert_expr": b.assert_expr,
        "trials": b.trials,
    }


def _find_manifests_for_sr(manifests: list[dict], sr_id: str) -> list[dict]:
    out: list[dict] = []
    for m in manifests:
        for v in m.get("validation") or []:
            if isinstance(v, dict):
                for req_entry in v.get("requirements", []):
                    if isinstance(req_entry, dict) and req_entry.get("id") == sr_id:
                        out.append(m)
                        break
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/coverage/test_scope.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/factory/coverage/scope.py tests/unit/coverage/test_scope.py
git commit -m "feat(coverage): feature scope resolution with completeness findings"
```

---

### Task 3: `audit.py` — verdict schema validation and classification

**Files:**
- Create: `src/factory/coverage/audit.py`
- Test: `tests/unit/coverage/test_audit.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/coverage/test_audit.py
from __future__ import annotations

import pytest

from factory.coverage.audit import (
    SrState,
    classify,
    validate_verdict,
)

pytestmark = pytest.mark.unit


def _sr(**kw: object) -> dict:
    return {
        "sr_id": "SR-001",
        "statement": "shall do X",
        "binding": {"experiment": "tests/test_x.py", "metric": "unit_pass_rate", "assert_expr": "== 1.0", "trials": 1},
        "checksum_state": "current",
        "tasks": ({"task_id": "T-001", "changed_files": ("src/x.py",)},),
        "measurement": {"passed": True, "value": 1.0},
        "deferred": False,
        "domain": "behavioral",
        **kw,
    }


def _overlap(ok: bool = True) -> dict:
    return {
        "ok": ok,
        "test_source": "tests/test_x.py",
        "reached_files": ("src/x.py",),
        "changed_files": ("src/x.py",),
        "overlap": ("src/x.py",),
        "unresolved": (),
    }


def _verdict(ok: bool = True) -> dict:
    return {
        "sr_id": "SR-001",
        "implemented": ok,
        "honest": ok,
        "confidence": "high",
        "margin": None,
        "reasoning": "Test exercises the preempt path.",
        "checked": ["preempt path in priority_filter.py"],
        "assumed": ["fixture represents the sim scenario"],
        "verify": [],
    }


def test_validate_verdict_ok() -> None:
    v = _verdict()
    result, error = validate_verdict(v)
    assert result is not None
    assert error is None


def test_validate_verdict_missing_reasoning() -> None:
    v = _verdict()
    v.pop("reasoning")
    result, error = validate_verdict(v)
    assert result is None
    assert "reasoning" in error


def test_validate_verdict_missing_checked() -> None:
    v = _verdict()
    v.pop("checked")
    result, error = validate_verdict(v)
    assert result is None
    assert "checked" in error


def test_validate_verdict_missing_assumed() -> None:
    v = _verdict()
    v.pop("assumed")
    result, error = validate_verdict(v)
    assert result is None
    assert "assumed" in error


def test_validate_verify_item_requires_item() -> None:
    v = _verdict()
    v["verify"] = [{"file": "src/x.py", "why": "tight margin"}]
    result, error = validate_verdict(v)
    assert result is None
    assert "verify" in error


def test_validate_verify_item_full() -> None:
    v = _verdict()
    v["verify"] = [{"item": "Check margin", "file": "src/x.py", "line": 42, "why": "tight"}]
    result, error = validate_verdict(v)
    assert result is not None


def test_classify_declined() -> None:
    sr = _sr(deferred=True)
    state, notes = classify(sr, None, None, False)
    assert state == SrState.DECLINED


def test_classify_unlinked() -> None:
    sr = _sr(tasks=())
    state, notes = classify(sr, None, None, False)
    assert state == SrState.UNLINKED


def test_classify_unverified() -> None:
    sr = _sr()
    state, notes = classify(sr, None, None, False)
    assert state == SrState.UNVERIFIED


def test_classify_not_implemented() -> None:
    sr = _sr()
    v = _verdict(ok=False)
    state, notes = classify(sr, _overlap(), v, False)
    assert state == SrState.NOT_IMPLEMENTED


def test_classify_dishonest() -> None:
    sr = _sr()
    v = _verdict(ok=True)
    v["honest"] = False
    state, notes = classify(sr, _overlap(), v, False)
    assert state == SrState.DISHONEST


def test_classify_pass() -> None:
    sr = _sr()
    v = _verdict()
    state, notes = classify(sr, _overlap(), v, False)
    assert state == SrState.PASS


def test_classify_unmeasured() -> None:
    sr = _sr(measurement=None)
    v = _verdict()
    state, notes = classify(sr, _overlap(), v, False)
    assert state == SrState.UNMEASURED


def test_classify_suspect_overlap() -> None:
    sr = _sr()
    v = _verdict()
    o = _overlap(ok=False)
    state, notes = classify(sr, o, v, False)
    assert state == SrState.SUSPECT
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/coverage/test_audit.py -v
```
Expected: 14 tests, all fail.

- [ ] **Step 3: Write `audit.py`**

```python
# src/factory/coverage/audit.py
from __future__ import annotations

from enum import Enum
from typing import Any


class SrState(str, Enum):
    DECLINED = "declined"
    PASS = "pass"
    SUSPECT = "suspect"
    UNMEASURED = "unmeasured"
    UNLINKED = "unlinked"
    UNVERIFIED = "unverified"
    NOT_IMPLEMENTED = "not_implemented"
    DISHONEST = "dishonest"


# Required fields and their types
_VERDICT_REQUIRED = {
    "sr_id": str,
    "implemented": bool,
    "honest": bool,
    "confidence": str,
    "reasoning": str,
    "checked": list,
    "assumed": list,
    "verify": list,
}


def validate_verdict(raw: dict) -> tuple[dict | None, str | None]:
    """Return (validated_verdict, error) — error is None when valid."""
    for field, expected_type in _VERDICT_REQUIRED.items():
        if field not in raw:
            return None, f"missing required field: {field}"
        if not isinstance(raw[field], expected_type):
            return None, f"field {field}: expected {expected_type.__name__}, got {type(raw[field]).__name__}"
    if not isinstance(raw.get("margin"), (str, type(None))):
        return None, "field margin: expected str or None"

    for i, item in enumerate(raw.get("verify", [])):
        if not isinstance(item, dict):
            return None, f"verify[{i}]: expected dict"
        if "item" not in item or not isinstance(item["item"], str):
            return None, f"verify[{i}]: missing required str field 'item'"

    return raw, None


def classify(
    sr: dict,
    overlap: dict | None,
    verdict: dict | None,
    tool_failure: bool,
) -> tuple[SrState, list[str]]:
    """Classify an SR's coverage state (spec §8 priority order).

    Returns (state, notes) where notes are human-readable warnings or
    explanations.
    """
    notes: list[str] = []

    # 1. Declined (recorded decision, not a gap)
    if sr.get("deferred"):
        return SrState.DECLINED, []

    # 2. Unlinked (no satisfying task)
    if not sr.get("tasks"):
        return SrState.UNLINKED, ["no satisfying task"]

    # 3. Unverified (no subagent verdict)
    if verdict is None:
        if tool_failure:
            notes.append("subagent dispatch failed")
        else:
            notes.append("no subagent verdict recorded")
        return SrState.UNVERIFIED, notes

    # 4. Not implemented
    if not verdict["implemented"]:
        return SrState.NOT_IMPLEMENTED, [verdict.get("reasoning", "")]

    # 5. Dishonest
    if not verdict["honest"]:
        return SrState.DISHONEST, [verdict.get("reasoning", "")]

    # 6. Overlap check
    overlap_ok = overlap is not None and overlap.get("ok", False)
    if not overlap_ok:
        notes.append("import-graph overlap check failed — test does not reach changed files")

    # 7. Measurement
    measured = sr.get("measurement") is not None
    stale = sr.get("checksum_state") == "stale"
    if stale:
        notes.append("requirement statement is stale (checksum mismatch)")

    if overlap_ok and not stale and measured:
        state = SrState.PASS
    elif overlap_ok and not stale and not measured:
        state = SrState.UNMEASURED
        notes.append("no passing measurement recorded")
    else:
        state = SrState.SUSPECT

    return state, notes
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/coverage/test_audit.py -v
```
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add src/factory/coverage/audit.py tests/unit/coverage/test_audit.py
git commit -m "feat(coverage): verdict schema validation and classification"
```

---

### Task 4: `gate.py` — gate rules (pass / fail / degraded)

**Files:**
- Create: `src/factory/coverage/gate.py`
- Test: `tests/unit/coverage/test_gate.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/coverage/test_gate.py
from __future__ import annotations

import pytest

from factory.coverage.gate import GateOutcome, run_gate

pytestmark = pytest.mark.unit


def test_pass() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("pass", ["some note"]), "SR-002": ("pass", [])},
        [],
    )
    assert outcome == GateOutcome.PASS


def test_fail_unlinked() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("unlinked", ["no task"])},
        [],
    )
    assert outcome == GateOutcome.FAIL
    assert "SR-001" in failed


def test_fail_not_implemented() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("not_implemented", ["code does not implement"])},
        [],
    )
    assert outcome == GateOutcome.FAIL
    assert "SR-001" in failed


def test_fail_dishonest() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("dishonest", ["binding test does not exercise behavior"])},
        [],
    )
    assert outcome == GateOutcome.FAIL
    assert "SR-001" in failed


def test_degraded_when_all_unverified_are_tool_failures() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("unverified", ["subagent dispatch failed"])},
        [{"sr_id": "SR-001", "issue": "subagent tool error"}],
    )
    assert outcome == GateOutcome.DEGRADED
    assert "SR-001" in degraded


def test_fail_when_unverified_and_no_tool_failure() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("unverified", ["no verdict recorded"])},
        [],
    )
    assert outcome == GateOutcome.FAIL
    assert "SR-001" in failed


def test_warn_on_suspect() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("suspect", ["overlap fails"])},
        [],
    )
    assert outcome == GateOutcome.PASS
    assert "SR-001" in warned


def test_warn_on_unmeasured() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("unmeasured", ["no passing measurement"])},
        [],
    )
    assert outcome == GateOutcome.PASS
    assert "SR-001" in warned


def test_declined_skipped() -> None:
    outcome, failed, warned, degraded = run_gate(
        {"SR-001": ("declined", [])},
        [],
    )
    assert outcome == GateOutcome.PASS


def test_mixed_degraded_and_fail() -> None:
    outcome, failed, warned, degraded = run_gate(
        {
            "SR-001": ("unverified", ["subagent dispatch failed"]),
            "SR-002": ("unlinked", ["no task"]),
        },
        [{"sr_id": "SR-001", "issue": "subagent tool error"}],
    )
    # Hard fail takes precedence over degraded
    assert outcome == GateOutcome.FAIL
    assert "SR-002" in failed
    assert "SR-001" in degraded
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/coverage/test_gate.py -v
```
Expected: 10 tests, all fail.

- [ ] **Step 3: Write `gate.py`**

```python
# src/factory/coverage/gate.py
from __future__ import annotations

from enum import Enum
from typing import Mapping


class GateOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    DEGRADED = "degraded"


_GATE_FAIL_STATES = frozenset({"unlinked", "not_implemented", "dishonest"})
_GATE_WARN_STATES = frozenset({"suspect", "unmeasured"})


def run_gate(
    states: Mapping[str, tuple[str, list[str]]],
    tool_failures: list[dict],
) -> tuple[GateOutcome, list[str], list[str], list[str]]:
    """Evaluate gate rules.

    Returns (outcome, failed_srs, warned_srs, degraded_srs).
    """
    failed: list[str] = []
    warned: list[str] = []
    degraded: list[str] = []
    unverified_srs: list[str] = []

    for sr_id, (state, notes) in states.items():
        if state == "declined":
            continue
        if state in _GATE_FAIL_STATES:
            failed.append(sr_id)
        elif state in _GATE_WARN_STATES:
            warned.append(sr_id)
        elif state == "unverified":
            unverified_srs.append(sr_id)

    # Determine hard vs degraded
    tool_failure_ids = {f.get("sr_id", "") for f in tool_failures if f.get("sr_id")}
    for sr_id in unverified_srs:
        if sr_id in tool_failure_ids:
            degraded.append(sr_id)
        else:
            failed.append(sr_id)

    if failed:
        return GateOutcome.FAIL, failed, warned, degraded
    if degraded:
        return GateOutcome.DEGRADED, [], warned, degraded
    return GateOutcome.PASS, [], warned, degraded
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/coverage/test_gate.py -v
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/factory/coverage/gate.py tests/unit/coverage/test_gate.py
git commit -m "feat(coverage): gate rules with pass/fail/degraded outcomes"
```

---

### Task 5: `report.py` + `cli.py` — CLI verbs and JSON artifacts

**Files:**
- Create: `src/factory/coverage/report.py`
- Create: `src/factory/coverage/cli.py`
- Create: `src/factory/coverage/__main__.py`
- Test: `tests/unit/coverage/test_cli.py` (test the CLI subcommands)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/coverage/test_cli.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.coverage.cli import (
    cmd_audit,
    cmd_consolidate,
    cmd_gate,
    cmd_record_failure,
    cmd_report,
    cmd_verdict,
)

pytestmark = pytest.mark.unit


def _feat_scope(tmp_path: Path) -> None:
    """Minimal fixture with one SR, one task, one manifest."""
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: [SR-001]\n---\n"
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: X\nstatement: shall do X\ndomain: behavioral\n"
        "binding:\n  harness: sim-testbench\n  experiment: tests/test_x.py\n"
        "  metric: unit_pass_rate\n  trials: 1\n  assert: '== 1.0'\nchecksum: null\n---\n"
    )
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: T\ndeliverables: []\nsatisfies: [SR-001]\n---\n"
    )
    (tmp_path / "evidence" / "runs").mkdir(parents=True)
    manifest = {
        "schema_version": 2, "run_id": "RUN-001", "task_id": "T-001",
        "started_at": "2026-08-01T00:00:00Z", "ended_at": "2026-08-01T01:00:00Z",
        "start_commit": "a" * 40, "result_commit": "b" * 40, "outcome": "completed",
        "inputs": {"task": {"path": "tasks/T-001.md", "sha256": "0"*64}, "requirements": [], "factory_config_sha256": "0"*64},
        "implementation": {"changed_files": ["src/x.py"]},
        "dependencies": [], "validation": [], "reviews": [], "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    (tmp_path / "evidence" / "runs" / "RUN-001.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_audit_writes_scope_json(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    result = cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    assert result["feature"] == "FEAT-001"
    assert "SR-001" in result["srs"]
    assert result["gate"] is None


def test_verdict_validates_and_writes(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    verdict = {
        "sr_id": "SR-001", "implemented": True, "honest": True,
        "confidence": "high", "margin": None,
        "reasoning": "Test exercises the preempt path.",
        "checked": ["preempt path"], "assumed": ["fixture"],
        "verify": [],
    }
    result = cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", verdict)
    assert result["valid"] is True
    v_dir = tmp_path / "coverage-reviews" / "FEAT-001-test-run" / "verdicts"
    assert (v_dir / "SR-001.json").exists()


def test_verdict_rejects_invalid(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    result = cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", {"sr_id": "SR-001"})
    assert result["valid"] is False
    assert result["error"] is not None


def test_consolidate_classifies_and_gates(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    verdict = {
        "sr_id": "SR-001", "implemented": True, "honest": True,
        "confidence": "high", "margin": None,
        "reasoning": "Test exercises the preempt path.",
        "checked": ["preempt path"], "assumed": ["fixture"],
        "verify": [],
    }
    cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", verdict)
    result = cmd_consolidate(tmp_path, "FEAT-001", "test-run")
    assert result["gate"]["outcome"] == "pass"
    assert len(result["states"]) == 1


def test_gate_re_derives(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    v = {"sr_id": "SR-001", "implemented": True, "honest": True,
         "confidence": "high", "margin": None, "reasoning": "R",
         "checked": ["preempt"], "assumed": ["fixture"], "verify": []}
    cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", v)
    cmd_consolidate(tmp_path, "FEAT-001", "test-run")
    outcome = cmd_gate(tmp_path, "FEAT-001", "test-run")
    assert outcome == "pass"


def test_gate_fails_on_dishonest(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    v = {"sr_id": "SR-001", "implemented": True, "honest": False,
         "confidence": "low", "margin": None, "reasoning": "Test does not exercise behavior",
         "checked": ["preempt"], "assumed": ["fixture"], "verify": [{"item": "Rewrite test", "file": "tests/test_x.py", "why": "does not assert the claim"}]}
    cmd_verdict(tmp_path, "FEAT-001", "test-run", "SR-001", v)
    cmd_consolidate(tmp_path, "FEAT-001", "test-run")
    outcome = cmd_gate(tmp_path, "FEAT-001", "test-run")
    assert outcome == "fail"


def test_record_failure_then_degraded_gate(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    result = cmd_record_failure(tmp_path, "FEAT-001", "test-run", "SR-001", "subagent tool error")
    assert result["recorded"] is True
    consolidated = cmd_consolidate(tmp_path, "FEAT-001", "test-run")
    assert consolidated["gate"]["outcome"] == "degraded"
    assert "SR-001" in consolidated["gate"]["degraded"]


def test_report_renders_human_summary(tmp_path: Path) -> None:
    _feat_scope(tmp_path)
    cmd_audit(tmp_path, "FEAT-001", run_id="test-run")
    assert cmd_report(tmp_path, "FEAT-001", "test-run")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/coverage/test_cli.py -v
```
Expected: 8 tests, all fail.

- [ ] **Step 3: Write `report.py`**

```python
# src/factory/coverage/report.py
from __future__ import annotations

from typing import Any


def render_human_summary(report: dict) -> str:
    """Return a plain-text human summary of the coverage report."""
    lines: list[str] = []
    lines.append(f"Coverage Review: {report.get('feature', '?')}")
    lines.append(f"Run: {report.get('run_id', '?')}")
    lines.append(f"Generated: {report.get('generated_at', '?')}")
    lines.append("")

    gate = report.get("gate", {})
    outcome = gate.get("outcome", "unknown")
    lines.append(f"Gate: {outcome.upper()}")
    if gate.get("failed"):
        lines.append(f"  FAILED: {', '.join(gate['failed'])}")
    if gate.get("degraded"):
        lines.append(f"  DEGRADED: {', '.join(gate['degraded'])}")
    if gate.get("warned"):
        lines.append(f"  WARNED: {', '.join(gate['warned'])}")
    lines.append("")

    scope = report.get("scope", {})
    lines.append(f"Declared SRs: {len(scope.get('declared', []))}")
    lines.append(f"Linked SRs:   {len(scope.get('linked', []))}")
    lines.append(f"Tasks:        {len(scope.get('tasks', {}))}")
    lines.append("")

    completeness = report.get("completeness", [])
    if completeness:
        lines.append("Completeness findings:")
        for f in completeness:
            lines.append(f"  - {f.get('kind', '?')}: {f.get('sr_id', '?')}")
        lines.append("")

    for sr_id, sr_data in report.get("srs", {}).items():
        lines.append(f"--- {sr_id} ---")
        lines.append(f"  Statement: {sr_data.get('statement', '?')[:80]}")
        lines.append(f"  Checksum: {sr_data.get('checksum_state', '?')}")
        lines.append(f"  Tasks: {len(sr_data.get('tasks', []))}")
        meas = sr_data.get("measurement")
        if meas:
            lines.append(f"  Measured: {meas.get('passed')} ({meas.get('value', '?')} vs {meas.get('assert', '?')})")
        else:
            lines.append("  Measured: (none)")
        if sr_data.get("states"):
            state, notes = sr_data["states"][0]
            lines.append(f"  State: {state}")
            for note in notes:
                lines.append(f"    - {note}")
        lines.append("")

    lines.append("--- Gate ---")
    lines.append(f"Outcome: {outcome}")

    return "\n".join(lines)
```

- [ ] **Step 4: Write `cli.py`**

```python
# src/factory/coverage/cli.py
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factory.coverage.audit import SrState, classify, validate_verdict
from factory.coverage.gate import run_gate
from factory.coverage.imports import compute_overlap
from factory.coverage.report import render_human_summary
from factory.coverage.scope import resolve_feature_scope


_COVERAGE_REVIEWS = "coverage-reviews"


def _run_dir(root: Path, feat: str, run_id: str) -> Path:
    return root / _COVERAGE_REVIEWS / f"{feat}-{run_id}"


def cmd_audit(root: Path, feat: str, run_id: str | None = None) -> dict:
    """Phase 0 + 1: write scope + overlap to a run directory."""
    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = _run_dir(root, feat, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    scope = resolve_feature_scope(root, feat)

    # Phase 1: overlap for each SR with a pytest binding
    overlaps: dict[str, dict] = {}
    for sr_id, sr in scope.srs.items():
        if sr.binding is None:
            continue
        experiment = sr.binding.get("experiment", "")
        if not experiment:
            continue
        changed_files: list[str] = []
        for task in sr.tasks:
            changed_files.extend(task.changed_files)
        changed_files = list(set(changed_files))
        if not changed_files:
            overlaps[sr_id] = {"ok": False, "reason": "no changed files from tasks"}
        else:
            result = compute_overlap(root, experiment, changed_files)
            overlaps[sr_id] = asdict(result)

    # Build the audit JSON
    audit = {
        "feature": feat,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "declared": list(scope.declared),
            "contains": list(scope.contains),
            "linked": list(scope.linked),
            "register": list(scope.register),
        },
        "completeness": [dict(f) for f in scope.completeness],
        "srs": {
            sr_id: {
                "sr_id": sr.sr_id,
                "statement": sr.statement,
                "binding": sr.binding,
                "checksum_state": sr.checksum_state,
                "tasks": [{"task_id": t.task_id, "changed_files": list(t.changed_files)} for t in sr.tasks],
                "measurement": sr.measurement,
                "deferred": sr.deferred,
                "domain": sr.domain,
            }
            for sr_id, sr in scope.srs.items()
        },
        "overlaps": overlaps,
        "states": {},  # populated by consolidate
        "gate": None,  # populated by consolidate
        "tool_failures": [],  # appended via the failure verb
    }
    (run_dir / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit


def cmd_verdict(root: Path, feat: str, run_id: str, sr_id: str, verdict: dict) -> dict:
    """Validate and record a subagent verdict for one SR."""
    validated, error = validate_verdict(verdict)
    if error:
        return {"valid": False, "error": error}
    run_dir = _run_dir(root, feat, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True, exist_ok=True)
    (verdict_dir / f"{sr_id}.json").write_text(
        json.dumps(validated, indent=2), encoding="utf-8"
    )
    return {"valid": True, "path": str(verdict_dir / f"{sr_id}.json")}


def _load_verdicts(run_dir: Path) -> dict[str, dict]:
    verdict_dir = run_dir / "verdicts"
    verdicts: dict[str, dict] = {}
    if not verdict_dir.exists():
        return verdicts
    for p in sorted(verdict_dir.glob("*.json")):
        sr_id = p.stem
        try:
            verdicts[sr_id] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return verdicts


def cmd_record_failure(root: Path, feat: str, run_id: str, sr_id: str, issue: str) -> dict:
    """Record a workflow/tool failure for an SR (subagent dispatch, etc.)."""
    run_dir = _run_dir(root, feat, run_id)
    audit_path = run_dir / "audit.json"
    if not audit_path.exists():
        return {"recorded": False, "error": f"no audit.json at {audit_path}"}
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    failures = audit.get("tool_failures", [])
    if not any(f.get("sr_id") == sr_id for f in failures):
        failures.append({"sr_id": sr_id, "issue": issue})
    audit["tool_failures"] = failures
    (audit_path).write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return {"recorded": True, "tool_failures": failures}


def cmd_consolidate(root: Path, feat: str, run_id: str) -> dict:
    """Phase 3 + 4: classify, gate, write report."""
    run_dir = _run_dir(root, feat, run_id)
    audit_path = run_dir / "audit.json"
    if not audit_path.exists():
        return {"error": f"no audit.json found at {audit_path}"}
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    verdicts = _load_verdicts(run_dir)

    # Workflow issues: tool failures from subagent dispatch
    tool_failures = audit.get("tool_failures", [])
    # Classify each SR
    states: dict[str, list] = {}
    for sr_id, sr_data in audit.get("srs", {}).items():
        verdict = verdicts.get(sr_id)
        overlap = audit.get("overlaps", {}).get(sr_id)
        tool_failure = any(f.get("sr_id") == sr_id for f in tool_failures)
        state, notes = classify(sr_data, overlap, verdict, tool_failure)
        states[sr_id] = [state.value, notes]

    # Run gate
    outcome, failed, warned, degraded = run_gate(
        {sr_id: (s[0], s[1]) for sr_id, s in states.items()},
        tool_failures,
    )

    report = {
        "feature": feat,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": audit.get("scope", {}),
        "completeness": audit.get("completeness", []),
        "srs": audit.get("srs", {}),
        "overlaps": audit.get("overlaps", {}),
        "states": states,
        "gate": {
            "outcome": outcome.value,
            "failed": failed,
            "warned": warned,
            "degraded": degraded,
        },
        "workflow_issues": tool_failures,
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def cmd_gate(root: Path, feat: str, run_id: str) -> str:
    """Re-derive gate from disk (stateless)."""
    run_dir = _run_dir(root, feat, run_id)
    report_path = run_dir / "report.json"
    if not report_path.exists():
        return "no_report"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    outcome = report.get("gate", {}).get("outcome", "unknown")
    return outcome


def cmd_report(root: Path, feat: str, run_id: str) -> str:
    """Render the human summary."""
    run_dir = _run_dir(root, feat, run_id)
    report_path = run_dir / "report.json"
    if not report_path.exists():
        # Try to consolidate first
        consolidated = cmd_consolidate(root, feat, run_id)
        if "error" in consolidated:
            return consolidated["error"]
        report_path = run_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return render_human_summary(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-coverage")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=Path("."), type=Path)

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit", parents=[common])
    p_audit.add_argument("feat")
    p_audit.add_argument("--run-id", default=None)

    p_verdict = sub.add_parser("verdict", parents=[common])
    p_verdict.add_argument("feat")
    p_verdict.add_argument("run_id")
    p_verdict.add_argument("sr_id")
    p_verdict.add_argument("--file", required=True, type=Path,
                           help="path to verdict JSON file")

    p_consolidate = sub.add_parser("consolidate", parents=[common])
    p_consolidate.add_argument("feat")
    p_consolidate.add_argument("run_id")

    p_gate = sub.add_parser("gate", parents=[common])
    p_gate.add_argument("feat")
    p_gate.add_argument("run_id")

    p_report = sub.add_parser("report", parents=[common])
    p_report.add_argument("feat")
    p_report.add_argument("run_id")

    p_failure = sub.add_parser("failure", parents=[common])
    p_failure.add_argument("feat")
    p_failure.add_argument("run_id")
    p_failure.add_argument("sr_id")
    p_failure.add_argument("--issue", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "audit":
        result = cmd_audit(args.project_root, args.feat, run_id=args.run_id)
        print(json.dumps(result, indent=2))
    elif args.cmd == "failure":
        result = cmd_record_failure(
            args.project_root, args.feat, args.run_id, args.sr_id, args.issue
        )
        print(json.dumps(result, indent=2))
    elif args.cmd == "verdict":
        verdict = json.loads(args.file.read_text(encoding="utf-8"))
        result = cmd_verdict(args.project_root, args.feat, args.run_id, args.sr_id, verdict)
        print(json.dumps(result, indent=2))
        return 1 if not result.get("valid") else 0
    elif args.cmd == "consolidate":
        result = cmd_consolidate(args.project_root, args.feat, args.run_id)
        print(json.dumps(result, indent=2))
    elif args.cmd == "gate":
        outcome = cmd_gate(args.project_root, args.feat, args.run_id)
        print(outcome)
        if outcome == "fail":
            return 1
        if outcome == "degraded":
            return 2
    elif args.cmd == "report":
        text = cmd_report(args.project_root, args.feat, args.run_id)
        print(text)

    return 0
```

- [ ] **Step 5: Write `__main__.py`**

```python
# src/factory/coverage/__main__.py
import sys
from factory.coverage.cli import main

sys.exit(main())
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/coverage/test_cli.py -v
```
Expected: 8 passed.

- [ ] **Step 7: Verify the CLI works end-to-end**

```bash
# Create a temp fixture project and run the full pipeline
cd /c/coding/pi-agent-factory
uv run python -m factory.coverage audit FEAT-001 --project-root tests/fixtures/coverage-demo 2>&1 || true
# (fixture not yet created — this is a smoke test that the CLI loads)
```

If the fixture doesn't exist, create it quickly:

```bash
mkdir -p tests/fixtures/coverage-demo/{docs/features,requirements,tasks,evidence/runs}
echo '---\nid: FEAT-001\ntitle: Demo\nrequirements: [SR-001]\n---\n' > tests/fixtures/coverage-demo/docs/features/FEAT-001.md
echo '---\nid: SR-001\ntitle: X\nstatement: shall do X\ndomain: behavioral\nbinding:\n  harness: sim-testbench\n  experiment: tests/test_x.py\n  metric: unit_pass_rate\n  trials: 1\n  assert: "== 1.0"\nchecksum: null\n---\n' > tests/fixtures/coverage-demo/requirements/SR-001.md
echo '---\nid: T-001\ntitle: T\ndeliverables: []\nsatisfies: [SR-001]\n---\n' > tests/fixtures/coverage-demo/tasks/T-001.md
```

- [ ] **Step 8: Commit**

```bash
git add src/factory/coverage/report.py src/factory/coverage/cli.py src/factory/coverage/__main__.py tests/unit/coverage/test_cli.py
git commit -m "feat(coverage): CLI verbs, JSON artifacts, and human-summary report"
```

---

### Task 6: Skills — coverage-review (main orchestration) + requirement-traceability-audit (per-SR)

**Files:**
- Create: `.pi/skills/coverage-review/SKILL.md`
- Create: `.pi/skills/requirement-traceability-audit/SKILL.md`

- [ ] **Step 1: Write `coverage-review/SKILL.md`**

```markdown
---
name: coverage-review
description: >
  Orchestrate a feature-scoped requirement coverage audit. Resolve the scope,
  dispatch one subagent per SR for semantic review, consolidate verdicts, run
  the gate, and present the report with human-gated disposition for new
  requirements.
---

# Requirement Coverage Review

## Phase order

### Phase 0 + 1 — Machine resolution
Run: `factory coverage audit <feat:FEAT-XXX> --project-root .`
This writes `coverage-reviews/<feat>-<run-id>/audit.json` with the scope,
completeness findings, and import-graph overlap results.

### Phase 2 — Per-SR subagent audit
For each SR in the audit result, dispatch one subagent with the following
task packet:
```
You are auditing SR-{id} of feature {feat}.

Statement: {statement}
Binding: {harness}/{experiment} {metric} {assert_expr} (trials={trials})
Implementing tasks: {task_ids}
Changed files: {changed_files}
Binding test source: {experiment_path}
Validation report: {measurement}
Import-graph overlap: {overlap_ok} (reached {reached_files},
changed {changed_files}, overlap {overlap})
Import-unresolved: {unresolved_modules}

Follow the requirement-traceability-audit skill. Return ONLY a JSON verdict
with the following fields (mandatory):

{sr_id, implemented, honest, confidence, margin, reasoning,
 checked: [...], assumed: [...], verify: [{item, file?, line?, why?}]}
```

Output the verdict to a file and run:
`factory coverage verdict <feat> <run-id> <sr_id> --file <verdict_path>`

### Phase 3 + 4 — Consolidation + gate
Run: `factory coverage consolidate <feat> <run-id> --project-root .`
Then: `factory coverage gate <feat> <run-id> --project-root .`

### Phase 5 — Report + disposition
Run: `factory coverage report <feat> <run-id> --project-root .`

Present the report to the human. For each proposed_requirement finding:
- Accept → route through the doctor skill (mint → human review → promote)
- Reject → record via doctor: create SR file with `trace_deferred: <reason>`
- Defer → same pattern with a reason

## Important rules
- Never write an SR file yourself. Only the doctor skill does that.
- Report workflow_issues (subagent failures) to the human so the workflow
  itself can be improved.
- Subagents are independent sessions — never the session that wrote the code.
- If a subagent fails, record it with `factory coverage failure <feat> <run-id>
  <sr_id> --issue "..."` and continue with the remaining SRs. The gate will
  report degraded if needed.
```

- [ ] **Step 2: Write `requirement-traceability-audit/SKILL.md`**

```markdown
---
name: requirement-traceability-audit
description: >
  Per-SR semantic audit: judge whether the implementing code genuinely satisfies
  the requirement statement, and whether the binding test exercises the claimed
  behavior. Read-only; returns a structured verdict.
---

# Requirement Traceability Audit

## Audit protocol

You are a read-only reviewer. You receive:

1. The requirement statement (EARS: When <trigger>, the <system> shall <response>)
2. The binding (harness, experiment, metric, threshold)
3. The changed files of the satisfying task(s) — verbatim code excerpts
4. The binding test source — verbatim
5. The validation report excerpt (if measured)
6. The import-graph overlap result (machine-computed)

## Your judgment

Answer two questions:

**implemented** (bool): Does the code in the changed files implement the behavior
the statement requires? If the statement says "when shark detected, preempt
patrol" and the code contains a preempt path triggered by a detector, this is
true. If the code only touches logging or config, this is false.

**honest** (bool): Is the implementation genuinely verified by the binding test?
This is true ONLY if:
  - implemented is true, AND
  - the binding test exercises the relevant behavior (not just the module's
    public API — the specific path the statement names), AND
  - the import-graph overlap check passes (the test reaches the implementation)

## Output format

Return ONLY a JSON object (no markdown fences, no commentary):

```json
{
  "sr_id": "SR-001",
  "implemented": true,
  "honest": true,
  "confidence": "high|medium|low",
  "margin": "0.90 vs >= 0.90 (tight)" or null,
  "reasoning": "Why. What was checked, what was found, what was absent.",
  "checked": ["concrete list of behavior paths verified"],
  "assumed": ["concrete list of assumptions made (fixture fidelity, etc.)"],
  "verify": [
    {"item": "specific check for a human to do", "file": "path/to/file.py", "line": 42, "why": "why this matters"}
  ]
}
```

## Rules

- **Reasoning, checked, and assumed are mandatory.** A verdict without them is
  invalid. The human must understand your audit's limits.
- **Never guess.** If a code path is not visible in the injected excerpts, mark
  it as assumed and explain why. Do not claim to have verified code you did not
  read.
- **Threshold-tight passes are verify items.** If the metric passes exactly at
  the threshold (e.g., 0.90 vs >= 0.90), emit a verify item suggesting the
  human re-run with a different seed.
- **Any binding test that does not import the implementing module is suspect.**
  If the import-graph overlap fails, `honest` must be false unless the test
  validates the behavior through indirect means (e.g., black-box integration).
- **You are read-only.** Do not edit files, do not write code, do not propose
  changes. Your output is a verdict, nothing else.
```

- [ ] **Step 3: Commit**

```bash
git add .pi/skills/coverage-review/SKILL.md .pi/skills/requirement-traceability-audit/SKILL.md
git commit -m "feat(skills): coverage-review orchestration and requirement-traceability-audit skills"
```

---

### Task 7: Integration — full suites, ruff, pyright, trace gate check

- [ ] **Step 1: Run full unit test suite**

```bash
uv run python -m pytest -m unit -q
```
Expected: 1363+ passed (new tests). Any failures must be from the new tests only.

- [ ] **Step 2: Run ruff**

```bash
uv run ruff check src/factory/coverage/ tests/unit/coverage/
```
Expected: clean.

- [ ] **Step 3: Run pyright on touched files**

```bash
uv run pyright src/factory/coverage/ 2>&1 | head -30
```
Expected: no errors (or only pre-existing ones from other files).

- [ ] **Step 4: Verify trace gate — the plan file references the spec**

The plan file text contains `docs/superpowers/specs/2026-08-17-requirement-coverage-review-design.md` which the trace model's regex picks up as a `spec_ref` edge. This is a plan markdown file, not a task — no new trace gaps.

- [ ] **Step 5: Commit**

```bash
git add -A tests/fixtures/coverage-demo/ 2>/dev/null || true
git commit -m "test(coverage): integration fixture and full suite verification"
```