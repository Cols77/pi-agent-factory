import json

import pytest
from factory.orchestrator.ledger import load_tasks
from factory.polish.cli import build_orchestrator, cmd_list, cmd_run, main

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
