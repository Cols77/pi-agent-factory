from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from substrate.ledger.plans import parse_plan_tasks

from coherence.planning.model import PlanningFinding, PlanningInput, PlanningReport

_CLAIM_RE = re.compile(r"(?<![A-Za-z0-9_-])claim:([A-Za-z0-9][A-Za-z0-9_.-]*)")
_TOKEN_PREFIX = "(?<![A-Za-z0-9_-])"
_TOKEN_SUFFIX = "(?![A-Za-z0-9_-])"
_REQUIRED_SPEC_FIELDS = ("id", "title", "status")


def _root(input_data: PlanningInput) -> Path:
    return input_data.project_root.resolve()


def _relative(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _subject(path: Path, root: Path) -> str:
    relative = _relative(path, root)
    return relative if relative is not None else path.name or "<outside-project>"


def _finding(
    code: str,
    severity: str,
    subject: str,
    detail: str,
) -> PlanningFinding:
    # All findings in this task are errors. Keeping construction in one place
    # makes the stable report ordering explicit and leaves room for warnings.
    return PlanningFinding(code, "warning" if severity == "warning" else "error", subject, detail)


def _record_artifact(path: Path, root: Path) -> dict[str, object]:
    record: dict[str, object] = {"path": _relative(path, root) or path.name or "<outside-project>"}
    try:
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        record["sha256"] = None
    return record


def _read_text(
    path: Path,
    root: Path,
    findings: list[PlanningFinding],
) -> str | None:
    subject = _subject(path, root)
    if _relative(path, root) is None:
        findings.append(
            _finding(
                "ARTIFACT_OUTSIDE_PROJECT",
                "error",
                subject,
                "source artifact must be located below project_root",
            )
        )
        return None
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        findings.append(_finding("ARTIFACT_MISSING", "error", subject, "source artifact does not exist"))
    except UnicodeError:
        findings.append(_finding("ARTIFACT_NOT_UTF8", "error", subject, "source artifact is not UTF-8"))
    except OSError as exc:
        findings.append(_finding("ARTIFACT_UNREADABLE", "error", subject, str(exc)))
    return None


def _metadata(text: str, path: Path, root: Path, findings: list[PlanningFinding]) -> dict[str, Any] | None:
    try:
        post = frontmatter.loads(text)
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        findings.append(_finding("FRONTMATTER_INVALID", "error", _subject(path, root), str(exc)))
        return None
    return dict(post.metadata)


def _require_nonempty_fields(
    metadata: dict[str, Any],
    fields: tuple[str, ...],
    path: Path,
    root: Path,
    findings: list[PlanningFinding],
    code: str,
) -> bool:
    valid = True
    for field in fields:
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(
                _finding(
                    code,
                    "error",
                    _subject(path, root),
                    f"frontmatter field {field!r} must be a non-empty string",
                )
            )
            valid = False
    return valid


def _valid_intent(
    payload: object,
    path: Path,
    root: Path,
    findings: list[PlanningFinding],
) -> list[str]:
    subject = _subject(path, root)
    if not isinstance(payload, dict):
        findings.append(_finding("INTENT_INVALID", "error", subject, "intent must be a JSON object"))
        return []

    valid = True
    if payload.get("schema") != 1:
        findings.append(_finding("INTENT_INVALID", "error", subject, "intent schema must equal 1"))
        valid = False
    if not isinstance(payload.get("prompt"), str) or not str(payload["prompt"]).strip():
        findings.append(_finding("INTENT_INVALID", "error", subject, "intent prompt must be non-empty"))
        valid = False

    answers = payload.get("answers")
    if not isinstance(answers, list):
        findings.append(_finding("INTENT_INVALID", "error", subject, "intent answers must be a list"))
        return []

    answer_ids: list[str] = []
    for index, answer in enumerate(answers):
        if not isinstance(answer, dict):
            findings.append(
                _finding("INTENT_INVALID", "error", subject, f"answer {index} must be an object")
            )
            valid = False
            continue
        answer_id = answer.get("id")
        text = answer.get("text")
        if not isinstance(answer_id, str) or not answer_id.strip():
            findings.append(
                _finding("INTENT_INVALID", "error", subject, f"answer {index} id must be non-empty")
            )
            valid = False
        elif answer_id in answer_ids:
            findings.append(
                _finding("INTENT_INVALID", "error", subject, f"duplicate answer id {answer_id!r}")
            )
            valid = False
        else:
            answer_ids.append(answer_id)
        if not isinstance(text, str) or not text.strip():
            findings.append(
                _finding("INTENT_INVALID", "error", subject, f"answer {index} text must be non-empty")
            )
            valid = False

    return answer_ids if valid else []


def _has_token(text: str, token: str) -> bool:
    return re.search(_TOKEN_PREFIX + re.escape(token) + _TOKEN_SUFFIX, text) is not None


def _spec_ref_matches(
    ref: str,
    spec_id: str | None,
    spec_path: Path,
    plan_path: Path,
    root: Path,
) -> bool:
    if spec_id is not None and ref == spec_id:
        return True
    ref_path = Path(ref)
    if ref_path.is_absolute():
        return False
    expected = spec_path.resolve()
    candidates = (
        root / ref_path,
        root / "docs" / "superpowers" / "specs" / ref_path,
        plan_path.parent / ref_path,
        plan_path.parent.parent / "specs" / ref_path,
    )
    return any(candidate.resolve() == expected for candidate in candidates)


def _parse_plan(
    text: str | None,
    path: Path,
    root: Path,
    findings: list[PlanningFinding],
) -> tuple[dict[str, Any] | None, list[Any]]:
    if text is None:
        return None, []
    metadata = _metadata(text, path, root, findings)
    try:
        tasks = parse_plan_tasks(text)
    except (OSError, UnicodeError, TypeError, ValueError, RuntimeError) as exc:
        findings.append(_finding("PLAN_INVALID", "error", _subject(path, root), str(exc)))
        tasks = []
    if not tasks:
        findings.append(
            _finding("PLAN_INVALID", "error", _subject(path, root), "plan must contain at least one task")
        )
    for task in tasks:
        if not task.files_block.strip():
            findings.append(
                _finding(
                    "PLAN_INVALID",
                    "error",
                    f"{_subject(path, root)}:task-{task.number}",
                    "task must contain a non-empty **Files:** block",
                )
            )
    return metadata, tasks


def _check_tasks(
    root: Path,
    plan_path: Path,
    tasks: list[Any],
    artifacts: dict[str, dict[str, object]],
    findings: list[PlanningFinding],
) -> None:
    expected_plan = _relative(plan_path, root)
    if expected_plan is None:
        return

    mappings: dict[int, list[str]] = {}
    tasks_dir = root / "tasks"
    if tasks_dir.is_dir():
        task_paths = sorted(tasks_dir.glob("T-*.md"), key=lambda path: path.name)
    else:
        task_paths = []

    for task_path in task_paths:
        record = _record_artifact(task_path, root)
        artifacts[str(record["path"])] = record
        text = _read_text(task_path, root, findings)
        if text is None:
            continue
        metadata = _metadata(text, task_path, root, findings)
        if metadata is None or metadata.get("source_plan") != expected_plan:
            continue
        source_task = metadata.get("source_task")
        if isinstance(source_task, bool) or not isinstance(source_task, int):
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    "error",
                    _subject(task_path, root),
                    "task source_task must be an integer for this plan",
                )
            )
            continue
        mappings.setdefault(source_task, []).append(_subject(task_path, root))

    plan_numbers: set[int] = set()
    for task in tasks:
        number = task.number
        if number in plan_numbers:
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    "error",
                    f"{_subject(plan_path, root)}:task-{number}",
                    "plan task number is duplicated",
                )
            )
        plan_numbers.add(number)
        matches = mappings.get(number, [])
        if not matches:
            detail = "no generated task has matching source_plan and source_task"
        elif len(matches) > 1:
            detail = f"multiple generated tasks map to this plan task: {', '.join(sorted(matches))}"
        else:
            continue
        findings.append(
            _finding(
                "PLAN_TASK_PARITY",
                "error",
                f"{_subject(plan_path, root)}:task-{number}",
                detail,
            )
        )

    for source_task, paths in sorted(mappings.items()):
        if source_task not in plan_numbers:
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    "error",
                    ", ".join(sorted(paths)),
                    f"generated task source_task {source_task} has no matching plan section",
                )
            )


def check_planning_input(input: PlanningInput) -> PlanningReport:
    """Check intent, authority spec, plan, and generated task parity.

    The function only reads source files. It never writes reports or review
    decisions and never invokes an agent or downstream workflow.
    """
    root = _root(input)
    findings: list[PlanningFinding] = []
    artifacts: dict[str, dict[str, object]] = {}

    source_paths = (input.intent_path, input.spec_path, input.plan_path)
    for path in source_paths:
        record = _record_artifact(path, root)
        artifacts[str(record["path"])] = record

    intent_text = _read_text(input.intent_path, root, findings)
    answer_ids: list[str] = []
    if intent_text is not None:
        try:
            intent_payload = json.loads(intent_text)
        except (json.JSONDecodeError, UnicodeError) as exc:
            findings.append(_finding("INTENT_INVALID", "error", _subject(input.intent_path, root), str(exc)))
        else:
            answer_ids = _valid_intent(intent_payload, input.intent_path, root, findings)

    spec_text = _read_text(input.spec_path, root, findings)
    spec_metadata: dict[str, Any] | None = None
    if spec_text is not None:
        spec_metadata = _metadata(spec_text, input.spec_path, root, findings)
        if spec_metadata is not None:
            _require_nonempty_fields(
                spec_metadata,
                _REQUIRED_SPEC_FIELDS,
                input.spec_path,
                root,
                findings,
                "SPEC_INVALID",
            )

    plan_text = _read_text(input.plan_path, root, findings)
    plan_metadata, plan_tasks = _parse_plan(plan_text, input.plan_path, root, findings)

    if plan_metadata is not None:
        spec_ref = plan_metadata.get("spec_ref")
        spec_id = (
            str(spec_metadata["id"])
            if spec_metadata is not None and isinstance(spec_metadata.get("id"), str)
            else None
        )
        if not isinstance(spec_ref, str) or not spec_ref.strip():
            findings.append(
                _finding(
                    "PLAN_SPEC_REF",
                    "error",
                    _subject(input.plan_path, root),
                    "plan frontmatter must contain a non-empty spec_ref",
                )
            )
        elif not _spec_ref_matches(
            spec_ref,
            spec_id,
            input.spec_path,
            input.plan_path,
            root,
        ):
            findings.append(
                _finding(
                    "PLAN_SPEC_REF",
                    "error",
                    _subject(input.plan_path, root),
                    "plan spec_ref does not resolve to the authority spec",
                )
            )

    _check_tasks(root, input.plan_path, plan_tasks, artifacts, findings)

    if answer_ids and spec_text is not None and plan_text is not None:
        for answer_id in answer_ids:
            if not _has_token(spec_text, answer_id):
                findings.append(
                    _finding(
                        "INTENT_UNCOVERED",
                        "error",
                        answer_id,
                        "intent answer id is not represented in the authority spec",
                    )
                )
            if not _has_token(plan_text, answer_id):
                findings.append(
                    _finding(
                        "INTENT_UNCOVERED",
                        "error",
                        answer_id,
                        "intent answer id is not represented in the plan",
                    )
                )

    if spec_text is not None:
        for match in sorted(set(_CLAIM_RE.findall(spec_text))):
            if match not in answer_ids:
                findings.append(
                    _finding(
                        "SPEC_UNSUPPORTED_CLAIM",
                        "error",
                        match,
                        "spec claim id is not declared by an intent answer",
                    )
                )

    findings.sort(key=lambda finding: (0 if finding.severity == "error" else 1, finding.code, finding.subject, finding.detail))
    frozen_findings = tuple(findings)
    ok = not any(finding.severity == "error" for finding in frozen_findings)
    sorted_artifacts = tuple(artifacts[key] for key in sorted(artifacts))
    return PlanningReport(
        schema=1,
        run_id=input.run_id,
        ok=ok,
        artifacts=sorted_artifacts,
        findings=frozen_findings,
        next_actions=(),
        review_required=ok,
        suggestion=None,
    )


__all__ = ["check_planning_input"]
