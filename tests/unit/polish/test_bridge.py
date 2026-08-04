import json

import pytest

from factory.polish import bridge as bridge_mod
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


def test_publish_retries_a_transiently_locked_rename(tmp_path, monkeypatch):
    # Windows holds files open without delete-share: the UI polls polish-state.json
    # every 200ms while this republishes, so os.replace hits WinError 5. Observed
    # live -- an unretried replace killed the whole serve loop and both dev-servers.
    real_replace = bridge_mod.os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(bridge_mod.os, "replace", flaky_replace)
    monkeypatch.setattr(bridge_mod, "_RETRY_SLEEP_S", 0.0)

    orch = make_orchestrator([{"description": "x"}])
    orch.setup("sign-in")
    b = PolishBridge(orch, tmp_path / "polish-state.json", tmp_path / "cmds")
    b.publish()

    assert calls["n"] == 3  # retried twice, then succeeded
    assert json.loads((tmp_path / "polish-state.json").read_text("utf-8"))["seq"] == 1
    assert not (tmp_path / "polish-state.json.tmp").exists()
    orch.teardown()


def test_publish_gives_up_without_leaking_a_tmp_file(tmp_path, monkeypatch):
    def always_denied(src, dst):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(bridge_mod.os, "replace", always_denied)
    monkeypatch.setattr(bridge_mod, "_RETRY_SLEEP_S", 0.0)

    orch = make_orchestrator([{"description": "x"}])
    orch.setup("sign-in")
    b = PolishBridge(orch, tmp_path / "polish-state.json", tmp_path / "cmds")
    with pytest.raises(PermissionError):
        b.publish()
    assert not (tmp_path / "polish-state.json.tmp").exists()
    orch.teardown()


def test_poll_commands_reads_a_bom_prefixed_command(tmp_path):
    # Command files may be written by tools that emit a UTF-8 BOM; a BOM made
    # json.loads raise, so the file was skipped forever instead of applied.
    orch = make_orchestrator([{"description": "x"}])
    orch.setup("sign-in")
    cmds = tmp_path / "cmds"
    cmds.mkdir()
    b = PolishBridge(orch, tmp_path / "polish-state.json", cmds)

    (cmds / "001.json").write_text(
        json.dumps({"kind": "feedback", "args": {"text": "broken"}}), encoding="utf-8-sig"
    )
    assert b.poll_commands() == 1
    assert orch.state()["gate1_ids"]
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
