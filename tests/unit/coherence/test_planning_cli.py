from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from coherence.cli import main
from coherence.planning.run import planning_report_digest

pytestmark = pytest.mark.unit


INTENT = {
    "schema": 1,
    "prompt": "Build a deterministic planner",
    "answers": [
        {"id": "goal", "text": "Build a deterministic planner"},
        {"id": "constraint-files", "text": "Files remain canonical"},
    ],
}

SPEC = """---
id: intent-spec
title: Intent Specification
status: draft
---
# Intent Specification

### goal

The goal is to build a deterministic planner.
The constraint-files rule says files remain canonical.
"""

PLAN = """---
spec_ref: intent-spec.md
---
# Deterministic Planner Plan

### Task 1: First Task

**Files:**
- Create: `src/first.py`

**Interfaces:**
- Produces: `goal` support.

### Task 2: Second Task

**Files:**
- Create: `src/second.py`

**Interfaces:**
- Produces: `constraint-files` support.
"""


def _write_fixture(root: Path, *, complete: bool) -> tuple[Path, Path, Path]:
    intent = root / ".intent" / "intent.json"
    spec = root / "docs" / "superpowers" / "specs" / "intent-spec.md"
    plan = root / "docs" / "superpowers" / "plans" / "intent-plan.md"
    for path in (intent, spec, plan):
        path.parent.mkdir(parents=True, exist_ok=True)
    intent.write_text(json.dumps(INTENT), encoding="utf-8")
    spec.write_text(SPEC, encoding="utf-8")
    plan.write_text(PLAN, encoding="utf-8")

    if complete:
        tasks = ((2, "Second"), (1, "First"))
        tasks_dir = root / "tasks"
        tasks_dir.mkdir()
        for number, title in tasks:
            (tasks_dir / f"T-{number:03d}-{title.lower()}.md").write_text(
                "---\n"
                f"id: T-{number:03d}\n"
                f"title: {title} Task\n"
                "status: todo\n"
                "source_plan: docs/superpowers/plans/intent-plan.md\n"
                f"source_task: {number}\n"
                "---\n",
                encoding="utf-8",
            )
        requirement_ids = ("SR-001", "SR-002")
        requirements_dir = root / "requirements"
        requirements_dir.mkdir()
        for req_id in requirement_ids:
            (requirements_dir / f"{req_id}.md").write_text(
                "---\n"
                f"id: {req_id}\n"
                f"title: {req_id} requirement\n"
                f"statement: {req_id} statement\n"
                "domain: behavioral\n"
                "upstream: []\n"
                "source: docs/superpowers/specs/intent-spec.md#goal\n"
                "---\n",
                encoding="utf-8",
            )
        feature_path = root / "docs" / "features" / "FEAT-017.md"
        feature_path.parent.mkdir(parents=True, exist_ok=True)
        feature_path.write_text(
            "---\n"
            "id: FEAT-017\n"
            "title: Planning Bootstrap\n"
            "requirements: [SR-001, SR-002]\n"
            "---\n",
            encoding="utf-8",
        )
        bundle_path = root / "bundles" / "FEAT-017.json"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps({"id": "FEAT-017", "members": ["feat:FEAT-017", "sr:SR-001", "sr:SR-002"]}),
            encoding="utf-8",
        )
        consent_path = root / ".factory" / "planning" / "run-001" / "requirement-consent.json"
        consent_path.parent.mkdir(parents=True, exist_ok=True)
        consent_path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "run_id": "run-001",
                    "decision": "approve",
                    "reviewer": "human",
                    "reason": "Reviewed the derived requirements.",
                    "requirements": list(requirement_ids),
                }
            ),
            encoding="utf-8",
        )
    return intent, spec, plan


def _check_args(root: Path, intent: Path, spec: Path, plan: Path) -> list[str]:
    return [
        "plan",
        "check",
        "--project-root",
        str(root),
        "--intent",
        str(intent),
        "--spec",
        str(spec),
        "--plan",
        str(plan),
        "--run-id",
        "run-001",
        "--json",
    ]


def test_plan_check_reports_structural_findings_and_persists_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    intent, spec, plan = _write_fixture(tmp_path, complete=False)

    assert main(_check_args(tmp_path, intent, spec, plan)) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "findings" in payload
    assert any(finding["code"] == "PLAN_TASK_PARITY" for finding in payload["findings"])
    report = tmp_path / ".factory" / "planning" / "run-001" / "report.json"
    assert json.loads(report.read_text(encoding="utf-8")) == payload


def _suggest_args(root: Path) -> list[str]:
    return [
        "plan",
        "suggest",
        "--project-root",
        str(root),
        "--run-id",
        "run-001",
        "--json",
    ]


def _write_checked_report(root: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    intent, spec, plan = _write_fixture(root, complete=True)
    assert main(_check_args(root, intent, spec, plan)) == 0
    return json.loads(capsys.readouterr().out)


def _approval(report: dict[str, object], *, decision: str = "approve") -> dict[str, object]:
    artifacts = report["artifacts"]
    assert isinstance(artifacts, list)
    return {
        "schema": 1,
        "run_id": "run-001",
        "decision": decision,
        "reviewer": "human",
        "reason": "Reviewed the generated planning artifacts.",
        "reviewed_artifacts": sorted(artifact["path"] for artifact in artifacts),
        "report_sha256": planning_report_digest(report),
    }


def test_valid_plan_check_is_successful_but_still_requires_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _write_checked_report(tmp_path, capsys)

    assert payload["ok"] is True
    assert payload["review_required"] is True
    assert payload["suggestion"] is None


def test_plan_suggest_is_blocked_without_a_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_checked_report(tmp_path, capsys)

    assert main(_suggest_args(tmp_path)) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert payload["suggestion"] is None
    assert payload["reason"] == "REVIEW_REQUIRED"


def test_plan_suggest_never_starts_workflow_for_rejected_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _write_checked_report(tmp_path, capsys)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report, decision="reject")), encoding="utf-8")

    assert main(_suggest_args(tmp_path)) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert payload["reason"] == "REVIEW_NOT_APPROVED"
    assert not (tmp_path / ".factory" / "runs").exists()


def test_plan_suggest_emits_only_explicit_approved_downstream_suggestion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _write_checked_report(tmp_path, capsys)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")

    assert main(_suggest_args(tmp_path)) == 0

    suggestion = json.loads(capsys.readouterr().out)
    assert suggestion == {
        "action": "suggest_downstream",
        "workflow": "standard",
        "plan": "docs/superpowers/plans/intent-plan.md",
        "tasks": ["T-001", "T-002"],
        "prerequisites": ["human_review", "requirement_consent"],
        "starts_automatically": False,
    }
    assert not (tmp_path / ".factory" / "runs").exists()


def test_plan_suggest_names_missing_requirement_consent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _write_checked_report(tmp_path, capsys)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")
    (tmp_path / ".factory" / "planning" / "run-001" / "requirement-consent.json").unlink()

    assert main(_suggest_args(tmp_path)) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert payload["reason"] == "REQUIREMENT_CONSENT_REQUIRED"


def test_plan_suggest_rechecks_artifact_hashes_before_approved_suggestion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _write_checked_report(tmp_path, capsys)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")
    (tmp_path / "docs" / "superpowers" / "specs" / "intent-spec.md").write_text(
        SPEC + "\nChanged after review.\n", encoding="utf-8"
    )

    assert main(_suggest_args(tmp_path)) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert payload["reason"] == "SUGGESTION_BLOCKED"


def _handoff_args(root: Path, workflow: str = "standard-development") -> list[str]:
    return [
        "plan", "handoff", "--project-root", str(root), "--run-id", "run-001",
        "--workflow", workflow, "--json",
    ]


def test_plan_handoff_emits_summary_menu_and_revalidates_existing_handoff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_checked_report(tmp_path, capsys)

    assert main(_handoff_args(tmp_path)) == 0
    output = json.loads(capsys.readouterr().out)
    assert "Semantic notes:" in output["summary"]
    assert "standard-development" in output["summary"]
    assert output["menu"] == [
        "standard-development", "health-recovery", "feature-planning"
    ]

    (tmp_path / "docs" / "superpowers" / "plans" / "intent-plan.md").write_text(
        PLAN + "\nChanged in a new session.\n", encoding="utf-8"
    )
    assert main(_handoff_args(tmp_path)) == 1
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["blocked"] is True
    assert blocked["reason"] == "HANDOFF_BLOCKED"


def test_plan_handoff_rejects_unknown_workflow_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_checked_report(tmp_path, capsys)
    assert main(_handoff_args(tmp_path, "launch-process")) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert not (tmp_path / ".factory" / "planning" / "run-001" / "handoff.json").exists()


def test_installed_coherence_entry_point_dispatches_plan_check(tmp_path: Path) -> None:
    intent, spec, plan = _write_fixture(tmp_path, complete=True)
    result = subprocess.run(
        ["coherence", *_check_args(tmp_path, intent, spec, plan)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"] is True


def test_plan_bootstrap_decomposes_and_reports_delegated_next_actions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    intent, spec, plan = _write_fixture(tmp_path, complete=False)
    factory_dir = tmp_path / ".factory"
    factory_dir.mkdir(exist_ok=True)
    (factory_dir / "factory.yaml").write_text("gates: {}\n", encoding="utf-8")
    args = [
        "plan",
        "bootstrap",
        "--project-root",
        str(tmp_path),
        "--intent",
        str(intent),
        "--spec",
        str(spec),
        "--plan",
        str(plan),
        "--run-id",
        "run-001",
        "--decompose",
        "--json",
    ]

    assert main(args) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["created_task_ids"] == ["T-001", "T-002"]
    assert any(action["action"] == "requirement_consent" for action in payload["next_actions"])
    assert any(action["action"] == "health_resolution_registration" for action in payload["next_actions"])
    assert not (tmp_path / "requirements").exists()
    assert not (tmp_path / "bundles").exists()
    assert not (tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json").exists()


def test_plan_bootstrap_rejects_symlinked_tasks_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    intent, spec, plan = _write_fixture(tmp_path, complete=False)
    factory_dir = tmp_path / ".factory"
    factory_dir.mkdir(exist_ok=True)
    (factory_dir / "factory.yaml").write_text("gates: {}\n", encoding="utf-8")
    outside_tasks = tmp_path.parent / "planning-outside-tasks"
    outside_tasks.mkdir()
    tasks_link = tmp_path / "tasks"
    try:
        tasks_link.symlink_to(outside_tasks, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows runner")

    args = [
        "plan",
        "bootstrap",
        "--project-root",
        str(tmp_path),
        "--intent",
        str(intent),
        "--spec",
        str(spec),
        "--plan",
        str(plan),
        "--run-id",
        "run-001",
        "--decompose",
        "--json",
    ]

    assert main(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert payload["reason"] == "BOOTSTRAP_PREREQUISITE"


def test_plan_bootstrap_requires_factory_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    intent, spec, plan = _write_fixture(tmp_path, complete=False)
    args = [
        "plan",
        "bootstrap",
        "--project-root",
        str(tmp_path),
        "--intent",
        str(intent),
        "--spec",
        str(spec),
        "--plan",
        str(plan),
        "--run-id",
        "run-001",
        "--json",
    ]

    assert main(args) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["blocked"] is True
    assert payload["reason"] == "BOOTSTRAP_PREREQUISITE"


def test_plan_suggest_rejects_approved_report_after_spec_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    intent, spec, plan = _write_fixture(tmp_path, complete=True)
    factory_dir = tmp_path / ".factory"
    factory_dir.mkdir(exist_ok=True)
    (factory_dir / "factory.yaml").write_text("gates: {}\n", encoding="utf-8")
    bootstrap_args = [
        "plan",
        "bootstrap",
        "--project-root",
        str(tmp_path),
        "--intent",
        str(intent),
        "--spec",
        str(spec),
        "--plan",
        str(plan),
        "--run-id",
        "run-001",
        "--decompose",
        "--json",
    ]
    assert main(bootstrap_args) == 0
    bootstrap_payload = json.loads(capsys.readouterr().out)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(bootstrap_payload)), encoding="utf-8")

    suggest_args = [
        "plan",
        "suggest",
        "--project-root",
        str(tmp_path),
        "--run-id",
        "run-001",
        "--json",
    ]
    assert main(suggest_args) == 0
    suggestion = json.loads(capsys.readouterr().out)
    assert suggestion["action"] == "suggest_downstream"
    assert suggestion["starts_automatically"] is False

    spec.write_text(spec.read_text(encoding="utf-8") + "\nChanged after review.\n", encoding="utf-8")
    assert main(suggest_args) == 1
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["reason"] == "SUGGESTION_BLOCKED"
    assert blocked["suggestion"] is None


__all__ = []
