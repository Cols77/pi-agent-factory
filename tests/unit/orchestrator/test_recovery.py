from __future__ import annotations

import json

import pytest

from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.journal import RunCheckpoint
from factory.orchestrator.recovery import (
    RecoveryState,
    abandon_run,
    assess_recovery,
)

pytestmark = pytest.mark.unit


def checkpoint(**changes) -> RunCheckpoint:
    values = {
        "schema_version": 1,
        "run_id": "run-1",
        "task_id": "T-001",
        "node": "validation",
        "attempt": 1,
        "remaining": {"dev": 2},
        "start_commit": "a" * 40,
        "head_commit": "a" * 40,
        "worktree_fingerprint": "f" * 64,
        "patch_path": None,
        "completed": [],
        "agent_sessions": {},
        "pending_human_round": None,
        "artifacts": [],
        "interruption": "process_exit",
    }
    values.update(changes)
    return RunCheckpoint(**values)


def test_matching_head_and_worktree_are_resumable(tmp_path):
    result = assess_recovery(tmp_path, checkpoint(), FakeGitOps(head="a" * 40))
    assert result.state is RecoveryState.RESUMABLE
    assert "resume" in result.actions


def test_completed_run_is_not_resumed(tmp_path):
    result = assess_recovery(
        tmp_path, checkpoint(node="closed"), FakeGitOps(head="a" * 40)
    )
    assert result.state is RecoveryState.COMPLETE


def test_missing_start_commit_is_inspect_only(tmp_path):
    result = assess_recovery(tmp_path, checkpoint(), FakeGitOps(head="b" * 40))
    # FakeGitOps only resolves its configured head; the baseline is unavailable.
    assert result.state is RecoveryState.INSPECT_ONLY
    assert "start commit" in result.reasons[0]


def test_changed_head_is_a_conflict(tmp_path):
    fake = FakeGitOps(head="a" * 40)
    cp = checkpoint(head_commit="b" * 40)
    result = assess_recovery(tmp_path, cp, fake)
    assert result.state is RecoveryState.CONFLICT
    assert "HEAD changed" in result.reasons[0]


def test_cleanly_applicable_saved_patch_can_be_restored(tmp_path):
    patch = tmp_path / "checkpoint.patch"
    patch.write_bytes(b"patch")
    fake = FakeGitOps(head="a" * 40)
    fake.fingerprint = "changed"
    result = assess_recovery(
        tmp_path,
        checkpoint(patch_path="checkpoint.patch"),
        fake,
    )
    assert result.state is RecoveryState.RESUMABLE
    assert result.actions[0] == "restore-patch"


def test_missing_checkpoint_artifact_is_inspect_only(tmp_path):
    result = assess_recovery(
        tmp_path,
        checkpoint(artifacts=["missing.log"]),
        FakeGitOps(head="a" * 40),
    )
    assert result.state is RecoveryState.INSPECT_ONLY


def test_changed_worktree_without_applicable_patch_is_conflict(tmp_path):
    fake = FakeGitOps(head="a" * 40)
    fake.fingerprint = "changed"
    result = assess_recovery(tmp_path, checkpoint(), fake)
    assert result.state is RecoveryState.CONFLICT


def test_abandonment_is_atomic_reasoned_and_keeps_checkpoint(tmp_path):
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text("{}", encoding="utf-8")
    path = abandon_run(tmp_path, "superseded by manual recovery")
    marker = json.loads(path.read_text(encoding="utf-8"))
    assert marker["reason"] == "superseded by manual recovery"
    assert len(marker["checkpoint_sha256"]) == 64
    assert checkpoint_path.exists()
    assert not path.with_name(path.name + ".tmp").exists()


def test_abandonment_is_idempotent_only_for_the_same_reason(tmp_path):
    first = abandon_run(tmp_path, "superseded")
    before = first.read_bytes()
    assert abandon_run(tmp_path, "superseded") == first
    assert first.read_bytes() == before
    with pytest.raises(ValueError, match="different reason"):
        abandon_run(tmp_path, "other")


def test_abandonment_requires_a_reason(tmp_path):
    with pytest.raises(ValueError, match="must not be blank"):
        abandon_run(tmp_path, "  ")


def test_tracked_diff_match_with_untracked_drift_is_resumable_with_warning(tmp_path):
    """KB-0004: factory scratch churn used to flip the full fingerprint into a
    hard CONFLICT. When HEAD matches and the tracked diff still matches, an
    untracked drift is a warning, not a refusal."""
    fake = FakeGitOps(head="a" * 40)
    fake.fingerprint = "changed-full"
    fake.tracked_fp = "t" * 64
    fake.untracked = {"new.bin": "u1"}
    fake.sidecar = {"new.bin": "u0"}
    cp = checkpoint(tracked_fingerprint="t" * 64, patch_path="checkpoint.patch")

    result = assess_recovery(tmp_path, cp, fake)

    assert result.state is RecoveryState.RESUMABLE
    assert "resume" in result.actions
    assert any("tracked diff still matches" in reason for reason in result.reasons)
    assert any("untracked files changed" in reason for reason in result.reasons)


def test_tracked_diff_match_without_untracked_drift_is_resumable(tmp_path):
    fake = FakeGitOps(head="a" * 40)
    fake.fingerprint = "changed-full"
    fake.tracked_fp = "t" * 64
    fake.untracked = {}
    fake.sidecar = {}
    cp = checkpoint(tracked_fingerprint="t" * 64, patch_path="checkpoint.patch")

    result = assess_recovery(tmp_path, cp, fake)

    assert result.state is RecoveryState.RESUMABLE
    assert not any("untracked files changed" in reason for reason in result.reasons)


def test_old_checkpoint_without_tracked_fingerprint_falls_back_to_patch_bytes(tmp_path):
    """Schema v1 checkpoints predate tracked_fingerprint; the tracked-diff
    comparison must fall back to byte-equality with the saved patch."""
    patch = tmp_path / "checkpoint.patch"
    patch.write_bytes(b"recorded-diff")
    fake = FakeGitOps(head="a" * 40)
    fake.fingerprint = "changed-full"
    fake.worktree_diff_result = b"recorded-diff"
    cp = checkpoint(patch_path="checkpoint.patch")  # no tracked_fingerprint

    result = assess_recovery(tmp_path, cp, fake)

    assert result.state is RecoveryState.RESUMABLE


def test_old_checkpoint_with_diverged_tracked_diff_is_conflict(tmp_path):
    patch = tmp_path / "checkpoint.patch"
    patch.write_bytes(b"recorded-diff")

    class Diverged(FakeGitOps):
        def check_patch(self, repo_root, path):
            return False  # patch does not apply against the diverged tree

    fake = Diverged(head="a" * 40)
    fake.fingerprint = "changed-full"
    fake.worktree_diff_result = b"different-diff"
    cp = checkpoint(patch_path="checkpoint.patch")

    result = assess_recovery(tmp_path, cp, fake)

    assert result.state is RecoveryState.CONFLICT
    assert "restart" in result.actions
    assert "preserve-external-edits" in result.actions
