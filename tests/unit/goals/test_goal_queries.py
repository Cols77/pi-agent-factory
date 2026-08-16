"""`system.queries.query_goal` / `query_goals` tests (Task 5, additive)."""

import pytest
from pathlib import Path

from factory.system.queries import (
    ScopeKindError,
    ScopeNotFoundError,
    query_goal,
    query_goals,
)

pytestmark = pytest.mark.unit

GOAL = """---
id: GOAL-NAV-003
title: Reacquisition accuracy
feature: FEAT-NAV-017
requirements: [SR-032]
metric: {name: reacquisition_rate, source_experiment: SIM-047}
target: {operator: ">=", value: 0.90}
state: REACHED
evidence: {experiment: SIM-047, run: RUN-9, commit: sha9, metrics_path: m.json}
history:
  - {state: REACHED, run: RUN-9, recorded_at: "2026-08-01T00:00:00+00:00"}
---

Body.
"""

GOAL_OTHER = """---
id: GOAL-NAV-004
title: Another goal on the same feature
feature: FEAT-NAV-017
requirements: [SR-066]
demonstrates: SR-066
metric: {name: precision, source_experiment: SIM-048}
target: {operator: ">=", value: 0.85}
---

Body.
"""


def _write_goal(root: Path, name: str, text: str) -> None:
    (root / "goals").mkdir(parents=True, exist_ok=True)
    (root / "goals" / name).write_text(text, encoding="utf-8")


def test_query_goal_returns_contract_and_state(tmp_path):
    _write_goal(tmp_path, "GOAL-NAV-003.md", GOAL)
    payload = query_goal(tmp_path, "GOAL-NAV-003")
    assert payload["id"] == "GOAL-NAV-003"
    assert payload["state"] == "REACHED"
    assert payload["feature"] == ["FEAT-NAV-017"]
    assert payload["evidence"]["run"] == "RUN-9"
    assert payload["history"][0]["state"] == "REACHED"
    assert payload["scope_errors"] == []


def test_query_goal_unknown_id_raises(tmp_path):
    _write_goal(tmp_path, "GOAL-NAV-003.md", GOAL)
    with pytest.raises(ScopeNotFoundError):
        query_goal(tmp_path, "GOAL-NOPE")


def test_query_goals_feat_binds_by_declared_feature(tmp_path):
    _write_goal(tmp_path, "GOAL-NAV-003.md", GOAL)
    _write_goal(tmp_path, "GOAL-NAV-004.md", GOAL_OTHER)
    payload = query_goals(tmp_path, "feat:FEAT-NAV-017")
    assert {g["id"] for g in payload["goals"]} == {"GOAL-NAV-003", "GOAL-NAV-004"}


def test_query_goals_sr_binds_by_declared_requirement(tmp_path):
    _write_goal(tmp_path, "GOAL-NAV-003.md", GOAL)
    _write_goal(tmp_path, "GOAL-NAV-004.md", GOAL_OTHER)
    payload = query_goals(tmp_path, "sr:SR-032")
    assert [g["id"] for g in payload["goals"]] == ["GOAL-NAV-003"]


def test_query_goals_sr_binds_via_demonstrates_edge(tmp_path):
    _write_goal(tmp_path, "GOAL-NAV-004.md", GOAL_OTHER)
    payload = query_goals(tmp_path, "sr:SR-066")
    assert [g["id"] for g in payload["goals"]] == ["GOAL-NAV-004"]


def test_query_goals_goal_scope_returns_that_goal(tmp_path):
    _write_goal(tmp_path, "GOAL-NAV-003.md", GOAL)
    payload = query_goals(tmp_path, "goal:GOAL-NAV-003")
    assert [g["id"] for g in payload["goals"]] == ["GOAL-NAV-003"]


def test_query_goals_unknown_kind_rejected(tmp_path):
    with pytest.raises(ScopeKindError):
        query_goals(tmp_path, "task:T-001")


def test_query_goals_missing_identifier_rejected(tmp_path):
    with pytest.raises(ScopeKindError):
        query_goals(tmp_path, "feat:")


def test_query_goals_empty_repo_is_empty(tmp_path):
    payload = query_goals(tmp_path, "feat:FEAT-NAV-017")
    assert payload["goals"] == []