from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import pytest

from coherence.planning import PlanningInput, check_planning_input
from coherence.planning.model import PlanningReport
from coherence.planning.run import (
    ReviewDecision,
    build_downstream_suggestion,
    planning_report_digest,
    read_review_decision,
    write_planning_run,
)

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


def _write_fixture(root: Path) -> PlanningInput:
    intent_path = root / ".intent" / "intent.json"
    spec_path = root / "docs" / "superpowers" / "specs" / "intent-spec.md"
    plan_path = root / "docs" / "superpowers" / "plans" / "intent-plan.md"
    for path in (intent_path, spec_path, plan_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    intent_path.write_text(json.dumps(INTENT), encoding="utf-8")
    spec_path.write_text(SPEC, encoding="utf-8")
    plan_path.write_text(PLAN, encoding="utf-8")

    tasks_dir = root / "tasks"
    tasks_dir.mkdir()
    for number, title in ((2, "Second"), (1, "First")):
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
    return PlanningInput(
        intent_path=intent_path,
        spec_path=spec_path,
        plan_path=plan_path,
        project_root=root,
        run_id="run-001",
    )


def _approval(report: object) -> dict[str, object]:
    assert hasattr(report, "artifacts")
    assert isinstance(report, PlanningReport)
    artifacts = getattr(report, "artifacts")
    return {
        "schema": 1,
        "run_id": "run-001",
        "decision": "approve",
        "reviewer": "human",
        "reason": "Reviewed the generated planning artifacts.",
        "reviewed_artifacts": sorted(artifact["path"] for artifact in artifacts),
        "report_sha256": planning_report_digest(report),
    }


def test_writes_report_with_fixed_field_order(tmp_path: Path) -> None:
    report = check_planning_input(_write_fixture(tmp_path))

    path = write_planning_run(tmp_path, report)

    assert path == tmp_path / ".factory" / "planning" / "run-001" / "report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert list(payload) == [
        "schema",
        "run_id",
        "ok",
        "artifacts",
        "findings",
        "next_actions",
        "review_required",
        "suggestion",
    ]
    assert payload["suggestion"] is None
    assert not list(path.parent.glob("*.tmp"))


def test_approval_is_explicit_and_builds_sorted_downstream_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    assert decision is not None
    assert build_downstream_suggestion(report) is None
    assert build_downstream_suggestion(report, decision) == {
        "action": "suggest_downstream",
        "workflow": "standard",
        "plan": "docs/superpowers/plans/intent-plan.md",
        "tasks": ["T-001", "T-002"],
        "prerequisites": ["human_review", "requirement_consent"],
        "starts_automatically": False,
    }


def test_synthesized_mapping_cannot_emit_downstream_suggestion(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)

    assert build_downstream_suggestion(report, _approval(report), root=tmp_path) is None


def test_forged_review_decision_capability_cannot_emit_downstream_suggestion(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)

    with pytest.raises(TypeError, match="private"):
        ReviewDecision(
            _approval(report),
            tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json",
            tmp_path,
        )


def test_read_review_decision_is_immutable_and_reread_before_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)
    assert decision is not None
    with pytest.raises(TypeError):
        decision.payload["decision"] = "reject"  # type: ignore[index]
    with pytest.raises(AttributeError):
        decision._payload = {}  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        decision.payload["reviewed_artifacts"].append("forged")  # type: ignore[union-attr]

    changed = _approval(report)
    changed["decision"] = "reject"
    decision_path.write_text(json.dumps(changed), encoding="utf-8")

    assert build_downstream_suggestion(report, decision, root=tmp_path) is None


def test_persisted_report_replacement_invalidates_review_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)
    assert decision is not None

    report_path = tmp_path / ".factory" / "planning" / "run-001" / "report.json"
    changed_report = report.to_dict()
    changed_report["next_actions"] = [{"action": "tampered"}]
    report_path.write_text(json.dumps(changed_report), encoding="utf-8")

    assert build_downstream_suggestion(report, decision, root=tmp_path) is None


def test_punctuated_authority_anchor_allows_approved_downstream_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_data = _write_fixture(tmp_path)
    input_data.spec_path.write_text(SPEC.replace("### goal", "### goal. Decision"), encoding="utf-8")
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    assert decision is not None
    assert build_downstream_suggestion(report, decision, root=tmp_path) == {
        "action": "suggest_downstream",
        "workflow": "standard",
        "plan": "docs/superpowers/plans/intent-plan.md",
        "tasks": ["T-001", "T-002"],
        "prerequisites": ["human_review", "requirement_consent"],
        "starts_automatically": False,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "reject"},
        {"decision": "defer"},
        {"reviewer": "agent"},
        {"reason": "  "},
        {"schema": 2},
        {"run_id": "run-002"},
        {"reviewed_artifacts": ["not-an-artifact"]},
    ],
)
def test_invalid_or_non_approval_decisions_never_suggest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changes: dict[str, object]
) -> None:
    report = check_planning_input(_write_fixture(tmp_path))
    write_planning_run(tmp_path, report)
    decision_payload = _approval(report)
    decision_payload.update(changes)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(decision_payload), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    if changes.get("decision") in {"reject", "defer"}:
        assert decision is not None
    else:
        assert decision is None
    assert build_downstream_suggestion(report, decision) is None

def test_malformed_decision_never_suggests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = check_planning_input(_write_fixture(tmp_path))
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text("{not-json", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    assert decision is None
    assert build_downstream_suggestion(report, decision) is None


def test_changed_requirement_hash_blocks_approved_suggestion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")
    requirement_path = tmp_path / "requirements" / "SR-001.md"
    requirement_path.write_text(requirement_path.read_text(encoding="utf-8") + "\nChanged after review.\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    assert decision is not None
    assert build_downstream_suggestion(report, decision) is None


def test_changed_artifact_hash_blocks_approved_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")
    input_data.spec_path.write_text(SPEC + "\nChanged after review.\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    assert decision is not None
    assert build_downstream_suggestion(report, decision) is None


def test_changed_generated_task_hash_blocks_approved_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")
    (tmp_path / "tasks" / "T-001-first.md").write_text(
        "---\nid: T-001\ntitle: Changed\nstatus: done\n"
        "source_plan: docs/superpowers/plans/intent-plan.md\nsource_task: 1\n---\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    assert decision is not None
    assert build_downstream_suggestion(report, decision) is None


def test_report_rewrite_after_approval_requires_a_new_run_id(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")

    with pytest.raises(ValueError, match="review decision already exists"):
        write_planning_run(tmp_path, report)


def test_missing_requirement_consent_blocks_approved_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")
    (tmp_path / ".factory" / "planning" / "run-001" / "requirement-consent.json").unlink()

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    assert decision is not None
    assert build_downstream_suggestion(report, decision) is None


def test_extra_bundle_member_blocks_approved_suggestion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    write_planning_run(tmp_path, report)
    bundle_path = tmp_path / "bundles" / "FEAT-017.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["members"].append("sr:SR-999")
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    assert decision is not None
    assert build_downstream_suggestion(report, decision) is None


def test_missing_declared_requirement_blocks_the_primary_check(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    (tmp_path / "requirements" / "SR-001.md").unlink()

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "INPUT_READ_ERROR" for finding in report.findings)


def test_malformed_declared_bundle_blocks_the_primary_check(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    (tmp_path / "bundles" / "FEAT-017.json").write_text("{not-json", encoding="utf-8")

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "PLANNING_REFERENCE_INVALID" for finding in report.findings)


def test_incomplete_requirement_blocks_the_primary_check(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    requirement_path = tmp_path / "requirements" / "SR-001.md"
    requirement_path.write_text(
        requirement_path.read_text(encoding="utf-8").replace("statement: SR-001 statement\n", ""),
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "PLANNING_REFERENCE_INVALID" for finding in report.findings)
def test_requirement_with_unknown_authority_anchor_blocks_primary_check(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    requirement_path = tmp_path / "requirements" / "SR-001.md"
    requirement_path.write_text(
        requirement_path.read_text(encoding="utf-8").replace("#goal", "#missing-anchor"),
        encoding="utf-8",
    )

    report = check_planning_input(input_data)

    assert report.ok is False
    assert any(finding.code == "PLANNING_REFERENCE_INVALID" for finding in report.findings)


def test_review_decision_reader_rejects_path_outside_project_root(tmp_path: Path) -> None:
    report = check_planning_input(_write_fixture(tmp_path))
    outside = tmp_path.parent / "review-decision.json"
    outside.write_text(json.dumps(_approval(report)), encoding="utf-8")

    assert read_review_decision(outside, report, project_root=tmp_path) is None


@pytest.mark.parametrize("run_id", ["../escape", "bad\x00id"])
def test_run_id_cannot_escape_planning_directory(tmp_path: Path, run_id: str) -> None:
    report = check_planning_input(_write_fixture(tmp_path))

    with pytest.raises(ValueError):
        write_planning_run(tmp_path, replace(report, run_id=run_id))


def test_run_directory_symlink_is_rejected(tmp_path: Path) -> None:
    report = check_planning_input(_write_fixture(tmp_path))
    planning_dir = tmp_path / ".factory" / "planning"
    planning_dir.mkdir(parents=True, exist_ok=True)
    target = planning_dir / "run-002"
    target.mkdir()
    run_dir = planning_dir / "run-001"
    try:
        run_dir.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows runner")

    with pytest.raises(ValueError):
        write_planning_run(tmp_path, report)


def test_symlinked_artifact_outside_root_blocks_approved_suggestion(tmp_path: Path) -> None:
    input_data = _write_fixture(tmp_path)
    report = check_planning_input(input_data)
    outside = tmp_path.parent / "planning-outside-spec.md"
    outside.write_text(SPEC, encoding="utf-8")
    linked = tmp_path / "docs" / "specs" / "linked-spec.md"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows runner")

    artifacts = tuple(
        {
            "path": "docs/specs/linked-spec.md" if artifact["path"] == "docs/specs/intent-spec.md" else artifact["path"],
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()
            if artifact["path"] == "docs/specs/intent-spec.md"
            else artifact["sha256"],
        }
        for artifact in report.artifacts
    )
    report = replace(report, artifacts=artifacts)
    write_planning_run(tmp_path, report)
    decision_path = tmp_path / ".factory" / "planning" / "run-001" / "review-decision.json"
    decision_path.write_text(json.dumps(_approval(report)), encoding="utf-8")
    decision = read_review_decision(decision_path, report, project_root=tmp_path)

    assert decision is not None
    assert build_downstream_suggestion(report, decision, root=tmp_path) is None




__all__ = []
