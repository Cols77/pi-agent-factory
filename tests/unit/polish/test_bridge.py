import json

import pytest

from factory.polish.bridge import PolishBridge

from ._fakes import make_orchestrator

pytestmark = pytest.mark.unit


def test_publish_writes_state_with_incrementing_seq(tmp_path):
    orch = make_orchestrator([{"description": "x"}])
    orch.setup("sign-in")
    b = PolishBridge(orch, tmp_path / "polish-state.json", tmp_path / "cmds")
    b.publish()
    b.publish()
    data = json.loads((tmp_path / "polish-state.json").read_text("utf-8"))
    assert data["seq"] == 2
    assert data["state"]["usecase"] == "sign-in"
    orch.teardown()


def test_poll_commands_dispatches_feedback_then_accept(tmp_path):
    orch = make_orchestrator([{"description": "sign-in broken", "sr": "SR-010"}])
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


def test_poll_commands_skips_half_written_file(tmp_path):
    orch = make_orchestrator([{"description": "x"}])
    orch.setup("sign-in")
    cmds = tmp_path / "cmds"
    cmds.mkdir()
    b = PolishBridge(orch, tmp_path / "polish-state.json", cmds)

    (cmds / "001.json").write_text('{"kind": "feed', "utf-8")  # truncated mid-write
    assert b.poll_commands() == 0
    assert (cmds / "001.json").exists()  # left for the next poll, not consumed
    orch.teardown()
