from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from factory.evidence.artifacts import LocalArtifactStore
from factory.evidence.manifests import load_run_manifest
from factory.freshness.fingerprint import fingerprint_file
from factory.orchestrator.journal import RunJournal
from factory.orchestrator.ledger import load_tasks


class ReconcileKind(str, Enum):
    MISSING_EVIDENCE = "missing_evidence"
    UNRESOLVED_COMMIT = "unresolved_commit"
    UNATTRIBUTED_CHANGE = "unattributed_change"
    STALE_VALIDATION = "stale_validation"
    MISSING_BLOB = "missing_blob"
    PUBLICATION_FAILED = "publication_failed"
    INTERRUPTED_RUN = "interrupted_run"
    LEGACY_REVIEW = "legacy_review"


@dataclass(frozen=True)
class ReconcileItem:
    kind: ReconcileKind
    subject: str
    detail: str
    repairable: bool
    source: str

    def to_dict(self) -> dict:
        value = asdict(self)
        value["kind"] = self.kind.value
        return value


def _commit_exists(repo_root: Path, commit: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
    ).returncode == 0


def _blob_refs(value: object) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        digest = value.get("sha256")
        if (
            isinstance(digest, str)
            and len(digest) == 64
            and isinstance(value.get("size"), int)
            and isinstance(value.get("media_type"), str)
        ):
            refs.append(digest)
        for child in value.values():
            refs.extend(_blob_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_blob_refs(child))
    return refs


def _manifest_staleness(repo_root: Path, manifest: dict) -> list[ReconcileItem]:
    items: list[ReconcileItem] = []
    for dependency in manifest.get("dependencies", []):
        if not isinstance(dependency, dict) or dependency.get("kind") != "file":
            continue
        source = dependency.get("source")
        expected = dependency.get("digest")
        name = dependency.get("name")
        if (
            not isinstance(source, str)
            or not isinstance(expected, str)
            or not isinstance(name, str)
        ):
            continue
        actual = fingerprint_file(name, repo_root / source, repo_root).digest
        if actual != expected:
            items.append(
                ReconcileItem(
                    ReconcileKind.STALE_VALIDATION,
                    str(manifest["task_id"]),
                    f"{name} changed: expected {expected}, actual {actual}",
                    False,
                    f"evidence/runs/{manifest['run_id']}.json",
                )
            )
    return items


def _active_run_ids(repo_root: Path) -> set[str]:
    active: set[str] = set()
    root = repo_root / "sessions" / ".factory-runs" / "by-session"
    for run_dir in sorted(root.glob("*")):
        checkpoint = RunJournal(run_dir).latest()
        if checkpoint is not None and checkpoint.node not in {"completed", "closed"}:
            active.add(checkpoint.run_id)
    return active


def reconcile(repo_root: Path, task_id: str | None = None) -> list[ReconcileItem]:
    evidence_runs = repo_root / "evidence" / "runs"
    store = LocalArtifactStore(repo_root / ".factory" / "artifacts" / "objects")
    items: list[ReconcileItem] = []
    manifests: list[dict] = []
    manifests_by_task: dict[str, list[dict]] = {}

    for path in sorted(evidence_runs.glob("*.json")):
        try:
            manifest = load_run_manifest(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            items.append(
                ReconcileItem(
                    ReconcileKind.MISSING_EVIDENCE,
                    path.stem,
                    f"manifest is unreadable or invalid: {exc}",
                    False,
                    path.relative_to(repo_root).as_posix(),
                )
            )
            continue
        if task_id is not None and manifest["task_id"] != task_id:
            continue
        manifests.append(manifest)
        manifests_by_task.setdefault(manifest["task_id"], []).append(manifest)

    for task in load_tasks(repo_root / "tasks"):
        if task_id is not None and task.id != task_id:
            continue
        if task.status == "done" and not manifests_by_task.get(task.id):
            items.append(
                ReconcileItem(
                    ReconcileKind.MISSING_EVIDENCE,
                    task.id,
                    "completed task has no validated evidence manifest",
                    False,
                    task.path.relative_to(repo_root).as_posix(),
                )
            )

    for manifest in manifests:
        source = f"evidence/runs/{manifest['run_id']}.json"
        for field in ("start_commit", "result_commit"):
            commit = manifest[field]
            if not _commit_exists(repo_root, commit):
                items.append(
                    ReconcileItem(
                        ReconcileKind.UNRESOLVED_COMMIT,
                        str(manifest["run_id"]),
                        f"{field} does not resolve: {commit}",
                        False,
                        source,
                    )
                )
        for digest in sorted(set(_blob_refs(manifest))):
            if not store.has(digest):
                items.append(
                    ReconcileItem(
                        ReconcileKind.MISSING_BLOB,
                        digest,
                        f"artifact referenced by run {manifest['run_id']} is unavailable locally",
                        False,
                        source,
                    )
                )
        publication = manifest.get("publication", {})
        if publication.get("state") == "failed":
            items.append(
                ReconcileItem(
                    ReconcileKind.PUBLICATION_FAILED,
                    str(manifest["run_id"]),
                    "; ".join(publication.get("errors", [])) or "publication failed",
                    True,
                    source,
                )
            )
        items.extend(_manifest_staleness(repo_root, manifest))

    active_runs = _active_run_ids(repo_root)
    for run_id in sorted(active_runs):
        run_dir = repo_root / "sessions" / ".factory-runs" / "by-session" / run_id
        checkpoint = RunJournal(run_dir).latest()
        if checkpoint is not None and (task_id is None or checkpoint.task_id == task_id):
            items.append(
                ReconcileItem(
                    ReconcileKind.INTERRUPTED_RUN,
                    run_id,
                    f"run stopped before {checkpoint.node}",
                    True,
                    run_dir.relative_to(repo_root).as_posix(),
                )
            )

    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=repo_root,
        capture_output=True,
    )
    if status.returncode == 0 and status.stdout and not active_runs:
        digest = hashlib.sha256(status.stdout).hexdigest()
        items.append(
            ReconcileItem(
                ReconcileKind.UNATTRIBUTED_CHANGE,
                "working-tree",
                f"working tree differs from HEAD (inventory {digest})",
                False,
                "git:working-tree",
            )
        )

    legacy_root = repo_root / "sessions" / ".factory-transcripts"
    for path in sorted(legacy_root.glob("*/review-history.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = None
        identified = isinstance(value, dict) and all(
            value.get(key) for key in ("task_id", "run_id", "start_commit")
        )
        subject = str(value.get("task_id")) if isinstance(value, dict) else path.parent.name
        if task_id is None or subject == task_id:
            items.append(
                ReconcileItem(
                    ReconcileKind.LEGACY_REVIEW,
                    subject,
                    "local review history is not yet represented by durable run evidence",
                    bool(identified),
                    path.relative_to(repo_root).as_posix(),
                )
            )

    return sorted(items, key=lambda item: (item.kind.value, item.subject, item.source, item.detail))
