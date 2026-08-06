from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from factory.orchestrator.git_ops import GitOps
from factory.orchestrator.journal import RunCheckpoint


class RecoveryState(str, Enum):
    RESUMABLE = "resumable"
    INSPECT_ONLY = "inspect-only"
    CONFLICT = "conflict"
    COMPLETE = "complete"


@dataclass(frozen=True)
class RecoveryAssessment:
    state: RecoveryState
    reasons: list[str]
    actions: list[str]


def _repo_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def assess_recovery(
    repo_root: Path, checkpoint: RunCheckpoint, git_ops: GitOps
) -> RecoveryAssessment:
    if checkpoint.node in {"completed", "closed"}:
        return RecoveryAssessment(RecoveryState.COMPLETE, ["run is already complete"], ["inspect"])

    if not git_ops.commit_exists(repo_root, checkpoint.start_commit):
        return RecoveryAssessment(
            RecoveryState.INSPECT_ONLY,
            ["recorded start commit no longer resolves"],
            ["inspect", "abandon"],
        )

    missing_artifacts = [
        value for value in checkpoint.artifacts if not _repo_path(repo_root, value).exists()
    ]
    if missing_artifacts:
        return RecoveryAssessment(
            RecoveryState.INSPECT_ONLY,
            ["checkpoint artifact is missing: " + ", ".join(missing_artifacts)],
            ["inspect", "abandon"],
        )

    current_head = git_ops.head_commit(repo_root)
    if current_head != checkpoint.head_commit:
        return RecoveryAssessment(
            RecoveryState.CONFLICT,
            [f"HEAD changed from {checkpoint.head_commit} to {current_head}"],
            ["inspect", "preserve-external-edits", "restart", "abandon"],
        )

    current_fingerprint = git_ops.worktree_fingerprint(repo_root, checkpoint.start_commit)
    if current_fingerprint == checkpoint.worktree_fingerprint:
        return RecoveryAssessment(
            RecoveryState.RESUMABLE,
            ["HEAD and working tree match the checkpoint"],
            ["resume", "inspect", "abandon"],
        )

    if checkpoint.patch_path is not None:
        patch = _repo_path(repo_root, checkpoint.patch_path)
        if patch.exists() and git_ops.check_patch(repo_root, patch):
            return RecoveryAssessment(
                RecoveryState.RESUMABLE,
                ["working tree differs, but the saved patch applies cleanly"],
                ["restore-patch", "inspect", "abandon"],
            )

    return RecoveryAssessment(
        RecoveryState.CONFLICT,
        ["working tree differs from the checkpoint"],
        ["inspect", "preserve-external-edits", "restart", "abandon"],
    )


def abandon_run(run_dir: Path, reason: str) -> Path:
    reason = reason.strip()
    if not reason:
        raise ValueError("abandon reason must not be blank")
    path = run_dir / "abandoned.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("existing abandonment marker is corrupt") from exc
        if existing.get("reason") != reason:
            raise ValueError("run is already abandoned with a different reason")
        return path
    checkpoint_path = run_dir / "checkpoint.json"
    checkpoint_bytes = checkpoint_path.read_bytes() if checkpoint_path.exists() else b""
    marker = {
        "reason": reason,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checkpoint_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path
