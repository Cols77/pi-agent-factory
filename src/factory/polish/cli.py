from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from factory.orchestrator.pi_backend import PiAgentBackend
from factory.polish.config import load_config
from factory.polish.executor import SubprocessFactoryRunner, WorktreeIsolatedExecutor
from factory.polish.finding import Finding
from factory.polish.orchestrator import PolishOrchestrator
from factory.polish.session import open_navigator, run_polish_session
from factory.polish.worker import FixWorker


def cmd_list(project_root: Path) -> str:
    lines: list[str] = []
    for name, pg in load_config(project_root).playgrounds.items():
        lines.extend(f"{name}:{uc}" for uc in pg.list_usecases())
    return "\n".join(lines) if lines else "no playgrounds/usecases"


def cmd_run(
    project_root: Path,
    playground_name: str,
    usecase: str,
    findings_json: Path,
    tasks_dir: Path,
    *,
    open_nav: Callable[[list[str]], None] = open_navigator,
) -> list[Path]:
    playground = load_config(project_root).playgrounds[playground_name]
    raw = json.loads(Path(findings_json).read_text(encoding="utf-8"))
    findings = [
        Finding(
            usecase=usecase,
            description=r["description"],
            snapshot=r.get("snapshot", {}),
            sr=r.get("sr"),
            artifacts=r.get("artifacts", []),
        )
        for r in raw
    ]
    return run_polish_session(playground, usecase, findings, tasks_dir, open_nav=open_nav)


def build_orchestrator(
    project_root: Path,
    playground: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> PolishOrchestrator:
    """Wire the deterministic polish loop: playground + LLM backend + a serial
    worker whose fixes run in an isolated worktree and are fast-forwarded into
    the live branch the dev-server watches (never edited in place)."""
    cfg = load_config(project_root)
    pg = cfg.playgrounds[playground]
    executor = WorktreeIsolatedExecutor(
        project_root,
        factory_run=SubprocessFactoryRunner(provider=provider, model=model).run,
    )
    worker = FixWorker(executor)
    ext = project_root / "pi-ext" / "scope-guard" / "src" / "index.ts"
    backend = PiAgentBackend(
        repo_root=project_root, extension_path=ext, provider=provider, model=model
    )
    return PolishOrchestrator(pg, backend, worker, open_nav=open_navigator)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-polish")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=Path("."), type=Path)
    common.add_argument("--tasks-dir", default=None, type=Path)

    sub.add_parser("list", parents=[common])
    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("--playground", required=True)
    p_run.add_argument("--usecase", required=True)
    p_run.add_argument("--from-json", required=True, type=Path)
    args = parser.parse_args(argv)

    tasks_dir = args.tasks_dir or (args.project_root / "tasks")
    if args.cmd == "list":
        print(cmd_list(args.project_root))
    elif args.cmd == "run":
        paths = cmd_run(args.project_root, args.playground, args.usecase, args.from_json, tasks_dir)
        print("\n".join(str(p) for p in paths))
    return 0
