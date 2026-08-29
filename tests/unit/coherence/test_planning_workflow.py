from __future__ import annotations

from pathlib import Path

from coherence.planning.semantic import SemanticReviewReport
from coherence.planning.workflow import PlanningWorkflow, WorkflowStage

import pytest

pytestmark = pytest.mark.unit


def _artifact(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _report(packet):
    return SemanticReviewReport(
        1, packet.run_id, packet.stage, packet.iteration, packet.sha256,
        packet.artifacts, packet.context, packet.sr_context_digest, packet.model,
        packet.reviewer_role, packet.reviewer_session_id, (), (), (), "clean",
    )


def test_three_checkpoints_run_in_order_with_one_reviewer_and_stable_status(tmp_path: Path) -> None:
    paths = [_artifact(tmp_path, name, name) for name in ("intent.json", "spec.md", "plan.md", "tasks/T-001.md")]
    reviewer_models: list[dict[str, str]] = []

    def review(packet):
        reviewer_models.append(packet.model)
        return _report(packet)

    workflow = PlanningWorkflow(
        tmp_path, "run-1", reviewer_model={"provider": "test", "model": "reviewer"},
        reviewer=review,
    )
    workflow.run_stage(WorkflowStage.SPEC_ALIGNMENT, paths[:3], context={"intent": "intent"}, sr_context={"SR-1": "full"})
    workflow.run_stage(WorkflowStage.PLAN_TASK_ALIGNMENT, paths, context={"plan": "plan"}, sr_context={"SR-1": "full"})
    workflow.run_stage(
        WorkflowStage.DERIVATION_ALIGNMENT,
        paths + [_artifact(tmp_path, "docs/features/FEAT-017.md", "feat"), _artifact(tmp_path, "bundles/FEAT-017.json", "bundle")],
        context={"candidates": ["SR-1"], "feature": "FEAT-017", "bundle": "FEAT-017"},
        sr_context={"SR-1": "full"},
    )

    assert reviewer_models == [{"provider": "test", "model": "reviewer"}] * 3
    status = workflow.status().to_dict()
    assert [stage["stage"] for stage in status["stages"]] == [s.value for s in WorkflowStage]
    assert status["ok"] is True
    assert status["blocked"] is False


def test_changed_artifact_invalidates_stage_and_downstream(tmp_path: Path) -> None:
    paths = [_artifact(tmp_path, name, name) for name in ("intent.json", "spec.md", "plan.md", "tasks/T-001.md")]
    workflow = PlanningWorkflow(tmp_path, "run-1", reviewer_model={"provider": "t", "model": "m"}, reviewer=lambda p: _report(p))
    workflow.run_stage(WorkflowStage.SPEC_ALIGNMENT, paths[:3], context={}, sr_context={})
    workflow.run_stage(WorkflowStage.PLAN_TASK_ALIGNMENT, paths, context={}, sr_context={})
    _artifact(tmp_path, "spec.md", "changed")
    status = workflow.status().to_dict()
    assert status["stages"][0]["status"] == "invalidated"
    assert status["stages"][1]["status"] == "invalidated"


def test_unresolved_and_warning_block_but_note_does_not(tmp_path: Path) -> None:
    path = _artifact(tmp_path, "spec.md", "spec")

    def report(packet):
        return SemanticReviewReport(
            1, packet.run_id, packet.stage, packet.iteration, packet.sha256, packet.artifacts,
            packet.context, packet.sr_context_digest, packet.model, packet.reviewer_role,
            packet.reviewer_session_id,
            ({"id": "f", "evidence": "e", "confidence": 1.0, "disposition": "escalate_to_human", "artifact_paths": ["spec.md"]},),
            ("answer",), ("note",), "escalate",
        )

    workflow = PlanningWorkflow(tmp_path, "run-1", reviewer_model={"provider": "t", "model": "m"}, reviewer=report)
    workflow.run_stage(WorkflowStage.SPEC_ALIGNMENT, [path], context={}, sr_context={})
    assert workflow.status().blocked is True
    assert workflow.status().to_dict()["reason"] == "semantic_review_escalation"


def test_reviewer_failure_is_fail_closed_and_changed_stage_can_rerun(tmp_path: Path) -> None:
    path = _artifact(tmp_path, "spec.md", "spec")
    attempts = 0

    def review(packet):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise Exception("provider unavailable")
        return _report(packet)

    workflow = PlanningWorkflow(tmp_path, "run-1", reviewer_model={"provider": "t", "model": "m"}, reviewer=review)
    assert workflow.run_stage(WorkflowStage.SPEC_ALIGNMENT, [path], context={}, sr_context={}) is None
    assert workflow.status().blocked is True
    assert workflow.run_stage(WorkflowStage.SPEC_ALIGNMENT, [path], context={}, sr_context={}) is not None
    _artifact(tmp_path, "spec.md", "changed")
    assert workflow.status().to_dict()["stages"][0]["status"] == "invalidated"
    assert workflow.run_stage(WorkflowStage.SPEC_ALIGNMENT, [path], context={}, sr_context={}) is not None


def test_lifecycle_composes_all_stages_and_reruns_after_invalidation(tmp_path: Path) -> None:
    paths = [_artifact(tmp_path, name, name) for name in ("intent.json", "spec.md", "plan.md", "tasks/T-001.md")]
    derived = [_artifact(tmp_path, name, name) for name in ("docs/features/FEAT-017.md", "bundles/FEAT-017.json")]
    seen: list[tuple[str, dict[str, object]]] = []

    def review(packet):
        seen.append((packet.stage, packet.context))
        return _report(packet)

    workflow = PlanningWorkflow(
        tmp_path, "run-1", reviewer_model={"provider": "test", "model": "reviewer"},
        reviewer=review,
    )
    status = workflow.run_lifecycle(
        spec_artifacts=paths[:3], plan_artifacts=paths, derivation_artifacts=paths + derived,
        intent_context={"intent": "intent"},
        plan_context={"intent": "intent", "spec": "spec", "plan": "plan", "tasks": ["T-001"]},
        derivation_context={"spec": "spec", "plan": "plan", "candidate_srs": ["SR-1"], "feature": "FEAT-017", "bundle": "FEAT-017"},
        sr_context={"SR-1": {"status": "proposed", "statement": "full"}},
    )
    assert status.ok is True
    assert [stage for stage, _ in seen] == [stage.value for stage in WorkflowStage]
    assert seen[1][1]["tasks"] == ["T-001"]
    assert seen[2][1]["candidate_srs"] == ["SR-1"]

    _artifact(tmp_path, "spec.md", "changed")
    rerun = workflow.run_lifecycle(
        spec_artifacts=paths[:3], plan_artifacts=paths, derivation_artifacts=paths + derived,
        intent_context={"intent": "intent"},
        plan_context={"intent": "intent", "spec": "spec", "plan": "plan", "tasks": ["T-001"]},
        derivation_context={"spec": "spec", "plan": "plan", "candidate_srs": ["SR-1"], "feature": "FEAT-017", "bundle": "FEAT-017"},
        sr_context={"SR-1": {"status": "proposed", "statement": "full"}},
    )
    assert rerun.ok is True
