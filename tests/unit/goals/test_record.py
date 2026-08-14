"""Persistence tests: record() frontmatter update + append-only transition log."""

import json

import pytest
from pathlib import Path

import frontmatter

from factory.goals.evaluator import GoalResult, evaluate
from factory.goals.registry import record, transition_log_path
from factory.goals.schema import parse_goal

pytestmark = pytest.mark.unit


GOAL_MD = """---
id: GOAL-NAV-003
title: Reacquisition accuracy
feature: FEAT-NAV-017
requirements: [SR-032]
metric: {name: reacquisition_rate, source_experiment: SIM-047}
target: {operator: ">=", value: 0.90}
---

Prose body survives persistence.
"""


def _goal_path(tmp_path) -> Path:
    (tmp_path / "goals").mkdir()
    path = tmp_path / "goals" / "GOAL-NAV-003.md"
    path.write_text(GOAL_MD, encoding="utf-8")
    return path


def _result() -> GoalResult:
    # Build the exact result record() persists, without touching disk.
    return GoalResult(
        goal_id="GOAL-NAV-003",
        state="REACHED",
        passed=True,
        value=0.93,
        target_value=0.90,
        operator=">=",
        evidence={
            "experiment": "SIM-047",
            "run": "RUN-demo1",
            "commit": "sha1",
            "metrics_path": "evidence/runs/x/metrics.json",
            "recorded_at": "2026-08-01T00:00:00+00:00",
        },
    )


def test_record_updates_frontmatter_state_result_evidence(tmp_path):
    path = _goal_path(tmp_path)
    updated = record(_result(), path)
    post = frontmatter.load(str(path))
    meta = post.metadata
    assert meta["state"] == "REACHED"
    assert meta["result"] == {"value": 0.93, "target": 0.90, "operator": ">=", "passed": True}
    assert meta["evidence"]["run"] == "RUN-demo1"
    assert meta["evidence"]["commit"] == "sha1"
    assert updated.state == "REACHED"


def test_record_appends_history_never_rewrites(tmp_path):
    path = _goal_path(tmp_path)
    record(_result(), path)
    record(_result(), path)
    meta = frontmatter.load(str(path)).metadata
    assert len(meta["history"]) == 2
    assert meta["history"][0]["state"] == "REACHED"
    assert meta["history"][1]["recorded_at"] == "2026-08-01T00:00:00+00:00"


def test_record_preserves_body_and_other_metadata(tmp_path):
    path = _goal_path(tmp_path)
    record(_result(), path)
    post = frontmatter.load(str(path))
    assert "Prose body survives persistence." in post.content
    assert post.metadata["title"] == "Reacquisition accuracy"


def test_transition_log_is_append_only(tmp_path):
    path = _goal_path(tmp_path)
    record(_result(), path)
    record(_result(), path)
    log = transition_log_path("GOAL-NAV-003", tmp_path)
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["goal_id"] == "GOAL-NAV-003"
    assert first["from_state"] == "DECLARED"
    assert first["to_state"] == "REACHED"
    assert first["run"] == "RUN-demo1"
    assert first["recorded_at"] == "2026-08-01T00:00:00+00:00"


def test_record_on_unreadable_goal_raises(tmp_path):
    with pytest.raises(ValueError):
        record(_result(), tmp_path / "missing.md")


def test_regression_record_moves_state_forward(tmp_path):
    path = _goal_path(tmp_path)
    g = parse_goal(path)
    result = evaluate(g, 0.82, run_id="RUN-2", commit="sha2", metrics_path=Path("m.json"))
    assert result.state == "NOT_REACHED"
    updated = record(result, path)
    assert updated.state == "NOT_REACHED"
    # Second evaluation from REACHED history derives REGRESSED.
    reached = record(_result(), path)
    assert reached.state == "REACHED"