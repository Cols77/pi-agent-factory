"""Goal schema + registry tests (Task 2)."""

import pytest

from factory.goals.registry import DuplicateGoalIdError, load_goals
from factory.goals.schema import parse_goal

pytestmark = pytest.mark.unit

_WELL_FORMED = """---
id: GOAL-NAV-003
title: Reacquisition accuracy on the NAV feature
feature: FEAT-NAV-017
requirements: [SR-032]
metric: {name: reacquisition_rate, source_experiment: SIM-047}
target: {operator: ">=", value: 0.90}
state: DECLARED
version: 1
---

Prose body after frontmatter.
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_well_formed_goal(tmp_path):
    path = _write(tmp_path, "GOAL-NAV-003.md", _WELL_FORMED)
    goal = parse_goal(path)
    assert goal.scope_errors == []
    assert goal.id == "GOAL-NAV-003"
    assert goal.title == "Reacquisition accuracy on the NAV feature"
    assert goal.feature == ["FEAT-NAV-017"]
    assert goal.requirements == ["SR-032"]
    assert goal.metric == {"name": "reacquisition_rate", "source_experiment": "SIM-047"}
    assert goal.target == {"operator": ">=", "value": 0.90}
    assert goal.state == "DECLARED"
    assert goal.version == 1


def test_scalar_feature_coerced_to_list(tmp_path):
    path = _write(tmp_path, "GOAL-X.md", _WELL_FORMED)
    goal = parse_goal(path)
    assert goal.feature == ["FEAT-NAV-017"]


def test_state_defaults_to_declared(tmp_path):
    # Without a state field, DEFFFFAULT is DECLARED.
    text = _WELL_FORMED.replace("state: DECLARED\n", "")
    goal = parse_goal(_write(tmp_path, "GOAL-Y.md", text))
    assert goal.scope_errors == []
    assert goal.state == "DECLARED"


def test_missing_required_field_degrades_to_scope_error(tmp_path):
    text = _WELL_FORMED.replace("feature: FEAT-NAV-017\n", "")
    goal = parse_goal(_write(tmp_path, "GOAL-Z.md", text))
    assert goal.scope_errors, "expected a schema error for the missing feature"
    assert goal.id == "GOAL-NAV-003"  # identity still recovered


def test_unreadable_goal_degrades_never_raises(tmp_path):
    goal = parse_goal(tmp_path / "does-not-exist.md")
    assert goal.scope_errors
    assert goal.id == ""


def test_load_goals_absent_dir_is_empty(tmp_path):
    assert load_goals(tmp_path) == {}


def test_load_goals_keys_by_id(tmp_path):
    (tmp_path / "goals").mkdir()
    _write(tmp_path / "goals", "GOAL-NAV-003.md", _WELL_FORMED)
    other = _WELL_FORMED.replace("GOAL-NAV-003", "GOAL-NAV-004")
    _write(tmp_path / "goals", "GOAL-NAV-004.md", other)
    loaded = load_goals(tmp_path)
    assert set(loaded) == {"GOAL-NAV-003", "GOAL-NAV-004"}
    assert loaded["GOAL-NAV-003"].path.name == "GOAL-NAV-003.md"


def test_load_goals_skips_documents_without_id(tmp_path):
    (tmp_path / "goals").mkdir()
    _write(tmp_path / "goals", "GOAL-NOID.md", "---\ntitle: No id here\n---\nbody\n")
    _write(tmp_path / "goals", "GOAL-NAV-003.md", _WELL_FORMED)
    assert set(load_goals(tmp_path)) == {"GOAL-NAV-003"}


def test_duplicate_id_raises(tmp_path):
    (tmp_path / "goals").mkdir()
    _write(tmp_path / "goals", "GOAL-NAV-003.md", _WELL_FORMED)
    # Second file claims the same id (must be a GOAL-* filename to count).
    _write(tmp_path / "goals", "GOAL-NAV-003b.md", _WELL_FORMED)
    with pytest.raises(DuplicateGoalIdError):
        load_goals(tmp_path)


def test_duplicate_id_is_a_value_error(tmp_path):
    (tmp_path / "goals").mkdir()
    _write(tmp_path / "goals", "GOAL-A.md", _WELL_FORMED)
    _write(tmp_path / "goals", "GOAL-B.md", _WELL_FORMED)
    with pytest.raises(ValueError):
        load_goals(tmp_path)