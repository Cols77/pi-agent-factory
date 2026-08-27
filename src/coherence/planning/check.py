from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from coherence.planning.model import PlanningFinding, PlanningInput, PlanningReport
from substrate.ledger.plans import ParsedPlanTask, parse_plan_tasks

_CLAIM_RE = re.compile(r"(?<![A-Za-z0-9_-])claim:([A-Za-z0-9][A-Za-z0-9_.-]*)")
_TOKEN_PREFIX = "(?<![A-Za-z0-9_-])"
_TOKEN_SUFFIX = "(?![A-Za-z0-9_-])"
_REQUIRED_SPEC_FIELDS = ("id", "title", "status")


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError, ValueError):
        return path.absolute()


def _relative(path: Path, root: Path) -> str | None:
    try:
        return _resolve(path).relative_to(root).as_posix()
    except ValueError:
        return None


def _subject(path: Path, root: Path) -> str:
    return _relative(path, root) or path.name or "<outside-project>"


def _finding(code: str, subject: str, detail: str) -> PlanningFinding:
    return PlanningFinding(code=code, severity="error", subject=subject, detail=detail)


def _record_artifact(path: Path, root: Path) -> dict[str, object]:
    relative = _relative(path, root)
    record: dict[str, object] = {"path": relative or path.name or "<outside-project>"}
    if relative is None:
        record["sha256"] = None
        return record
    try:
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        record["sha256"] = None
    return record


def _read_text(path: Path, root: Path, findings: list[PlanningFinding]) -> str | None:
    subject = _subject(path, root)
    if _relative(path, root) is None:
        findings.append(
            _finding("ARTIFACT_OUTSIDE_PROJECT", subject, "source artifact must be located below project_root")
        )
        return None
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        findings.append(_finding("INPUT_READ_ERROR", subject, "source artifact does not exist"))
    except UnicodeError:
        findings.append(_finding("ARTIFACT_NOT_UTF8", subject, "source artifact is not UTF-8"))
    except ValueError:
        findings.append(_finding("INPUT_READ_ERROR", subject, "source artifact path is invalid"))
    except OSError:
        findings.append(_finding("ARTIFACT_UNREADABLE", subject, "source artifact could not be read"))
    return None


def _metadata(
    text: str, path: Path, root: Path, findings: list[PlanningFinding]
) -> dict[str, Any] | None:
    try:
        post = frontmatter.loads(text)
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
        findings.append(_finding("FRONTMATTER_INVALID", _subject(path, root), "frontmatter is malformed"))
        return None
    return dict(post.metadata)


def _body(text: str) -> str:
    """Return document content without frontmatter metadata."""
    try:
        return frontmatter.loads(text).content
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
        return text


def _valid_intent(
    payload: object, path: Path, root: Path, findings: list[PlanningFinding]
) -> list[str]:
    subject = _subject(path, root)
    if not isinstance(payload, dict):
        findings.append(_finding("INTENT_INVALID", subject, "intent must be a JSON object"))
        return []
    valid = True
    if payload.get("schema") != 1:
        findings.append(_finding("INTENT_INVALID", subject, "intent schema must equal 1"))
        valid = False
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        findings.append(_finding("INTENT_INVALID", subject, "intent prompt must be non-empty"))
        valid = False
    answers = payload.get("answers")
    if not isinstance(answers, list) or not answers:
        findings.append(_finding("INTENT_INVALID", subject, "intent answers must be a non-empty list"))
        return []
    answer_ids: list[str] = []
    for index, answer in enumerate(answers):
        if not isinstance(answer, dict):
            findings.append(_finding("INTENT_INVALID", subject, f"answer {index} must be an object"))
            valid = False
            continue
        answer_id = answer.get("id")
        answer_text = answer.get("text")
        if not isinstance(answer_id, str) or not answer_id.strip():
            findings.append(_finding("INTENT_INVALID", subject, f"answer {index} id must be non-empty"))
            valid = False
        elif answer_id in answer_ids:
            findings.append(_finding("INTENT_INVALID", subject, f"duplicate answer id {answer_id!r}"))
            valid = False
        else:
            answer_ids.append(answer_id)
        if not isinstance(answer_text, str) or not answer_text.strip():
            findings.append(_finding("INTENT_INVALID", subject, f"answer {index} text must be non-empty"))
            valid = False
    return answer_ids if valid else []


def _has_token(text: str, token: str) -> bool:
    return re.search(_TOKEN_PREFIX + re.escape(token) + _TOKEN_SUFFIX, text) is not None


def _spec_ref_matches(
    ref: str, spec_id: str | None, spec_path: Path, plan_path: Path, root: Path
) -> bool:
    if spec_id is not None and ref in {spec_id, f"spec:{spec_id}"}:
        return True
    try:
        ref_path = Path(ref)
    except (OSError, ValueError):
        return False
    if ref_path.is_absolute():
        return False
    expected = _resolve(spec_path)
    candidates = (
        root / ref_path,
        root / "docs" / "superpowers" / "specs" / ref_path,
        plan_path.parent / ref_path,
        plan_path.parent.parent / "specs" / ref_path,
    )
    try:
        return any(_resolve(candidate) == expected for candidate in candidates)
    except (OSError, RuntimeError, ValueError):
        return False


def _parse_plan(
    text: str | None, path: Path, root: Path, findings: list[PlanningFinding]
) -> tuple[dict[str, Any] | None, list[ParsedPlanTask]]:
    if text is None:
        return None, []
    metadata = _metadata(text, path, root, findings)
    try:
        tasks = parse_plan_tasks(text)
    except (OSError, UnicodeError, TypeError, ValueError, RuntimeError):
        findings.append(_finding("PLAN_INVALID", _subject(path, root), "plan task sections are malformed"))
        tasks = []
    if not tasks:
        findings.append(_finding("PLAN_INVALID", _subject(path, root), "plan must contain at least one task"))
    for task in tasks:
        if not task.files_block.strip():
            findings.append(
                _finding(
                    "PLAN_INVALID",
                    f"{_subject(path, root)}:task-{task.number}",
                    "task must contain a non-empty **Files:** block",
                )
            )
    return metadata, tasks


def _check_tasks(
    root: Path, plan_path: Path, tasks: list[ParsedPlanTask], findings: list[PlanningFinding]
) -> None:
    expected_plan = _relative(plan_path, root)
    if expected_plan is None:
        return
    mappings: dict[int, list[str]] = {}
    tasks_dir = root / "tasks"
    try:
        task_paths = sorted(tasks_dir.glob("T-*.md"), key=lambda path: path.name) if tasks_dir.is_dir() else []
    except (OSError, ValueError):
        findings.append(_finding("ARTIFACT_UNREADABLE", "tasks", "generated task directory could not be read"))
        return
    for task_path in task_paths:
        text = _read_text(task_path, root, findings)
        if text is None:
            continue
        metadata = _metadata(text, task_path, root, findings)
        if metadata is None or metadata.get("source_plan") != expected_plan:
            continue
        if any(not isinstance(metadata.get(field), str) or not str(metadata[field]).strip() for field in ("id", "title", "status")):
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    _subject(task_path, root),
                    "generated task must declare non-empty id, title, and status",
                )
            )
        source_task = metadata.get("source_task")
        if isinstance(source_task, bool) or not isinstance(source_task, int):
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    _subject(task_path, root),
                    "task source_task must be an integer for this plan",
                )
            )
            continue
        mappings.setdefault(source_task, []).append(_subject(task_path, root))

    plan_numbers: set[int] = set()
    plan_subject = _subject(plan_path, root)
    for task in tasks:
        number = task.number
        if number in plan_numbers:
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    f"{plan_subject}:task-{number}",
                    "plan task number is duplicated",
                )
            )
        plan_numbers.add(number)
        matches = mappings.get(number, [])
        if len(matches) == 1:
            continue
        detail = (
            "no generated task has matching source_plan and source_task"
            if not matches
            else f"multiple generated tasks map to this plan task: {', '.join(sorted(matches))}"
        )
        findings.append(_finding("PLAN_TASK_PARITY", f"{plan_subject}:task-{number}", detail))

    for source_task, paths in sorted(mappings.items()):
        if source_task not in plan_numbers:
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    ", ".join(sorted(paths)),
                    f"generated task source_task {source_task} has no matching plan section",
                )
            )


def check_planning_input(input: PlanningInput) -> PlanningReport:
    """Check planning source files without writing or invoking downstream work."""
    root = _resolve(input.project_root)
    findings: list[PlanningFinding] = []
    artifacts: dict[str, dict[str, object]] = {}
    for path in (input.intent_path, input.spec_path, input.plan_path):
        record = _record_artifact(path, root)
        artifacts[str(record["path"])] = record

    intent_text = _read_text(input.intent_path, root, findings)
    answer_ids: list[str] = []
    if intent_text is not None:
        try:
            intent_payload = json.loads(intent_text)
        except (json.JSONDecodeError, UnicodeError, TypeError, ValueError):
            findings.append(_finding("INTENT_INVALID", _subject(input.intent_path, root), "intent is not valid JSON"))
        else:
            answer_ids = _valid_intent(intent_payload, input.intent_path, root, findings)

    spec_text = _read_text(input.spec_path, root, findings)
    spec_metadata: dict[str, Any] | None = None
    if spec_text is not None:
        spec_metadata = _metadata(spec_text, input.spec_path, root, findings)
        if spec_metadata is not None:
            for field in _REQUIRED_SPEC_FIELDS:
                value = spec_metadata.get(field)
                if not isinstance(value, str) or not value.strip():
                    findings.append(
                        _finding(
                            "SPEC_INVALID",
                            _subject(input.spec_path, root),
                            f"frontmatter field {field!r} must be a non-empty string",
                        )
                    )

    plan_text = _read_text(input.plan_path, root, findings)
    plan_metadata, plan_tasks = _parse_plan(plan_text, input.plan_path, root, findings)
    if plan_metadata is not None:
        spec_ref = plan_metadata.get("spec_ref")
        spec_id = (
            spec_metadata.get("id")
            if spec_metadata is not None and isinstance(spec_metadata.get("id"), str)
            else None
        )
        if not isinstance(spec_ref, str) or not spec_ref.strip():
            findings.append(
                _finding(
                    "PLAN_SPEC_REF",
                    _subject(input.plan_path, root),
                    "plan frontmatter must contain a non-empty spec_ref",
                )
            )
        elif not _spec_ref_matches(spec_ref, spec_id, input.spec_path, input.plan_path, root):
            findings.append(
                _finding(
                    "PLAN_SPEC_REF",
                    _subject(input.plan_path, root),
                    "plan spec_ref does not resolve to the authority spec",
                )
            )

    _check_tasks(root, input.plan_path, plan_tasks, findings)
    spec_body = _body(spec_text) if spec_text is not None else None
    plan_body = _body(plan_text) if plan_text is not None else None
    if answer_ids and spec_body is not None and plan_body is not None:
        for answer_id in answer_ids:
            if not _has_token(spec_body, answer_id):
                findings.append(
                    _finding(
                        "INTENT_UNCOVERED",
                        answer_id,
                        "intent answer id is not represented in the authority spec",
                    )
                )
            if not _has_token(plan_body, answer_id):
                findings.append(
                    _finding("INTENT_UNCOVERED", answer_id, "intent answer id is not represented in the plan")
                )

    if spec_body is not None:
        for claim_id in sorted(set(_CLAIM_RE.findall(spec_body))):
            if claim_id not in answer_ids:
                findings.append(
                    _finding(
                        "SPEC_UNSUPPORTED_CLAIM",
                        claim_id,
                        "spec claim id is not declared by an intent answer",
                    )
                )

    findings.sort(key=lambda finding: (finding.code, finding.subject, finding.detail))
    frozen_findings = tuple(findings)
    return PlanningReport(
        schema=1,
        run_id=input.run_id,
        ok=not frozen_findings,
        artifacts=tuple(artifacts[key] for key in sorted(artifacts)),
        findings=frozen_findings,
        next_actions=(),
        review_required=True,
        suggestion=None,
    )


__all__ = ["check_planning_input"]
