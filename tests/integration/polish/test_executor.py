import subprocess
from pathlib import Path

import pytest

from factory.polish.executor import WorktreeIsolatedExecutor
from factory.polish.finding import Finding
from factory.polish.worker import RunOutcome

pytestmark = pytest.mark.integration


def _git(root, *a):
    subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)


def _repo(tmp_path) -> Path:
    root = tmp_path / "live"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "app.txt").write_text("v0", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")
    return root


def test_green_fix_fast_forwards_into_live(tmp_path):
    live = _repo(tmp_path)

    def fake_run(task_id, wt: Path) -> RunOutcome:
        # dev agent edits in the worktree
        (wt / "app.txt").write_text("v1-fixed", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-am", f"fix {task_id}"],
            check=True,
            capture_output=True,
        )
        return RunOutcome(ok=True)

    ex = WorktreeIsolatedExecutor(live, factory_run=fake_run)
    landed = ex.execute(Finding(usecase="sign-in", description="broken"))

    assert landed.status == "landed"
    # FF'd into the LIVE tree
    assert (live / "app.txt").read_text(encoding="utf-8") == "v1-fixed"
    # task rode in with the fix
    assert (live / "tasks" / f"{landed.task_id}.md").exists()
    # worktree cleaned up
    leftover = list((live / ".worktrees").glob("*")) if (live / ".worktrees").exists() else []
    assert leftover == []


def test_green_run_that_committed_nothing_is_not_landed(tmp_path):
    # Observed live: factory-run exited 0 without producing a dev commit, so the
    # only thing fast-forwarded into CareerOS was the executor's own
    # "chore(polish): queue T-001" ticket -- reported to the human as "landed".
    # A landed row invites a Gate 2 tick, and ticking an SR-linked row re-grounds
    # that requirement, so a false green here certifies work that never happened.
    live = _repo(tmp_path)

    def fake_run(task_id, wt: Path) -> RunOutcome:
        return RunOutcome(ok=True)  # exits clean, changes nothing

    ex = WorktreeIsolatedExecutor(live, factory_run=fake_run)
    landed = ex.execute(Finding(usecase="sign-in", description="broken"))

    assert landed.status == "failed"
    assert "no fix" in landed.detail
    # the queue-only commit must NOT reach the live tree
    assert (live / "app.txt").read_text(encoding="utf-8") == "v0"
    assert not (live / "tasks").exists()


def test_red_fix_leaves_live_untouched(tmp_path):
    live = _repo(tmp_path)

    def fake_run(task_id, wt: Path) -> RunOutcome:
        # uncommitted; factory-run failed
        (wt / "app.txt").write_text("broken-half-edit", encoding="utf-8")
        return RunOutcome(ok=False, detail="validation red")

    ex = WorktreeIsolatedExecutor(live, factory_run=fake_run)
    landed = ex.execute(Finding(usecase="sign-in", description="broken"))

    assert landed.status == "failed"
    # live tree untouched
    assert (live / "app.txt").read_text(encoding="utf-8") == "v0"
