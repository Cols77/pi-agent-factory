from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from factory.evidence.artifacts import LocalArtifactStore
from factory.evidence.manifests import load_run_manifest, write_run_manifest
from factory.evidence.records import list_historical_records
from factory.freshness.fingerprint import fingerprint_file
from factory.kb.index import build_index, build_index_payload
from factory.orchestrator.journal import RunJournal
from factory.orchestrator.ledger import load_tasks
from factory.orchestrator.recovery import abandon_run


class ReconcileKind(str, Enum):
    MISSING_EVIDENCE = "missing_evidence"
    UNRESOLVED_COMMIT = "unresolved_commit"
    UNATTRIBUTED_CHANGE = "unattributed_change"
    STALE_VALIDATION = "stale_validation"
    MISSING_BLOB = "missing_blob"
    PUBLICATION_FAILED = "publication_failed"
    INTERRUPTED_RUN = "interrupted_run"
    LEGACY_REVIEW = "legacy_review"
    DISPOSABLE_INDEX = "disposable_index"


@dataclass(frozen=True)
class ReconcileItem:
    kind: ReconcileKind
    subject: str
    detail: str
    repairable: bool
    source: str
    blocking: bool = True

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


def _blob_publication_entries(value: object, path: str = "") -> list[tuple[str, dict]]:
    entries: list[tuple[str, dict]] = []
    if isinstance(value, dict):
        if (
            isinstance(value.get("sha256"), str)
            and isinstance(value.get("size"), int)
            and isinstance(value.get("media_type"), str)
            and isinstance(value.get("publication"), str)
        ):
            entries.append((path or "blob", value))
            return entries
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            entries.extend(_blob_publication_entries(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            entries.extend(_blob_publication_entries(child, child_path))
    return entries


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
        if (run_dir / "abandoned.json").exists():
            continue
        checkpoint = RunJournal(run_dir).latest()
        if checkpoint is not None and checkpoint.node not in {"completed", "closed"}:
            active.add(checkpoint.run_id)
    return active


def _publication_queue_items(repo_root: Path) -> list[ReconcileItem]:
    items: list[ReconcileItem] = []
    store = LocalArtifactStore(repo_root / ".factory" / "artifacts" / "objects")
    queue_root = store.publication_queue_root()
    for path in sorted(queue_root.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            items.append(
                ReconcileItem(
                    ReconcileKind.PUBLICATION_FAILED,
                    path.stem,
                    f"publication queue record is unreadable: {exc}",
                    False,
                    path.relative_to(repo_root).as_posix(),
                )
            )
            continue
        if not isinstance(record, dict):
            items.append(
                ReconcileItem(
                    ReconcileKind.PUBLICATION_FAILED,
                    path.stem,
                    "publication queue record is not an object",
                    False,
                    path.relative_to(repo_root).as_posix(),
                )
            )
            continue
        sha256 = record.get("sha256")
        state = record.get("state")
        publish_root = record.get("publish_root")
        errors = record.get("errors", [])
        if not isinstance(sha256, str) or len(sha256) != 64:
            items.append(
                ReconcileItem(
                    ReconcileKind.PUBLICATION_FAILED,
                    path.stem,
                    "publication queue record does not identify a blob hash",
                    False,
                    path.relative_to(repo_root).as_posix(),
                )
            )
            continue
        if state == "published":
            continue
        if not isinstance(state, str):
            state = "failed"
        detail = f"publication {state} for {sha256}"
        if isinstance(errors, list) and errors:
            detail += ": " + "; ".join(str(error) for error in errors)
        has_target = isinstance(publish_root, str) and bool(publish_root.strip())
        repairable = has_target and store.has(sha256)
        if not repairable:
            detail += " (no real configured publication target or local blob is missing)"
        items.append(
            ReconcileItem(
                ReconcileKind.PUBLICATION_FAILED,
                sha256,
                detail,
                repairable,
                path.relative_to(repo_root).as_posix(),
                blocking=has_target or not store.has(sha256),
            )
        )
    return items


def _manifest_publication_items(repo_root: Path, manifests: list[dict]) -> list[ReconcileItem]:
    items: list[ReconcileItem] = []
    known_publication_hashes = {
        item.subject for item in _publication_queue_items(repo_root) if len(item.subject) == 64
    }
    for manifest in manifests:
        source = f"evidence/runs/{manifest['run_id']}.json"
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
        for path, blob in _blob_publication_entries(manifest):
            sha256 = blob.get("sha256")
            state = blob.get("publication")
            if not isinstance(sha256, str) or state not in {"queued", "failed"}:
                continue
            if sha256 in known_publication_hashes:
                continue
            items.append(
                ReconcileItem(
                    ReconcileKind.PUBLICATION_FAILED,
                    sha256,
                    f"{path} publication is {state}",
                    False,
                    source,
                )
            )
        items.extend(_manifest_staleness(repo_root, manifest))
    return items


def _kb_index_items(repo_root: Path) -> list[ReconcileItem]:
    kb_dir = repo_root / "kb"
    if not kb_dir.exists():
        return []
    index_path = kb_dir / "index.json"
    expected = build_index_payload(kb_dir)
    try:
        current = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        current = None
    if current == expected:
        return []
    detail = "kb index is missing or stale"
    if index_path.exists():
        detail = "kb/index.json is stale"
    return [
        ReconcileItem(
            ReconcileKind.DISPOSABLE_INDEX,
            "kb/index.json",
            detail,
            True,
            index_path.relative_to(repo_root).as_posix() if index_path.exists() else "kb/index.json",
        )
    ]


BLOCKING_RECONCILE_KINDS = {
    ReconcileKind.MISSING_EVIDENCE,
    ReconcileKind.UNRESOLVED_COMMIT,
    ReconcileKind.STALE_VALIDATION,
    ReconcileKind.MISSING_BLOB,
    ReconcileKind.PUBLICATION_FAILED,
}


def blocks_evidence_gate(item: ReconcileItem) -> bool:
    return item.blocking and item.kind in BLOCKING_RECONCILE_KINDS


def _manifest_publication_state(manifest: dict) -> tuple[str, list[str]]:
    refs = [blob for _, blob in _blob_publication_entries(manifest)]
    if not refs:
        return "local", []
    states = {str(blob.get("publication")) for blob in refs}
    if states == {"local"}:
        return "local", []
    if states == {"published"} or states <= {"published", "local"}:
        return "published", []
    errors = [
        f"{blob.get('sha256')}: publication={blob.get('publication')}"
        for blob in refs
        if blob.get("publication") not in {"local", "published"}
    ]
    if "failed" in states:
        return "failed", errors
    return "queued", errors


def _set_blob_publication(value: object, sha256: str, *, state: str, uri: str | None) -> bool:
    changed = False
    if isinstance(value, dict):
        if (
            value.get("sha256") == sha256
            and isinstance(value.get("size"), int)
            and isinstance(value.get("media_type"), str)
            and isinstance(value.get("publication"), str)
        ):
            if value.get("publication") != state or value.get("uri") != uri:
                value["publication"] = state
                value["uri"] = uri
                changed = True
        for child in value.values():
            if _set_blob_publication(child, sha256, state=state, uri=uri):
                changed = True
    elif isinstance(value, list):
        for child in value:
            if _set_blob_publication(child, sha256, state=state, uri=uri):
                changed = True
    return changed


def _rewrite_manifests_for_publication(
    repo_root: Path, sha256: str, *, state: str, uri: str | None
) -> list[str]:
    updated: list[str] = []
    evidence_runs = repo_root / "evidence" / "runs"
    for path in sorted(evidence_runs.glob("*.json")):
        try:
            manifest = load_run_manifest(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not _set_blob_publication(manifest, sha256, state=state, uri=uri):
            continue
        manifest_state, errors = _manifest_publication_state(manifest)
        manifest["publication"] = {"state": manifest_state, "errors": errors}
        write_run_manifest(repo_root / "evidence", manifest)
        updated.append(path.relative_to(repo_root).as_posix())
    return updated


def _migrate_legacy_review(repo_root: Path, item: ReconcileItem) -> dict[str, str] | None:
    path = repo_root / item.source
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    task_id = value.get("task_id")
    run_id = value.get("run_id")
    start_commit = value.get("start_commit")
    if not all(isinstance(field, str) and field.strip() for field in (task_id, run_id, start_commit)):
        return None
    manifest_path = repo_root / "evidence" / "runs" / f"{run_id}.json"
    try:
        manifest = load_run_manifest(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if manifest.get("task_id") != task_id or manifest.get("start_commit") != start_commit:
        return None
    reviews = list(manifest.get("reviews", []))
    if any(isinstance(review, dict) and review.get("source") == item.source for review in reviews):
        return None
    migrated = dict(value)
    migrated["source"] = item.source
    reviews.append(migrated)
    manifest["reviews"] = reviews
    write_run_manifest(repo_root / "evidence", manifest)
    return {
        "kind": "migrate_legacy_review",
        "subject": str(run_id),
        "path": manifest_path.relative_to(repo_root).as_posix(),
    }


def repair_reconciliation(
    repo_root: Path,
    items: list[ReconcileItem],
    *,
    reason: str | None,
) -> list[dict[str, str]]:
    """Perform only repairs whose provenance is already explicit."""
    actions: list[dict[str, str]] = []
    interrupted = [item for item in items if item.kind is ReconcileKind.INTERRUPTED_RUN]
    if interrupted and (reason is None or not reason.strip()):
        raise ValueError("repairing an interrupted run requires --reason")
    for item in interrupted:
        run_dir = repo_root / item.source
        marker = abandon_run(run_dir, reason or "")
        actions.append(
            {
                "kind": "abandon_interrupted_run",
                "subject": item.subject,
                "path": marker.relative_to(repo_root).as_posix(),
            }
        )

    for item in items:
        if item.kind is not ReconcileKind.PUBLICATION_FAILED or not item.repairable:
            continue
        record_path = repo_root / item.source
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        sha256 = record.get("sha256")
        publish_root = record.get("publish_root")
        if not isinstance(sha256, str) or not isinstance(publish_root, str) or not publish_root.strip():
            continue
        store = LocalArtifactStore(repo_root / ".factory" / "artifacts" / "objects", Path(publish_root))
        try:
            publication = store.publish(sha256)
        except (OSError, ValueError):
            continue
        updated_manifests = _rewrite_manifests_for_publication(
            repo_root, sha256, state=publication.state, uri=publication.uri
        )
        if publication.state in {"published", "queued", "failed"}:
            actions.append(
                {
                    "kind": "retry_publication",
                    "subject": sha256,
                    "path": record_path.relative_to(repo_root).as_posix(),
                    "manifests": ",".join(updated_manifests),
                }
            )

    for item in items:
        if item.kind is ReconcileKind.DISPOSABLE_INDEX and item.repairable:
            kb_dir = repo_root / "kb"
            if not kb_dir.exists():
                continue
            build_index(kb_dir)
            actions.append(
                {
                    "kind": "rebuild_disposable_index",
                    "subject": "kb/index.json",
                    "path": (kb_dir / "index.json").relative_to(repo_root).as_posix(),
                }
            )

    for item in items:
        if item.kind is ReconcileKind.LEGACY_REVIEW and item.repairable:
            migrated = _migrate_legacy_review(repo_root, item)
            if migrated is not None:
                actions.append(migrated)

    # Missing evidence and unattributed changes are intentionally untouched:
    # no deterministic operation can create their absent provenance.
    return actions


def reconcile(repo_root: Path, task_id: str | None = None) -> list[ReconcileItem]:
    evidence_runs = repo_root / "evidence" / "runs"
    evidence_dir = repo_root / "evidence"
    store = LocalArtifactStore(repo_root / ".factory" / "artifacts" / "objects")
    items: list[ReconcileItem] = []
    manifests: list[dict] = []
    manifests_by_task: dict[str, list[dict]] = {}
    manual_records_by_task: dict[str, list[dict]] = {}

    try:
        manual_records = list_historical_records(repo_root, evidence_dir)
    except ValueError as exc:
        items.append(
            ReconcileItem(
                ReconcileKind.MISSING_EVIDENCE,
                "historical-records",
                f"invalid historical record: {exc}",
                False,
                "evidence/records",
            )
        )
    else:
        for record in manual_records:
            manual_records_by_task.setdefault(record["task_id"], []).append(record)

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
        if (
            task.status == "done"
            and not manifests_by_task.get(task.id)
            and not manual_records_by_task.get(task.id)
        ):
            items.append(
                ReconcileItem(
                    ReconcileKind.MISSING_EVIDENCE,
                    task.id,
                    "completed task has no validated evidence manifest or manual record",
                    False,
                    task.path.relative_to(repo_root).as_posix(),
                )
            )

    items.extend(_publication_queue_items(repo_root))
    items.extend(_manifest_publication_items(repo_root, manifests))

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
        if identified and isinstance(value, dict):
            manifest_path = evidence_runs / f"{value['run_id']}.json"
            try:
                legacy_manifest = load_run_manifest(manifest_path)
            except (OSError, ValueError, json.JSONDecodeError):
                legacy_manifest = None
            source = path.relative_to(repo_root).as_posix()
            if legacy_manifest is not None and any(
                isinstance(review, dict) and review.get("source") == source
                for review in legacy_manifest.get("reviews", [])
            ):
                continue
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

    items.extend(_kb_index_items(repo_root))

    return sorted(items, key=lambda item: (item.kind.value, item.subject, item.source, item.detail))
