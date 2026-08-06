from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from factory.config import GateConfigError, load_config, require_gates
from factory.evidence.artifacts import LocalArtifactStore
from factory.freshness.model import FreshnessSeverity
from factory.orchestrator.backends import ConfigGateRunner
from factory.orchestrator.deliverables import deliverables_exist
from factory.orchestrator.human_review import FileHumanReviewGate
from factory.orchestrator.journal import RunCheckpoint
from factory.orchestrator.ledger import format_task_board, load_tasks
from factory.orchestrator.lock import AlreadyRunningError, acquire_lock, remove_lock
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.run_cli import main as run_state_main
from factory.orchestrator.run_state import read_last_run
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FileStatusReporter
from factory.paths import scope_guard_extension
from factory.preflight.checks import run_preflight


def _git_info(repo_root: Path) -> dict:
    def _cmd(args: list[str]) -> str:
        return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    return {"branch": _cmd(["rev-parse", "--abbrev-ref", "HEAD"]), "head": _cmd(["rev-parse", "HEAD"])}


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _repo_from_run_state_args(argv: list[str]) -> Path:
    try:
        index = argv.index("--repo")
        return Path(argv[index + 1]).resolve()
    except (ValueError, IndexError):
        return Path(".").resolve()


def _resume_run(repo_root: Path, checkpoint: RunCheckpoint) -> None:
    """Execute a previously assessed checkpoint without silently starting a new run."""
    transcript_dir = (
        repo_root / "sessions" / ".factory-transcripts" / checkpoint.run_id
    )
    gates = ConfigGateRunner(
        repo_root,
        require_gates(load_config(repo_root), repo_root),
        log_dir=transcript_dir,
    )
    backend = PiAgentBackend(
        repo_root=repo_root,
        extension_path=scope_guard_extension(),
    )
    lock_path = repo_root / "sessions" / ".factory-run.lock"
    acquire_lock(lock_path, os.getpid(), checkpoint.run_id)
    status = FileStatusReporter(
        path=repo_root / "sessions" / ".factory-status.json",
        session_id=checkpoint.run_id,
    )
    try:
        path = run_next(
            repo_root,
            backend,
            gates,
            git_info=_git_info(repo_root),
            session_id=checkpoint.run_id,
            status=status,
            task_id=checkpoint.task_id,
            human_review=None,
            transcript_dir=transcript_dir,
            force=True,
            artifact_store=LocalArtifactStore(
                repo_root / ".factory" / "artifacts" / "objects"
            ),
            evidence_dir=repo_root / "evidence",
            checkpoint_runs=True,
            resume=checkpoint,
        )
        print(f"resumed session written: {path}", file=sys.stderr)
    finally:
        remove_lock(lock_path)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "run-state":
        state_args = sys.argv[2:]
        repo_root = _repo_from_run_state_args(state_args)
        raise SystemExit(
            run_state_main(
                state_args,
                resume_callback=lambda checkpoint: _resume_run(repo_root, checkpoint),
            )
        )

    parser = argparse.ArgumentParser(prog="factory.orchestrator")
    parser.add_argument("command", choices=["run", "list"])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--provider", default=None, help="Pi provider, e.g. openrouter")
    parser.add_argument("--model", default=None, help="Pi model id, e.g. anthropic/claude-opus-4")
    parser.add_argument("--task", default=None, help="Task id to run (default: next todo task)")
    parser.add_argument("--json", action="store_true", help="list command only: output tasks as JSON")
    parser.add_argument(
        "--auto", action="store_true",
        help="skip the human review gate; fully automated (today's behavior)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="re-run --task even if it is not 'todo' (e.g. resume the pipeline after manual work)",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()

    if args.command == "list":
        tasks = load_tasks(repo_root / "tasks")
        if args.json:
            print(json.dumps([
                {
                    "id": t.id, "title": t.title, "status": t.status,
                    "already_done": deliverables_exist(t.body, repo_root),
                    "last_run": read_last_run(repo_root, t.id),
                }
                for t in tasks
            ]))
        else:
            print(format_task_board(tasks))
        return

    preflight = run_preflight(repo_root, args.task)
    if not preflight.ok:
        for issue in preflight.issues:
            print(
                f"factory preflight {issue.severity.value}: {issue.code}: {issue.detail}",
                file=sys.stderr,
            )
        code = (
            3
            if any(
                issue.severity is FreshnessSeverity.INTEGRITY
                for issue in preflight.issues
            )
            else 2
        )
        raise SystemExit(code)

    # The extension ships with the FACTORY. Deriving it from --repo meant every
    # cross-repo run launched pi with a path that does not exist there: pi
    # refused to start, context-gather returned nothing and rejected, the run
    # abandoned the task and still exited 0 -- reported upstream as a clean run
    # that simply committed nothing.
    backend = PiAgentBackend(
        repo_root=repo_root,
        extension_path=scope_guard_extension(),
        provider=args.provider,
        model=args.model,
    )

    session_id = _now_id()
    transcript_dir = repo_root / "sessions" / ".factory-transcripts" / session_id
    try:
        gates = ConfigGateRunner(
            repo_root, require_gates(load_config(repo_root), repo_root), log_dir=transcript_dir
        )
    except GateConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    kwargs = {}
    if args.provider and args.model:
        kwargs["model_backend"] = f"{args.provider}:{args.model}"

    lock_path = repo_root / "sessions" / ".factory-run.lock"
    status_path = repo_root / "sessions" / ".factory-status.json"

    try:
        acquire_lock(lock_path, os.getpid(), session_id)
    except AlreadyRunningError as exc:
        print(f"factory orchestrator already running (pid {exc.pid}); refusing to start a second run", file=sys.stderr)
        raise SystemExit(1) from exc

    status = FileStatusReporter(path=status_path, session_id=session_id)
    human_review = None if args.auto else FileHumanReviewGate(transcript_dir, repo_root=repo_root)
    artifact_store = LocalArtifactStore(repo_root / ".factory" / "artifacts" / "objects")
    try:
        path = run_next(
            repo_root, backend, gates, git_info=_git_info(repo_root),
            session_id=session_id, status=status, task_id=args.task,
            human_review=human_review, transcript_dir=transcript_dir, force=args.force,
            artifact_store=artifact_store, evidence_dir=repo_root / "evidence",
            checkpoint_runs=True, **kwargs,
        )
        print("no todo tasks" if path is None else f"session written: {path}", file=sys.stderr)
    except Exception as exc:
        # Report the failure for the dashboard, but never let a failure of
        # THIS report (e.g. a locked status file on Windows) mask the original
        # exception -- re-raise the original error regardless.
        try:
            status.report(
                task_id="", node="orchestrator", node_state="error",
                attempt=0, max_attempts=0, snippet=str(exc),
            )
        except Exception:
            pass
        raise
    finally:
        remove_lock(lock_path)


if __name__ == "__main__":
    main()
