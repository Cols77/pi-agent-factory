from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from factory.orchestrator.backends import SubprocessGateRunner
from factory.orchestrator.ledger import format_task_board, load_tasks
from factory.orchestrator.lock import AlreadyRunningError, acquire_lock, remove_lock
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FileStatusReporter


def _git_info(repo_root: Path) -> dict:
    def _cmd(args: list[str]) -> str:
        return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    return {"branch": _cmd(["rev-parse", "--abbrev-ref", "HEAD"]), "head": _cmd(["rev-parse", "HEAD"])}


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(prog="factory.orchestrator")
    parser.add_argument("command", choices=["run", "list"])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--provider", default=None, help="Pi provider, e.g. openrouter")
    parser.add_argument("--model", default=None, help="Pi model id, e.g. anthropic/claude-opus-4")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()

    if args.command == "list":
        print(format_task_board(load_tasks(repo_root / "tasks")))
        return

    ext = repo_root / "pi-ext" / "scope-guard" / "src" / "index.ts"
    backend = PiAgentBackend(
        repo_root=repo_root, extension_path=ext, provider=args.provider, model=args.model
    )
    gates = SubprocessGateRunner(repo_root)

    kwargs = {}
    if args.provider and args.model:
        kwargs["model_backend"] = f"{args.provider}:{args.model}"

    session_id = _now_id()
    lock_path = repo_root / "sessions" / ".factory-run.lock"
    status_path = repo_root / "sessions" / ".factory-status.json"

    try:
        acquire_lock(lock_path, os.getpid(), session_id)
    except AlreadyRunningError as exc:
        print(f"factory orchestrator already running (pid {exc.pid}); refusing to start a second run")
        raise SystemExit(1) from exc

    status = FileStatusReporter(path=status_path, session_id=session_id)
    try:
        path = run_next(
            repo_root, backend, gates, git_info=_git_info(repo_root),
            session_id=session_id, status=status, **kwargs,
        )
        print("no todo tasks" if path is None else f"session written: {path}")
    except Exception as exc:
        status.report(
            task_id="", node="orchestrator", node_state="error",
            attempt=0, max_attempts=0, snippet=str(exc),
        )
        raise
    finally:
        remove_lock(lock_path)


if __name__ == "__main__":
    main()
