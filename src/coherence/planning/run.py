from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from substrate.ledger.plans import ParsedPlanTask, parse_plan_tasks

from coherence.planning.model import PlanningFinding, PlanningReport

_DECISION_KEYS = frozenset(
    {"schema", "run_id", "decision", "reviewer", "reason", "reviewed_artifacts"}
)
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TASK_ID = re.compile(r"^T-[0-9]+$")


def _valid_run_id(run_id: object) -> bool:
    return (
        isinstance(run_id, str)
        and bool(run_id.strip())
        and run_id == run_id.strip()
        and not any(ord(char) < 32 for char in run_id)
        and run_id not in {".", ".."}
        and "/" not in run_id
        and "\\" not in run_id
    )


def write_planning_run(root: Path, report: PlanningReport) -> Path:
    """Atomically write one derived planning report under ``root``.

    The report is written through a temporary file in the destination
    directory, then replaced into place. Run identifiers are restricted to one
    path component so a report can never escape the planning evidence folder.
    """
    if not isinstance(report, PlanningReport):
        raise TypeError("report must be a PlanningReport")
    if not _valid_run_id(report.run_id):
        raise ValueError("run_id must be a non-empty path-safe identifier")

    try:
        resolved_root = root.resolve()
        run_dir = (resolved_root / ".factory" / "planning" / report.run_id).resolve()
        run_dir.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("planning run directory must remain inside project_root") from exc
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.json"
    content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"

    temporary_path: Path | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=".report-",
            suffix=".tmp",
            dir=str(run_dir),
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, report_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    return report_path


def _safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    normalized = value.replace("\\", "/")
    if any(ord(char) < 32 for char in normalized):
        return False
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return False
    parts = normalized.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _safe_root_path(root: Path, relative: str) -> Path | None:
    if not _safe_relative_path(relative):
        return None
    try:
        resolved_root = root.resolve()
        candidate = (resolved_root / Path(relative)).resolve()
        candidate.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


def _report_artifacts(report: PlanningReport) -> tuple[tuple[str, str], ...] | None:
    """Validate the in-memory report shape and return source paths/hashes."""
    if not isinstance(report, PlanningReport):
        return None
    if type(report.schema) is not int or report.schema != 1:
        return None
    if not _valid_run_id(report.run_id):
        return None
    if report.ok is not True or report.review_required is not True:
        return None
    if report.suggestion is not None:
        return None
    if not isinstance(report.artifacts, tuple) or not isinstance(report.findings, tuple):
        return None

    for finding in report.findings:
        if not isinstance(finding, PlanningFinding):
            return None
        if finding.severity == "error" or finding.severity != "warning":
            return None
        if not all(
            isinstance(value, str)
            for value in (finding.code, finding.subject, finding.detail)
        ):
            return None

    artifacts: list[tuple[str, str]] = []
    for artifact in report.artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            return None
        path = artifact.get("path")
        digest = artifact.get("sha256")
        if not isinstance(path, str) or not _safe_relative_path(path) or not isinstance(digest, str):
            return None
        if _HEX_SHA256.fullmatch(digest) is None:
            return None
        artifacts.append((path, digest))

    paths = [path for path, _ in artifacts]
    if not artifacts or paths != sorted(paths) or len(paths) != len(set(paths)):
        return None
    return tuple(artifacts)


def _validated_decision(
    payload: object,
    report: PlanningReport,
) -> dict[str, object] | None:
    artifacts = _report_artifacts(report)
    if artifacts is None or not isinstance(payload, dict):
        return None
    if set(payload) != _DECISION_KEYS:
        return None
    if type(payload.get("schema")) is not int or payload.get("schema") != 1:
        return None
    if payload.get("run_id") != report.run_id:
        return None
    decision = payload.get("decision")
    if not isinstance(decision, str) or decision not in {"approve", "reject", "defer"}:
        return None
    if payload.get("reviewer") != "human":
        return None
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None

    reviewed = payload.get("reviewed_artifacts")
    expected_paths = [path for path, _ in artifacts]
    if not isinstance(reviewed, list) or reviewed != expected_paths:
        return None
    if not all(isinstance(path, str) for path in reviewed):
        return None
    return dict(payload)


def read_review_decision(
    path: Path,
    report: PlanningReport,
) -> dict[str, object] | None:
    """Read and strictly validate a human review decision.

    Invalid, unreadable, or malformed decisions collapse to ``None``. This is
    the deterministic fail-closed state: callers can never mistake an invalid
    file for an approval.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return _validated_decision(payload, report)


def _read_plan(
    root: Path,
    artifact_paths: tuple[str, ...],
    task_records: list[tuple[str, str, int, Path]],
) -> tuple[str, list[ParsedPlanTask]] | None:
    artifact_set = set(artifact_paths)
    referenced = sorted(
        {
            source_plan
            for source_plan, _, _, _ in task_records
            if source_plan in artifact_set
        }
    )
    if len(referenced) == 1:
        candidates = referenced
    else:
        candidates = [
            path
            for path in artifact_paths
            if path.endswith(".md")
            and ("plan" in Path(path).stem.lower() or "/plans/" in path)
        ]
    if len(candidates) != 1:
        return None

    plan_path = candidates[0]
    safe_plan = _safe_root_path(root, plan_path)
    if safe_plan is None:
        return None
    try:
        text = safe_plan.read_text(encoding="utf-8")
        parsed = parse_plan_tasks(text)
    except (OSError, UnicodeError, TypeError, ValueError, RuntimeError):
        return None
    if not parsed:
        return None
    numbers = [task.number for task in parsed]
    if len(numbers) != len(set(numbers)):
        return None
    return plan_path, parsed


def _read_task_records(root: Path) -> list[tuple[str, str, int, Path]] | None:
    try:
        resolved_root = root.resolve()
        tasks_dir = (resolved_root / "tasks").resolve()
        tasks_dir.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return None
    try:
        paths = sorted(tasks_dir.glob("T-*.md"), key=lambda path: path.name)
    except OSError:
        return None

    records: list[tuple[str, str, int, Path]] = []
    for path in paths:
        try:
            safe_path = path.resolve()
            safe_path.relative_to(resolved_root)
        except (OSError, RuntimeError, ValueError):
            return None
        try:
            post = frontmatter.loads(safe_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
            return None
        metadata: dict[str, Any] = dict(post.metadata)
        source_plan = metadata.get("source_plan")
        source_task = metadata.get("source_task")
        task_id = metadata.get("id")
        if not isinstance(source_plan, str):
            continue
        if isinstance(source_task, bool) or not isinstance(source_task, int):
            continue
        if not isinstance(task_id, str) or _TASK_ID.fullmatch(task_id) is None:
            continue
        records.append((source_plan, task_id, source_task, path))
    return records


def _current_task_ids(
    root: Path,
    plan_path: str,
    plan_tasks: list[ParsedPlanTask],
) -> list[str] | None:
    records = _read_task_records(root)
    if records is None:
        return None
    mappings: dict[int, list[str]] = {}
    for source_plan, task_id, source_task, _ in records:
        if source_plan == plan_path:
            mappings.setdefault(source_task, []).append(task_id)

    numbers = [task.number for task in plan_tasks]
    if set(mappings) != set(numbers) or any(
        len(mappings[number]) != 1 for number in numbers
    ):
        return None
    task_ids = [mappings[number][0] for number in numbers]
    if len(task_ids) != len(set(task_ids)):
        return None
    return sorted(task_ids)


def _hashes_current(root: Path, artifacts: tuple[tuple[str, str], ...]) -> bool:
    for relative, expected in artifacts:
        safe_path = _safe_root_path(root, relative)
        if safe_path is None:
            return False
        try:
            actual = hashlib.sha256(safe_path.read_bytes()).hexdigest()
        except (OSError, ValueError):
            return False
        if actual != expected:
            return False
    return True


def build_downstream_suggestion(
    report: PlanningReport,
    decision: Mapping[str, object] | None = None,
    *,
    root: Path | None = None,
) -> dict[str, object] | None:
    """Return an explicit downstream handoff only for a fresh human approval."""
    artifacts = _report_artifacts(report)
    if artifacts is None or decision is None:
        return None
    if not isinstance(decision, Mapping):
        return None
    try:
        decision_payload = dict(decision)
    except (TypeError, ValueError):
        return None
    validated = _validated_decision(decision_payload, report)
    if validated is None or validated.get("decision") != "approve":
        return None

    try:
        root = Path.cwd().resolve() if root is None else root.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    artifact_paths = tuple(path for path, _ in artifacts)
    task_records = _read_task_records(root)
    if task_records is None:
        return None
    plan = _read_plan(root, artifact_paths, task_records)
    if plan is None:
        return None
    plan_path, plan_tasks = plan
    if not _hashes_current(root, artifacts):
        return None
    task_ids = _current_task_ids(root, plan_path, plan_tasks)
    if task_ids is None:
        return None

    return {
        "action": "suggest_downstream",
        "workflow": "standard",
        "plan": plan_path,
        "tasks": task_ids,
        "prerequisites": ["human_review", "requirement_consent"],
        "starts_automatically": False,
    }


__all__ = [
    "build_downstream_suggestion",
    "read_review_decision",
    "write_planning_run",
]
