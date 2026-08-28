from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator

import yaml

from coherence.planning.check import check_planning_input
from coherence.planning.gates import validate_requirement_consent
from coherence.planning.model import PlanningFinding, PlanningInput, PlanningReport
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_frontmatter_loads, strict_json_loads
from coherence.planning.model_policy import ModelCatalogEntry, persist_model_selection
from substrate.ledger.plans import ParsedPlanTask, parse_plan_tasks

_DECISION_KEYS = frozenset(
    {
        "schema",
        "run_id",
        "decision",
        "reviewer",
        "reason",
        "reviewed_artifacts",
        "report_sha256",
    }
)
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TASK_ID = re.compile(r"^T-[0-9]+$")
_REPORT_DIGEST_KEYS = (
    "schema",
    "run_id",
    "ok",
    "artifacts",
    "findings",
    "next_actions",
    "review_required",
    "suggestion",
)


_REVIEW_CAPABILITY = object()


class ReviewDecision(Mapping[str, object]):
    """Immutable capability minted only after validating a decision file."""

    __slots__ = ("_payload", "_path", "_project_root", "_capability")

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("ReviewDecision construction is private; read the decision file")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ReviewDecision capabilities are immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("ReviewDecision capabilities are immutable")

    @property
    def payload(self) -> Mapping[str, object]:
        return self._payload

    @property
    def path(self) -> Path:
        return self._path

    @property
    def project_root(self) -> Path:
        return self._project_root

    def __getitem__(self, key: str) -> object:
        return self._payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _mint_review_decision(
    payload: Mapping[str, object], path: Path, project_root: Path
) -> ReviewDecision:
    decision = object.__new__(ReviewDecision)
    frozen_payload = {key: _freeze(value) for key, value in payload.items()}
    object.__setattr__(decision, "_payload", MappingProxyType(frozen_payload))
    object.__setattr__(decision, "_path", path)
    object.__setattr__(decision, "_project_root", project_root)
    object.__setattr__(decision, "_capability", _REVIEW_CAPABILITY)
    return decision


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

    resolved_root = safe_root(root)
    if resolved_root is None:
        raise ValueError("project_root contains a symlink or reparse point")
    factory_dir = resolved_root / ".factory"
    planning_dir = factory_dir / "planning"
    run_dir = planning_dir / report.run_id
    safe_directories = tuple(safe_resolve(resolved_root, directory) for directory in (factory_dir, planning_dir, run_dir))
    if any(directory is None for directory in safe_directories):
        raise ValueError("planning evidence directories must not be symlinks or reparse points")
    if any(directory.exists() and not directory.is_dir() for directory in safe_directories if directory is not None):
        raise ValueError("planning evidence paths must be directories")
    safe_run_dir = safe_directories[-1]
    if safe_run_dir is None:
        raise ValueError("planning run directory must remain inside project_root")
    safe_run_dir.mkdir(parents=True, exist_ok=True)
    report_path = safe_resolve(resolved_root, safe_run_dir / "report.json")
    decision_path = safe_resolve(resolved_root, safe_run_dir / "review-decision.json")
    if report_path is None or decision_path is None:
        raise ValueError("planning run files must not be symlinks or reparse points")
    if decision_path.exists():
        raise ValueError("review decision already exists; use a new run_id")
    content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n"

    temporary_path: Path | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=".report-",
            suffix=".tmp",
            dir=str(safe_run_dir),
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


def write_model_selection(
    root: Path, run_id: str, classifier: ModelCatalogEntry, reviewer: ModelCatalogEntry
) -> Path:
    """Persist the one reviewer choice for a run; credentials never cross this boundary."""
    return persist_model_selection(root, run_id, classifier, reviewer)


def planning_report_digest(report: PlanningReport | Mapping[str, object]) -> str:
    """Return the canonical digest a review decision must bind to."""
    if isinstance(report, PlanningReport):
        payload = report.to_dict()
    elif isinstance(report, Mapping):
        payload = {key: report[key] for key in _REPORT_DIGEST_KEYS if key in report}
    else:
        raise TypeError("report must be a PlanningReport or report mapping")
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
        resolved_root = safe_root(root)
        if resolved_root is None:
            return None
        candidate = resolved_root / Path(relative)
        return safe_resolve(resolved_root, candidate)
    except (OSError, RuntimeError, ValueError):
        return None


def _root_relative(path: Path, root: Path) -> str | None:
    resolved_root = safe_root(root)
    resolved = safe_resolve(root, path)
    if resolved_root is None or resolved is None:
        return None
    return resolved.relative_to(resolved_root).as_posix()


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
    report_sha256 = payload.get("report_sha256")
    if not isinstance(report_sha256, str) or _HEX_SHA256.fullmatch(report_sha256) is None:
        return None
    if report_sha256 != planning_report_digest(report):
        return None
    return dict(payload)


def _canonical_report_matches(root: Path, report: PlanningReport) -> bool:
    report_path = _safe_root_path(
        root,
        f".factory/planning/{report.run_id}/report.json",
    )
    if report_path is None:
        return False
    try:
        persisted = strict_json_loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(persisted, dict) and persisted == report.to_dict()


def read_review_decision(
    path: Path,
    report: PlanningReport,
    project_root: Path,
) -> ReviewDecision | None:
    """Read and strictly validate a human review decision.

    Invalid, unreadable, or malformed decisions collapse to ``None``. This is
    the deterministic fail-closed state: callers can never mistake an invalid
    file for an approval.
    """
    safe_project_root = safe_root(project_root)
    if safe_project_root is None:
        return None
    expected = _safe_root_path(
        safe_project_root,
        f".factory/planning/{report.run_id}/review-decision.json",
    )
    safe_path = safe_resolve(safe_project_root, path)
    if expected is None or safe_path != expected or not _canonical_report_matches(safe_project_root, report):
        return None
    try:
        raw = expected.read_text(encoding="utf-8")
        payload = strict_json_loads(raw)
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return None
    validated = _validated_decision(payload, report)
    if validated is None:
        return None
    return _mint_review_decision(validated, expected, safe_project_root)


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
        resolved_root = safe_root(root)
        if resolved_root is None:
            return None
        tasks_dir = safe_resolve(resolved_root, resolved_root / "tasks")
        if tasks_dir is None or not tasks_dir.is_dir():
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    try:
        paths = sorted(tasks_dir.glob("T-*.md"), key=lambda path: path.name)
    except OSError:
        return None

    records: list[tuple[str, str, int, Path]] = []
    for path in paths:
        try:
            safe_path = safe_resolve(resolved_root, path)
            if safe_path is None:
                return None
        except (OSError, RuntimeError, ValueError):
            return None
        try:
            post = strict_frontmatter_loads(safe_path.read_text(encoding="utf-8"))
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


def _planning_input_from_report(root: Path, report: PlanningReport) -> PlanningInput | None:
    """Recover the three source inputs from a persisted report's artifact set."""
    artifacts = _report_artifacts(report)
    if artifacts is None:
        return None
    intent_path: Path | None = None
    spec_path: Path | None = None
    plan_path: Path | None = None
    for relative, _ in artifacts:
        safe_path = _safe_root_path(root, relative)
        if safe_path is None:
            return None
        try:
            text = safe_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            return None
        if relative.endswith(".json"):
            try:
                payload = strict_json_loads(text)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if (
                isinstance(payload, dict)
                and "schema" in payload
                and "prompt" in payload
                and "answers" in payload
            ):
                if intent_path is not None:
                    return None
                intent_path = safe_path
            continue
        if not relative.endswith(".md") or "/tasks/" in f"/{relative}":
            continue
        try:
            metadata = dict(strict_frontmatter_loads(text).metadata)
        except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
            continue
        if isinstance(metadata.get("spec_ref"), str):
            if plan_path is not None:
                return None
            plan_path = safe_path
        elif all(field in metadata for field in ("id", "title", "status")):
            if spec_path is not None:
                return None
            spec_path = safe_path
    if intent_path is None or spec_path is None or plan_path is None:
        return None
    return PlanningInput(
        intent_path=intent_path,
        spec_path=spec_path,
        plan_path=plan_path,
        project_root=root,
        run_id=report.run_id,
    )


def _same_source_report(expected: PlanningReport, actual: PlanningReport) -> bool:
    expected_payload = expected.to_dict()
    actual_payload = actual.to_dict()
    return all(
        expected_payload[key] == actual_payload[key]
        for key in ("schema", "run_id", "ok", "artifacts", "findings", "review_required", "suggestion")
    )


def _revalidate_report(root: Path, report: PlanningReport) -> bool:
    planning_input = _planning_input_from_report(root, report)
    if planning_input is None:
        return False
    try:
        current = check_planning_input(planning_input)
    except (OSError, UnicodeError, TypeError, ValueError, RuntimeError):
        return False
    return _same_source_report(report, current)


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


def requirement_consent_status(
    report: PlanningReport,
    root: Path,
) -> tuple[bool, str]:
    """Return the deterministic registration/consent status for a report."""
    expected_consent_path = root / ".factory" / "planning" / report.run_id / "requirement-consent.json"
    expected_consent_relative = _root_relative(expected_consent_path, root)
    artifact_paths = {
        str(artifact.get("path"))
        for artifact in report.artifacts
        if isinstance(artifact, dict)
    }
    if expected_consent_relative is None or expected_consent_relative not in artifact_paths:
        return False, "requirement consent must exist before the planning report is reviewed"
    planning_input = _planning_input_from_report(root, report)
    if planning_input is None:
        return False, "planning source artifacts cannot be reconstructed from the report"
    return validate_requirement_consent(root, report.run_id, planning_input.spec_path)


def build_downstream_suggestion(
    report: PlanningReport,
    decision: Mapping[str, object] | None = None,
    *,
    root: Path | None = None,
) -> dict[str, object] | None:
    """Return an explicit downstream handoff only for a fresh human approval."""
    if not isinstance(decision, ReviewDecision) or getattr(decision, "_capability", None) is not _REVIEW_CAPABILITY:
        return None

    try:
        safe_root_path = safe_root(Path.cwd() if root is None else root)
    except (OSError, RuntimeError, ValueError):
        return None
    if safe_root_path is None or decision.project_root != safe_root_path:
        return None
    expected_decision_path = _safe_root_path(
        safe_root_path,
        f".factory/planning/{report.run_id}/review-decision.json",
    )
    if expected_decision_path is None or decision.path != expected_decision_path:
        return None

    if not _revalidate_report(safe_root_path, report):
        return None
    artifacts = _report_artifacts(report)
    if artifacts is None:
        return None
    planning_input = _planning_input_from_report(safe_root_path, report)
    if planning_input is None:
        return None
    consent_ok, _ = requirement_consent_status(report, safe_root_path)
    if not consent_ok:
        return None
    artifact_paths = tuple(path for path, _ in artifacts)
    task_records = _read_task_records(safe_root_path)
    if task_records is None:
        return None
    plan = _read_plan(safe_root_path, artifact_paths, task_records)
    if plan is None:
        return None
    plan_path, plan_tasks = plan
    if not _hashes_current(safe_root_path, artifacts):
        return None
    task_ids = _current_task_ids(safe_root_path, plan_path, plan_tasks)
    if task_ids is None:
        return None

    refreshed = read_review_decision(expected_decision_path, report, project_root=safe_root_path)
    if refreshed is None or refreshed.get("decision") != "approve":
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
    "ReviewDecision",
    "build_downstream_suggestion",
    "planning_report_digest",
    "read_review_decision",
    "requirement_consent_status",
    "write_planning_run",
    "write_model_selection",
]
