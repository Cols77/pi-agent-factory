from __future__ import annotations

from pathlib import Path

import pytest

from coherence.planning.bootstrap import BootstrapPrerequisiteError, bootstrap_planning
from coherence.planning.model import PlanningInput
from coherence.planning.semantic import SemanticReviewReport
from coherence.planning.workflow import PlanningWorkflow, WorkflowStage


def _input(root: Path) -> PlanningInput:
    intent = root / ".intent" / "intent.json"
    spec = root / "docs" / "spec.md"
    plan = root / "docs" / "plan.md"
    intent.parent.mkdir(parents=True)
    spec.parent.mkdir(parents=True)
    intent.write_text('{"schema": 1, "prompt": "x", "answers": []}', encoding="utf-8")
    spec.write_text("---\nid: SPEC-1\ntitle: Spec\nstatus: draft\n---\n", encoding="utf-8")
    plan.write_text(
        "---\nid: PLAN-1\ntitle: Plan\nstatus: draft\nspec_ref: docs/spec.md\n---\n\n"
        "### Task 1: Bootstrap\n\n**Files:**\n- Create: `src/x.py`\n\n**Interfaces:**\n- Produces: `x`\n",
        encoding="utf-8",
    )
    (root / ".factory").mkdir()
    (root / ".factory" / "factory.yaml").write_text("profile: test\n", encoding="utf-8")
    return PlanningInput(intent, spec, plan, root, "run-001")


def test_bootstrap_missing_factory_config_is_side_effect_free(tmp_path: Path) -> None:
    planning_input = _input(tmp_path)
    (tmp_path / ".factory" / "factory.yaml").unlink()

    with pytest.raises(BootstrapPrerequisiteError):
        bootstrap_planning(tmp_path, planning_input, decompose=True)

    assert not (tmp_path / "tasks").exists()


def test_bootstrap_rejects_existing_generated_task_symlink(tmp_path: Path) -> None:
    planning_input = _input(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    outside = tmp_path.parent / "planning-bootstrap-outside.md"
    outside.write_text("do not overwrite", encoding="utf-8")
    link = tasks_dir / "T-001-bootstrap.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    with pytest.raises(BootstrapPrerequisiteError):
        bootstrap_planning(tmp_path, planning_input, decompose=True)

    assert outside.read_text(encoding="utf-8") == "do not overwrite"


def test_bootstrap_rejects_preexisting_generated_task_collision(tmp_path: Path) -> None:
    planning_input = _input(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    existing = tasks_dir / "T-002-bootstrap.md"
    existing.write_text("---\nid: T-001\ntitle: Existing\nstatus: todo\nsource_plan: docs/other.md\nsource_task: 99\n---\nORIGINAL\n", encoding="utf-8")

    with pytest.raises(BootstrapPrerequisiteError):
        bootstrap_planning(tmp_path, planning_input, decompose=True)

    assert existing.read_text(encoding="utf-8").endswith("ORIGINAL\n")


def test_bootstrap_rejects_hardlinked_generated_task_collision(tmp_path: Path) -> None:
    planning_input = _input(tmp_path)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    outside = tmp_path.parent / "planning-bootstrap-hardlink-target.md"
    outside.write_text("---\nid: T-001\ntitle: Existing\nstatus: todo\nsource_plan: docs/other.md\nsource_task: 99\n---\nORIGINAL\n", encoding="utf-8")
    destination = tasks_dir / "T-002-bootstrap.md"
    try:
        destination.hardlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("hardlinks unavailable on this platform")

    with pytest.raises(BootstrapPrerequisiteError):
        bootstrap_planning(tmp_path, planning_input, decompose=True)

    assert outside.read_text(encoding="utf-8").endswith("ORIGINAL\n")


def test_bootstrap_rejects_malformed_existing_task_frontmatter(tmp_path: Path) -> None:
    planning_input = _input(tmp_path)
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001-bootstrap.md").write_text("---\nid: [broken\n---\n", encoding="utf-8")

    with pytest.raises(BootstrapPrerequisiteError):
        bootstrap_planning(tmp_path, planning_input, decompose=True)

def test_bootstrap_can_invoke_ordered_semantic_checkpoints(tmp_path: Path) -> None:
    planning_input = _input(tmp_path)
    calls: list[str] = []

    def review(packet):
        calls.append(packet.stage)
        return SemanticReviewReport(
            1, packet.run_id, packet.stage, packet.iteration, packet.sha256,
            packet.artifacts, packet.context, packet.sr_context_digest, packet.model,
            packet.reviewer_role, packet.reviewer_session_id, (), (), (), "clean",
        )

    workflow = PlanningWorkflow(
        tmp_path, planning_input.run_id, reviewer_model={"provider": "test", "model": "reviewer"},
        reviewer=review,
    )
    bootstrap_planning(tmp_path, planning_input, workflow=workflow)

    assert calls == [WorkflowStage.SPEC_ALIGNMENT.value, WorkflowStage.PLAN_TASK_ALIGNMENT.value]
