"""SR-034/SR-049 fresh-context parallel review swarm.

Two independent ``AgentRole.REVIEW`` invocations -- the spec-compliance lane and
the code-quality lane -- run concurrently in a ``ThreadPoolExecutor``. Each
worker builds its own prompt from the task, manifest and contract and opens its
own agent session; neither worker ever sees the other's output. Decision 4
(2026-09-11) fixed the design: there is no new ``AgentRole``. The two reviews are
prompt-distinguished and separated in evidence by their lanes and by the
canonical stage ids ``review-spec`` / ``review-quality`` (see
``execution_contract.STAGE_TO_LANE``).

The join fails closed: a blank session id, a duplicated session id, or a lane
missing from / duplicated inside the result all raise ``ReviewProtocolError``
before any caller can dispatch a fixer.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from factory.orchestrator.backends import AgentBackend
from factory.orchestrator.execution_contract import (
    LANE_TO_STAGE,
    ExecutionContract,
    Lane,
    WorkerAssignment,
)
from factory.orchestrator.types import AgentRole, NodeEvent
from substrate.agents.model import AgentResult
from substrate.ledger.tasks import Task

# The closed review-lane vocabulary, in the stable order results are returned.
REVIEW_LANES: tuple[Lane, ...] = ("spec-review", "quality-review")


class ReviewProtocolError(RuntimeError):
    """The review swarm could not produce two distinct, complete reviews."""


@dataclass(frozen=True)
class ReviewResult:
    """One lane's fresh review: its prompt-distinguished agent result and session."""

    lane: Lane
    result: AgentResult
    session_id: str
    findings: tuple[str, ...]
    dod_met: bool

    def __post_init__(self) -> None:
        if self.lane not in REVIEW_LANES:
            raise ReviewProtocolError(f"unknown review lane: {self.lane!r}")


@dataclass(frozen=True)
class ReviewSwarmResult:
    """Both reviews plus their join instant."""

    reviews: tuple[ReviewResult, ...]
    completed_at: datetime

    def __post_init__(self) -> None:
        lanes = tuple(review.lane for review in self.reviews)
        if sorted(lanes) != sorted(REVIEW_LANES):
            raise ReviewProtocolError(
                f"swarm result must carry exactly {list(REVIEW_LANES)}, got {list(lanes)}"
            )

    def review_for(self, lane: Lane) -> ReviewResult:
        """Closed-lane lookup.

        ``__post_init__`` is the single gate for the exactly-one-review-per-lane
        guarantee, so this is a total lookup with no unreachable re-validation.
        """
        if lane not in REVIEW_LANES:
            raise ReviewProtocolError(f"unknown review lane: {lane!r}")
        return next(review for review in self.reviews if review.lane == lane)


def build_review_prompt(
    *,
    lane: Lane,
    task: Task,
    contract: ExecutionContract,
    manifest: dict,
    events: Sequence[NodeEvent],
) -> str:
    """One lane's prompt, built only from the task, manifest and contract.

    ``LANE_TO_STAGE`` and ``WorkerAssignment.for_lane`` are the single source of
    the lane -> role -> prompt mapping, so this never drifts from the driver.
    """
    assignment = WorkerAssignment.for_lane(contract, lane, contract.workspace)
    dod = "\n".join(f"- {item}" for item in task.dod)
    manifest_json = json.dumps(manifest, sort_keys=True, default=str)
    return (
        f"{assignment.prompt}\n"
        f"CANONICAL STAGE: {LANE_TO_STAGE[lane]}\n"
        f"TASK: {task.id} {task.title}\n"
        f"DEFINITION OF DONE:\n{dod}\n"
        f"MANIFEST: {manifest_json}\n"
        f"PRIOR EVENT COUNT: {len(events)}\n"
        "Judge only the current change on its own evidence."
    )


def _run_one_review(
    backend: AgentBackend,
    lane: Lane,
    task: Task,
    contract: ExecutionContract,
    manifest: dict,
    event_snapshot: tuple[NodeEvent, ...],
) -> ReviewResult:
    prompt = build_review_prompt(
        lane=lane, task=task, contract=contract, manifest=manifest, events=event_snapshot
    )
    captured: list[str] = []

    def _capture(session_id: str) -> None:
        captured.append(session_id)

    result = backend.run(AgentRole.REVIEW, prompt, on_session_id=_capture)
    if not result.ok:
        # A failed lane run is not a completed review: fail the swarm closed.
        raise ReviewProtocolError(
            f"{lane}: review lane interrupted (ok=False, interruption={result.interruption!r})"
        )
    session_id = (captured[-1] if captured else None) or (result.session_id or "")
    if not session_id.strip():
        raise ReviewProtocolError(f"{lane}: review session id is missing")
    findings = tuple(str(item) for item in (result.output.get("findings") or ()))
    dod_met = bool(result.output.get("dod_met"))
    return ReviewResult(
        lane=lane,
        result=result,
        session_id=session_id,
        findings=findings,
        dod_met=dod_met,
    )


def run_review_swarm(
    *,
    backend: AgentBackend,
    task: Task,
    contract: ExecutionContract,
    manifest: dict,
    events: Sequence[NodeEvent],
) -> ReviewSwarmResult:
    """Run both review lanes concurrently and join them fail-closed."""
    # Immutable snapshot: workers may read it, never append to the caller's list.
    event_snapshot = tuple(events)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            lane: pool.submit(
                _run_one_review, backend, lane, task, contract, manifest, event_snapshot
            )
            for lane in REVIEW_LANES
        }
        reviews: list[ReviewResult] = []
        for lane in REVIEW_LANES:
            try:
                reviews.append(futures[lane].result())
            except ReviewProtocolError:
                raise
            except Exception as exc:
                raise ReviewProtocolError(f"{lane}: review lane raised {exc!r}") from exc

    session_ids = [review.session_id for review in reviews]
    if len(set(session_ids)) != len(session_ids):
        raise ReviewProtocolError("reviewer sessions must be distinct")
    return ReviewSwarmResult(tuple(reviews), datetime.now(timezone.utc))


__all__ = [
    "REVIEW_LANES",
    "ReviewProtocolError",
    "ReviewResult",
    "ReviewSwarmResult",
    "build_review_prompt",
    "run_review_swarm",
]
