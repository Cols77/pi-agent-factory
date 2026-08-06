from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from factory.evidence.artifacts import ArtifactStore, BlobRef
from factory.evidence.manifests import MANIFEST_SCHEMA_VERSION, write_run_manifest
from factory.orchestrator.git_ops import GitOps
from factory.orchestrator.ledger import Task
from factory.orchestrator.types import TaskResult
from factory.requirements.register import load_register


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _blob_dict(ref: BlobRef) -> dict:
    return asdict(ref)


def _load_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _review_evidence(transcript_dir: Path, store: ArtifactStore) -> list[dict]:
    reviews: list[dict] = []
    reviews_dir = transcript_dir / "reviews"
    for path in sorted(reviews_dir.glob("review-*.json")):
        record = _load_json(path)
        if record is None:
            continue
        diff = record.pop("diff", "")
        if isinstance(diff, str):
            record["patch"] = _blob_dict(store.put(diff.encode("utf-8"), "text/x-diff"))
        guide = record.pop("review_guide", None)
        if isinstance(guide, dict):
            guide_bytes = json.dumps(guide, indent=2).encode("utf-8")
            record["guide"] = _blob_dict(store.put(guide_bytes, "application/json"))
        reviews.append(record)

    guide_path = transcript_dir / "review-guide.json"
    try:
        guide_data = guide_path.read_bytes()
    except OSError:
        guide_data = b""
    if guide_data and reviews and "guide" not in reviews[-1]:
        reviews[-1]["guide"] = _blob_dict(store.put(guide_data, "application/json"))
    return reviews


def _validation_evidence(transcript_dir: Path, store: ArtifactStore) -> list[dict]:
    path = transcript_dir / "validation-report.json"
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    parsed = _load_json(path)
    if parsed is None:
        return []
    return [{"report": _blob_dict(store.put(raw, "application/json")), **parsed}]


def finalize_run_evidence(
    *,
    repo_root: Path,
    run_id: str,
    task: Task,
    result: TaskResult,
    transcript_dir: Path,
    store: ArtifactStore,
    evidence_dir: Path,
    git_ops: GitOps,
    started_at: str,
    ended_at: str,
) -> Path:
    if result.start_commit is None or result.result_commit is None:
        raise ValueError("task result must record start_commit and result_commit")

    task_bytes = task.path.read_bytes()
    task_input = {"path": _relative(repo_root, task.path), "sha256": _digest(task_bytes)}

    requirements = {req.id: req for req in load_register(repo_root / "requirements")}
    requirement_inputs: list[dict] = []
    for req_id in sorted(task.satisfies):
        req = requirements.get(req_id)
        if req is None:
            raise ValueError(f"task {task.id} satisfies missing requirement: {req_id}")
        requirement_inputs.append(
            {
                "id": req.id,
                "path": _relative(repo_root, req.path),
                "sha256": _digest(req.path.read_bytes()),
            }
        )

    config_path = repo_root / ".factory" / "factory.yaml"
    config_bytes = config_path.read_bytes() if config_path.exists() else b""

    if result.result_commit == result.start_commit:
        patch = git_ops.binary_diff(repo_root, result.start_commit)
        changed_files = git_ops.changed_files(repo_root, result.start_commit)
    else:
        patch = git_ops.binary_diff(repo_root, result.start_commit, result.result_commit)
        changed_files = git_ops.changed_files_between(
            repo_root, result.start_commit, result.result_commit
        )
    task_relative = _relative(repo_root, task.path)
    changed_files = sorted({path for path in changed_files if path != task_relative})
    patch_ref = store.put(patch, "text/x-diff")

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "task_id": task.id,
        "started_at": started_at,
        "ended_at": ended_at,
        "start_commit": result.start_commit,
        "result_commit": result.result_commit,
        "outcome": result.outcome,
        "inputs": {
            "task": task_input,
            "requirements": requirement_inputs,
            "factory_config_sha256": _digest(config_bytes),
        },
        "implementation": {
            "changed_files": changed_files,
            "patch": _blob_dict(patch_ref),
        },
        "validation": _validation_evidence(transcript_dir, store),
        "reviews": _review_evidence(transcript_dir, store),
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    return write_run_manifest(evidence_dir, manifest)
