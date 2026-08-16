"""vcycle_health findings (Inc 7 Task 5).

The derived-impact probe reuses trace gaps + goal registry + simulation
registry to surface missing/inconsistent V-cycle relationships. Findings
are deterministic, sorted, and pending-only (deferred/exempt gaps are
explicit acceptances and never reported).
"""

from __future__ import annotations

import json

import pytest

from factory.system import health

pytestmark = pytest.mark.unit


def _write_sr(root, req_id, *, binding=True, stale_report=False):
    req_dir = root / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    binding_yaml = (
        "binding:\n  experiment: e\n  metric: m\n  assert: a\n  harness: h\n"
        if binding
        else ""
    )
    (req_dir / f"{req_id}.md").write_text(
        f"---\nid: {req_id}\ntitle: T\nstatement: s\ndomain: d\n"
        f"{binding_yaml}---\nbody\n",
        encoding="utf-8",
    )
    if binding and stale_report:
        report = root / "validation" / "validation-report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps({"requirements": [{"id": req_id, "passed": True, "stale": True}]}),
            encoding="utf-8",
        )


def _write_task(root, task_id, sr_id=None):
    tasks_dir = root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    satisfies = f"satisfies: ['{sr_id}']\n" if sr_id else ""
    (tasks_dir / f"{task_id}.md").write_text(
        f"---\nid: {task_id}\ntitle: T\nstatus: done\n{satisfies}---\nbody\n",
        encoding="utf-8",
    )


def _write_goal(root, goal_id, *, metric=None):
    goals_dir = root / "goals"
    goals_dir.mkdir(parents=True, exist_ok=True)
    metric_yaml = f"metric: {metric}\n" if metric else ""
    (goals_dir / f"{goal_id}.md").write_text(
        f"---\nid: {goal_id}\ntitle: G\ndemonstrates: [SR-999]\n{metric_yaml}---\n",
        encoding="utf-8",
    )


def _write_run(root, run_id, *, commit="c" * 40, result="passed"):
    run_dir = root / "evidence" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"run": run_id, "experiment": "SIM-047", "feature": "FEAT-001"}
    if commit is not None:
        manifest["commit"] = commit
    if result is not None:
        manifest["result"] = result
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _codes(findings):
    return [(f.code, f.subject) for f in findings]


def test_requirement_without_test(tmp_path):
    _write_sr(tmp_path, "SR-001", binding=True)
    findings = health.vcycle_health(tmp_path)
    assert ("REQ_NO_TEST", "sr:SR-001") in _codes(findings)


def test_requirement_without_implementation(tmp_path):
    _write_sr(tmp_path, "SR-002", binding=True)
    findings = health.vcycle_health(tmp_path)
    assert ("REQ_NO_IMPLEMENTATION", "sr:SR-002") in _codes(findings)


def test_implementation_without_traceable_requirement(tmp_path):
    _write_task(tmp_path, "T-001")
    findings = health.vcycle_health(tmp_path)
    assert ("IMPL_NO_REQ", "task:T-001") in _codes(findings)


def test_satisfied_and_validated_requirement_has_no_finding(tmp_path):
    _write_sr(tmp_path, "SR-003", binding=True)
    _write_task(tmp_path, "T-003", "SR-003")
    report_dir = tmp_path / "validation"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "validation-report.json").write_text(
        json.dumps({"requirements": [{"id": "SR-003", "passed": True, "stale": False}]}),
        encoding="utf-8",
    )
    findings = health.vcycle_health(tmp_path)
    assert not any(f.subject == "sr:SR-003" for f in findings)


def test_goal_without_metric(tmp_path):
    _write_goal(tmp_path, "GOAL-001")
    findings = health.vcycle_health(tmp_path)
    assert ("GOAL_NO_METRIC", "goal:GOAL-001") in _codes(findings)


def test_goal_metric_without_experiment(tmp_path):
    _write_goal(tmp_path, "GOAL-002", metric='{"name": "reacquisition_rate"}')
    findings = health.vcycle_health(tmp_path)
    assert ("GOAL_NO_EXPERIMENT", "goal:GOAL-002") in _codes(findings)


def test_simulation_without_commit(tmp_path):
    _write_run(tmp_path, "RUN-20260816-0100", commit=None)
    findings = health.vcycle_health(tmp_path)
    assert ("RUN_NO_COMMIT", "run:RUN-20260816-0100") in _codes(findings)


def test_stale_evidence_finding(tmp_path):
    _write_sr(tmp_path, "SR-004", binding=True, stale_report=True)
    findings = health.vcycle_health(tmp_path)
    assert ("REQ_STALE", "sr:SR-004") in _codes(findings)


def test_feature_with_failing_latest_verification(tmp_path):
    # Need a feature file + SR + run to trigger the finding
    feat_dir = tmp_path / "docs" / "features"
    feat_dir.mkdir(parents=True, exist_ok=True)
    (feat_dir / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test feature\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    _write_sr(tmp_path, "SR-001", binding=True)
    _write_run(tmp_path, "RUN-20260816-0200", result="failed")
    findings = health.vcycle_health(tmp_path)
    assert ("FEATURE_FAILING_VERIFICATION", "feat:FEAT-001") in _codes(findings)


def test_feature_with_passing_latest_run_has_no_failing_finding(tmp_path):
    feat_dir = tmp_path / "docs" / "features"
    feat_dir.mkdir(parents=True, exist_ok=True)
    (feat_dir / "FEAT-002.md").write_text(
        "---\nid: FEAT-002\ntitle: Test feature\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    _write_sr(tmp_path, "SR-007", binding=True)
    _write_run(tmp_path, "RUN-20260816-0300", result="passed")
    findings = health.vcycle_health(tmp_path)
    assert not any(f.code == "FEATURE_FAILING_VERIFICATION" for f in findings)


def test_deferred_gap_is_not_reported(tmp_path):
    req_dir = tmp_path / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    (req_dir / "SR-006.md").write_text(
        "---\nid: SR-006\ntitle: T\nstatement: s\ndomain: d\n"
        "trace_deferred: waiting on hardware\n---\nbody\n",
        encoding="utf-8",
    )
    findings = health.vcycle_health(tmp_path)
    assert not any(f.subject == "sr:SR-006" for f in findings)


def test_findings_are_deterministically_sorted(tmp_path):
    _write_sr(tmp_path, "SR-010", binding=True)
    _write_sr(tmp_path, "SR-002", binding=True)
    _write_task(tmp_path, "T-002")
    findings = health.vcycle_health(tmp_path)
    codes = [f.code for f in findings]
    assert codes == sorted(codes)
    # Same input twice -> identical output.
    assert _codes(health.vcycle_health(tmp_path)) == _codes(findings)


def test_query_health_includes_vcycle_findings(tmp_path):
    _write_sr(tmp_path, "SR-001", binding=True)
    payload = health.query_health(tmp_path)
    assert "vcycle_findings" in payload
    assert any(f["code"] == "REQ_NO_IMPLEMENTATION" for f in payload["vcycle_findings"])
