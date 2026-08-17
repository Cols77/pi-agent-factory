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


def _tracked_diff_matches(
    repo_root: Path, checkpoint: RunCheckpoint, git_ops: GitOps
) -> bool:
    """True when the tracked diff still matches what the checkpoint recorded.

    Newer checkpoints record tracked_fingerprint directly. Older (schema v1)
    checkpoints have neither it nor the excludes in their fingerprint, so the
    comparison falls back to byte-equality of the current filtered diff against
    the saved patch -- the patch IS the tracked diff at checkpoint time."""
    if checkpoint.tracked_fingerprint is not None:
        return git_ops.tracked_fingerprint(repo_root, checkpoint.start_commit) == (
            checkpoint.tracked_fingerprint
        )
    if checkpoint.patch_path is None:
        return False
    patch = _repo_path(repo_root, checkpoint.patch_path)
    try:
        recorded = patch.read_bytes()
    except OSError:
        return False
    return bool(recorded) and git_ops.worktree_diff(repo_root, checkpoint.start_commit) == recorded


def _untracked_drifted(
    repo_root: Path, checkpoint: RunCheckpoint, git_ops: GitOps
) -> list[str]:
    """Untracked paths whose content differs from the checkpoint's sidecar.

    Only paths recorded by the checkpoint (or newly appeared since) count;
    missing sidecars or unreadable records mean "cannot tell", which reports no
    drift rather than a false alarm."""
    if checkpoint.patch_path is None:
        return []
    patch = _repo_path(repo_root, checkpoint.patch_path)
    recorded = git_ops.read_untracked_sidecar(patch)
    if not recorded:
        return []
    current = git_ops.untracked_snapshot(repo_root)
    drifted = [
        path
        for path, digest in recorded.items()
        if current.get(path) != digest
    ]
    drifted.extend(path for path in current if path not in recorded)
    return sorted(drifted)


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

    # Tolerant resume (KB-0004): when HEAD matches and the TRACKED diff still
    # matches the checkpoint, the run can continue even though untracked files
    # drifted (they are simply left in place) -- factory scratch churn used to
    # flip the full fingerprint into a hard CONFLICT with no continuation path.
    if _tracked_diff_matches(repo_root, checkpoint, git_ops):
        reasons = ["HEAD matches and the tracked diff still matches the checkpoint"]
        drifted = _untracked_drifted(repo_root, checkpoint, git_ops)
        if drifted:
            reasons.append(
                "untracked files changed since the checkpoint: " + ", ".join(drifted[:5])
                + ("..." if len(drifted) > 5 else "")
            )
        return RecoveryAssessment(
            RecoveryState.RESUMABLE,
            reasons,
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
