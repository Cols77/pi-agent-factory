from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
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
    preserve = sub.add_parser("preserve-external-edits")
    preserve.add_argument("run_id")
    preserve.add_argument("--repo", default=".")
    preserve.add_argument("--json", action="store_true")
    restart = sub.add_parser("restart")
    restart.add_argument("run_id")
    restart.add_argument("--reason", default=None)
    restart.add_argument("--repo", default=".")
    restart.add_argument("--json", action="store_true")
    abandon = sub.add_parser("abandon")
    abandon.add_argument("run_id")
    abandon.add_argument("--reason", required=True)
    abandon.add_argument("--repo", default=".")
    abandon.add_argument("--json", action="store_true")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--repo", default=".")
    doctor.add_argument("--json", action="store_true")
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


def _resolve_patch(repo_root, checkpoint) -> Path:
    assert checkpoint.patch_path is not None
    patch = Path(checkpoint.patch_path)
    if not patch.is_absolute():
        patch = repo_root / patch
    return patch


def _fresh_checkpoint(
    run_dir: Path, checkpoint: RunCheckpoint, repo_root: Path, git_ops: GitOps
) -> RunCheckpoint:
    """Synthetic checkpoint for a restart: same run_id, task_id, fresh at HEAD."""
    head = git_ops.head_commit(repo_root)
    return RunCheckpoint(
        schema_version=2,
        run_id=checkpoint.run_id,
        task_id=checkpoint.task_id,
        node="context-gather",
        attempt=1,
        remaining={"dev": 3, "review": 3},
        start_commit=head,
        head_commit=head,
        worktree_fingerprint=git_ops.worktree_fingerprint(repo_root, head),
        tracked_fingerprint=git_ops.tracked_fingerprint(repo_root, head),
        patch_path=None,
        completed=[],
        agent_sessions={},
        pending_human_round=None,
        artifacts=[],
        interruption="restart",
    )


def run_doctor(repo_root: Path, *, git_ops: GitOps | None = None) -> dict:
    """Scan the repository for conditions that would break a run or its recovery.

    Returns a dict with findings (each with severity, code, detail) and a
    summary. Exit code 3 (blocking) for oversized run dirs, embedded git repos,
    and reserved-name files; exit code 0 for warnings only.
    """
    from factory.orchestrator.git_ops import _find_reserved_name_files

    findings: list[dict] = []

    # 1. Oversized run dirs
    run_root = _run_root(repo_root)
    if run_root.is_dir():
        for run_dir in sorted(run_root.glob("*")):
            oversized: list[str] = []
            for name, limit in (
                ("checkpoint.json", 10 * 1024 * 1024),
                ("journal.jsonl", 10 * 1024 * 1024),
            ):
                path = run_dir / name
                if path.is_file() and path.stat().st_size > limit:
                    oversized.append(f"{name}={path.stat().st_size / 1024 / 1024:.1f}MB")
            if oversized:
                findings.append(
                    {
                        "severity": "blocking",
                        "code": "run_oversized",
                        "detail": f"{run_dir.name}: {', '.join(oversized)}",
                    }
                )

    # 2. Embedded git repositories
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=repo_root, capture_output=True, check=True,
        )
        for raw in (result.stdout or b"").split(b"\0"):
            if not raw:
                continue
            relative = os.fsdecode(raw)
            candidate = repo_root / relative
            if candidate.is_dir() and (candidate / ".git").exists():
                findings.append(
                    {
                        "severity": "blocking",
                        "code": "embedded_repo",
                        "detail": f"nested repository at {relative}; remove or exclude it before running",
                    }
                )
    except subprocess.CalledProcessError:
        pass
    try:
        result = subprocess.run(
            ["git", "ls-files", "-s"], cwd=repo_root, capture_output=True, check=True,
        )
        for line in (result.stdout or b"").splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0][:6] == b"160000":
                findings.append(
                    {
                        "severity": "blocking",
                        "code": "embedded_repo",
                        "detail": f"submodule/gitlink at {parts[3].decode('utf-8', errors='replace')}; the factory cannot stage submodules",
                    }
                )
    except subprocess.CalledProcessError:
        pass

    # 3. Reserved-name files
    reserved = _find_reserved_name_files(repo_root)
    if reserved:
        findings.append(
            {
                "severity": "blocking",
                "code": "reserved_name",
                "detail": "Windows reserved device names present: " + ", ".join(reserved[:10])
                + (f" ({len(reserved)} total)" if len(reserved) > 10 else ""),
            }
        )

    # 4. Dirty tracked files (outside factory scratch)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-z"],
            cwd=repo_root, capture_output=True, check=True,
        )
        dirty: list[str] = []
        for entry in (result.stdout or b"").split(b"\0"):
            if len(entry) < 4:
                continue
            if entry[0:1] != b" ":
                continue  # staged or untracked entries are not fingerprint-flipping
            relative = os.fsdecode(entry[3:])
            if not _is_scratch_relative(relative):
                dirty.append(relative)
        if dirty:
            findings.append(
                {
                    "severity": "warning",
                    "code": "dirty_tracked",
                    "detail": f"{len(dirty)} tracked file(s) modified (will flip the run fingerprint): "
                    + "; ".join(dirty[:5])
                    + (f" (+{len(dirty) - 5} more)" if len(dirty) > 5 else ""),
                }
            )
    except subprocess.CalledProcessError:
        pass

    # 5. Interrupted run present
    try:
        checkpoint = load_current_checkpoint(repo_root)
        if checkpoint is not None:
            findings.append(
                {
                    "severity": "warning",
                    "code": "interrupted_run",
                    "detail": f"run {checkpoint.run_id} ({checkpoint.task_id}) is interrupted at {checkpoint.node}; "
                    f"use `run-state inspect {checkpoint.run_id}`",
                }
            )
    except (OSError, ValueError):
        pass

    ok = not any(f.get("severity") == "blocking" for f in findings)
    return {
        "findings": findings,
        "ok": ok,
        "summary": f"{'OK' if ok else 'BLOCKING'} -- {len(findings)} finding(s)",
    }


def _is_scratch_relative(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    return normalized.startswith(
        ("sessions/.factory-runs/", "sessions/.factory-transcripts/", ".factory/", "sessions/latest.md", "sessions/.factory-")
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

        if args.action == "doctor":
            report = run_doctor(repo_root, git_ops=operations)
            if args.json:
                print(json.dumps(report))
            else:
                for finding in report["findings"]:
                    print(f"{finding['severity']}: {finding['code']}: {finding['detail']}")
                print(report["summary"])
            return 0 if report["ok"] else 3

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

        if args.action == "restart":
            if checkpoint.node in {"completed", "closed"}:
                payload = {"error": "run is already complete; nothing to restart"}
                _emit(payload, args.json)
                return 2
            reason = args.reason or "restarted at current HEAD to resume work"
            abandon_run(run_dir, reason)
            fresh = _fresh_checkpoint(run_dir, checkpoint, repo_root, operations)
            payload = {
                "checkpoint": asdict(checkpoint),
                "assessment": {"state": "restarted", "reasons": [reason], "actions": ["resume"]},
                "restarted": True,
            }
            if resume_callback is not None:
                resume_callback(fresh)
                payload["resumed"] = True
            else:
                payload["next"] = f"factory run --task {checkpoint.task_id} --force"
            _emit(payload, args.json)
            return 0

        payload = _payload(repo_root, checkpoint, operations)
        assessment = assess_recovery(repo_root, checkpoint, operations)

        if args.action == "inspect":
            _emit(payload, args.json)
            return 0

        if assessment.state is RecoveryState.INSPECT_ONLY:
            _emit(payload, args.json)
            return 4

        if assessment.state is RecoveryState.COMPLETE:
            _emit(payload, args.json)
            return 0

        if args.action == "preserve-external-edits":
            current_head = operations.head_commit(repo_root)
            if current_head != checkpoint.head_commit:
                payload["error"] = (
                    f"HEAD changed from {checkpoint.head_commit} to {current_head}; "
                    "use `restart` to resume from current HEAD preserving external edits"
                )
                _emit(payload, args.json)
                return 3
            if checkpoint.patch_path is None:
                payload["error"] = "checkpoint has no saved patch to restore around"
                _emit(payload, args.json)
                return 3
            patch = _resolve_patch(repo_root, checkpoint)
            if not operations.check_patch(repo_root, patch):
                payload["error"] = (
                    "checkpoint patch conflicts with external edits; "
                    f"use `restart {checkpoint.run_id}` to resume from current HEAD"
                )
                _emit(payload, args.json)
                return 3
            # Snapshot pre-dirty tracked files, then verify they are preserved
            # byte-for-byte after the restore (stash/restore around resume).
            pre_dirty = operations.dirty_snapshot(repo_root)
            operations.restore_patch(repo_root, patch)
            for relative, digest in pre_dirty.items():
                try:
                    current = hashlib.sha256(
                        (repo_root / relative).read_bytes()
                    ).hexdigest()
                except OSError:
                    continue
                if current != digest:
                    payload["error"] = (
                        f"external edit was overwritten by restore: {relative}; "
                        f"use `restart {checkpoint.run_id}` to resume from current HEAD"
                    )
                    _emit(payload, args.json)
                    return 3
            if resume_callback is None:
                payload["error"] = "resume executor is not configured"
                _emit(payload, args.json)
                return 4
            resume_callback(checkpoint)
            payload["resumed"] = True
            _emit(payload, args.json)
            return 0

        # Resume action
        if assessment.state is RecoveryState.CONFLICT:
            _emit(payload, args.json)
            return 3
        if resume_callback is None:
            payload["error"] = "resume executor is not configured"
            _emit(payload, args.json)
            return 4
        if assessment.actions and assessment.actions[0] == "restore-patch":
            assert checkpoint.patch_path is not None
            operations.restore_patch(repo_root, _resolve_patch(repo_root, checkpoint))
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
