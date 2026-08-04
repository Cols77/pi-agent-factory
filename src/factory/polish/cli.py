from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from collections.abc import Callable
from pathlib import Path

from factory.orchestrator.pi_backend import PiAgentBackend
from factory.polish.bridge import PolishBridge
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


# Bridge filenames under the session dir. The TS side (polish-protocol.ts) must
# use these exact names -- they are the whole contract between the two processes.
STATE_FILE = "polish-state.json"
COMMANDS_DIR = "polish-commands"
LIVE_FILE = "polish-session.live"


def run_polish_serve(
    orchestrator: PolishOrchestrator,
    bridge: PolishBridge,
    *,
    should_stop: Callable[[], bool],
    poll_interval: float = 0.2,
) -> None:
    """Publish state, then drain UI commands until should_stop(). Always tears down."""
    bridge.publish()
    try:
        while not should_stop():
            bridge.poll_commands()
            # the worker may have landed a fix between polls -> Gate 2 grows
            bridge.publish()
            if poll_interval:
                time.sleep(poll_interval)
    finally:
        orchestrator.teardown()


def session_bridge_dir(project_root: Path, session_id: str) -> Path:
    """Where the bridge files live. Mirrored by polishStatePath/polishCommandsDir
    in pi-ext/factory-watch/src/polish-protocol.ts -- both sides must agree."""
    return project_root / "sessions" / ".factory-transcripts" / session_id


def cmd_serve(
    project_root: Path,
    playground: str,
    usecase: str,
    session_dir: Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    poll_interval: float = 0.2,
) -> None:
    """Run the orchestrator behind a file bridge until asked to stop.

    Stops when the UI removes the live sentinel, or on SIGTERM (which is what
    the /polish command's child.kill() sends when the panel closes).
    """
    orchestrator = build_orchestrator(project_root, playground, provider=provider, model=model)
    orchestrator.setup(usecase)
    session_dir.mkdir(parents=True, exist_ok=True)
    live = session_dir / LIVE_FILE
    live.write_text("live", encoding="utf-8")

    terminated = threading.Event()

    def _on_sigterm(signum, frame):
        terminated.set()

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except (ValueError, OSError):
        pass  # not the main thread, or unsupported here; the sentinel still works

    bridge = PolishBridge(orchestrator, session_dir / STATE_FILE, session_dir / COMMANDS_DIR)
    try:
        run_polish_serve(
            orchestrator,
            bridge,
            should_stop=lambda: terminated.is_set() or not live.exists(),
            poll_interval=poll_interval,
        )
    finally:
        live.unlink(missing_ok=True)


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

    p_serve = sub.add_parser("serve", parents=[common])
    p_serve.add_argument("--playground", required=True)
    p_serve.add_argument("--usecase", required=True)
    # --session is what the /polish command passes; --session-dir is an explicit
    # override for tests and non-standard layouts.
    p_serve.add_argument("--session", default=None)
    p_serve.add_argument("--session-dir", default=None, type=Path)
    p_serve.add_argument("--provider", default=None)
    p_serve.add_argument("--model", default=None)

    args = parser.parse_args(argv)

    tasks_dir = args.tasks_dir or (args.project_root / "tasks")
    if args.cmd == "list":
        print(cmd_list(args.project_root))
    elif args.cmd == "run":
        paths = cmd_run(args.project_root, args.playground, args.usecase, args.from_json, tasks_dir)
        print("\n".join(str(p) for p in paths))
    elif args.cmd == "serve":
        if args.session_dir is None and not args.session:
            parser.error("serve requires --session <id> (or --session-dir <path>)")
        session_dir = args.session_dir or session_bridge_dir(args.project_root, args.session)
        cmd_serve(
            args.project_root,
            args.playground,
            args.usecase,
            session_dir,
            provider=args.provider,
            model=args.model,
        )
    return 0
