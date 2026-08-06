from __future__ import annotations

import re
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

from factory.polish.finding import Finding
from factory.polish.routing import route
from factory.polish.worker import LandedChange, RunOutcome

_ID_RE = re.compile(r"T-(\d+)")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


class SubprocessFactoryRunner:
    """Runs factory-run in --auto mode (no human gate) inside a given repo dir.
    In --auto mode factory-run's own VALIDATION (the task's SR gate + standing
    regression) and LLM review ARE the acceptance; commit-on-green happens inside
    factory-run. This runner just reports ok/failed."""

    def __init__(self, provider: str | None = None, model: str | None = None) -> None:
        self._provider = provider
        self._model = model

    def run(self, task_id: str, repo_root: Path) -> RunOutcome:
        argv = [sys.executable, "-m", "factory.orchestrator", "run",
                "--repo", str(repo_root), "--task", task_id, "--auto"]
        if self._provider:
            argv += ["--provider", self._provider]
        if self._model:
            argv += ["--model", self._model]
        proc = subprocess.run(argv, cwd=str(repo_root), check=False)
        return RunOutcome(ok=proc.returncode == 0,
                          detail="" if proc.returncode == 0 else f"factory-run exit {proc.returncode}")


class WorktreeIsolatedExecutor:
    """Apply a fix in an isolated worktree, then fast-forward the finished green
    result into the live branch. The dev-server's tree only ever sees committed,
    validated states."""

    def __init__(self, live_root: Path, *, factory_run: Callable[[str, Path], RunOutcome],
                 tasks_subdir: str = "tasks", worktrees_root: Path | None = None) -> None:
        self._live = live_root
        self._factory_run = factory_run
        self._tasks_subdir = tasks_subdir
        self._worktrees_root = worktrees_root or (live_root / ".worktrees")

    def execute(self, finding: Finding) -> LandedChange:
        branch = f"polish-fix/{uuid.uuid4().hex[:8]}"
        self._worktrees_root.mkdir(parents=True, exist_ok=True)
        wt = self._worktrees_root / branch.replace("/", "-")
        _git(self._live, "worktree", "add", "-b", branch, str(wt), "HEAD")
        keep = False  # a failed run's worktree is kept for inspection
        task_path = wt / self._tasks_subdir / "pending.md"  # replaced below; keeps type-checkers happy
        try:
            task_path = route(finding, wt / self._tasks_subdir)
            m = _ID_RE.search(task_path.name)
            task_id = m.group(0) if m else task_path.stem
            _git(wt, "add", "-A")
            _git(wt, "commit", "-m", f"chore(polish): queue {task_id}")
            queued_head = _git(wt, "rev-parse", "HEAD").stdout.strip()
            outcome = self._factory_run(task_id, wt)
            status, detail, live_task_path = "failed", outcome.detail, task_path
            if outcome.ok:
                # A clean exit is NOT a fix. If factory-run committed nothing, the
                # only commit on this branch is our own queued ticket; landing that
                # would report "fixed" for work that never happened -- and a landed
                # row invites a Gate 2 tick, which re-grounds a linked SR.
                if _git(wt, "rev-parse", "HEAD").stdout.strip() == queued_head:
                    detail = (
                        f"factory-run exited 0 but committed no fix for {task_id} "
                        "(only the queued task was on the branch); nothing landed"
                    )
                else:
                    ff = _git(self._live, "merge", "--ff-only", branch)
                    if ff.returncode == 0:
                        status, detail = "landed", ""
                        live_task_path = self._live / self._tasks_subdir / task_path.name
                    else:
                        detail = f"fast-forward into live failed: {ff.stderr.strip()}"
            if status == "failed":
                # Keep the worktree: it holds the only record of what the dev
                # agent actually did, and discarding it makes the failure
                # impossible to diagnose afterwards. Say where it is.
                keep = True
                detail = f"{detail} -- worktree kept for debugging: {wt}"
            return LandedChange(finding=finding, task_path=live_task_path,
                                task_id=task_id, status=status, detail=detail)
        finally:
            if not keep:
                _git(self._live, "worktree", "remove", "--force", str(wt))
                _git(self._live, "branch", "-D", branch)  # best-effort if already gone
