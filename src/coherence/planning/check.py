from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from coherence.planning.anchors import authority_anchor_matches
from coherence.planning.model import PlanningFinding, PlanningInput, PlanningReport
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_frontmatter_loads, strict_json_loads
from coherence.planning.model_policy import ModelPolicyError, load_model_policy
from substrate.ledger.plans import ParsedPlanTask, parse_plan_tasks

_CLAIM_RE = re.compile(r"(?<![A-Za-z0-9_-])claim:([A-Za-z0-9][A-Za-z0-9_.-]*)")
_TOKEN_PREFIX = "(?<![A-Za-z0-9_-])"
_TOKEN_SUFFIX = "(?![A-Za-z0-9_-])"
_REQUIRED_SPEC_FIELDS = ("id", "title", "status")
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_REQUIREMENT_ID_RE = re.compile(r"^SR-[0-9]+$")
_TASK_ID_RE = re.compile(r"^T-[0-9]+$")


def check_model_policy(root: Path) -> tuple[PlanningFinding, ...]:
    """Validate the optional project model policy without discovering providers."""
    try:
        load_model_policy(root)
    except ModelPolicyError as exc:
        return (_finding("MODEL_POLICY_INVALID", ".factory/planning/models.json", str(exc)),)
    return ()


def _relative(path: Path, root: Path) -> str | None:
    resolved = safe_resolve(root, path)
    return resolved.relative_to(root).as_posix() if resolved is not None else None


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
        canonical_path = safe_resolve(root, path)
        if canonical_path is None:
            raise ValueError("artifact path is not a safe project path")
        record["sha256"] = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    except (OSError, RuntimeError, ValueError):
        record["sha256"] = None
    return record


def _read_text(path: Path, root: Path, findings: list[PlanningFinding]) -> str | None:
    subject = _subject(path, root)
    if "\x00" in str(path):
        findings.append(_finding("INPUT_READ_ERROR", subject, "source artifact path is invalid"))
        return None
    if _relative(path, root) is None:
        findings.append(
            _finding("ARTIFACT_OUTSIDE_PROJECT", subject, "source artifact must be located below project_root")
        )
        return None
    try:
        canonical_path = safe_resolve(root, path)
        if canonical_path is None:
            raise ValueError("artifact path is not a safe project path")
        return canonical_path.read_text(encoding="utf-8")
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
        post = strict_frontmatter_loads(text)
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
        findings.append(_finding("FRONTMATTER_INVALID", _subject(path, root), "frontmatter is malformed"))
        return None
    return dict(post.metadata)


def _body(text: str) -> str:
    """Return document content without frontmatter metadata."""
    try:
        return strict_frontmatter_loads(text).content
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
        return text


def _valid_intent(
    payload: object,
    path: Path,
    root: Path,
    findings: list[PlanningFinding],
    expected_run_id: str | None = None,
) -> list[str]:
    subject = _subject(path, root)
    if not isinstance(payload, dict):
        findings.append(_finding("INTENT_INVALID", subject, "intent must be a JSON object"))
        return []
    schema = payload.get("schema")
    if type(schema) is not int or schema not in {1, 2}:
        findings.append(_finding("INTENT_INVALID", subject, "intent schema must equal 1 or 2"))
        return []
    valid = True
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        findings.append(_finding("INTENT_INVALID", subject, "intent prompt must be non-empty"))
        valid = False
    if schema == 2:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or _SAFE_IDENTIFIER_RE.fullmatch(run_id) is None:
            findings.append(_finding("INTENT_INVALID", subject, "schema-2 intent run_id is invalid"))
            valid = False
        elif expected_run_id is not None and run_id != expected_run_id:
            findings.append(_finding("INTENT_INVALID", subject, "schema-2 intent run_id does not match the planning run"))
            valid = False
        brief = payload.get("brief")
        required_brief = {"goal", "scope", "constraints", "non_goals", "done_when", "open_questions"}
        if (
            not isinstance(brief, dict)
            or set(brief) != required_brief
            or any(not isinstance(value, list) or any(not isinstance(item, str) for item in value) for value in brief.values())
        ):
            findings.append(_finding("INTENT_INVALID", subject, "schema-2 intent brief is invalid"))
            valid = False
        if payload.get("capture_status") not in {"provisional", "needs_user", "cancelled"}:
            findings.append(_finding("INTENT_INVALID", subject, "schema-2 capture_status is invalid"))
            valid = False
        redactions = payload.get("redactions")
        if not isinstance(redactions, list) or any(not isinstance(item, str) for item in redactions):
            findings.append(_finding("INTENT_INVALID", subject, "schema-2 redactions must be a list of text values"))
            valid = False
    answers = payload.get("answers")
    answer_ids: list[str] = []
    if not isinstance(answers, list):
        findings.append(_finding("INTENT_INVALID", subject, "intent answers must be a list"))
        return []
    if not answers:
        if schema == 1:
            findings.append(_finding("INTENT_INVALID", subject, "intent answers must be a non-empty list"))
        return answer_ids if valid else []
    sequences: list[int] = []
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
            findings.append(_finding("INTENT_INVALID", subject, f"duplicate answer id {_redact_detail(answer_id)}"))
            valid = False
        else:
            answer_ids.append(answer_id)
        if not isinstance(answer_text, str) or not answer_text.strip():
            findings.append(_finding("INTENT_INVALID", subject, f"answer {index} text must be non-empty"))
            valid = False
        if schema == 2:
            for field in ("question", "source"):
                if not isinstance(answer.get(field), str):
                    findings.append(_finding("INTENT_INVALID", subject, f"answer {index} {field} must be text"))
                    valid = False
            sequence = answer.get("sequence")
            if type(sequence) is not int or sequence < 1:
                findings.append(_finding("INTENT_INVALID", subject, f"answer {index} sequence must be positive"))
                valid = False
            elif sequence in sequences:
                findings.append(_finding("INTENT_INVALID", subject, f"duplicate answer sequence {sequence}"))
                valid = False
            else:
                sequences.append(sequence)
    return answer_ids if valid else []


def _redact_detail(value: object) -> str:
    return re.sub(
        r"(?i)\\b(?:api[_-]?key|secret|password|passwd|token)\\b\\s*[:=]\\s*[^\\s,;]+",
        "[REDACTED]",
        str(value),
    )


def _has_token(text: str, token: str) -> bool:
    return re.search(_TOKEN_PREFIX + re.escape(token) + _TOKEN_SUFFIX, text) is not None


def _safe_reference(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    normalized = value.replace("\\", "/")
    return (
        not any(ord(char) < 32 for char in normalized)
        and not normalized.startswith("/")
        and re.match(r"^[A-Za-z]:", normalized) is None
        and all(part not in {"", ".", ".."} for part in normalized.split("/"))
    )


def _spec_ref_matches(
    ref: str, spec_id: str | None, spec_path: Path, plan_path: Path, root: Path
) -> bool:
    if spec_id is not None and _SAFE_IDENTIFIER_RE.fullmatch(spec_id) is None:
        return False
    if spec_id is not None and ref in {spec_id, f"spec:{spec_id}"}:
        return True
    if not _safe_reference(ref):
        return False
    try:
        ref_path = Path(ref)
    except (OSError, ValueError):
        return False
    if ref_path.is_absolute():
        return False
    expected = safe_resolve(root, spec_path)
    if expected is None:
        return False
    candidates = (
        root / ref_path,
        root / "docs" / "superpowers" / "specs" / ref_path,
        plan_path.parent / ref_path,
        plan_path.parent.parent / "specs" / ref_path,
    )
    return any(safe_resolve(root, candidate) == expected for candidate in candidates)


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
    else:
        numbers = [task.number for task in tasks]
        if len(numbers) != len(set(numbers)):
            findings.append(_finding("PLAN_INVALID", _subject(path, root), "plan task numbers must be unique"))
        for task in tasks:
            if not isinstance(task.files_block, str) or not task.files_block.strip():
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
) -> tuple[Path, ...]:
    expected_plan = _relative(plan_path, root)
    if expected_plan is None:
        return ()
    mappings: dict[int, list[str]] = {}
    task_ids: dict[str, str] = {}
    matched_paths: list[Path] = []
    tasks_dir = root / "tasks"
    if _relative(tasks_dir, root) != "tasks":
        findings.append(
            _finding(
                "ARTIFACT_OUTSIDE_PROJECT",
                "tasks",
                "generated task directory must remain inside project_root",
            )
        )
        return ()
    try:
        task_paths = sorted(tasks_dir.glob("T-*.md"), key=lambda path: path.name)
    except OSError:
        findings.append(_finding("TASKS_UNREADABLE", "tasks", "generated task directory could not be read"))
        return ()
    for task_path in task_paths:
        text = _read_text(task_path, root, findings)
        if text is None:
            continue
        metadata = _metadata(text, task_path, root, findings)
        if metadata is None:
            continue
        matched_paths.append(task_path)
        task_id = metadata.get("id")
        if not isinstance(task_id, str) or _TASK_ID_RE.fullmatch(task_id) is None:
            findings.append(
                _finding("PLAN_TASK_PARITY", _subject(task_path, root), "generated task id must match T-<digits>")
            )
        elif task_id in task_ids:
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    _subject(task_path, root),
                    f"generated task id duplicates {_subject(Path(task_ids[task_id]), root)}",
                )
            )
        else:
            task_ids[task_id] = str(task_path)
        if metadata.get("source_plan") != expected_plan:
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    _subject(task_path, root),
                    "generated task source_plan does not match the selected plan",
                )
            )
            continue
        source_task = metadata.get("source_task")
        if type(source_task) is not int or source_task < 1:
            findings.append(_finding("PLAN_TASK_PARITY", _subject(task_path, root), "source_task must be a positive integer"))
            continue
        mappings.setdefault(source_task, []).append(str(task_id))
        for field in ("id", "title", "status", "source_plan", "source_task"):
            value = metadata.get(field)
            if field == "source_task":
                valid = type(value) is int and value > 0
            else:
                valid = isinstance(value, str) and bool(value.strip())
            if not valid:
                findings.append(_finding("TASK_METADATA_INVALID", _subject(task_path, root), f"task field {field} is invalid"))
    expected_numbers = {task.number for task in tasks}
    for number in sorted(expected_numbers):
        ids = mappings.get(number, [])
        if len(ids) != 1:
            findings.append(
                _finding(
                    "PLAN_TASK_PARITY",
                    _subject(plan_path, root),
                    f"plan task {number} maps to {len(ids)} generated task records",
                )
            )
    for number in sorted(set(mappings) - expected_numbers):
        findings.append(
            _finding(
                "PLAN_TASK_PARITY",
                _subject(plan_path, root),
                f"generated task source_task {number} is not present in the plan",
            )
        )
    return tuple(matched_paths)


def _planning_reference_paths(root: Path, run_id: str) -> tuple[Path, ...]:
    """Collect optional FEAT-017 closure inputs into the review evidence."""
    feature_path = root / "docs" / "features" / "FEAT-017.md"
    bundle_path = root / "bundles" / "FEAT-017.json"
    paths: list[Path] = []
    for path in (feature_path, bundle_path):
        safe_path = safe_resolve(root, path)
        if safe_path is not None and safe_path.is_file():
            paths.append(path)
    if safe_resolve(root, feature_path) is not None and feature_path.is_file():
        try:
            metadata = strict_frontmatter_loads(feature_path.read_text(encoding="utf-8")).metadata
        except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
            metadata = {}
        requirement_ids = metadata.get("requirements", [])
        if isinstance(requirement_ids, list):
            paths.extend(
                root / "requirements" / f"{item}.md"
                for item in requirement_ids
                if isinstance(item, str) and _REQUIREMENT_ID_RE.fullmatch(item) is not None
            )
    consent_path = root / ".factory" / "planning" / run_id / "requirement-consent.json"
    if safe_resolve(root, consent_path) is not None and consent_path.is_file():
        paths.append(consent_path)
    capture_journal = root / ".factory" / "planning" / run_id / "capture" / "events.jsonl"
    if safe_resolve(root, capture_journal) is not None and capture_journal.is_file():
        paths.append(capture_journal)
    return tuple(paths)


def _check_planning_references(
    root: Path,
    spec_path: Path,
    spec_text: str | None,
    findings: list[PlanningFinding],
) -> None:
    """Validate FEAT-017 closure inputs when a feature dossier is present."""
    feature_candidate = root / "docs" / "features" / "FEAT-017.md"
    feature_path = safe_resolve(root, feature_candidate)
    if feature_path is None:
        if feature_candidate.exists() or feature_candidate.is_symlink():
            _read_text(feature_candidate, root, findings)
        return
    if not feature_path.is_file():
        return
    feature_text = _read_text(feature_path, root, findings)
    feature_metadata = _metadata(feature_text, feature_path, root, findings) if feature_text is not None else None
    if feature_metadata is None:
        return
    requirement_ids = feature_metadata.get("requirements")
    if (
        feature_metadata.get("id") != "FEAT-017"
        or not isinstance(feature_metadata.get("title"), str)
        or not str(feature_metadata.get("title", "")).strip()
        or not isinstance(requirement_ids, list)
        or not requirement_ids
        or any(not isinstance(item, str) or _REQUIREMENT_ID_RE.fullmatch(item) is None for item in requirement_ids)
        or len(requirement_ids) != len(set(requirement_ids))
    ):
        findings.append(_finding("PLANNING_REFERENCE_INVALID", _subject(feature_path, root), "FEAT-017 dossier has invalid closure metadata"))
        return
    bundle_path = root / "bundles" / "FEAT-017.json"
    bundle_text = _read_text(bundle_path, root, findings)
    if bundle_text is None:
        return
    try:
        bundle = strict_json_loads(bundle_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        findings.append(_finding("PLANNING_REFERENCE_INVALID", _subject(bundle_path, root), "FEAT-017 bundle is invalid JSON"))
        return
    members = bundle.get("members") if isinstance(bundle, dict) else None
    expected_members = {"feat:FEAT-017", *(f"sr:{item}" for item in requirement_ids)}
    members_valid = (
        isinstance(members, list)
        and all(isinstance(item, str) for item in members)
        and len(members) == len(set(members))
        and set(members) == expected_members
    )
    if not isinstance(bundle, dict) or bundle.get("id") != "FEAT-017" or not members_valid:
        findings.append(_finding("PLANNING_REFERENCE_INVALID", _subject(bundle_path, root), "FEAT-017 bundle membership is not an exact closure"))
    for req_id in requirement_ids:
        req_path = root / "requirements" / f"{req_id}.md"
        req_text = _read_text(req_path, root, findings)
        req_metadata = _metadata(req_text, req_path, root, findings) if req_text is not None else None
        if req_metadata is None:
            continue
        required = ("id", "title", "statement", "domain", "source")
        if (
            req_metadata.get("id") != req_id
            or any(not isinstance(req_metadata.get(field), str) or not str(req_metadata[field]).strip() for field in required)
            or not isinstance(req_metadata.get("upstream"), list)
            or any(not isinstance(item, str) for item in req_metadata["upstream"])
        ):
            findings.append(_finding("PLANNING_REFERENCE_INVALID", _subject(req_path, root), "requirement has incomplete canonical metadata"))
            continue
        source = str(req_metadata["source"])
        source_path, _, anchor = source.partition("#")
        safe_source = safe_resolve(root, root / source_path)
        safe_spec = safe_resolve(root, spec_path)
        if (
            not _safe_reference(source_path)
            or not anchor.strip()
            or spec_text is None
            or safe_source is None
            or safe_spec is None
            or safe_source != safe_spec
            or not authority_anchor_matches(_body(spec_text), anchor.strip())
        ):
            findings.append(_finding("PLANNING_REFERENCE_INVALID", _subject(req_path, root), "requirement source does not resolve to the authority spec"))


def check_planning_input(input: PlanningInput) -> PlanningReport:
    """Check planning source files without writing or invoking downstream work."""
    root = safe_root(input.project_root)
    findings: list[PlanningFinding] = []
    if root is None:
        root = input.project_root.absolute()
        findings.append(
            _finding(
                "PROJECT_ROOT_INVALID",
                "project_root",
                "project_root contains a symlink or reparse point",
            )
        )
    artifacts: dict[str, dict[str, object]] = {}
    intent_text = _read_text(input.intent_path, root, findings)
    spec_text = _read_text(input.spec_path, root, findings)
    plan_text = _read_text(input.plan_path, root, findings)
    for path in (input.intent_path, input.spec_path, input.plan_path):
        record = _record_artifact(path, root)
        artifacts[str(record["path"])] = record
    intent_payload: object = None
    if intent_text is not None:
        try:
            intent_payload = strict_json_loads(intent_text)
        except (TypeError, ValueError, json.JSONDecodeError):
            findings.append(_finding("INTENT_INVALID", _subject(input.intent_path, root), "intent is invalid JSON"))
    answer_ids = _valid_intent(intent_payload, input.intent_path, root, findings, input.run_id)
    spec_metadata = _metadata(spec_text, input.spec_path, root, findings) if spec_text is not None else None
    if spec_metadata is not None:
        for field in _REQUIRED_SPEC_FIELDS:
            if not isinstance(spec_metadata.get(field), str) or not spec_metadata[field].strip():
                findings.append(_finding("SPEC_INVALID", _subject(input.spec_path, root), f"spec field {field} is required"))
    plan_metadata, plan_tasks = _parse_plan(plan_text, input.plan_path, root, findings)
    if plan_metadata is not None:
        spec_ref = plan_metadata.get("spec_ref")
        spec_id = spec_metadata.get("id") if spec_metadata else None
        if not isinstance(spec_ref, str) or not spec_ref.strip():
            findings.append(_finding("PLAN_SPEC_REF", _subject(input.plan_path, root), "plan frontmatter must contain a non-empty spec_ref"))
        elif not _spec_ref_matches(spec_ref, spec_id, input.spec_path, input.plan_path, root):
            findings.append(_finding("PLAN_SPEC_REF", _subject(input.plan_path, root), "plan spec_ref does not resolve to the authority spec"))
    for task_path in _check_tasks(root, input.plan_path, plan_tasks, findings):
        record = _record_artifact(task_path, root)
        artifacts[str(record["path"])] = record
    for reference_path in _planning_reference_paths(root, input.run_id):
        record = _record_artifact(reference_path, root)
        artifacts[str(record["path"])] = record
    _check_planning_references(root, input.spec_path, spec_text, findings)
    spec_body = _body(spec_text) if spec_text is not None else None
    plan_body = _body(plan_text) if plan_text is not None else None
    if answer_ids and spec_body is not None and plan_body is not None:
        for answer_id in answer_ids:
            if not _has_token(spec_body, answer_id):
                findings.append(_finding("INTENT_UNCOVERED", answer_id, "intent answer id is not represented in the authority spec"))
            if not _has_token(plan_body, answer_id):
                findings.append(_finding("INTENT_UNCOVERED", answer_id, "intent answer id is not represented in the plan"))
    if spec_body is not None:
        for claim_id in sorted(set(_CLAIM_RE.findall(spec_body))):
            if claim_id not in answer_ids:
                findings.append(_finding("SPEC_UNSUPPORTED_CLAIM", claim_id, "spec claim id is not declared by an intent answer"))
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
