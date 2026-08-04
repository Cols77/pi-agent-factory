import json
from pathlib import Path

import pytest

from factory.orchestrator.backends import FakeAgentBackend
from factory.orchestrator.types import AgentResult, AgentRole
from factory.polish.bridge import PolishBridge
from factory.polish.orchestrator import PolishOrchestrator
from factory.polish.playground import PlaygroundSession
from factory.polish.worker import FixWorker, LandedChange

pytestmark = pytest.mark.unit


class _Pg:
    def list_usecases(self):
        return ["sign-in"]

    def setup(self, uc):
        return PlaygroundSession(entrypoints=["http://x"], describe="up")


class _FakeExecutor:  # stands in for WorktreeIsolatedExecutor
    def __init__(self):
        self.n = 0

    def execute(self, finding):
        self.n += 1
        return LandedChange(
            finding=finding,
            task_path=Path(f"tasks/T-{self.n:03d}.md"),
            task_id=f"T-{self.n:03d}",
            status="landed",
        )


def _orch(tmp_path, findings):
    backend = FakeAgentBackend(
        {AgentRole.SYNTHESIS: [AgentResult(ok=True, output={"findings": findings})]}
    )
    worker = FixWorker(_FakeExecutor())
    return PolishOrchestrator(_Pg(), backend, worker, open_nav=lambda e: None)


def test_publish_writes_state_with_incrementing_seq(tmp_path):
    orch = _orch(tmp_path, [{"description": "x"}])
    orch.setup("sign-in")
    b = PolishBridge(orch, tmp_path / "polish-state.json", tmp_path / "cmds")
    b.publish()
    b.publish()
    data = json.loads((tmp_path / "polish-state.json").read_text("utf-8"))
    assert data["seq"] == 2
    assert data["state"]["usecase"] == "sign-in"
    orch.teardown()


def test_poll_commands_dispatches_feedback_then_accept(tmp_path):
    orch = _orch(tmp_path, [{"description": "sign-in broken", "sr": "SR-010"}])
    orch.setup("sign-in")
    cmds = tmp_path / "cmds"
    cmds.mkdir()
    b = PolishBridge(orch, tmp_path / "polish-state.json", cmds)

    (cmds / "001.json").write_text(
        json.dumps({"kind": "feedback", "args": {"text": "broken"}}), "utf-8"
    )
    assert b.poll_commands() == 1
    assert not (cmds / "001.json").exists()  # consumed

    gid = orch.state()["gate1_ids"][0]
    (cmds / "002.json").write_text(
        json.dumps({"kind": "accept", "args": {"gid": gid}}), "utf-8"
    )
    assert b.poll_commands() == 1
    assert orch.state()["gate1"] == []
    orch.teardown()
