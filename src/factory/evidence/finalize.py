from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from factory.evidence.artifacts import ArtifactStore, BlobRef
from factory.evidence.manifests import write_run_manifest
from factory.freshness.fingerprint import (
    fingerprint_file,
    fingerprint_git_tree,
    fingerprint_tool,
)
from factory.orchestrator.git_ops import GitOps
from factory.orchestrator.types import TaskResult
from factory.requirements.register import load_register
from factory.trace.graph import build_graph
from substrate.evidence.model import MANIFEST_SCHEMA_VERSION
from substrate.ledger.tasks import Task


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _blob_dict(ref: BlobRef) -> dict:
    return asdict(ref)


def _publish_blob(store: ArtifactStore, data: bytes, media_type: str) -> BlobRef:
    ref = store.put(data, media_type)
    publication = store.publish(ref.sha256)
    return replace(ref, publication=publication.state, uri=publication.uri)


def _load_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _review_evidence(transcript_dir: Path, store: ArtifactStore) -> tuple[list[dict], list[BlobRef]]:
    reviews: list[dict] = []
    blobs: list[BlobRef] = []
    reviews_dir = transcript_dir / "reviews"
    for path in sorted(reviews_dir.glob("review-*.json")):
        record = _load_json(path)
        if record is None:
            continue
        diff = record.pop("diff", "")
        if isinstance(diff, str):
            ref = _publish_blob(store, diff.encode("utf-8"), "text/x-diff")
            blobs.append(ref)
            record["patch"] = _blob_dict(ref)
        guide = record.pop("review_guide", None)
        if isinstance(guide, dict):
            guide_bytes = json.dumps(guide, indent=2).encode("utf-8")
            ref = _publish_blob(store, guide_bytes, "application/json")
            blobs.append(ref)
            record["guide"] = _blob_dict(ref)
        reviews.append(record)

    guide_path = transcript_dir / "review-guide.json"
    try:
        guide_data = guide_path.read_bytes()
    except OSError:
        guide_data = b""
    if guide_data and reviews and "guide" not in reviews[-1]:
        ref = _publish_blob(store, guide_data, "application/json")
        blobs.append(ref)
        reviews[-1]["guide"] = _blob_dict(ref)
    return reviews, blobs


def _validation_evidence(transcript_dir: Path, store: ArtifactStore) -> tuple[list[dict], list[BlobRef]]:
    path = transcript_dir / "validation-report.json"
    try:
        raw = path.read_bytes()
    except OSError:
        return [], []
    parsed = _load_json(path)
    if parsed is None:
        return [], []
    ref = _publish_blob(store, raw, "application/json")
    return ([{"report": _blob_dict(ref), **parsed}], [ref])


def _trace_dependencies(repo_root: Path, task_id: str) -> list:
    graph = build_graph(repo_root)
    by_id = {node.id: node for node in graph.nodes}
    selected: list = []
    plan_ids = [
        edge.dst
        for edge in graph.edges
        if edge.src == task_id and edge.kind == "source_plan"
    ]
    for plan_id in sorted(plan_ids):
        plan = by_id.get(plan_id)
        if plan is None:
            continue
        selected.append(
            fingerprint_file(f"source-plan:{plan_id}", plan.path, repo_root)
        )
        for edge in sorted(
            (item for item in graph.edges if item.src == plan_id and item.kind == "spec_ref"),
            key=lambda item: item.dst,
        ):
            spec = by_id.get(edge.dst)
            if spec is not None:
                selected.append(
                    fingerprint_file(f"source-spec:{edge.dst}", spec.path, repo_root)
                )
    return selected


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
    dependencies = [
        fingerprint_file(f"task:{task.id}", task.path, repo_root),
        *(
            fingerprint_file(
                f"requirement:{item['id']}", repo_root / item["path"], repo_root
            )
            for item in requirement_inputs
        ),
        fingerprint_file("factory-config", config_path, repo_root),
        *_trace_dependencies(repo_root, task.id),
        *(
            fingerprint_tool(
                f"validator:{req.id}",
                f"factory.validation:{req.binding.harness}:v1",
            )
            for req in requirements.values()
            if req.id in task.satisfies and req.binding is not None
        ),
        fingerprint_git_tree(repo_root, ref=result.result_commit),
        fingerprint_tool("evidence-schema", f"v{MANIFEST_SCHEMA_VERSION}"),
    ]
    dependencies.sort(key=lambda item: item.name)

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
    patch_ref = _publish_blob(store, patch, "text/x-diff")
    reviews, review_blobs = _review_evidence(transcript_dir, store)
    validation, validation_blobs = _validation_evidence(transcript_dir, store)
    publication_refs = [patch_ref, *review_blobs, *validation_blobs]
    publication_state = "local"
    publication_errors: list[str] = []
    if getattr(store, "publish_root", None) is not None:
        states = {ref.publication for ref in publication_refs}
        if states == {"published"}:
            publication_state = "published"
        elif "failed" in states:
            publication_state = "failed"
        elif "queued" in states:
            publication_state = "queued"
        publication_errors = [
            f"{ref.sha256}: publication={ref.publication}"
            for ref in publication_refs
            if ref.publication not in {"local", "published"}
        ]

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
        "dependencies": [asdict(item) for item in dependencies],
        "implementation": {
            "changed_files": changed_files,
            "patch": _blob_dict(patch_ref),
        },
        "validation": validation,
        "reviews": reviews,
        "decisions": [],
        "publication": {"state": publication_state, "errors": publication_errors},
    }
    return write_run_manifest(evidence_dir, manifest)
