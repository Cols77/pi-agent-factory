# Evidence Store and Manifests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist hash-verifiable factory-run evidence tied to the code commit, migrate human-review rounds into that evidence, and expose it through one Python CLI.

**Architecture:** Extend the existing `factory.evidence` package with a content-addressed local object store, a validated run-manifest repository, and a finalizer called by `run_next`. Runtime review files remain a compatibility input, while durable manifests under `evidence/runs/` become the canonical browser/agent API. The finalizer records the code commit before making a separate exact-path evidence commit.

**Tech Stack:** Python 3.11+, dataclasses, hashlib, pathlib, jsonschema, subprocess Git, pytest.

## Global Constraints

- The browser is a projection, never the source of truth.
- Artifact identity is SHA-256 of bytes; mtime is never evidence identity.
- Local writes complete atomically before the pipeline advances.
- Large blobs live under ignored `.factory/artifacts/`; compact manifests live under `evidence/runs/`.
- No inferred task/code/requirement relationship may be persisted.
- Runtime transcripts remain local-only unless explicitly published.
- The evidence commit stages exact paths; never use `git add -A` for evidence finalization.

---

## File Structure

**Create:**
- `src/factory/evidence/artifacts.py` — `BlobRef`, `PublicationResult`, `ArtifactStore`, and `LocalArtifactStore`.
- `src/factory/evidence/manifests.py` — manifest validation, atomic persistence, and loading/querying.
- `src/factory/evidence/finalize.py` — convert one completed `run_task` result and transcript evidence into a run manifest.
- `src/factory/evidence/cli.py` — deterministic `run`, `task`, and `list` queries.
- `src/factory/evidence/__main__.py` — `python -m factory.evidence` entry point.
- `src/factory/schemas/evidence_manifest.schema.json` — portable manifest contract.
- `tests/unit/evidence/test_artifacts.py`
- `tests/unit/evidence/test_manifests.py`
- `tests/unit/evidence/test_finalize.py`
- `tests/unit/evidence/test_cli.py`

**Modify:**
- `src/factory/orchestrator/types.py` — retain `start_commit` and `result_commit` on `TaskResult`.
- `src/factory/orchestrator/runner.py` — finalize evidence after task status update and before session review.
- `src/factory/orchestrator/git_ops.py` — binary patch and exact-path commit operations.
- `src/factory/orchestrator/human_review.py` — include run-compatible round metadata and review-guide snapshot in runtime archives.
- `src/factory/orchestrator/__main__.py` — construct artifact store/finalizer paths.
- `.gitignore` — ignore `.factory/artifacts/`, keep `evidence/runs/` tracked.
- corresponding orchestrator tests.

### Task 1: Content-addressed local artifact store

**Files:**
- Create: `src/factory/evidence/artifacts.py`
- Create: `tests/unit/evidence/test_artifacts.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces `BlobRef(sha256: str, size: int, media_type: str, local: bool = True, publication: str = "local", uri: str | None = None)`.
- Produces `PublicationResult(state: str, uri: str | None = None, error: str | None = None)`.
- Produces `ArtifactStore` protocol with `put`, `get`, `has`, and `publish`.
- Produces `LocalArtifactStore(root: Path, publish_root: Path | None = None)`.

- [ ] **Step 1: Write failing object-store tests**

```python
from hashlib import sha256

import pytest

from factory.evidence.artifacts import LocalArtifactStore

pytestmark = pytest.mark.unit


def test_put_is_content_addressed_and_idempotent(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects")
    first = store.put(b"hello", "text/plain")
    second = store.put(b"hello", "text/plain")
    assert first == second
    assert first.sha256 == sha256(b"hello").hexdigest()
    assert first.size == 5
    assert store.get(first.sha256) == b"hello"


def test_corrupt_object_is_rejected_on_read(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects")
    ref = store.put(b"hello", "text/plain")
    store.path_for(ref.sha256).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        store.get(ref.sha256)


def test_publish_copies_and_verifies_object(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects", tmp_path / "published")
    ref = store.put(b"hello", "text/plain")
    result = store.publish(ref.sha256)
    assert result.state == "published"
    assert (tmp_path / "published" / ref.sha256[:2] / ref.sha256).read_bytes() == b"hello"


def test_publish_without_destination_stays_local(tmp_path):
    store = LocalArtifactStore(tmp_path / "objects")
    ref = store.put(b"hello", "text/plain")
    assert store.publish(ref.sha256).state == "local"
```

- [ ] **Step 2: Run the tests and verify import failure**

Run: `uv run pytest tests/unit/evidence/test_artifacts.py -v`
Expected: FAIL because `factory.evidence.artifacts` does not exist.

- [ ] **Step 3: Implement the store**

```python
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BlobRef:
    sha256: str
    size: int
    media_type: str
    local: bool = True
    publication: str = "local"
    uri: str | None = None


@dataclass(frozen=True)
class PublicationResult:
    state: str
    uri: str | None = None
    error: str | None = None


class ArtifactStore(Protocol):
    def put(self, data: bytes, media_type: str) -> BlobRef: ...
    def get(self, sha256: str) -> bytes: ...
    def has(self, sha256: str) -> bool: ...
    def publish(self, sha256: str) -> PublicationResult: ...


class LocalArtifactStore:
    def __init__(self, root: Path, publish_root: Path | None = None) -> None:
        self.root = root
        self.publish_root = publish_root

    def path_for(self, digest: str, root: Path | None = None) -> Path:
        base = root or self.root
        return base / digest[:2] / digest

    def put(self, data: bytes, media_type: str) -> BlobRef:
        digest = hashlib.sha256(data).hexdigest()
        path = self.path_for(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if self.get(digest) != data:
                raise ValueError(f"object collision for {digest}")
        else:
            tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return BlobRef(digest, len(data), media_type)

    def get(self, sha256: str) -> bytes:
        data = self.path_for(sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError(f"artifact hash mismatch: {sha256}")
        return data

    def has(self, sha256: str) -> bool:
        try:
            self.get(sha256)
            return True
        except (OSError, ValueError):
            return False

    def publish(self, sha256: str) -> PublicationResult:
        data = self.get(sha256)
        if self.publish_root is None:
            return PublicationResult("local")
        target = self.path_for(sha256, self.publish_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
            return PublicationResult("failed", error="destination hash mismatch")
        return PublicationResult("published", uri=target.as_uri())
```

- [ ] **Step 4: Ignore local objects**

Append to `.gitignore`:

```gitignore
# Content-addressed evidence blobs; compact evidence/runs manifests stay tracked.
.factory/artifacts/
```

- [ ] **Step 5: Run tests and static checks**

Run: `uv run pytest tests/unit/evidence/test_artifacts.py -v && uv run pyright && uv run ruff check src tests`
Expected: all tests pass; no type/lint findings.

- [ ] **Step 6: Commit**

```bash
git add .gitignore src/factory/evidence/artifacts.py tests/unit/evidence/test_artifacts.py
git commit -m "feat(evidence): add content-addressed artifact store"
```

### Task 2: Validated run-manifest repository

**Files:**
- Create: `src/factory/schemas/evidence_manifest.schema.json`
- Create: `src/factory/evidence/manifests.py`
- Create: `tests/unit/evidence/test_manifests.py`

**Interfaces:**
- Produces `MANIFEST_SCHEMA_VERSION = 1`.
- Produces `write_run_manifest(evidence_dir: Path, manifest: dict) -> Path`.
- Produces `load_run_manifest(path: Path) -> dict`.
- Produces `list_run_manifests(evidence_dir: Path, task_id: str | None = None) -> list[dict]`.

- [ ] **Step 1: Write failing manifest tests**

```python
import json

import pytest

from factory.evidence.manifests import list_run_manifests, load_run_manifest, write_run_manifest

pytestmark = pytest.mark.unit


def manifest(run_id="run-1", task_id="T-001"):
    return {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": task_id,
        "started_at": "2026-08-07T12:00:00Z",
        "ended_at": "2026-08-07T12:01:00Z",
        "start_commit": "a" * 40,
        "result_commit": "b" * 40,
        "outcome": "completed",
        "inputs": {"task": {"path": "tasks/T-001.md", "sha256": "c" * 64}, "requirements": [], "factory_config_sha256": "d" * 64},
        "implementation": {"changed_files": ["src/a.py"], "patch": {"sha256": "e" * 64, "size": 12, "media_type": "text/x-diff"}},
        "validation": [], "reviews": [], "decisions": [],
        "publication": {"state": "local", "errors": []},
    }


def test_manifest_round_trip_is_atomic_and_validated(tmp_path):
    path = write_run_manifest(tmp_path / "evidence", manifest())
    assert path.name == "run-1.json"
    assert load_run_manifest(path)["result_commit"] == "b" * 40
    assert not path.with_suffix(".json.tmp").exists()


def test_invalid_manifest_is_refused(tmp_path):
    bad = manifest(); del bad["task_id"]
    with pytest.raises(ValueError, match="invalid evidence manifest"):
        write_run_manifest(tmp_path / "evidence", bad)


def test_list_filters_by_task_and_skips_corrupt_files(tmp_path):
    root = tmp_path / "evidence"
    write_run_manifest(root, manifest("run-1", "T-001"))
    write_run_manifest(root, manifest("run-2", "T-002"))
    (root / "runs" / "corrupt.json").write_text("nope", encoding="utf-8")
    assert [m["run_id"] for m in list_run_manifests(root, "T-001")] == ["run-1"]
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest tests/unit/evidence/test_manifests.py -v`
Expected: FAIL because manifest module/schema do not exist.

- [ ] **Step 3: Add the JSON Schema**

Create `src/factory/schemas/evidence_manifest.schema.json` with Draft 2020-12, `additionalProperties: false`, and required fields exactly matching the manifest in Step 1. Define `$defs.blob` requiring `sha256` (`^[a-f0-9]{64}$`), non-negative `size`, and `media_type`. Allow review/validation/decision entries as objects in schema version 1 so their producers can evolve without changing the top-level contract.

- [ ] **Step 4: Implement repository functions**

```python
from __future__ import annotations

import json
from pathlib import Path

from factory.validation.schema_validator import SCHEMA_DIR, validate

MANIFEST_SCHEMA_VERSION = 1
_SCHEMA = SCHEMA_DIR / "evidence_manifest.schema.json"


def _validate(manifest: dict) -> None:
    errors = validate(manifest, _SCHEMA)
    if errors:
        raise ValueError(f"invalid evidence manifest: {'; '.join(errors)}")


def write_run_manifest(evidence_dir: Path, manifest: dict) -> Path:
    _validate(manifest)
    runs = evidence_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{manifest['run_id']}.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_run_manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid evidence manifest: {path}")
    _validate(value)
    return value


def list_run_manifests(evidence_dir: Path, task_id: str | None = None) -> list[dict]:
    out: list[dict] = []
    for path in sorted((evidence_dir / "runs").glob("*.json")):
        try:
            manifest = load_run_manifest(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if task_id is None or manifest["task_id"] == task_id:
            out.append(manifest)
    return sorted(out, key=lambda m: (m["ended_at"], m["run_id"]), reverse=True)
```

- [ ] **Step 5: Run tests and checks**

Run: `uv run pytest tests/unit/evidence/test_manifests.py -v && uv run pyright && uv run ruff check src tests`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/factory/schemas/evidence_manifest.schema.json src/factory/evidence/manifests.py tests/unit/evidence/test_manifests.py
git commit -m "feat(evidence): add validated run manifests"
```

### Task 3: Git operations and evidence finalizer

**Files:**
- Modify: `src/factory/orchestrator/git_ops.py`
- Modify: `src/factory/orchestrator/types.py`
- Create: `src/factory/evidence/finalize.py`
- Modify: `tests/unit/orchestrator/test_git_ops.py`
- Create: `tests/unit/evidence/test_finalize.py`

**Interfaces:**
- Extend `GitOps` with `binary_diff(repo_root, start_commit, end_commit=None) -> bytes` and `commit_paths(repo_root, paths: list[Path], message: str) -> bool`.
- Extend `TaskResult` with `start_commit: str | None = None`, `result_commit: str | None = None`.
- Produce `finalize_run_evidence(...) -> Path` with explicit repo, task, result, transcript, artifact store, and evidence-directory inputs.

- [ ] **Step 1: Add failing exact-path Git tests**

```python
def test_commit_paths_does_not_stage_unrelated_files(tmp_path):
    repo = _init_repo(tmp_path)
    wanted = repo / "evidence" / "runs" / "r.json"
    wanted.parent.mkdir(parents=True)
    wanted.write_text("{}", encoding="utf-8")
    (repo / "unrelated.txt").write_text("leave me", encoding="utf-8")
    assert SubprocessGitOps().commit_paths(repo, [wanted], "evidence: record run") is True
    status = subprocess.run(["git", "status", "--short"], cwd=repo, capture_output=True, text=True, check=True).stdout
    assert "unrelated.txt" in status
    assert "evidence/runs/r.json" not in status


def test_binary_diff_captures_committed_range(tmp_path):
    repo = _init_repo(tmp_path)
    start = SubprocessGitOps().head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    SubprocessGitOps().commit_all(repo, "change")
    end = SubprocessGitOps().head_commit(repo)
    assert b"+two" in SubprocessGitOps().binary_diff(repo, start, end)
```

- [ ] **Step 2: Implement the Git methods**

`binary_diff` runs `git diff --binary <start> <end>` when `end_commit` is provided and `git diff --binary <start>` otherwise, returning `stdout` as bytes. `commit_paths` resolves each path relative to `repo_root`, rejects paths outside it, runs `git add -- <paths>`, checks `git diff --cached --quiet -- <paths>`, and commits with the supplied message. It propagates failures: unlike legacy `commit_all`, evidence finalization must not report success after a failed commit.

- [ ] **Step 3: Write failing finalizer test**

Create a temporary Git repo containing a task, requirement, config, committed implementation range, transcript `reviews/review-001.json`, `review-guide.json`, and `validation-report.json`. Assert that `finalize_run_evidence`:

```python
path = finalize_run_evidence(
    repo_root=repo,
    run_id="run-1",
    task=task,
    result=result,
    transcript_dir=transcript,
    store=LocalArtifactStore(repo / ".factory" / "artifacts" / "objects"),
    evidence_dir=repo / "evidence",
    git_ops=SubprocessGitOps(),
)
manifest = load_run_manifest(path)
assert manifest["result_commit"] == result.result_commit
assert manifest["implementation"]["changed_files"] == ["src/a.py"]
assert store.has(manifest["implementation"]["patch"]["sha256"])
assert manifest["reviews"][0]["decision"] == "reject"
assert manifest["validation"]
```

- [ ] **Step 4: Implement the finalizer**

The finalizer must:

1. require `result.start_commit` and `result.result_commit`;
2. hash task bytes, every declared requirement file found by exact ID, and `.factory/factory.yaml` (empty bytes if absent);
3. store `git_ops.binary_diff(start, result)` as `text/x-diff`;
4. derive changed files with `git diff --name-only start result` through `GitOps.changed_files_between` or a focused helper in `finalize.py`;
5. load runtime review JSON, remove inline `diff`, store it as a blob, and retain its `BlobRef`;
6. store review guide and validation report as `application/json` blobs while retaining compact parsed summaries;
7. write a schema-valid manifest atomically;
8. return its path without committing it.

Use `dataclasses.asdict(ref)` for blob references, omitting `local/publication/uri` only if the JSON schema does not declare them.

- [ ] **Step 5: Run focused and regression tests**

Run: `uv run pytest tests/unit/evidence/test_finalize.py tests/unit/orchestrator/test_git_ops.py -v`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/git_ops.py src/factory/orchestrator/types.py src/factory/evidence/finalize.py tests/unit/orchestrator/test_git_ops.py tests/unit/evidence/test_finalize.py
git commit -m "feat(evidence): finalize implementation evidence"
```

### Task 4: Wire evidence finalization into `run_next`

**Files:**
- Modify: `src/factory/orchestrator/runner.py`
- Modify: `src/factory/orchestrator/__main__.py`
- Modify: `tests/unit/orchestrator/test_run_next.py`
- Create: `tests/unit/orchestrator/test_run_evidence.py`

**Interfaces:**
- `run_task(..., start_commit: str | None = None)` records both commit fields on every `TaskResult`.
- `run_next(..., artifact_store: ArtifactStore | None = None, evidence_dir: Path | None = None)` finalizes only when both are supplied; existing callers remain compatible.

- [ ] **Step 1: Write failing runner evidence test**

Use a real temporary Git repository and scripted passing backend/gates. Supply a `LocalArtifactStore` and `evidence_dir`. Assert:

- completed run writes one evidence manifest;
- manifest references the code commit, not the later evidence commit;
- task status and manifest are committed by `commit_paths` after finalization;
- failed/escalated runs still write a manifest with their outcome but do not claim `dod_met` or a successful result commit when no code commit exists.

- [ ] **Step 2: Capture the baseline once**

At the start of `run_next`, capture `start_commit = git_ops.head_commit(repo_root)` and pass it into `run_task`. In `run_task`, use the passed value or capture one for direct-call compatibility. Add a private `_result(...)` helper if necessary to avoid repeating commit fields across five return sites.

- [ ] **Step 3: Finalize after status update**

After `set_status`, set `result.result_commit = git_ops.head_commit(repo_root)`. When evidence dependencies are supplied:

```python
manifest_path = finalize_run_evidence(...)
paths = [manifest_path, task.path]
git_ops.commit_paths(repo_root, paths, f"evidence: record {task.id} run {sid}")
```

The manifest must retain the pre-evidence `result_commit`. An evidence failure raises and prevents the run from being reported completed.

- [ ] **Step 4: Construct dependencies in the CLI**

In `__main__.py`:

```python
store = LocalArtifactStore(repo_root / ".factory" / "artifacts" / "objects")
...
run_next(..., artifact_store=store, evidence_dir=repo_root / "evidence")
```

Do not configure publication yet.

- [ ] **Step 5: Run orchestrator and evidence regression tests**

Run: `uv run pytest tests/unit/orchestrator tests/unit/evidence -q`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/factory/orchestrator/runner.py src/factory/orchestrator/__main__.py tests/unit/orchestrator/test_run_next.py tests/unit/orchestrator/test_run_evidence.py
git commit -m "feat(orchestrator): publish evidence for factory runs"
```

### Task 5: Evidence query CLI

**Files:**
- Create: `src/factory/evidence/cli.py`
- Create: `src/factory/evidence/__main__.py`
- Create: `tests/unit/evidence/test_cli.py`

**Interfaces:**
- `main(argv: list[str] | None = None) -> int`.
- Commands: `run <run-id> --repo <path> --json`, `task <task-id> --repo <path> --json`, and `list --repo <path> --json`.
- JSON errors go to stderr and return `2`; successful JSON is stdout-only.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_task_json_returns_newest_first(tmp_path, capsys):
    write_run_manifest(tmp_path / "evidence", manifest("old", "T-001", ended="2026-01-01T00:00:00Z"))
    write_run_manifest(tmp_path / "evidence", manifest("new", "T-001", ended="2026-01-02T00:00:00Z"))
    assert main(["task", "T-001", "--repo", str(tmp_path), "--json"]) == 0
    assert [m["run_id"] for m in json.loads(capsys.readouterr().out)["runs"]] == ["new", "old"]


def test_missing_run_is_nonzero(tmp_path, capsys):
    assert main(["run", "gone", "--repo", str(tmp_path), "--json"]) == 2
    assert "not found" in capsys.readouterr().err
```

- [ ] **Step 2: Implement argument parsing and commands**

Use `argparse`, `list_run_manifests`, and `load_run_manifest`. The `run` command resolves only `<repo>/evidence/runs/<run-id>.json`; it does not accept arbitrary paths.

- [ ] **Step 3: Run tests and real smoke command**

Run: `uv run pytest tests/unit/evidence/test_cli.py -v && uv run python -m factory.evidence list --repo . --json`
Expected: tests pass and command emits `{"runs": [...]}`.

- [ ] **Step 4: Run full gates**

Run: `uv run pytest -q && uv run pyright && uv run ruff check src tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/factory/evidence/cli.py src/factory/evidence/__main__.py tests/unit/evidence/test_cli.py
git commit -m "feat(evidence): expose run evidence through CLI"
```

## Plan Self-review

- Spec coverage: local object storage, compact manifests, review migration, implementation commit identity, exact-path evidence commit, and shared query API are covered.
- Deliberately deferred to later plans: publication retry policy, journaling/resume, freshness/reconcile, and browser rendering.
- Type consistency: `BlobRef`, `ArtifactStore`, manifest repository, finalizer, and runner dependencies use the same names throughout.
- Placeholder scan: no implementation placeholder or unspecified test step remains; schema construction is bounded by the exact manifest fixture and required constraints.
