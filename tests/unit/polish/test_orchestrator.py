import time
from pathlib import Path

import pytest

from factory.orchestrator.backends import FakeAgentBackend
from factory.orchestrator.types import AgentResult, AgentRole
from factory.polish.orchestrator import PolishOrchestrator
from factory.polish.playground import PlaygroundSession
from factory.polish.worker import FixWorker, LandedChange

pytestmark = pytest.mark.unit


class _StubPlayground:
    def list_usecases(self):
        return ["sign-in"]

    def setup(self, usecase):
        return PlaygroundSession(entrypoints=["http://localhost:3000"], describe="up")


class _FakeExecutor:
    """Stands in for WorktreeIsolatedExecutor: returns a LandedChange per finding."""

    def __init__(self, statuses):
        self.statuses = statuses
        self.n = 0

    def execute(self, finding):
        self.n += 1
        st = self.statuses.pop(0)
        return LandedChange(
            finding=finding,
            task_path=Path(f"tasks/T-{self.n:03d}.md"),
            task_id=f"T-{self.n:03d}",
            status=st,
        )


def _backend(findings):
    return FakeAgentBackend(
        {AgentRole.SYNTHESIS: [AgentResult(ok=True, output={"findings": findings})]}
    )


def _wait_gate2(orch, n=1, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(orch.state()["gate2"]) >= n:
            return orch.state()["gate2"]
        time.sleep(0.02)
    raise AssertionError(f"gate2 did not reach {n} row(s) in time")


def test_feedback_to_gate1_to_worker_to_gate2(tmp_path):
    backend = _backend([{"description": "sign-in broken", "sr": "SR-010"}])
    worker = FixWorker(_FakeExecutor(["landed"]))
    orch = PolishOrchestrator(_StubPlayground(), backend, worker, open_nav=lambda eps: None)
    orch.setup("sign-in")  # starts the background worker thread
    gids = orch.submit_feedback("the sign in is broken")
    assert len(gids) == 1
    assert orch.state()["gate1"][0]["description"] == "sign-in broken"
    # accept -> the background worker drains it and calls record_landed itself
    orch.accept_finding(gids[0])
    row = _wait_gate2(orch)[0]
    assert row["status"] == "landed" and row["verdict"] == "pending"
    orch.teardown()


def test_gate2_rows_expose_the_failure_detail(tmp_path):
    # LandedChange.detail says WHY a fix failed; without it in state() the panel
    # shows a bare "failed" and the human has to go read serve's stdout.
    class _FailingExecutor:
        def execute(self, finding):
            return LandedChange(
                finding=finding,
                task_path=Path("tasks/T-001.md"),
                task_id="T-001",
                status="failed",
                detail="factory-run exited 0 but committed no fix for T-001",
            )

    backend = _backend([{"description": "pdf blank"}])
    orch = PolishOrchestrator(
        _StubPlayground(), backend, FixWorker(_FailingExecutor()), open_nav=lambda eps: None
    )
    orch.setup("sign-in")
    (gid,) = orch.submit_feedback("pdf is blank")
    orch.accept_finding(gid)
    row = _wait_gate2(orch)[0]
    assert row["status"] == "failed"
    assert "committed no fix" in row["detail"]
    orch.teardown()


def test_comment_requeues_rework(tmp_path):
    backend = _backend([{"description": "pdf blank"}])
    worker = FixWorker(_FakeExecutor(["landed"]))
    orch = PolishOrchestrator(_StubPlayground(), backend, worker, open_nav=lambda eps: None)
    orch.setup("sign-in")
    (gid,) = orch.submit_feedback("pdf is blank")
    orch.accept_finding(gid)
    g2 = _wait_gate2(orch)[0]["gid"]
    new_g1 = orch.comment(g2, "still blank")
    assert new_g1 in orch.state()["gate1_ids"]
    orch.teardown()
