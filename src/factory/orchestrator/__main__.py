from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from factory.orchestrator.backends import SubprocessGateRunner
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.runner import run_next


def _git_info(repo_root: Path) -> dict:
    def _cmd(args: list[str]) -> str:
        return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True).stdout.strip()

    return {"branch": _cmd(["rev-parse", "--abbrev-ref", "HEAD"]), "head": _cmd(["rev-parse", "HEAD"])}


def main() -> None:
    parser = argparse.ArgumentParser(prog="factory.orchestrator")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    ext = repo_root / "pi-ext" / "scope-guard" / "src" / "index.ts"
    backend = PiAgentBackend(repo_root=repo_root, extension_path=ext)
    gates = SubprocessGateRunner(repo_root)

    path = run_next(repo_root, backend, gates, git_info=_git_info(repo_root))
    print("no todo tasks" if path is None else f"session written: {path}")


if __name__ == "__main__":
    main()
