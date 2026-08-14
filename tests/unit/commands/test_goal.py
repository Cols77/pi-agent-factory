"""`/goal` command shim tests (Task 6)."""

import pytest

from factory.commands.goal import create_goal, notify_goal_transition, parse_goal_cmd
from factory.goals.evaluator import GoalResult

pytestmark = pytest.mark.unit


def test_short_form_parses_requirement_metric_target():
    parsed = parse_goal_cmd("NAV-REQ-021 reacquisition_rate >= 0.90")
    assert parsed == {"requirement": "NAV-REQ-021", "metric": "reacquisition_rate", "target": ">= 0.90"}


def test_long_form_parses_key_values_and_feature():
    parsed = parse_goal_cmd(
        'FEAT-NAV-017 "Reacquisition accuracy" metric=reacquisition_rate target=">= 0.90" experiment=SIM-047'
    )
    assert parsed["feature"] == "FEAT-NAV-017"
    assert parsed["metric"] == "reacquisition_rate"
    assert parsed["target"] == ">= 0.90"
    assert parsed["source_experiment"] == "SIM-047"


def test_empty_arg_parses_to_empty():
    assert parse_goal_cmd("") == {}


def test_create_goal_writes_contract_goal(tmp_path):
    parsed = parse_goal_cmd(
        'FEAT-NAV-017 "Reacquisition accuracy" metric=reacquisition_rate target=">= 0.90" '
        "experiment=SIM-047 requirement=SR-032"
    )
    parsed["guardrails"] = [{"metric": "false_reacquisition_rate", "operator": "<=", "value": 0.03}]
    parsed["stop_rule"] = "all_met"
    goal = create_goal(tmp_path, parsed)
    assert goal.scope_errors == []
    assert goal.id == "GOAL-AUTO-001"
    assert goal.feature == ["FEAT-NAV-017"]
    assert goal.metric == {"name": "reacquisition_rate", "source_experiment": "SIM-047"}
    assert goal.guardrails
    assert goal.stop_rule == "all_met"
    assert (tmp_path / "goals" / "GOAL-AUTO-001.md").is_file()


def test_create_goal_rejects_missing_contract_fields(tmp_path):
    parsed = {"feature": "FEAT-NAV-017", "metric": "m", "target": ">= 0.9"}
    with pytest.raises(ValueError) as exc:
        create_goal(tmp_path, parsed)
    assert "guardrails" in str(exc.value)
    assert "stop_rule" in str(exc.value)


def test_create_goal_rejects_missing_base_fields(tmp_path):
    with pytest.raises(ValueError):
        create_goal(tmp_path, {"guardrails": [], "stop_rule": "all_met"})


def test_create_goal_never_reached(tmp_path):
    parsed = {
        "feature": "FEAT-NAV-017",
        "requirement": "SR-032",
        "metric": "m",
        "target": ">= 0.9",
        "guardrails": [{"metric": "x", "operator": "<=", "value": 0.1}],
        "stop_rule": "all_met",
        "state": "REACHED",
    }
    goal = create_goal(tmp_path, parsed)
    assert goal.state == "DECLARED"


def test_notify_reached_prints_spec16(capsys):
    result = GoalResult(
        goal_id="GOAL-NAV-003", state="REACHED", passed=True, value=0.93,
        target_value=0.90, operator=">=", evidence={},
    )
    notify_goal_transition("NOT_REACHED", result)
    assert "✓ GOAL REACHED" in capsys.readouterr().out


def test_notify_regressed_prints_spec17(capsys):
    result = GoalResult(
        goal_id="GOAL-NAV-003", state="REGRESSED", passed=False, value=0.82,
        target_value=0.90, operator=">=", evidence={},
    )
    notify_goal_transition("REACHED", result)
    assert "GOAL REGRESSED" in capsys.readouterr().out