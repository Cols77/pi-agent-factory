from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from factory.config import GateConfigError, load_config, require_gates
from factory.freshness.model import FreshnessIssue, FreshnessReport, FreshnessSeverity
from factory.orchestrator.git_ops import SubprocessGitOps
from factory.orchestrator.ledger import Task, get_task, load_tasks
from factory.orchestrator.recovery import assess_recovery
from factory.orchestrator.run_cli import load_current_checkpoint
from factory.requirements.register import load_register
from factory.trace.graph import build_graph


@dataclass(frozen=True)
class Override:
    issue_codes: list[str]
    reason: str
    actor: str
    at: str


_OVERRIDABLE = {"review_missing"}


def apply_override(report: FreshnessReport, override: Override) -> FreshnessReport:
    if not override.reason.strip() or not override.actor.strip() or not override.at.strip():
        raise ValueError("override reason, actor, and timestamp must not be blank")
    known = {issue.code for issue in report.issues}
    unknown = set(override.issue_codes) - known
    if unknown:
        raise ValueError("override references unknown issue codes: " + ", ".join(sorted(unknown)))
    selected = [issue for issue in report.issues if issue.code in override.issue_codes]
    if any(issue.severity is FreshnessSeverity.INTEGRITY for issue in selected):
        raise ValueError("integrity issues cannot be overridden")
    refused = {issue.code for issue in selected if issue.code not in _OVERRIDABLE}
    if refused:
        raise ValueError("issue is not overridable: " + ", ".join(sorted(refused)))
    return FreshnessReport(
        [
            replace(
                issue,
                severity=FreshnessSeverity.WARNING,
                detail=issue.detail + f" (overridden by {override.actor}: {override.reason})",
            )
            if issue.code in override.issue_codes
            else issue
            for issue in report.issues
        ]
    )


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


def run_completion_preflight(
    repo_root: Path,
    task: Task,
    transcript_dir: Path,
    *,
    require_review: bool,
) -> FreshnessReport:
    issues: list[FreshnessIssue] = []
    requirements = {item.id: item for item in load_register(repo_root / "requirements")}
    report_path = transcript_dir / "validation-report.json"
    try:
        value = json.loads(report_path.read_text(encoding="utf-8"))
        entries = value.get("requirements", []) if isinstance(value, dict) else []
        by_id = {
            item.get("id"): item
            for item in entries
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
    except (OSError, ValueError, json.JSONDecodeError):
        by_id = {}
    for requirement_id in task.satisfies:
        requirement = requirements.get(requirement_id)
        if requirement is not None and requirement.binding is None:
            continue
        entry = by_id.get(requirement_id)
        if entry is None:
            issues.append(
                _issue(
                    "validation_missing",
                    FreshnessSeverity.BLOCKING,
                    task.id,
                    f"mandatory validation is missing for {requirement_id}",
                    requirement_id,
                )
            )
        elif entry.get("error") or not entry.get("passed"):
            issues.append(
                _issue(
                    "validation_failed",
                    FreshnessSeverity.BLOCKING,
                    task.id,
                    f"mandatory validation did not pass for {requirement_id}: "
                    + str(entry.get("error") or "failed"),
                    requirement_id,
                )
            )
        elif entry.get("stale"):
            issues.append(
                _issue(
                    "validation_stale",
                    FreshnessSeverity.BLOCKING,
                    task.id,
                    f"mandatory validation is stale for {requirement_id}",
                    requirement_id,
                )
            )

    reviews_dir = transcript_dir / "reviews"
    review_values: list[dict] = []
    for path in sorted(reviews_dir.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                review_values.append(value)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    if require_review and not review_values:
        issues.append(
            _issue(
                "review_missing",
                FreshnessSeverity.BLOCKING,
                task.id,
                "interactive completion has no persisted human-review evidence",
                "human-review",
            )
        )
    if review_values:
        final = review_values[-1]
        unresolved = [
            item
            for item in final.get("annotations", [])
            if isinstance(item, dict) and item.get("severity") == "must-fix"
        ]
        if unresolved and final.get("decision") != "reject":
            issues.append(
                _issue(
                    "must_fix_unresolved",
                    FreshnessSeverity.BLOCKING,
                    task.id,
                    f"final review retains {len(unresolved)} must-fix annotation(s)",
                    "human-review",
                )
            )
    return FreshnessReport(sorted(issues, key=lambda item: (item.code, item.dependency)))


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

    checkpoint = load_current_checkpoint(repo_root)
    if checkpoint is not None:
        try:
            assessment = assess_recovery(repo_root, checkpoint, SubprocessGitOps())
            issues.append(
                _issue(
                    "interrupted_run",
                    FreshnessSeverity.BLOCKING,
                    checkpoint.run_id,
                    "an interrupted run requires explicit recovery: "
                    + "; ".join(assessment.reasons)
                    + f"; use run-state inspect {checkpoint.run_id}",
                    "run-checkpoint",
                )
            )
        except (OSError, TypeError, ValueError) as exc:
            issues.append(
                _issue(
                    "run_checkpoint_invalid",
                    FreshnessSeverity.INTEGRITY,
                    checkpoint.run_id,
                    str(exc),
                    "run-checkpoint",
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
