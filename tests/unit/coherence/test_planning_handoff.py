from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.planning.handoff import (
    HandoffError,
    build_downstream_menu,
    build_handoff,
    render_summary,
    validate_handoff,
    write_handoff,
)
from coherence.planning.model import PlanningFinding, PlanningReport

pytestmark = pytest.mark.unit


def _report(root: Path) -> PlanningReport:
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "plan.md").write_text("plan", encoding="utf-8")
    import hashlib
    digest = hashlib.sha256(b"plan").hexdigest()
    return PlanningReport(1, "run-001", True, ({"path": "docs/plan.md", "sha256": digest},),
                          (PlanningFinding("NOTE", "warning", "plan", "unresolved note"),),
                          (), True, None)


def test_clean_result_summary_and_menu_are_explicit_without_launching() -> None:
    report = _report(Path("."))
    summary = render_summary(report, semantic_notes=("semantic note",), unresolved=("open question",),
                             gate_summary={"status": "pass"})
    assert "semantic note" in summary and "open question" in summary
    assert "docs/plan.md" in summary and "pass" in summary
    menu = build_downstream_menu()
    assert [item["id"] for item in menu] == ["standard-development", "health-recovery", "feature-planning"]
    assert all(item["starts_automatically"] is False for item in menu)


def test_handoff_round_trip_is_hash_bound_and_paths_stay_in_run(tmp_path: Path) -> None:
    report = _report(tmp_path)
    (tmp_path / ".factory/planning/run-001").mkdir(parents=True)
    (tmp_path / ".factory/planning/run-001/semantic-review-report.json").write_text("{}", encoding="utf-8")
    payload = build_handoff(tmp_path, report, workflow="standard-development",
                            gate_summary={"status": "pass"})
    paths = write_handoff(tmp_path, payload)
    assert paths[0] == tmp_path / ".factory/planning/run-001/handoff.json"
    assert paths[1].read_text(encoding="utf-8").find("run-001") >= 0
    loaded = json.loads(paths[0].read_text(encoding="utf-8"))
    assert loaded["starts_automatically"] is False
    assert validate_handoff(tmp_path, paths[0]) == loaded
    (tmp_path / "docs/plan.md").write_text("changed", encoding="utf-8")
    with pytest.raises(HandoffError):
        validate_handoff(tmp_path, paths[0])


def test_invalid_workflow_fails_closed() -> None:
    with pytest.raises(HandoffError):
        build_downstream_menu("run-process")
