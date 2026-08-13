"""`factory goals` CLI tests (Task 5)."""

import json

import pytest

from factory.goals.cli import main
from factory.goals.schema import parse_goal

pytestmark = pytest.mark.unit


def _run(tmp_path, *args):
    return main([str(a) for a in (*args, "--repo", str(tmp_path))])


def test_list_empty_repo(tmp_path, capsys):
    assert _run(tmp_path, "list") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["goals"] == []


def test_create_writes_goal_file(tmp_path):
    rc = _run(
        tmp_path,
        "create",
        "--id",
        "GOAL-NAV-003",
        "--title",
        "Reacquisition accuracy",
        "--feature",
        "FEAT-NAV-017",
        "--requirements",
        "SR-032",
        "--metric",
        "reacquisition_rate",
        "--source-experiment",
        "SIM-047",
        "--target",
        ">= 0.90",
    )
    assert rc == 0
    path = tmp_path / "goals" / "GOAL-NAV-003.md"
    assert path.is_file()
    goal = parse_goal(path)
    assert goal.scope_errors == []
    assert goal.metric == {"name": "reacquisition_rate", "source_experiment": "SIM-047"}
    assert goal.target == {"operator": ">=", "value": 0.90}
    assert goal.state == "DECLARED"


def test_create_refuses_existing_file(tmp_path):
    _run(tmp_path, "create", "--id", "GOAL-X", "--title", "t", "--feature", "FEAT-A",
         "--requirements", "SR-1", "--metric", "m", "--source-experiment", "SIM-1", "--target", ">= 1.0")
    with pytest.raises(SystemExit):
        _run(tmp_path, "create", "--id", "GOAL-X", "--title", "t", "--feature", "FEAT-A",
             "--requirements", "SR-1", "--metric", "m", "--source-experiment", "SIM-1", "--target", ">= 1.0")


def test_show_round_trips(tmp_path, capsys):
    _run(tmp_path, "create", "--id", "GOAL-NAV-003", "--title", "Reacquisition accuracy",
         "--feature", "FEAT-NAV-017", "--requirements", "SR-032", "--metric", "reacquisition_rate",
         "--source-experiment", "SIM-047", "--target", ">= 0.90")
    capsys.readouterr()  # drain create's payload
    assert _run(tmp_path, "show", "GOAL-NAV-003") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "GOAL-NAV-003"
    assert payload["state"] == "DECLARED"
    assert payload["target"] == {"operator": ">=", "value": 0.90}


def test_set_state_legal_transition(tmp_path):
    _run(tmp_path, "create", "--id", "GOAL-NAV-003", "--title", "t", "--feature", "FEAT-NAV-017",
         "--requirements", "SR-032", "--metric", "reacquisition_rate", "--source-experiment", "SIM-047",
         "--target", ">= 0.90")
    assert _run(tmp_path, "set-state", "GOAL-NAV-003", "ACTIVE") == 0
    assert parse_goal(tmp_path / "goals" / "GOAL-NAV-003.md").state == "ACTIVE"


def test_set_state_illegal_transition_fails(tmp_path):
    _run(tmp_path, "create", "--id", "GOAL-NAV-003", "--title", "t", "--feature", "FEAT-NAV-017",
         "--requirements", "SR-032", "--metric", "reacquisition_rate", "--source-experiment", "SIM-047",
         "--target", ">= 0.90")
    with pytest.raises(SystemExit):
        _run(tmp_path, "set-state", "GOAL-NAV-003", "REACHED")  # DECLARED -> REACHED illegal


def test_evaluate_records_state_and_history(tmp_path, capsys):
    _run(tmp_path, "create", "--id", "GOAL-NAV-003", "--title", "t", "--feature", "FEAT-NAV-017",
         "--requirements", "SR-032", "--metric", "reacquisition_rate", "--source-experiment", "SIM-047",
         "--target", ">= 0.90")
    capsys.readouterr()
    assert _run(tmp_path, "evaluate", "GOAL-NAV-003", "--value", "0.93", "--run", "RUN-1",
                "--commit", "abc", "--metrics", "evidence/runs/x/metrics.json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "REACHED"
    goal = parse_goal(tmp_path / "goals" / "GOAL-NAV-003.md")
    assert goal.state == "REACHED"
    assert len(goal.history) == 1
    assert (tmp_path / "goals" / "GOAL-NAV-003-transitions.jsonl").is_file()


def test_history_after_evaluation(tmp_path, capsys):
    _run(tmp_path, "create", "--id", "GOAL-NAV-003", "--title", "t", "--feature", "FEAT-NAV-017",
         "--requirements", "SR-032", "--metric", "reacquisition_rate", "--source-experiment", "SIM-047",
         "--target", ">= 0.90")
    _run(tmp_path, "evaluate", "GOAL-NAV-003", "--value", "0.93", "--run", "RUN-1")
    _run(tmp_path, "evaluate", "GOAL-NAV-003", "--value", "0.82", "--run", "RUN-2")
    capsys.readouterr()
    assert _run(tmp_path, "history", "GOAL-NAV-003") == 0
    payload = json.loads(capsys.readouterr().out)
    assert [h["state"] for h in payload["history"]] == ["REACHED", "REGRESSED"]


def test_show_unknown_goal_exits_nonzero(tmp_path):
    with pytest.raises(SystemExit):
        _run(tmp_path, "show", "GOAL-NOPE")