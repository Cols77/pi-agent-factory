from __future__ import annotations

import subprocess
from enum import Enum
from pathlib import Path

from factory.config import GateConfigError, load_config, require_gates
from factory.freshness.model import FreshnessIssue, FreshnessReport, FreshnessSeverity
from factory.orchestrator.ledger import get_task, load_tasks
from factory.requirements.register import load_register
from factory.trace.graph import build_graph


class PreflightPhase(str, Enum):
    START = "start"
    COMPLETE = "complete"


def _issue(
    code: str,
    severity: FreshnessSeverity,
    subject: str,
    detail: str,
    dependency: str = "project",
) -> FreshnessIssue:
    return FreshnessIssue(code, severity, subject, dependency, None, None, detail)


def run_preflight(
    repo_root: Path,
    task_id: str | None,
    phase: PreflightPhase = PreflightPhase.START,
    *,
    candidate_tree: str | None = None,
) -> FreshnessReport:
    del candidate_tree  # completion evidence checks are added in the next increment
    issues: list[FreshnessIssue] = []
    try:
        tasks = load_tasks(repo_root / "tasks")
    except (OSError, TypeError, ValueError) as exc:
        return FreshnessReport(
            [_issue("task_register_invalid", FreshnessSeverity.INTEGRITY, task_id or "tasks", str(exc))]
        )

    ids = [task.id for task in tasks]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    for duplicate in duplicates:
        issues.append(
            _issue(
                "duplicate_task_id",
                FreshnessSeverity.INTEGRITY,
                duplicate,
                f"task id {duplicate} is declared by more than one file",
                "tasks",
            )
        )

    task = get_task(tasks, task_id) if task_id else next(
        (candidate for candidate in tasks if candidate.status == "todo"), None
    )
    if task_id and task is None:
        issues.append(
            _issue("task_missing", FreshnessSeverity.INTEGRITY, task_id, f"task not found: {task_id}", "tasks")
        )

    try:
        requirements = load_register(repo_root / "requirements")
    except (OSError, TypeError, ValueError) as exc:
        requirements = []
        issues.append(
            _issue(
                "requirement_register_invalid",
                FreshnessSeverity.INTEGRITY,
                task_id or "requirements",
                str(exc),
                "requirements",
            )
        )
    requirement_ids = {req.id for req in requirements}
    if task is not None:
        for requirement_id in task.satisfies:
            if requirement_id not in requirement_ids:
                issues.append(
                    _issue(
                        "requirement_missing",
                        FreshnessSeverity.INTEGRITY,
                        task.id,
                        f"declared requirement does not exist: {requirement_id}",
                        requirement_id,
                    )
                )

    try:
        require_gates(load_config(repo_root), repo_root)
    except (GateConfigError, TypeError, ValueError) as exc:
        issues.append(
            _issue(
                "factory_config_invalid",
                FreshnessSeverity.INTEGRITY,
                task_id or "factory",
                str(exc),
                ".factory/factory.yaml",
            )
        )

    git = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True
    )
    if git.returncode != 0:
        issues.append(
            _issue(
                "baseline_unresolved",
                FreshnessSeverity.INTEGRITY,
                task_id or "repository",
                git.stderr.strip() or "git HEAD cannot be resolved",
                "git:HEAD",
            )
        )

    if task is not None:
        try:
            graph = build_graph(repo_root)
            for gap in graph.gaps:
                if gap.node_id != task.id or gap.disposition != "pending":
                    continue
                if gap.kind == "task_plan_missing":
                    severity = FreshnessSeverity.INTEGRITY
                elif gap.kind in {"task_no_sr", "task_no_plan"}:
                    severity = FreshnessSeverity.BLOCKING
                else:
                    severity = FreshnessSeverity.WARNING
                issues.append(_issue(gap.kind, severity, task.id, gap.detail, "trace"))
        except (OSError, TypeError, ValueError) as exc:
            issues.append(
                _issue("trace_model_invalid", FreshnessSeverity.INTEGRITY, task.id, str(exc), "trace")
            )

    # Completion-specific evidence policy is deliberately not guessed here.
    if phase is PreflightPhase.COMPLETE:
        pass
    return FreshnessReport(sorted(issues, key=lambda item: (item.severity.value, item.code, item.subject)))
