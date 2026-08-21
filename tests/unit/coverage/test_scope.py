# tests/unit/coverage/test_scope.py
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from factory.coverage.scope import (
    EvidenceState,
    _latest_validation,
    resolve_feature_scope,
)
from factory.evidence.records import build_historical_record, write_historical_record

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
        "implementation": {
            "changed_files": changed_files or [],
            "patch": {"sha256": "0" * 64, "size": 0, "media_type": "application/json"},
        },
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
    # Stamp the content checksum so the requirement reads as "current".
    from factory.requirements.register import content_checksum, parse_requirement

    digest = content_checksum(parse_requirement(p))
    p.write_text(content.replace("checksum: null", f"checksum: {digest}"))
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


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write_historical_record(root: Path, task_id: str, changed_file: str) -> Path:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Coverage Scope Test")
    _feat_file(root, "FEAT-001", ["SR-001"])
    _req_file(root, "SR-001")
    _task_file(root, task_id, ["SR-001"])
    start = _commit(root, "add task")

    path = root / changed_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("RECORDED = True\n", encoding="utf-8")
    result = _commit(root, "complete task")
    record = build_historical_record(
        root,
        task_id,
        start,
        result,
        "human@example.invalid",
        "Recover completed historical work.",
    )
    return write_historical_record(root / "evidence", record)


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


def test_resolve_scope_marks_tasks_without_evidence_as_missing(tmp_path: Path) -> None:
    _feat_file(tmp_path, "FEAT-001", ["SR-058", "SR-067"])
    _task_file(tmp_path, "T-058", ["SR-058"])
    _task_file(tmp_path, "T-067", ["SR-067"])

    scope = resolve_feature_scope(tmp_path, "FEAT-001")

    for task_id in ("T-058", "T-067"):
        task = scope.tasks[task_id]
        assert task.evidence_state is EvidenceState.missing
        assert task.changed_files == ()
        assert task.manifests == ()
        assert task.record_paths == ()


def test_resolve_scope_marks_empty_manifest_evidence_as_empty(tmp_path: Path) -> None:
    _feat_file(tmp_path, "FEAT-001", ["SR-001"])
    _task_file(tmp_path, "T-058", ["SR-001"])
    run_path = tmp_path / "evidence" / "runs" / "RUN-001.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(json.dumps(_manifest(task_id="T-058", changed_files=[])), encoding="utf-8")

    task = resolve_feature_scope(tmp_path, "FEAT-001").tasks["T-058"]

    assert task.evidence_state is EvidenceState.empty
    assert task.changed_files == ()
    assert task.manifests == ("RUN-001",)
    assert task.record_paths == ()


def test_resolve_scope_includes_valid_historical_record_evidence(tmp_path: Path) -> None:
    record_path = _write_historical_record(tmp_path, "T-058", "src/factory/historical.py")

    task = resolve_feature_scope(tmp_path, "FEAT-001").tasks["T-058"]

    assert task.evidence_state is EvidenceState.present
    assert task.changed_files == ("src/factory/historical.py",)
    assert task.manifests == ()
    assert task.record_paths == (record_path.relative_to(tmp_path).as_posix(),)


def test_resolve_scope_unions_manifest_and_historical_record_evidence(tmp_path: Path) -> None:
    record_path = _write_historical_record(tmp_path, "T-058", "src/factory/historical.py")
    run_path = tmp_path / "evidence" / "runs" / "RUN-001.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(
            _manifest(
                task_id="T-058",
                changed_files=["src/factory/normal.py", "src/factory/historical.py"],
            )
        ),
        encoding="utf-8",
    )

    task = resolve_feature_scope(tmp_path, "FEAT-001").tasks["T-058"]

    assert task.evidence_state is EvidenceState.present
    assert task.changed_files == ("src/factory/historical.py", "src/factory/normal.py")
    assert task.manifests == ("RUN-001",)
    assert task.record_paths == (record_path.relative_to(tmp_path).as_posix(),)


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


def test_latest_validation_empty(tmp_path: Path) -> None:
    assert _latest_validation([], "SR-001") is None


def test_latest_validation_newest_wins(tmp_path: Path) -> None:
    old = _manifest(
        task_id="T-001",
        validation=[{"requirements": [{"id": "SR-001", "passed": False, "value": 0.0}]}],
    )
    new = _manifest(
        task_id="T-001",
        validation=[{"requirements": [{"id": "SR-001", "passed": True, "value": 1.0, "assert": "== 1.0", "trials": 1}]}],
    )
    result = _latest_validation([new, old], "SR-001")
    assert result is not None
    assert result["passed"] is True
