from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# How long the grill gate will wait for a human verdict before treating the
# grill as abandoned. Mirrors pi_backend's agent-timeout env contract; a
# non-positive value disables the bound. A generous default: an active grill is
# a human dialogue that can legitimately take a while, but a dead/hung grill
# must never block the pipeline forever.
_DEFAULT_POLL_INTERVAL = 1.0
_DEFAULT_TOTAL_TIMEOUT_S = float(os.environ.get("FACTORY_GRILL_TOTAL_TIMEOUT_S", "7200"))


@dataclass
class GrillResult:
    # One of "agreed" | "not-agreed" | "skipped". All three proceed to dev;
    # the grill never hard-blocks (see the grill design spec).
    decision: str
    summary: str | None = None
    explainers: int = 0  # visual explainers reused or generated this grill


class GrillGate(Protocol):
    def request_grill(self, task_id: str) -> GrillResult: ...


class FileGrillGate:
    """Blocking grill handoff, mirroring FileHumanReviewGate.

    Polls ``<transcript_dir>/grill-result.json`` until a verdict is present
    (written by the interactive grill session for ``agreed``/``not-agreed``, or
    by the extension for ``skipped``). A hang or crash is resolved by the total
    timeout, which records an abandoned ``not-agreed`` rather than stalling the
    run. No diff archiving here -- the grill produces explainers, not a review
    decision.
    """

    def __init__(
        self,
        transcript_dir: Path,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        total_timeout_s: float = _DEFAULT_TOTAL_TIMEOUT_S,
    ) -> None:
        self._transcript_dir = transcript_dir
        self._verdict_path = transcript_dir / "grill-result.json"
        self._poll_interval = poll_interval
        self._total_timeout_s = total_timeout_s

    def request_grill(self, task_id: str) -> GrillResult:
        deadline = time.monotonic() + self._total_timeout_s
        while True:
            if self._verdict_path.exists():
                try:
                    payload = json.loads(self._verdict_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    payload = {}
                self._verdict_path.unlink()
                decision = payload.get("decision")
                summary = payload.get("summary")
                return GrillResult(
                    decision=str(decision) if isinstance(decision, str) else "not-agreed",
                    summary=summary if isinstance(summary, str) else None,
                    explainers=int(payload.get("explainers", 0) or 0),
                )
            if self._total_timeout_s > 0 and time.monotonic() >= deadline:
                return GrillResult(decision="not-agreed", summary="grill timed out")
            time.sleep(self._poll_interval)


class FakeGrillGate:
    def __init__(self, results: list[GrillResult]) -> None:
        self._results = list(results)
        self.requests: list[str] = []

    def request_grill(self, task_id: str) -> GrillResult:
        self.requests.append(task_id)
        assert self._results, "FakeGrillGate: no scripted result left"
        return self._results.pop(0)
