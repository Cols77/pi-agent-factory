from __future__ import annotations

import threading
from collections.abc import Callable

from factory.orchestrator.backends import AgentBackend
from factory.polish.gates import Gate1, Gate2
from factory.polish.playground import Playground, PlaygroundSession
from factory.polish.synthesis import synthesize
from factory.polish.worker import FixWorker, LandedChange


class PolishOrchestrator:
    """Deterministic polish loop. Python owns the topology; the LLM is invoked
    only inside submit_feedback (SYNTHESIS). Fixes run on the worker's background
    thread, so the feedback path never blocks."""

    def __init__(self, playground: Playground, backend: AgentBackend, worker: FixWorker,
                 *, open_nav: Callable[[list[str]], None] | None = None) -> None:
        self._pg = playground
        self._backend = backend
        self._worker = worker
        self._open_nav = open_nav
        self._lock = threading.Lock()
        self._gate1 = Gate1()
        self._gate2 = Gate2()
        self._session: PlaygroundSession | None = None
        self._usecase = ""

    # --- lifecycle ---
    def setup(self, usecase: str) -> None:
        with self._lock:
            self._usecase = usecase
            self._session = self._pg.setup(usecase)
            entrypoints = list(self._session.entrypoints)
        if self._open_nav is not None:
            self._open_nav(entrypoints)
        self._worker.start(self.record_landed)

    def teardown(self) -> None:
        self._worker.stop()
        with self._lock:
            if self._session is not None:
                self._session.teardown()
                self._session = None

    # --- feedback -> synthesis -> Gate 1 ---
    def submit_feedback(self, text: str) -> list[str]:
        findings = synthesize(self._backend, text, self._usecase)
        with self._lock:
            return [self._gate1.add(f) for f in findings]

    def accept_finding(self, gid: str) -> None:
        with self._lock:
            finding = self._gate1.accept(gid)
        self._worker.submit(finding)

    def edit_finding(self, gid: str, **changes) -> None:
        with self._lock:
            finding = self._gate1.edit(gid, **changes)
        self._worker.submit(finding)

    def discard_finding(self, gid: str) -> None:
        with self._lock:
            self._gate1.discard(gid)

    # --- worker landing -> Gate 2 ---
    def record_landed(self, change: LandedChange) -> None:
        with self._lock:
            self._gate2.add(change)

    def tick(self, gid: str) -> None:
        with self._lock:
            self._gate2.tick(gid)  # re-ground handled by caller/telemetry; no re-queue

    def comment(self, gid: str, text: str) -> str:
        with self._lock:
            rework = self._gate2.comment(gid, text)
            new_gid = self._gate1.add(rework)
        return new_gid

    # --- UI contract ---
    def state(self) -> dict:
        with self._lock:
            g1 = self._gate1.pending()
            return {
                "usecase": self._usecase,
                "entrypoints": list(self._session.entrypoints) if self._session else [],
                "queue_size": self._worker.pending_count(),
                "gate1_ids": list(g1),
                "gate1": [{"gid": k, "description": v.description, "sr": v.sr}
                          for k, v in g1.items()],
                "gate2": [
                    {"gid": r.gid, "task_id": r.change.task_id,
                     "description": r.change.finding.description,
                     "sr": r.change.finding.sr, "status": r.change.status,
                     # why a fix failed -- otherwise the panel shows a bare
                     # "failed" and the human must go read serve's stdout
                     "detail": r.change.detail, "verdict": r.verdict}
                    for r in self._gate2.rows()
                ],
            }
