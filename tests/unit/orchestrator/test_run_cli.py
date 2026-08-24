from __future__ import annotations

import inspect
import json
import re
import subprocess

import pytest

from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.journal import RunCheckpoint, RunJournal
from factory.orchestrator.run_cli import load_current_checkpoint, main

pytestmark = pytest.mark.unit


def checkpoint(run_id: str = "run-1", **changes) -> RunCheckpoint:
    values = {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": "T-001",
        "node": "validation",
        "attempt": 1,
        "remaining": {},
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


def write(repo, cp):
    RunJournal(repo / "sessions" / ".factory-runs" / "by-session" / cp.run_id).checkpoint(cp)


def test_current_returns_newest_noncomplete_checkpoint(tmp_path, capsys):
    write(tmp_path, checkpoint("run-a"))
    write(tmp_path, checkpoint("run-b", node="closed"))
    assert load_current_checkpoint(tmp_path).run_id == "run-a"
    assert main(["current", "--repo", str(tmp_path), "--json"], git_ops=FakeGitOps(head="a" * 40)) == 0
    assert json.loads(capsys.readouterr().out)["checkpoint"]["run_id"] == "run-a"


def test_current_is_empty_after_reasoned_abandonment(tmp_path, capsys):
    write(tmp_path, checkpoint())
    assert main(
        ["abandon", "run-1", "--reason", "superseded", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 0
    capsys.readouterr()
    assert load_current_checkpoint(tmp_path) is None


def test_inspect_is_read_only_and_structured(tmp_path, capsys):
    write(tmp_path, checkpoint())
    assert main(["inspect", "run-1", "--repo", str(tmp_path), "--json"], git_ops=FakeGitOps(head="a" * 40)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["assessment"]["state"] == "resumable"
    assert not (tmp_path / "sessions" / ".factory-runs" / "by-session" / "run-1" / "abandoned.json").exists()


def test_resume_invokes_callback_only_when_resumable(tmp_path, capsys):
    write(tmp_path, checkpoint())
    resumed = []
    assert main(
        ["resume", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
        resume_callback=lambda cp: resumed.append(cp.run_id),
    ) == 0
    assert resumed == ["run-1"]
    assert json.loads(capsys.readouterr().out)["resumed"] is True


def test_resume_restores_a_cleanly_applicable_saved_patch_before_callback(tmp_path, capsys):
    write(tmp_path, checkpoint(patch_path="checkpoint.patch"))
    (tmp_path / "checkpoint.patch").write_bytes(b"patch")

    class RestoringFake(FakeGitOps):
        def __init__(self):
            super().__init__(head="a" * 40)
            self.fingerprint = "changed"
            self.restored = False

        def restore_patch(self, repo_root, path):
            self.restored = True
            self.fingerprint = "f" * 64

    fake = RestoringFake()
    resumed = []
    assert main(
        ["resume", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=fake,
        resume_callback=lambda cp: resumed.append(cp.run_id),
    ) == 0
    assert fake.restored is True
    assert resumed == ["run-1"]


def test_resume_conflict_and_inspect_only_exit_codes(tmp_path, capsys):
    write(tmp_path, checkpoint(head_commit="b" * 40))
    assert main(
        ["resume", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 3
    capsys.readouterr()
    write(tmp_path, checkpoint(start_commit="missing"))
    assert main(
        ["resume", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 4


def test_resume_refuses_incompatible_repository_state_without_callback(tmp_path, capsys):
    write(tmp_path, checkpoint(head_commit="b" * 40))
    resumed: list[str] = []
    assert main(
        ["resume", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
        resume_callback=lambda cp: resumed.append(cp.run_id),
    ) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["assessment"]["state"] == "conflict"
    assert resumed == []


def test_missing_and_invalid_run_ids_are_operational_errors(tmp_path, capsys):
    assert main(["inspect", "../escape", "--repo", str(tmp_path), "--json"]) == 2
    assert "invalid run id" in json.loads(capsys.readouterr().out)["error"]
    assert main(["inspect", "gone", "--repo", str(tmp_path), "--json"]) == 2


def test_restart_abandons_and_offers_the_rerun_command(tmp_path, capsys):
    write(tmp_path, checkpoint())
    assert main(
        ["restart", "run-1", "--reason", "fix applied externally", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["restarted"] is True
    assert "factory run --task T-001 --force" in payload["next"]
    # The old checkpoint must no longer block preflight.
    assert load_current_checkpoint(tmp_path) is None
    marker = json.loads(
        (tmp_path / "sessions" / ".factory-runs" / "by-session" / "run-1" / "abandoned.json").read_text(
            encoding="utf-8"
        )
    )
    assert "fix applied externally" in marker["reason"]


def test_restart_invokes_callback_with_fresh_checkpoint_at_head(tmp_path, capsys):
    write(tmp_path, checkpoint())
    seen = []
    assert main(
        ["restart", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="b" * 40),
        resume_callback=lambda cp: seen.append(cp),
    ) == 0
    fresh = seen[0]
    assert fresh.node == "context-gather"
    assert fresh.start_commit == "b" * 40  # current HEAD, not the old start commit
    assert fresh.completed == []
    assert fresh.patch_path is None


def test_restart_refuses_a_completed_run(tmp_path, capsys):
    write(tmp_path, checkpoint(node="closed"))
    assert main(
        ["restart", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 2
    assert "already complete" in json.loads(capsys.readouterr().out)["error"]


def test_preserve_external_edits_restores_and_resumes_without_clobbering(tmp_path, capsys):
    """KB-0004 action: stash/restore user-dirty files around resume. The patch is
    restored, every pre-dirty file keeps its bytes, and the run resumes."""
    write(tmp_path, checkpoint(patch_path="checkpoint.patch"))
    (tmp_path / "checkpoint.patch").write_bytes(b"patch")

    class PreservingFake(FakeGitOps):
        def __init__(self):
            super().__init__(head="a" * 40)
            self.fingerprint = "changed"
            self.tracked_fp = "changed"
            self.restored = False
            self.preserved = {"notes.txt": "d" * 64}

        def restore_patch(self, repo_root, path):
            self.restored = True

        def dirty_snapshot(self, repo_root):
            return dict(self.preserved)

    fake = PreservingFake()
    resumed = []
    assert main(
        ["preserve-external-edits", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=fake,
        resume_callback=lambda cp: resumed.append(cp.run_id),
    ) == 0
    assert fake.restored is True
    assert resumed == ["run-1"]


def test_preserve_external_edits_refuses_when_patch_conflicts(tmp_path, capsys):
    write(tmp_path, checkpoint(patch_path="checkpoint.patch"))

    class ConflictingFake(FakeGitOps):
        def __init__(self):
            super().__init__(head="a" * 40)
            self.fingerprint = "changed"

        def check_patch(self, repo_root, path):
            return False

    assert main(
        ["preserve-external-edits", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=ConflictingFake(),
    ) == 3
    payload = json.loads(capsys.readouterr().out)
    assert "conflicts with external edits" in payload["error"]


def test_preserve_external_edits_refuses_when_head_moved(tmp_path, capsys):
    write(tmp_path, checkpoint(head_commit="b" * 40, patch_path="checkpoint.patch"))
    (tmp_path / "checkpoint.patch").write_bytes(b"patch")
    assert main(
        ["preserve-external-edits", "run-1", "--repo", str(tmp_path), "--json"],
        git_ops=FakeGitOps(head="a" * 40),
    ) == 3
    payload = json.loads(capsys.readouterr().out)
    assert "use `restart`" in payload["error"]


def test_doctor_reports_oversized_checkpoint_and_dirty_tracked(tmp_path, capsys):
    run_dir = tmp_path / "sessions" / ".factory-runs" / "by-session" / "run-big"
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_bytes(b"x" * (10 * 1024 * 1024 + 1))

    from factory.orchestrator.run_cli import run_doctor

    report = run_doctor(tmp_path)
    codes = [f["code"] for f in report["findings"]]
    assert "run_oversized" in codes
    assert report["ok"] is False
    assert main(["doctor", "--repo", str(tmp_path), "--json"]) == 3
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


def test_doctor_flags_embedded_repo_and_reserved_name(tmp_path, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    embedded = tmp_path / "vendor"
    embedded.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=embedded, check=True)

    from factory.orchestrator.run_cli import run_doctor
    from unittest.mock import patch

    report = run_doctor(tmp_path)
    assert any(f["code"] == "embedded_repo" for f in report["findings"])

    (tmp_path / "a.txt").write_text("y\n", encoding="utf-8")
    with patch(
        "factory.orchestrator.git_ops._find_reserved_name_files",
        return_value=["nul"],
    ):
        report = run_doctor(tmp_path)
    assert any(f["code"] == "reserved_name" for f in report["findings"])
    assert any(f["code"] == "dirty_tracked" for f in report["findings"])


def test_doctor_ok_on_clean_repo(tmp_path, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)

    assert main(["doctor", "--repo", str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["findings"] == []


def test_doctor_stays_scoped_to_run_recovery_not_bootstrap_diagnostics(tmp_path):
    """Regression guard against confusing the two unrelated "doctor"s.

    factory.orchestrator.run_cli's `doctor` subcommand (this module,
    run-recovery diagnostics: interrupted runs, oversized run dirs, embedded
    repos, reserved names, dirty tracked files) is completely unrelated to
    the pi-ext `/factory-doctor` command (now `/factory-selfcheck`, a Pi
    extension command diagnosing project bootstrap: profile freshness, the
    AGENTS.md managed block, essential tools, subagent metadata). This test
    pins run_doctor's scope so a future change to one does not silently grow
    into the other's territory.
    """
    from factory.orchestrator.run_cli import run_doctor

    source = inspect.getsource(run_doctor)
    lowered = source.lower()
    forbidden_terms = [
        "agents.md",
        "profile",
        "subagent",
        "tools aligned",
        "tools_aligned",
        "code index",
        "code_index",
        "bootstrap",
    ]
    for term in forbidden_terms:
        assert term not in lowered, (
            f"run_doctor source mentions {term!r}, which reads as bootstrap-"
            "diagnostic content bleeding in from the unrelated /factory-selfcheck "
            "(pi-ext) command; run_doctor must stay run-recovery only"
        )

    # The closed set of finding codes run_doctor can ever emit today. Growing
    # this set with more run-recovery codes is fine; a code drawn from the
    # forbidden vocabulary above would be scope creep this test should catch.
    known_codes = {
        "run_oversized",
        "embedded_repo",
        "reserved_name",
        "dirty_tracked",
        "interrupted_run",
    }
    emitted_codes = set(re.findall(r'"code":\s*"([a-z_]+)"', source))
    assert emitted_codes == known_codes

    # End-to-end sanity check: on a clean repo the report shape itself stays
    # minimal (ok/findings/summary) -- no bootstrap-shaped keys.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    report = run_doctor(tmp_path)
    assert set(report.keys()) == {"findings", "ok", "summary"}
