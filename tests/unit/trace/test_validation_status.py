from __future__ import annotations

import json
from pathlib import Path

import pytest
from factory.goals.schema import Goal
from factory.trace.validation_status import load_validation, requirement_validation

pytestmark = pytest.mark.unit


# A report must declare its provenance to be readable at all (review round
# 3, Critical 2); these fixtures stand in for harness-emitted reports.
_PROVENANCE = {"recorded_by": "harness", "recorded_at": "2026-01-01T00:00:00Z", "command": "coherence-measurement run"}


def _report(tmp_path: Path, entries: list[dict]) -> None:
    path = tmp_path / "validation" / "validation-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"provenance": _PROVENANCE, "requirements": entries}), encoding="utf-8"
    )


def test_passing_entry(tmp_path):
    _report(
        tmp_path,
        [{
            "id": "SR-001", "domain": "behavioral", "metric": "preemption_success_rate",
            "value": 1.0, "assert": ">= 0.90", "passed": True, "trials": 3,
            "declared_trials": 3, "stale": False, "artifacts": ["traces/shark.json"],
        }],
    )

    status = load_validation(tmp_path)["SR-001"]

    assert status.state == "passed"
    assert status.stale is False
    assert status.value == 1.0
    assert status.assert_expr == ">= 0.90"
    assert status.trials == 3
    assert status.declared_trials == 3
    assert status.artifacts == ["traces/shark.json"]


def test_failing_entry(tmp_path):
    _report(tmp_path, [{"id": "SR-002", "passed": False, "stale": False}])

    assert load_validation(tmp_path)["SR-002"].state == "failed"


def test_harness_error_entry_is_its_own_state(tmp_path):
    _report(tmp_path, [{"id": "SR-003", "error": "unknown harness: bogus"}])

    status = load_validation(tmp_path)["SR-003"]

    assert status.state == "error"
    assert status.error == "unknown harness: bogus"


def test_stale_is_orthogonal_to_passed(tmp_path):
    # The dangerous state: green earned against a statement that has since changed.
    _report(tmp_path, [{"id": "SR-004", "passed": True, "stale": True}])

    status = load_validation(tmp_path)["SR-004"]

    assert status.state == "passed"
    assert status.stale is True


def test_missing_report_yields_empty_map_not_an_error(tmp_path):
    assert load_validation(tmp_path) == {}


def test_unreadable_report_yields_empty_map(tmp_path):
    path = tmp_path / "validation" / "validation-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert load_validation(tmp_path) == {}


# ── Task 7: derived goal-aware requirement status (additive) ─────────────


def _goal(state: str) -> Goal:
    return Goal(id="GOAL-NAV-003", title="t", path=Path("goals/x.md"), state=state)  # type: ignore[arg-type]


def test_no_goals_yields_none():
    assert requirement_validation([]) is None


def test_goal_all_reached_yields_validated():
    assert requirement_validation([_goal("REACHED"), _goal("REACHED")]) == "VALIDATED"


def test_goal_any_regressed_yields_regressed():
    assert requirement_validation([_goal("REACHED"), _goal("REGRESSED")]) == "REGRESSED"


def test_goal_none_reached_yields_verification_pending():
    assert requirement_validation([_goal("DECLARED"), _goal("NOT_REACHED")]) == "VERIFICATION_PENDING"


def test_goal_blocked_counts_as_pending_not_reached():
    assert requirement_validation([_goal("BLOCKED")]) == "VERIFICATION_PENDING"


# ── Inc 7 Task 4: VERIFICATION_STALE (additive, spec §28–§30) ──────────────


def test_stale_validation_of_reached_goals_yields_verification_stale():
    # Code/statement changed since the evidence: green goals alone must not
    # read as VALIDATED (spec §30 A→C example).
    assert requirement_validation([_goal("REACHED")], stale=True) == "VERIFICATION_STALE"


def test_stale_validation_without_reached_goals_stays_pending():
    # Nothing validated yet; staleness does not upgrade PENDING.
    assert requirement_validation([_goal("NOT_REACHED")], stale=True) == "VERIFICATION_PENDING"


def test_regressed_beats_stale():
    # A regressed goal is the stronger signal even when evidence is stale.
    assert (
        requirement_validation([_goal("REGRESSED")], stale=True) == "REGRESSED"
    )


def test_stale_defaults_false_keeps_v1_behavior():
    assert requirement_validation([_goal("REACHED")]) == "VALIDATED"
    assert requirement_validation([]) is None
