from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import yaml

from coherence.planning.check import check_planning_input
from coherence.planning.model import PlanningInput, PlanningReport
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.workflow import PlanningWorkflow, WorkflowStage
from substrate.ledger.plans import NoTasksFoundError, run as decompose_plan


class BootstrapPrerequisiteError(ValueError):
    """The project is not ready for the thin planning bootstrap composition."""


def _resolved(path: Path) -> Path:
    resolved = safe_root(path)
    if resolved is None:
        raise BootstrapPrerequisiteError("planning bootstrap path contains a symlink or reparse point")
    return resolved


def _inside(path: Path, root: Path, label: str) -> Path:
    resolved = safe_resolve(root, path)
    if resolved is None:
        raise BootstrapPrerequisiteError(f"{label} must be a safe path inside project_root")
    return resolved


def bootstrap_planning(
    root: Path,
    planning_input: PlanningInput,
    *,
    decompose: bool = False,
    workflow: PlanningWorkflow | None = None,
    sr_context: dict[str, object] | None = None,
) -> tuple[PlanningReport, tuple[str, ...]]:
    """Compose plan decomposition and deterministic checking without authoring approvals."""
    project_root = _resolved(root)
    factory_config = safe_resolve(project_root, project_root / ".factory" / "factory.yaml")
    if factory_config is None or not factory_config.is_file():
        raise BootstrapPrerequisiteError(".factory/factory.yaml is required before planning bootstrap")

    declared_root = _resolved(planning_input.project_root)
    if declared_root != project_root:
        raise BootstrapPrerequisiteError("planning input project_root does not match bootstrap root")
    intent_path = _inside(planning_input.intent_path, project_root, "intent")
    spec_path = _inside(planning_input.spec_path, project_root, "spec")
    plan_path = _inside(planning_input.plan_path, project_root, "plan")
    normalized_input = PlanningInput(
        intent_path=intent_path,
        spec_path=spec_path,
        plan_path=plan_path,
        project_root=project_root,
        run_id=planning_input.run_id,
    )

    created: tuple[str, ...] = ()
    if decompose:
        tasks_dir = safe_resolve(project_root, project_root / "tasks")
        try:
            lexical_tasks_dir = project_root / "tasks"
            if tasks_dir is None:
                if lexical_tasks_dir.exists() or lexical_tasks_dir.is_symlink():
                    raise BootstrapPrerequisiteError(
                        "tasks directory must be a real directory inside project_root"
                    )
                tasks_dir = lexical_tasks_dir
            if tasks_dir.exists() and not tasks_dir.is_dir():
                raise BootstrapPrerequisiteError(
                    "tasks directory must be a real directory inside project_root"
                )
            for task_path in tasks_dir.glob("T-*.md"):
                if safe_resolve(project_root, task_path) is None:
                    raise BootstrapPrerequisiteError(
                        "existing generated task paths must not be symlinks or reparse points"
                    )
        except OSError as exc:
            raise BootstrapPrerequisiteError("tasks directory could not be inspected") from exc
        if not plan_path.is_file():
            raise BootstrapPrerequisiteError("plan file is required when --decompose is selected")
        try:
            created = tuple(decompose_plan(plan_path, project_root))
        except NoTasksFoundError as exc:
            raise BootstrapPrerequisiteError("plan contains no decomposable task sections") from exc
        except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError) as exc:
            raise BootstrapPrerequisiteError("generated task decomposition input is malformed") from exc

    report = check_planning_input(normalized_input)
    next_actions = tuple(report.next_actions) + (
        {
            "action": "requirement_consent",
            "status": "required",
            "detail": "obtain explicit human consent for each derived SR before adoption",
        },
        {
            "action": "health_resolution_registration",
            "status": "delegated",
            "detail": "register approved requirements and feature membership through health-resolution",
        },
    )
    report = replace(report, next_actions=next_actions)
    if workflow is not None:
        workflow.run_stage(
            WorkflowStage.SPEC_ALIGNMENT,
            [intent_path, spec_path],
            context={"intent": intent_path.as_posix(), "spec": spec_path.as_posix()},
            sr_context=sr_context or {},
        )
        if plan_path.is_file() and (not decompose or created):
            workflow.run_stage(
                WorkflowStage.PLAN_TASK_ALIGNMENT,
                [intent_path, spec_path, plan_path],
                context={
                    "intent": intent_path.as_posix(),
                    "spec": spec_path.as_posix(),
                    "plan": plan_path.as_posix(),
                    "tasks": list(created),
                },
                sr_context=sr_context or {},
            )
    return report, created


__all__ = ["BootstrapPrerequisiteError", "bootstrap_planning"]
