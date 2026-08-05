import json

import pytest

from factory.orchestrator.ledger import load_tasks
from factory.polish.bridge import PolishBridge
from factory.polish.cli import (
    build_orchestrator,
    cmd_list,
    cmd_run,
    main,
    run_polish_serve,
    scope_guard_extension,
)

from ._fakes import make_orchestrator

pytestmark = pytest.mark.unit

_YAML = """
playgrounds:
  ref:
    type: scenario-replay
    usecases_dir: usecases
"""


def _project(tmp_path):
    fac = tmp_path / ".factory"
    fac.mkdir(parents=True)
    (tmp_path / "usecases").mkdir(parents=True)
    (fac / "factory.yaml").write_text(_YAML, encoding="utf-8")
    (tmp_path / "usecases" / "shark_warning.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_cmd_list(tmp_path):
    _project(tmp_path)
    assert cmd_list(tmp_path) == "ref:shark_warning"


def test_cmd_run_creates_tickets(tmp_path):
    _project(tmp_path)
    findings = tmp_path / "f.json"
    findings.write_text(
        json.dumps(
            [
                {"description": "ignored swimmer", "snapshot": {"t": 20}, "sr": "SR-001"},
                {"description": "slow response"},
            ]
        ),
        encoding="utf-8",
    )
    tasks_dir = tmp_path / "tasks"
    paths = cmd_run(
        tmp_path, "ref", "shark_warning", findings, tasks_dir, open_nav=lambda eps: None
    )
    assert len(paths) == 2
    tasks = load_tasks(tasks_dir)
    assert [t.satisfies for t in tasks] == [["SR-001"], []]


def test_main_list_exit_code(tmp_path, capsys):
    _project(tmp_path)
    rc = main(["list", "--project-root", str(tmp_path)])
    assert rc == 0
    assert "ref:shark_warning" in capsys.readouterr().out


def test_build_orchestrator_wires_from_config(tmp_path):
    # minimal .factory/factory.yaml with a dev-server playground
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "playgrounds:\n  web:\n    type: dev-server\n    browse_url: http://x\n"
        "    usecases: [sign-in]\n    services: []\n",
        encoding="utf-8",
    )
    orch = build_orchestrator(tmp_path, playground="web", provider=None, model=None)
    assert orch is not None
    assert hasattr(orch, "submit_feedback") and hasattr(orch, "state")


def test_scope_guard_extension_resolves_inside_the_factory_not_the_target_repo(tmp_path):
    # The scope-guard extension ships with the factory. Deriving it from the
    # polished project's root breaks every cross-repo polish session (the whole
    # point of Increment 2), and only at the first real SYNTHESIS call.
    ext = scope_guard_extension()
    assert ext.exists(), f"scope-guard extension missing at {ext}"
    assert tmp_path not in ext.parents


def test_serve_tears_down_even_if_the_first_publish_fails(tmp_path):
    # The opening publish must be inside the try: a throw there would otherwise
    # skip teardown entirely and leave both dev-servers running.
    orch = make_orchestrator([{"description": "x"}])
    orch.setup("sign-in")

    class _BoomBridge:
        def publish(self):
            raise OSError("state file unwritable")

        def poll_commands(self):
            return 0

    with pytest.raises(OSError):
        run_polish_serve(orch, _BoomBridge(), should_stop=lambda: True, poll_interval=0.0)

    # teardown ran: the playground session was released
    assert orch.state()["entrypoints"] == []


def test_serve_applies_a_command_then_stops(tmp_path):
    orch = make_orchestrator([{"description": "x"}])
    orch.setup("sign-in")
    cmds = tmp_path / "cmds"
    cmds.mkdir()
    (cmds / "001.json").write_text(
        json.dumps({"kind": "feedback", "args": {"text": "broken"}}), "utf-8"
    )
    bridge = PolishBridge(orch, tmp_path / "state.json", cmds)

    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return calls["n"] > 2  # let a couple of polls run

    run_polish_serve(orch, bridge, should_stop=should_stop, poll_interval=0.0)

    assert orch.state()["gate1_ids"]  # feedback was applied
    assert not (cmds / "001.json").exists()
