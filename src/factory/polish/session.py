from __future__ import annotations

import atexit
import signal
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from factory.polish.finding import Finding
from factory.polish.playground import Playground
from factory.polish.routing import route


def open_navigator(entrypoints: list[str]) -> None:
    for ep in entrypoints:
        try:
            if sys.platform == "win32":
                subprocess.Popen(["cmd", "/c", "start", "", ep])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", ep])
            else:
                subprocess.Popen(["xdg-open", ep])
        except OSError:
            pass  # best-effort: opening the navigator must never break the session


def _install_sigterm(tear: Callable[[], None]):
    """Install a SIGTERM handler that tears down then exits. Returns the previous
    handler, or None if signals aren't settable here (e.g. not the main thread).
    SIGINT/KeyboardInterrupt is already covered by the caller's finally; SIGKILL
    is uncatchable. Residual window: a bare SIGTERM arriving *during*
    playground.setup() (before this guard installs) is not caught here — a
    playground's own setup cleanup handles SIGINT/errors, but bare
    SIGTERM-during-setup, like SIGKILL, can still leak."""

    def _handler(signum, frame):
        tear()
        raise SystemExit(1)

    try:
        return signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):
        return None


def run_polish_session(
    playground: Playground,
    usecase: str,
    findings: list[Finding],
    tasks_dir: Path,
    *,
    open_nav: Callable[[list[str]], None] | None = None,
) -> list[Path]:
    """DEPRECATED lifecycle wrapper: routes a *pre-supplied* findings list.

    Superseded by PolishOrchestrator (factory.polish.orchestrator), which owns the
    loop and *produces* findings from live feedback instead of taking them as an
    argument. Kept for the `factory polish run --from-json` path; new callers
    should build the orchestrator via factory.polish.cli.build_orchestrator.
    """
    session = playground.setup(usecase)
    torn = False

    def _tear() -> None:
        nonlocal torn
        if not torn:
            torn = True
            session.teardown()

    atexit.register(_tear)
    prev_term = _install_sigterm(_tear)
    try:
        if open_nav is not None:
            open_nav(session.entrypoints)
        return [route(f, tasks_dir) for f in findings]
    finally:
        _tear()
        if prev_term is not None:
            try:
                signal.signal(signal.SIGTERM, prev_term)
            except (ValueError, OSError):
                pass
        atexit.unregister(_tear)
