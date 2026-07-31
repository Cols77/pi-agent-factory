from __future__ import annotations

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


def run_polish_session(
    playground: Playground,
    usecase: str,
    findings: list[Finding],
    tasks_dir: Path,
    *,
    open_nav: Callable[[list[str]], None] | None = None,
) -> list[Path]:
    session = playground.setup(usecase)
    try:
        if open_nav is not None:
            open_nav(session.entrypoints)
        return [route(f, tasks_dir) for f in findings]
    finally:
        session.teardown()
