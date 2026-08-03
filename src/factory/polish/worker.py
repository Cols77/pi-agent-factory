from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from factory.polish.finding import Finding


@dataclass
class RunOutcome:
    ok: bool
    detail: str = ""


@dataclass
class LandedChange:
    finding: Finding
    task_path: Path
    task_id: str
    status: str  # "landed" | "failed"
    detail: str = ""


class FixExecutor(Protocol):
    """Applies one finding as a fix and reports what landed. The isolation
    strategy (worktree + fast-forward integrate) lives behind this seam so the
    worker stays a pure queue/thread."""

    def execute(self, finding: Finding) -> LandedChange: ...


class FixWorker:
    """Serial worker: drains findings one at a time on a background thread and
    delegates each to the injected FixExecutor. Never blocks the feedback path."""

    def __init__(self, executor: FixExecutor) -> None:
        self._executor = executor
        self._q: queue.Queue[Finding] = queue.Queue()
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def submit(self, finding: Finding) -> None:
        self._q.put(finding)

    def pending_count(self) -> int:
        return self._q.qsize()

    def process_next(self, timeout: float | None = None) -> LandedChange | None:
        try:
            finding = self._q.get(timeout=timeout) if timeout is not None else self._q.get_nowait()
        except queue.Empty:
            return None
        try:
            return self._executor.execute(finding)
        finally:
            self._q.task_done()

    def start(self, on_landed: Callable[[LandedChange], None]) -> None:
        self._stop = threading.Event()

        def _loop() -> None:
            while self._stop is not None and not self._stop.is_set():
                landed = self.process_next(timeout=0.1)
                if landed is not None:
                    on_landed(landed)

        self._thread = threading.Thread(target=_loop, name="polish-fix-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
