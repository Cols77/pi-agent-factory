from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess

import pytest
from factory.orchestrator.git_ops import FakeGitOps, SubprocessGitOps

pytestmark = pytest.mark.unit


def _init_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_subprocess_git_ops_head_commit_matches_rev_parse(tmp_path):
    repo = _init_repo(tmp_path)
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert SubprocessGitOps().head_commit(repo) == expected


def test_subprocess_git_ops_commit_all_returns_false_when_nothing_to_commit(tmp_path):
    repo = _init_repo(tmp_path)
    assert SubprocessGitOps().commit_all(repo, "no-op") is False


def test_subprocess_git_ops_commit_all_commits_uncommitted_changes(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    before = SubprocessGitOps().head_commit(repo)
    committed = SubprocessGitOps().commit_all(repo, "review: address direct edits during human review")
    assert committed is True
    after = SubprocessGitOps().head_commit(repo)
    assert after != before
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert log == "review: address direct edits during human review"


def test_fake_git_ops_records_commit_messages_only_when_has_uncommitted():
    clean = FakeGitOps(head="abc123", has_uncommitted=False)
    assert clean.head_commit(None) == "abc123"
    assert clean.commit_all(None, "msg") is False
    assert clean.commit_messages == []

    dirty = FakeGitOps(head="def456", has_uncommitted=True)
    assert dirty.commit_all(None, "msg") is True
    assert dirty.commit_messages == ["msg"]


def test_subprocess_git_ops_changed_files_lists_modified_paths(tmp_path):
    repo = _init_repo(tmp_path)
    start = SubprocessGitOps().head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    (repo / "b.txt").write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "change"], cwd=repo, check=True)

    files = SubprocessGitOps().changed_files(repo, start)

    assert sorted(files) == ["a.txt", "b.txt"]


def test_subprocess_git_ops_changed_files_empty_when_nothing_changed(tmp_path):
    repo = _init_repo(tmp_path)
    start = SubprocessGitOps().head_commit(repo)
    assert SubprocessGitOps().changed_files(repo, start) == []


def test_subprocess_git_ops_changed_files_sees_uncommitted_changes(tmp_path):
    # Regression test: review's changed_files call can run before dev's work
    # is committed. A single-ref `git diff <start_commit>` (no `..HEAD`)
    # compares start_commit to the working tree, so uncommitted modifications
    # to tracked files must show up here -- unlike the old
    # `{start_commit}..HEAD` form, which only ever saw committed history and
    # would silently return [].
    repo = _init_repo(tmp_path)
    start = SubprocessGitOps().head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    # Deliberately no `git add`/`git commit` here.

    files = SubprocessGitOps().changed_files(repo, start)

    assert files == ["a.txt"]


def test_fake_git_ops_returns_scripted_changed_files():
    fake = FakeGitOps(changed_files_result=["src/a.py", "src/b.py"])
    assert fake.changed_files(None, "abc123") == ["src/a.py", "src/b.py"]


def test_fake_git_ops_changed_files_defaults_to_empty():
    assert FakeGitOps().changed_files(None, "abc123") == []


def test_commit_paths_does_not_stage_or_commit_unrelated_files(tmp_path):
    repo = _init_repo(tmp_path)
    wanted = repo / "evidence" / "runs" / "run-1.json"
    wanted.parent.mkdir(parents=True)
    wanted.write_text("{}", encoding="utf-8")
    unrelated = repo / "unrelated.txt"
    unrelated.write_text("leave me", encoding="utf-8")

    assert SubprocessGitOps().commit_paths(repo, [wanted], "evidence: record run") is True

    status = subprocess.run(
        ["git", "status", "--short"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert "unrelated.txt" in status
    assert "evidence/runs/run-1.json" not in status
    committed = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert committed == ["evidence/runs/run-1.json"]


def test_commit_paths_refuses_a_path_outside_repository(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = _init_repo(repo_dir)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="outside repository"):
        SubprocessGitOps().commit_paths(repo, [outside], "not allowed")


def test_binary_diff_and_changed_files_between_capture_committed_range(tmp_path):
    repo = _init_repo(tmp_path)
    start = SubprocessGitOps().head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    assert SubprocessGitOps().commit_all(repo, "change") is True
    end = SubprocessGitOps().head_commit(repo)

    assert b"+two" in SubprocessGitOps().binary_diff(repo, start, end)
    assert SubprocessGitOps().changed_files_between(repo, start, end) == ["a.txt"]


def test_worktree_fingerprint_covers_tracked_and_untracked_bytes_not_mtime(tmp_path):
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    (repo / "new.bin").write_bytes(b"\x00\x01")
    first = ops.worktree_fingerprint(repo, start)

    os.utime(repo / "a.txt", (1_700_000_000, 1_700_000_000))
    os.utime(repo / "new.bin", (1_700_000_000, 1_700_000_000))
    assert ops.worktree_fingerprint(repo, start) == first

    (repo / "new.bin").write_bytes(b"\x00\x02")
    assert ops.worktree_fingerprint(repo, start) != first


def test_write_patch_captures_tracked_diff_and_untracked_sidecar(tmp_path):
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    (repo / "new.bin").write_bytes(b"\x00\x01")
    patch = repo / "sessions" / "checkpoint.patch"

    assert ops.write_patch(repo, start, patch) == patch
    assert b"+two" in patch.read_bytes()
    sidecar = json.loads(
        patch.with_suffix(".patch.untracked.json").read_text(encoding="utf-8")
    )
    assert sidecar["files"][0]["path"] == "new.bin"
    assert base64.b64decode(sidecar["files"][0]["data"]) == b"\x00\x01"


def test_restore_patch_recovers_tracked_and_untracked_bytes(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / ".gitignore").write_text("sessions/\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "ignore recovery"], cwd=repo, check=True)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    (repo / "new.bin").write_bytes(b"\x00\x01")
    expected = ops.worktree_fingerprint(repo, start)
    patch = repo / "sessions" / "checkpoint.patch"
    ops.write_patch(repo, start, patch)

    subprocess.run(["git", "reset", "--hard", start], cwd=repo, check=True)
    (repo / "new.bin").unlink()
    assert ops.check_patch(repo, patch) is True
    ops.restore_patch(repo, patch)
    assert (repo / "a.txt").read_text(encoding="utf-8") == "two\n"
    assert (repo / "new.bin").read_bytes() == b"\x00\x01"
    assert ops.worktree_fingerprint(repo, start) == expected


def test_write_patch_rejects_recovery_data_outside_repository(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = _init_repo(repo_path)
    ops = SubprocessGitOps()
    with pytest.raises(ValueError, match="inside the repository"):
        ops.write_patch(repo, ops.head_commit(repo), tmp_path / "outside.patch")


def test_check_patch_distinguishes_clean_and_conflicting_worktrees(tmp_path):
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    patch = tmp_path / "checkpoint.patch"
    ops.write_patch(repo, start, patch)
    subprocess.run(["git", "reset", "--hard", start], cwd=repo, check=True)
    assert ops.check_patch(repo, patch) is True

    (repo / "a.txt").write_text("conflicting\n", encoding="utf-8")
    assert ops.check_patch(repo, patch) is False


def test_subprocess_git_ops_commit_all_survives_git_failure(tmp_path):
    # A git failure (e.g. a Windows reserved-name path git refuses with exit
    # 128) must NOT crash the caller -- commit_all returns False and warns,
    # never raises. Regression: an already-done human-review approve crashed the
    # whole orchestrator on `git add -A` and stranded the approve.
    import subprocess as _sp
    from unittest.mock import patch
    from factory.orchestrator.git_ops import SubprocessGitOps

    ops = SubprocessGitOps()

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "add"]:
            raise _sp.CalledProcessError(128, args)
        return _sp.CompletedProcess(args, 0)

    with patch("factory.orchestrator.git_ops.subprocess.run", side_effect=fake_run):
        result = ops.commit_all(tmp_path, "msg")  # must not raise
    assert result is False


def test_write_patch_never_inlines_the_factorys_own_scratch_output(tmp_path):
    """A sidecar must never embed a previous sidecar.

    write_patch writes `<checkpoint>.patch.untracked.json` into
    sessions/.factory-runs/, which is untracked in a target repo. Enumerating
    untracked files therefore picked up every earlier sidecar and inlined it,
    base64-encoded, into the new one. Observed in cool_physical_ai_project:
    768MB -> 1.8GB -> 4.3GB -> 10GB across four checkpoints (~2.3x each), then
    MemoryError in json.dumps -- which killed the run before
    finalize_run_evidence, so no evidence manifest was ever written.
    """
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)

    # A previous run's scratch output, exactly where the orchestrator puts it.
    checkpoints = repo / "sessions" / ".factory-runs" / "by-session" / "r1" / "checkpoints"
    checkpoints.mkdir(parents=True)
    (checkpoints / "000001.patch.untracked.json").write_text(
        json.dumps({"files": [{"path": "x", "data": "QQ==", "mode": 420}]}), encoding="utf-8"
    )
    (repo / "sessions" / ".factory-transcripts").mkdir(parents=True)
    (repo / "sessions" / ".factory-transcripts" / "big.log").write_text("t\n", encoding="utf-8")
    (repo / ".factory" / "artifacts").mkdir(parents=True)
    (repo / ".factory" / "artifacts" / "blob").write_bytes(b"\x00")
    # A genuine untracked source file still must be captured.
    (repo / "new.bin").write_bytes(b"\x00\x01")

    patch = checkpoints / "000002.patch"
    ops.write_patch(repo, start, patch)
    sidecar = json.loads(
        patch.with_suffix(".patch.untracked.json").read_text(encoding="utf-8")
    )
    paths = [p["path"] for p in sidecar["files"]]

    assert "new.bin" in paths, "real untracked work must still be captured"
    assert not [p for p in paths if ".factory-runs" in p], f"sidecar embedded itself: {paths}"
    assert not [p for p in paths if ".factory-transcripts" in p], f"transcripts inlined: {paths}"
    assert not [p for p in paths if ".factory/artifacts" in p.replace("\\", "/")], (
        f"artifact store inlined: {paths}"
    )


def test_ensure_factory_ignores_is_additive_and_idempotent(tmp_path):
    """A target repo does not inherit the factory's .gitignore, and commit_all
    runs `git add -A` -- so unignored run output can be committed into the
    user's repository. Adding the entries must never rewrite what is there."""
    from factory.orchestrator.git_ops import ensure_factory_ignores

    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".venv/\n", encoding="utf-8")

    assert ensure_factory_ignores(tmp_path) is True
    text = gitignore.read_text(encoding="utf-8")
    assert text.startswith(".venv/\n"), "existing entries must be preserved verbatim"
    for line in (
        "sessions/.factory-runs/",
        "sessions/.factory-transcripts/",
        ".factory/",
        "sessions/latest.md",
        "sessions/.factory-*",
    ):
        assert line in text

    # Second call is a no-op: no duplicate block, no rewrite.
    assert ensure_factory_ignores(tmp_path) is False
    assert gitignore.read_text(encoding="utf-8") == text


def test_ensure_factory_ignores_creates_the_file_when_absent(tmp_path):
    from factory.orchestrator.git_ops import ensure_factory_ignores

    assert ensure_factory_ignores(tmp_path) is True
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith("# factory scratch")
    assert not text.startswith("\n"), "no leading blank line on a fresh file"


def test_write_patch_skips_untracked_directory_nested_repo(tmp_path):
    """A nested git worktree (reported by git as an untracked *directory*) must
    not crash patch recording nor appear in the sidecar as a file. Regression for
    the PermissionError from read_bytes() on a directory (e.g. Windows)."""
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "new.bin").write_bytes(b"\x00\x01")
    snap = repo / "snap"
    snap.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=snap, check=True)
    (snap / "inner.txt").write_text("x\n", encoding="utf-8")

    patch = repo / "checkpoint.patch"
    assert ops.write_patch(repo, start, patch) == patch  # must not raise
    sidecar = json.loads(
        patch.with_suffix(".patch.untracked.json").read_text(encoding="utf-8")
    )
    assert all(p["path"] != "snap" for p in sidecar["files"])
    assert "new.bin" in [p["path"] for p in sidecar["files"]]
    # Nested-repo directory is also excluded from the fingerprint.
    ops.worktree_fingerprint(repo, start)


def _commit_file(repo, name, text):
    (repo / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", name], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", f"add {name}"], cwd=repo, check=True)


def _track_scratch(repo):
    """Track the factory's own scratch files, the way a real target repo does."""
    for name in ("sessions/latest.md", "sessions/.factory-status.json"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("v0\n", encoding="utf-8")
        _commit_file(repo, name, "v0\n")


def test_fingerprint_ignores_factory_scratch_tracked_churn(tmp_path):
    """KB-0004: the worktree fingerprint must not flip on the factory's own
    mid-run rewrites of tracked scratch files (sessions/latest.md,
    sessions/.factory-*.json), which used to send resume into CONFLICT even
    though HEAD and the real work matched the checkpoint."""
    repo = _init_repo(tmp_path)
    _track_scratch(repo)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    baseline = ops.worktree_fingerprint(repo, start)

    (repo / "sessions" / "latest.md").write_text("factory rewrite\n", encoding="utf-8")
    (repo / "sessions" / ".factory-status.json").write_text("{\"state\":\"running\"}\n", encoding="utf-8")
    (repo / "sessions" / ".factory-review-surface.json").write_text("{}\n", encoding="utf-8")

    assert ops.worktree_fingerprint(repo, start) == baseline
    assert ops.tracked_fingerprint(repo, start) == ops.worktree_fingerprint(
        repo, start, include_untracked=False
    )

    # Real work must still flip it.
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    assert ops.worktree_fingerprint(repo, start) != baseline


def test_fingerprint_untracked_churn_flips_only_full_not_tracked(tmp_path):
    """Resume tolerance: a new untracked file flips the full fingerprint but not
    the tracked-only fingerprint, so a checkpoint whose tracked state matches
    can still be classified resumable."""
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    tracked = ops.tracked_fingerprint(repo, start)
    full = ops.worktree_fingerprint(repo, start)

    (repo / "unrelated.bin").write_bytes(b"\x00\x01")

    assert ops.tracked_fingerprint(repo, start) == tracked
    assert ops.worktree_fingerprint(repo, start) != full


def test_write_patch_excludes_tracked_scratch_from_patch_bytes(tmp_path):
    repo = _init_repo(tmp_path)
    _track_scratch(repo)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    (repo / "sessions" / "latest.md").write_text("factory rewrite\n", encoding="utf-8")
    patch = repo / "sessions" / "checkpoint.patch"

    ops.write_patch(repo, start, patch)
    raw = patch.read_bytes()

    assert b"+two" in raw
    assert b"latest.md" not in raw, "tracked scratch churn leaked into the patch"


def test_commit_all_never_commits_factory_scratch_tracked_writes(tmp_path):
    """A run's commit must not carry the factory's own writes to tracked
    scratch files under the task's message."""
    repo = _init_repo(tmp_path)
    _track_scratch(repo)
    ops = SubprocessGitOps()
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    (repo / "sessions" / "latest.md").write_text("factory rewrite\n", encoding="utf-8")

    assert ops.commit_all(repo, "T-999: agent work") is True
    committed = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "a.txt" in committed
    assert "sessions/latest.md" not in committed, f"committed factory scratch: {committed}"
    assert "sessions/.factory-status.json" not in committed


def test_commit_all_raises_commit_all_error_on_invalid_path_refusal(tmp_path):
    """KB-0004: an `invalid path 'nul'`-style staging failure must surface as a
    run-blocking CommitAllError with remediation, not a silent
    "completing without a commit" -- the failure mode that let a broken tree
    keep producing checkpoints nobody noticed were uncommitted."""
    from factory.orchestrator.git_ops import CommitAllError
    from unittest.mock import patch

    repo = _init_repo(tmp_path)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    ops = SubprocessGitOps()

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "add"]:
            raise subprocess.CalledProcessError(
                128, args, output=b"", stderr=b"error: invalid path 'nul'\nfatal: adding files failed"
            )
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    with patch("factory.orchestrator.git_ops.subprocess.run", side_effect=fake_run):
        with pytest.raises(CommitAllError, match="refused to stage"):
            ops.commit_all(repo, "T-999: agent work")


def test_commit_all_raises_when_reserved_name_file_present(tmp_path):
    """A reserved-name path is detected even when git's stderr is empty (the
    Windows `nul` device-interception case is not reliably reported; on Windows
    the file cannot even physically exist -- git's readdir reports it as a
    phantom and `git add` refuses it)."""
    from factory.orchestrator.git_ops import CommitAllError

    repo = _init_repo(tmp_path)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    ops = SubprocessGitOps()

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "add"]:
            raise subprocess.CalledProcessError(128, args)
        if args[:2] == ["git", "ls-files"]:
            return subprocess.CompletedProcess(args, 0, stdout=b"nul\x00", stderr=b"")
        if args[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(args, 0, stdout=b"!! nul\x00", stderr=b"")
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    from unittest.mock import patch

    with patch("factory.orchestrator.git_ops.subprocess.run", side_effect=fake_run):
        with pytest.raises(CommitAllError, match="refused to stage"):
            ops.commit_all(repo, "T-999: agent work")


def test_untracked_snapshot_and_sidecar_round_trip(tmp_path):
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "new.bin").write_bytes(b"\x00\x01\x02")
    (repo / "scratch.log").write_bytes(b"s")
    subprocess.run(["git", "check-ignore"], cwd=repo, capture_output=True)  # no-op
    repo.joinpath(".gitignore").write_text("scratch.log\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "ignore"], cwd=repo, check=True)

    snapshot = ops.untracked_snapshot(repo)
    assert snapshot == {"new.bin": hashlib.sha256(b"\x00\x01\x02").hexdigest()}

    patch = repo / "checkpoint.patch"
    ops.write_patch(repo, start, patch)
    assert ops.read_untracked_sidecar(patch) == snapshot


def test_read_untracked_sidecar_tolerates_old_sidecar_without_sha256(tmp_path):
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    patch = repo / "checkpoint.patch"
    patch.write_bytes(b"")
    patch.with_suffix(".patch.untracked.json").write_text(
        json.dumps({"files": [{"path": "new.bin", "data": "AAEC", "mode": 420}]}),
        encoding="utf-8",
    )
    assert ops.read_untracked_sidecar(patch) == {
        "new.bin": hashlib.sha256(b"\x00\x01\x02").hexdigest()
    }


def test_write_patch_skips_untracked_files_over_size_cap(tmp_path):
    from factory.orchestrator.git_ops import MAX_SIDECAR_FILE_BYTES

    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "giant.bin").write_bytes(b"\x00" * (MAX_SIDECAR_FILE_BYTES + 1))
    (repo / "small.bin").write_bytes(b"\x00\x01")
    patch = repo / "checkpoint.patch"

    ops.write_patch(repo, start, patch)
    sidecar = json.loads(
        patch.with_suffix(".patch.untracked.json").read_text(encoding="utf-8")
    )
    by_path = {item["path"]: item for item in sidecar["files"]}
    assert by_path["giant.bin"]["skipped"] is True
    assert by_path["giant.bin"]["reason"] == "too_large"
    assert "data" not in by_path["giant.bin"]
    assert by_path["small.bin"]["data"] == base64.b64encode(b"\x00\x01").decode("ascii")


def test_restore_patch_ignores_skipped_untracked_entries(tmp_path):
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    start = ops.head_commit(repo)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    patch = repo / "checkpoint.patch"
    ops.write_patch(repo, start, patch)  # real, applicable patch
    patch.with_suffix(".patch.untracked.json").write_text(
        json.dumps(
            {
                "files": [
                    {"path": "giant.bin", "size": 999, "skipped": True, "reason": "too_large"},
                    {"path": "small.bin", "data": "AAEC", "mode": 420},
                ]
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "reset", "--hard", start], cwd=repo, check=True)
    (repo / "small.bin").write_bytes(b"\x00\x01\x02")

    ops.restore_patch(repo, patch)  # must not crash on the skipped entry
    assert (repo / "a.txt").read_text(encoding="utf-8") == "two\n"
    assert (repo / "small.bin").read_bytes() == b"\x00\x01\x02"
    assert not (repo / "giant.bin").exists()


def test_commit_all_leaves_untouched_preexisting_edits_alone(tmp_path):
    """A run must not commit the human's work-in-progress under its own message.

    `git add -A` swept everything dirty. Observed in cool_physical_ai_project:
    commit 3d1ab1b, titled "T-059: Implement the Common Planner Protocol",
    contained none of T-059's implementation and four unrelated task files the
    human was mid-edit on.

    Only files byte-identical to their run-start state are skipped -- if the
    agent touched a file, it is the run's work regardless of who dirtied it
    first, and dropping it would be worse than over-committing.
    """
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    _commit_file(repo, "wip.txt", "original\n")
    _commit_file(repo, "agent.txt", "original\n")

    # Human's uncommitted edit, present before the run starts.
    (repo / "wip.txt").write_text("human edit\n", encoding="utf-8")
    preserve = ops.dirty_snapshot(repo)
    assert "wip.txt" in preserve

    # The agent's work during the run.
    (repo / "agent.txt").write_text("agent edit\n", encoding="utf-8")

    assert ops.commit_all(repo, "T-999: agent work", preserve=preserve) is True
    committed = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "agent.txt" in committed
    assert "wip.txt" not in committed, f"committed the human's WIP: {committed}"
    # And the human's edit is still there, uncommitted.
    assert (repo / "wip.txt").read_text(encoding="utf-8") == "human edit\n"


def test_commit_all_still_commits_a_preexisting_file_the_agent_changed(tmp_path):
    """Dirty-at-start is not ownership. If the agent changed it too, it is the
    run's work and must be committed."""
    repo = _init_repo(tmp_path)
    ops = SubprocessGitOps()
    _commit_file(repo, "shared.txt", "original\n")

    (repo / "shared.txt").write_text("human edit\n", encoding="utf-8")
    preserve = ops.dirty_snapshot(repo)
    (repo / "shared.txt").write_text("human edit + agent edit\n", encoding="utf-8")

    assert ops.commit_all(repo, "T-999: agent work", preserve=preserve) is True
    committed = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "shared.txt" in committed
