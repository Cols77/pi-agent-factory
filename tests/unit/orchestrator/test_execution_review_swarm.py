"""SR-034 review-swarm protocol tests (RED first).

The swarm runs two fresh ``AgentRole.REVIEW`` sessions concurrently, each with
its own prompt and its own session; the join fails closed on a missing or a
duplicated session id, and the caller's event list is never mutated.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from factory.orchestrator.execution_contract import ExecutionContract
from factory.orchestrator.review_swarm import (
    REVIEW_LANES,
    ReviewProtocolError,
    ReviewResult,
    ReviewSwarmResult,
    run_review_swarm,
)
from factory.orchestrator.types import AgentRole
from substrate.agents.model import AgentResult
from substrate.ledger.tasks import Task

pytestmark = pytest.mark.unit


def contract_fixture(workspace: Path) -> ExecutionContract:
    return ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="governed-execution/v1",
        workspace=workspace,
        required_gates=("unit",),
        satisfies=("SR-034", "SR-049"),
        plan_ref="docs/superpowers/plans/plan.md",
        spec_ref=None,
        max_fixer_iterations=2,
    )


def task_fixture(tmp_path: Path) -> Task:
    return Task(
        id="T-013",
        title="Governed execution driver",
        status="todo",
        dod=["both reviews reported"],
        body="",
        path=tmp_path / "T-013.md",
    )


def _result_for(prompt: str) -> AgentResult:
    if "SPEC-COMPLIANCE" in prompt:
        return AgentResult(
            ok=True,
            output={"findings": ["spec ok"], "dod_met": True},
            session_id="review-session-1",
        )
    return AgentResult(
        ok=True,
        output={"findings": ["quality ok"], "dod_met": True},
        session_id="review-session-2",
    )


class BarrierBackend:
    """Both workers must be in flight simultaneously or the barrier times out."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._barrier = threading.Barrier(2, timeout=5)
        self.calls: list[tuple[str, str]] = []
        self.first_started_at: datetime | None = None
        self.dev_calls: int = 0

    def run(self, role, prompt, on_snippet=None, on_session_id=None):  # noqa: ANN001
        with self._lock:
            if role is AgentRole.DEV:
                self.dev_calls += 1
            if self.first_started_at is None:
                self.first_started_at = datetime.now(timezone.utc)
            self.calls.append((role.value, prompt))
        result = _result_for(prompt)
        self._barrier.wait()
        time.sleep(0.01)  # model review latency so completed_at is strictly later
        if on_session_id is not None:
            on_session_id(result.session_id or "")
        return result


class _NullSessionBackend:
    def run(self, role, prompt, on_snippet=None, on_session_id=None):  # noqa: ANN001
        if on_session_id is not None:
            on_session_id("")
        return AgentResult(ok=True, output={}, session_id=None)


class _DuplicateSessionBackend:
    def run(self, role, prompt, on_snippet=None, on_session_id=None):  # noqa: ANN001
        if on_session_id is not None:
            on_session_id("same-session")
        return AgentResult(ok=True, output={}, session_id="same-session")


def test_review_swarm_waits_for_both_fresh_review_sessions(tmp_path: Path) -> None:
    backend = BarrierBackend()
    events: list[object] = []

    result = run_review_swarm(
        backend=backend,
        task=task_fixture(tmp_path),
        contract=contract_fixture(tmp_path / "worktree"),
        manifest={},
        events=events,  # type: ignore[arg-type]
    )

    assert {review.lane for review in result.reviews} == {"spec-review", "quality-review"}
    assert [review.lane for review in result.reviews] == list(REVIEW_LANES)
    assert {review.session_id for review in result.reviews} == {
        "review-session-1",
        "review-session-2",
    }
    assert result.completed_at > backend.first_started_at  # type: ignore[operator]
    assert backend.calls and all(
        "prior review output" not in prompt for _, prompt in backend.calls
    )
    # No fixer can be dispatched from the swarm, and the caller's list is untouched.
    assert backend.dev_calls == 0
    assert events == []
    assert result.review_for("spec-review").session_id == "review-session-1"
    assert result.review_for("quality-review").session_id == "review-session-2"


def test_review_session_ids_must_be_present_and_distinct(tmp_path: Path) -> None:
    for backend in (_NullSessionBackend(), _DuplicateSessionBackend()):
        with pytest.raises(ReviewProtocolError):
            run_review_swarm(
                backend=backend,
                task=task_fixture(tmp_path),
                contract=contract_fixture(tmp_path / "worktree"),
                manifest={},
                events=[],
            )


def test_review_for_is_a_closed_lane_lookup(tmp_path: Path) -> None:
    review = ReviewResult(
        lane="spec-review",
        result=AgentResult(ok=True, output={}, session_id="s"),
        session_id="s",
        findings=(),
        dod_met=True,
    )
    complete = ReviewSwarmResult((review,), datetime.now(timezone.utc))

    with pytest.raises(ReviewProtocolError):
        complete.review_for("quality-review")  # missing lane
    with pytest.raises(ReviewProtocolError):
        complete.review_for("fixer")  # unknown lane  # type: ignore[arg-type]

    duplicated = ReviewSwarmResult(
        (review, ReviewResult("spec-review", review.result, "t", (), True)),
        datetime.now(timezone.utc),
    )
    with pytest.raises(ReviewProtocolError):
        duplicated.review_for("spec-review")
