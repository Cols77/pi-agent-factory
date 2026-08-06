from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from factory.orchestrator.git_ops import GitOps, SubprocessGitOps
from factory.orchestrator.journal import RunCheckpoint, RunJournal
from factory.orchestrator.recovery import RecoveryState, abandon_run, assess_recovery

_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")
ResumeCallback = Callable[[RunCheckpoint], None]


def _run_root(repo_root: Path) -> Path:
    return repo_root / "sessions" / ".factory-runs" / "by-session"


def _run_dir(repo_root: Path, run_id: str) -> Path:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError(f"invalid run id: {run_id}")
    return _run_root(repo_root) / run_id


def _payload(repo_root: Path, checkpoint: RunCheckpoint | None, git_ops: GitOps) -> dict:
    if checkpoint is None:
        return {"checkpoint": None, "assessment": None}
    assessment = assess_recovery(repo_root, checkpoint, git_ops)
    return {"checkpoint": asdict(checkpoint), "assessment": asdict(assessment)}


def load_current_checkpoint(repo_root: Path) -> RunCheckpoint | None:
    candidates: list[tuple[int, str, RunCheckpoint]] = []
    for run_dir in sorted(_run_root(repo_root).glob("*")):
        if (run_dir / "abandoned.json").exists():
            continue
        journal = RunJournal(run_dir)
        checkpoint = journal.latest()
        if checkpoint is None or checkpoint.node in {"completed", "closed"}:
            continue
        try:
            stamp = journal.checkpoint_path.stat().st_mtime_ns
        except OSError:
            stamp = 0
        candidates.append((stamp, checkpoint.run_id, checkpoint))
    return max(candidates, default=(0, "", None), key=lambda item: (item[0], item[1]))[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factory.orchestrator run-state")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("current",):
        command = sub.add_parser(name)
        command.add_argument("--repo", default=".")
        command.add_argument("--json", action="store_true")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("run_id")
    inspect.add_argument("--repo", default=".")
    inspect.add_argument("--json", action="store_true")
    resume = sub.add_parser("resume")
    resume.add_argument("run_id")
    resume.add_argument("--repo", default=".")
    resume.add_argument("--json", action="store_true")
    abandon = sub.add_parser("abandon")
    abandon.add_argument("run_id")
    abandon.add_argument("--reason", required=True)
    abandon.add_argument("--repo", default=".")
    abandon.add_argument("--json", action="store_true")
    return parser


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload))
        return
    checkpoint = payload.get("checkpoint")
    assessment = payload.get("assessment")
    if checkpoint is None:
        print("no interrupted run")
    elif isinstance(assessment, dict):
        print(
            f"{checkpoint['run_id']}  {checkpoint['task_id']}  "
            f"{checkpoint['node']}  {assessment['state']}"
        )


def main(
    argv: list[str] | None = None,
    *,
    git_ops: GitOps | None = None,
    resume_callback: ResumeCallback | None = None,
) -> int:
    args = _parser().parse_args(argv)
    repo_root = Path(args.repo).resolve()
    operations = git_ops or SubprocessGitOps()
    try:
        if args.action == "current":
            payload = _payload(repo_root, load_current_checkpoint(repo_root), operations)
            _emit(payload, args.json)
            return 0

        run_dir = _run_dir(repo_root, args.run_id)
        checkpoint = RunJournal(run_dir).latest()
        if checkpoint is None:
            raise FileNotFoundError(f"run checkpoint not found: {args.run_id}")

        if args.action == "abandon":
            marker = abandon_run(run_dir, args.reason)
            payload = {
                "checkpoint": asdict(checkpoint),
                "assessment": None,
                "abandoned": marker.relative_to(repo_root).as_posix(),
            }
            _emit(payload, args.json)
            return 0

        payload = _payload(repo_root, checkpoint, operations)
        assessment = assess_recovery(repo_root, checkpoint, operations)
        if args.action == "inspect":
            _emit(payload, args.json)
            return 0
        if assessment.state is RecoveryState.CONFLICT:
            _emit(payload, args.json)
            return 3
        if assessment.state is RecoveryState.INSPECT_ONLY:
            _emit(payload, args.json)
            return 4
        if assessment.state is RecoveryState.COMPLETE:
            _emit(payload, args.json)
            return 0
        if resume_callback is None:
            payload["error"] = "resume executor is not configured"
            _emit(payload, args.json)
            return 4
        if assessment.actions and assessment.actions[0] == "restore-patch":
            assert checkpoint.patch_path is not None
            patch = Path(checkpoint.patch_path)
            if not patch.is_absolute():
                patch = repo_root / patch
            operations.restore_patch(repo_root, patch)
            restored = operations.worktree_fingerprint(repo_root, checkpoint.start_commit)
            if restored != checkpoint.worktree_fingerprint:
                payload["error"] = "restored worktree does not match checkpoint fingerprint"
                _emit(payload, args.json)
                return 3
        resume_callback(checkpoint)
        payload["resumed"] = True
        _emit(payload, args.json)
        return 0
    except (OSError, TypeError, ValueError) as exc:
        payload = {"error": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(payload))
        else:
            print(str(exc))
        return 2
