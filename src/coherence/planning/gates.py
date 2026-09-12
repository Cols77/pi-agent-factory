from __future__ import annotations

import json
import hashlib
import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import yaml

from coherence.planning.anchors import authority_anchor_matches
from coherence.planning.artifacts import ArtifactError, read_artifact_manifest
from coherence.planning.check import (
    _CLAIM_RE,
    _REQUIRED_SPEC_FIELDS,
    _check_planning_references,
    _has_token,
    _spec_ref_matches,
)
from coherence.planning.consent import validate_sr_decisions
from coherence.planning.intent import IntentError, read_intent, validate_intent
from coherence.planning.model import PlanningFinding
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_frontmatter_loads, strict_json_loads
from coherence.planning.review import GeneratedTaskReviewInput, review_cross_artifact_relations
from coherence.register.register import parse_requirement
from substrate.ledger.tasks import load_tasks

_REQUIRED_FEATURE_ID = "FEAT-017"
_CONSENT_KEYS = frozenset({"schema", "run_id", "decision", "reviewer", "reason", "requirements"})
_SR_CONSENT_KEYS = frozenset({
    "schema", "run_id", "decision", "reviewer", "phrase", "candidate_srs",
    "derivation_report_sha256", "artifact_hashes",
})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SR_ID = re.compile(r"^SR-[0-9]+$")
_CONSENT_PHRASE = "I explicitly consent to adopt exactly these candidate SRs."

# Planning gates are deliberately a separate, small assurance surface.  They
# attest only the persisted planning records below; they never dispatch the
# factory gate runner or make claims about implementation validation.
_PLANNING_GATE_FEATURE = "FEAT-017"
_PLANNING_GATE_VERSION = "v1"
_PACK_KEYS = frozenset({"schema", "feature_id", "version", "workflows", "gates", "sha256"})
_PACK_GATE_KEYS = frozenset({
    "id", "stage", "required", "resolver", "dependencies", "expected_evidence",
    "failure_behavior",
})
_RESULT_KEYS = frozenset({
    "schema", "run_id", "feature_id", "version", "planning_gate_pack_sha256",
    "executions",
})
_EXECUTION_KEYS = frozenset({"gate_id", "status", "required", "evidence"})
_PLANNING_REPORT_KEYS = (
    "schema", "run_id", "ok", "artifacts", "findings", "next_actions", "review_required",
    "suggestion",
)
_REVIEW_DECISION_KEYS = frozenset({
    "schema", "run_id", "decision", "reviewer", "reason", "reviewed_artifacts",
    "report_sha256",
})
_WORKFLOWS = ("standard-development", "health-recovery", "feature-planning")
_REQUIRED_ARTIFACT_KINDS = frozenset({"intent", "spec", "plan", "feature", "bundle", "requirements"})


class PlanningGateError(ValueError):
    """A compiled planning gate pack or its result is invalid or stale."""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_digest(payload: Mapping[str, object]) -> str:
    return _digest(json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8"))


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _valid_gate_run_id(value: object) -> bool:
    return isinstance(value, str) and _RUN_ID.fullmatch(value) is not None


def _planning_run_dir(root: Path, run_id: object) -> Path:
    if not _valid_gate_run_id(run_id):
        raise PlanningGateError("planning gate run_id is invalid")
    project_root = safe_root(root)
    if project_root is None:
        raise PlanningGateError("planning gate project root is unsafe")
    run_dir = safe_resolve(project_root, project_root / ".factory" / "planning" / str(run_id))
    if run_dir is None:
        raise PlanningGateError("planning gate run directory is unsafe")
    return run_dir


def _pack_without_digest(feature_id: str, version: str) -> dict[str, object]:
    gates: list[dict[str, object]] = [
        {
            "id": "planning-report-current",
            "stage": "planning",
            "required": True,
            "resolver": "planning_report_current",
            "dependencies": [],
            "expected_evidence": ["report.json", "canonical_artifacts"],
            "failure_behavior": "block_handoff",
        },
        {
            "id": "human-review-current",
            "stage": "planning",
            "required": True,
            "resolver": "human_review_current",
            "dependencies": ["planning-report-current"],
            "expected_evidence": ["review-decision.json", "report.json"],
            "failure_behavior": "block_handoff",
        },
        {
            "id": "requirement-consent-current",
            "stage": "planning",
            "required": True,
            "resolver": "requirement_consent_current",
            "dependencies": ["planning-report-current"],
            "expected_evidence": ["feature_requirements", "per_sr_consent"],
            "failure_behavior": "block_handoff",
        },
        {
            "id": "cross-artifact-review-current",
            "stage": "planning",
            "required": True,
            "resolver": "cross_artifact_review_current",
            "dependencies": ["planning-report-current"],
            "expected_evidence": ["cross-artifact-review.json", "task_relation_artifacts"],
            "failure_behavior": "block_handoff",
        },
    ]
    return {
        "schema": 1,
        "feature_id": feature_id,
        "version": version,
        "workflows": list(_WORKFLOWS),
        "gates": gates,
    }


def compile_planning_gate_pack(feature_id: str, version: str) -> dict[str, object]:
    """Compile the one supported, deterministic FEAT-017 planning gate pack."""
    if feature_id != _PLANNING_GATE_FEATURE:
        raise PlanningGateError("unknown planning gate feature")
    if version != _PLANNING_GATE_VERSION:
        raise PlanningGateError("unknown planning gate pack version")
    payload = _pack_without_digest(feature_id, version)
    return {**payload, "sha256": _canonical_digest(payload)}


def _validated_pack(pack: object) -> dict[str, object]:
    if type(pack) is not dict or set(pack) != _PACK_KEYS:
        raise PlanningGateError("planning gate pack schema is invalid")
    if type(pack.get("schema")) is not int or pack.get("schema") != 1:
        raise PlanningGateError("planning gate pack schema is invalid")
    if type(pack.get("feature_id")) is not str or type(pack.get("version")) is not str:
        raise PlanningGateError("planning gate pack identity is invalid")
    supplied_digest = pack.get("sha256")
    supplied_payload = {key: value for key, value in pack.items() if key != "sha256"}
    if type(supplied_digest) is not str or not _valid_digest(supplied_digest) or supplied_digest != _canonical_digest(supplied_payload):
        raise PlanningGateError("planning gate pack digest is invalid")
    workflows = pack.get("workflows")
    if workflows != list(_WORKFLOWS):
        raise PlanningGateError("planning gate pack workflows are invalid")
    gates = pack.get("gates")
    if type(gates) is not list or not gates:
        raise PlanningGateError("planning gate pack gates are invalid")
    for gate in gates:
        if type(gate) is not dict or set(gate) != _PACK_GATE_KEYS:
            raise PlanningGateError("planning gate entry schema is invalid")
        if (
            type(gate.get("id")) is not str or not gate["id"]
            or type(gate.get("stage")) is not str or not gate["stage"]
            or type(gate.get("required")) is not bool
            or type(gate.get("resolver")) is not str or not gate["resolver"]
            or type(gate.get("failure_behavior")) is not str or not gate["failure_behavior"]
        ):
            raise PlanningGateError("planning gate entry has invalid field types")
        dependencies = gate.get("dependencies")
        expected_evidence = gate.get("expected_evidence")
        if (
            type(dependencies) is not list or not all(type(item) is str and item for item in dependencies)
            or dependencies != sorted(dependencies) or len(dependencies) != len(set(dependencies))
            or type(expected_evidence) is not list or not all(type(item) is str and item for item in expected_evidence)
            or len(expected_evidence) != len(set(expected_evidence))
        ):
            raise PlanningGateError("planning gate entry lists are invalid")
    if pack.get("feature_id") != _PLANNING_GATE_FEATURE or pack.get("version") != _PLANNING_GATE_VERSION:
        raise PlanningGateError("planning gate pack identity is unknown")
    expected = compile_planning_gate_pack(_PLANNING_GATE_FEATURE, _PLANNING_GATE_VERSION)
    if pack != expected:
        raise PlanningGateError("planning gate pack is malformed or does not match its version")
    return expected


def _read_json(path: Path, detail: str) -> object:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PlanningGateError(detail) from exc


def _planning_report(root: Path, run_id: str) -> tuple[dict[str, object], list[dict[str, str]]]:
    run_dir = _planning_run_dir(root, run_id)
    report_path = safe_resolve(root, run_dir / "report.json")
    if report_path is None or not report_path.is_file():
        raise PlanningGateError("planning report evidence is missing")
    payload = _read_json(report_path, "planning report evidence is unreadable")
    if not isinstance(payload, dict) or tuple(payload) != _PLANNING_REPORT_KEYS:
        raise PlanningGateError("planning report evidence has an invalid schema")
    if (
        type(payload.get("schema")) is not int or payload.get("schema") != 1
        or payload.get("run_id") != run_id or payload.get("ok") is not True
        or payload.get("review_required") is not True or payload.get("suggestion") is not None
    ):
        raise PlanningGateError("planning report evidence is not a clean current report")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise PlanningGateError("planning report findings are invalid")
    # Match run._report_artifacts' review-decision contract: only warnings
    # are compatible with a clean report, regardless of the report's ok flag.
    for finding in findings:
        if (
            not isinstance(finding, dict) or set(finding) != {"code", "severity", "subject", "detail"}
            or not all(isinstance(finding.get(field), str) for field in ("code", "severity", "subject", "detail"))
            or finding["severity"] not in {"error", "warning"}
        ):
            raise PlanningGateError("planning report findings are invalid")
        if finding["severity"] == "error":
            raise PlanningGateError("planning report contains blocking error findings")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise PlanningGateError("planning report has no canonical artifacts")
    expected: list[dict[str, str]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise PlanningGateError("planning report has invalid canonical artifacts")
        path, digest = artifact.get("path"), artifact.get("sha256")
        if not _safe_relative(path) or not _valid_digest(digest):
            raise PlanningGateError("planning report has invalid canonical artifacts")
        source = safe_resolve(root, root / Path(str(path)))
        if source is None or not source.is_file() or _digest(source.read_bytes()) != digest:
            raise PlanningGateError("planning report canonical artifact is stale")
        expected.append({"path": str(path), "sha256": str(digest)})
    if [entry["path"] for entry in expected] != sorted(entry["path"] for entry in expected):
        raise PlanningGateError("planning report canonical artifacts are not ordered")
    if len({entry["path"] for entry in expected}) != len(expected):
        raise PlanningGateError("planning report canonical artifacts are duplicated")
    return payload, [{"path": ".factory/planning/%s/report.json" % run_id, "sha256": _digest(report_path.read_bytes())}, *expected]


def _resolve_planning_report(root: Path, run_id: str) -> tuple[str, list[dict[str, str]]]:
    try:
        _, evidence = _planning_report(root, run_id)
    except PlanningGateError:
        return "fail", []
    return "pass", evidence


def _required_planning_sources(
    root: Path, run_id: str,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Validate and hash the complete, current planning source set.

    The manifest is the existing transport for source selection.  It is not a
    second planning state: this boundary merely requires that its selections,
    the report, and the canonical FEAT-017 registration describe the same
    current files.
    """
    run_dir = _planning_run_dir(root, run_id)
    manifest_path = safe_resolve(root, run_dir / "artifacts.json")
    if manifest_path is None or not manifest_path.is_file():
        raise PlanningGateError("artifact manifest is missing")
    try:
        manifest = read_artifact_manifest(root, run_id)
    except ArtifactError as exc:
        raise PlanningGateError("artifact manifest is invalid") from exc
    manifest_items = manifest.get("artifacts")
    if not isinstance(manifest_items, list):
        raise PlanningGateError("artifact manifest entries are invalid")
    by_kind = {item["kind"]: item for item in manifest_items if isinstance(item, dict)}
    if set(by_kind) != _REQUIRED_ARTIFACT_KINDS:
        raise PlanningGateError("artifact manifest does not cover the required planning sources")
    fixed_paths = {
        "intent": ".intent/intent.json",
        "feature": "docs/features/FEAT-017.md",
        "bundle": "bundles/FEAT-017.json",
    }
    if any(by_kind[kind].get("path") != path for kind, path in fixed_paths.items()):
        raise PlanningGateError("artifact manifest source paths are invalid")
    spec_path = safe_resolve(root, root / str(by_kind["spec"]["path"]))
    plan_path = safe_resolve(root, root / str(by_kind["plan"]["path"]))
    intent_path = safe_resolve(root, root / ".intent" / "intent.json")
    if (
        spec_path is None or plan_path is None or intent_path is None
        or not spec_path.is_file() or not plan_path.is_file() or not intent_path.is_file()
    ):
        raise PlanningGateError("required planning source is missing")
    try:
        intent = read_intent(intent_path, project_root=root)
    except IntentError as exc:
        raise PlanningGateError("captured intent is invalid") from exc
    if intent.run_id is not None and intent.run_id != run_id:
        raise PlanningGateError("captured intent belongs to another run")
    if any(finding.severity == "error" for finding in validate_intent(intent)):
        raise PlanningGateError("captured intent is not current and valid")
    spec_metadata = _read_metadata(spec_path)
    plan_metadata = _read_metadata(plan_path)
    if spec_metadata is None or plan_metadata is None:
        raise PlanningGateError("captured intent, specification, and plan are not aligned")
    if any(
        not isinstance(spec_metadata.get(field), str) or not str(spec_metadata[field]).strip()
        for field in _REQUIRED_SPEC_FIELDS
    ):
        raise PlanningGateError("specification has incomplete required fields")
    spec_ref = plan_metadata.get("spec_ref")
    if not isinstance(spec_ref, str) or not _spec_ref_matches(
        spec_ref, spec_metadata["id"], spec_path, plan_path, root,
    ):
        raise PlanningGateError("plan spec_ref does not resolve to the authority specification")
    try:
        spec_body = strict_frontmatter_loads(spec_path.read_text(encoding="utf-8")).content
        plan_body = strict_frontmatter_loads(plan_path.read_text(encoding="utf-8")).content
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise PlanningGateError("captured intent, specification, and plan are unreadable") from exc
    answer_ids = {answer.id for answer in intent.answers}
    if (
        not answer_ids
        or any(not _has_token(spec_body, answer_id) or not _has_token(plan_body, answer_id) for answer_id in answer_ids)
        or any(claim_id not in answer_ids for claim_id in _CLAIM_RE.findall(spec_body))
    ):
        raise PlanningGateError("captured intent, specification, and plan are not aligned")
    reference_findings: list[PlanningFinding] = []
    _check_planning_references(root, spec_path, spec_path.read_text(encoding="utf-8"), reference_findings)
    if reference_findings:
        raise PlanningGateError("feature registration or requirement metadata is invalid")
    current, feature_evidence = _current_feature_requirements(root, spec_path=spec_path)
    requirement_manifest_path = by_kind["requirements"].get("path")
    if requirement_manifest_path not in {f"requirements/{requirement_id}.md" for requirement_id in current}:
        raise PlanningGateError("artifact manifest requirement source is invalid")
    report, report_evidence = _planning_report(root, run_id)
    report_artifacts = report.get("artifacts")
    assert isinstance(report_artifacts, list)  # guaranteed by _planning_report
    report_hashes = {item["path"]: item["sha256"] for item in report_artifacts}
    required_evidence = [
        *manifest_items,
        *({"path": item["path"], "sha256": item["sha256"]} for item in feature_evidence),
    ]
    for item in required_evidence:
        path, digest = item.get("path"), item.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str) or report_hashes.get(path) != digest:
            raise PlanningGateError("planning report does not cover the current planning sources")
    evidence = [
        *report_evidence,
        {"path": f".factory/planning/{run_id}/artifacts.json", "sha256": _digest(manifest_path.read_bytes())},
    ]
    return current, _deduplicated_evidence(evidence)


def _deduplicated_evidence(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Reject conflicting evidence and retain deterministic first occurrence order."""
    result: list[dict[str, str]] = []
    seen: dict[str, str] = {}
    for item in items:
        path, digest = item.get("path"), item.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str) or not _valid_digest(digest):
            raise PlanningGateError("planning gate evidence is invalid")
        if path in seen:
            if seen[path] != digest:
                raise PlanningGateError("planning gate evidence is contradictory")
            continue
        seen[path] = digest
        result.append({"path": path, "sha256": digest})
    return result


def _resolve_human_review(root: Path, run_id: str) -> tuple[str, list[dict[str, str]]]:
    try:
        report, report_evidence = _planning_report(root, run_id)
        _, source_evidence = _required_planning_sources(root, run_id)
        run_dir = _planning_run_dir(root, run_id)
        path = safe_resolve(root, run_dir / "review-decision.json")
        if path is None or not path.is_file():
            raise PlanningGateError("review decision is missing")
        decision = _read_json(path, "review decision is unreadable")
        if not isinstance(decision, dict) or set(decision) != _REVIEW_DECISION_KEYS:
            raise PlanningGateError("review decision schema is invalid")
        reviewed = decision.get("reviewed_artifacts")
        artifacts = report.get("artifacts")
        if not isinstance(artifacts, list) or not all(isinstance(artifact, dict) for artifact in artifacts):
            raise PlanningGateError("planning report artifacts are invalid")
        if (
            type(decision.get("schema")) is not int or decision.get("schema") != 1
            or decision.get("run_id") != run_id or decision.get("decision") != "approve"
            or decision.get("reviewer") != "human"
            or not isinstance(decision.get("reason"), str) or not str(decision["reason"]).strip()
            or not isinstance(reviewed, list)
            or reviewed != [artifact["path"] for artifact in artifacts]
            or decision.get("report_sha256") != _canonical_digest(report)
        ):
            raise PlanningGateError("review decision is not current and approved")
        evidence = [
            {"path": f".factory/planning/{run_id}/review-decision.json", "sha256": _digest(path.read_bytes())},
            *source_evidence,
        ]
        return "pass", _deduplicated_evidence(evidence)
    except (PlanningGateError, ArtifactError):
        return "fail", []


def _current_feature_requirements(
    root: Path, *, spec_path: Path | None = None,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Return the current FEAT-017 requirements and their planning consent evidence."""
    feature_path = safe_resolve(root, root / "docs" / "features" / f"{_PLANNING_GATE_FEATURE}.md")
    if feature_path is None or not feature_path.is_file():
        raise PlanningGateError("feature requirement coverage is missing")
    metadata = _read_metadata(feature_path)
    requirement_ids = metadata.get("requirements") if metadata is not None else None
    if (
        metadata is None or metadata.get("id") != _PLANNING_GATE_FEATURE
        or not isinstance(requirement_ids, list) or not requirement_ids
        or not all(isinstance(item, str) and _SR_ID.fullmatch(item) is not None for item in requirement_ids)
        or len(requirement_ids) != len(set(requirement_ids))
    ):
        raise PlanningGateError("feature requirement coverage is invalid")
    current: dict[str, str] = {}
    evidence = [{"path": "docs/features/FEAT-017.md", "sha256": _digest(feature_path.read_bytes())}]
    if spec_path is not None:
        bundle_path = safe_resolve(root, root / "bundles" / f"{_PLANNING_GATE_FEATURE}.json")
        if bundle_path is None or not bundle_path.is_file():
            raise PlanningGateError("feature bundle is missing")
        bundle = _read_json(bundle_path, "feature bundle is unreadable")
        if not isinstance(bundle, dict) or set(bundle) != {"id", "members"} or bundle.get("id") != _PLANNING_GATE_FEATURE:
            raise PlanningGateError("feature bundle is invalid")
        bundle_valid, _ = _validate_feat17_bundle_members(bundle.get("members"), list(requirement_ids))
        if not bundle_valid:
            raise PlanningGateError("feature bundle membership is invalid")
        evidence.append({"path": "bundles/FEAT-017.json", "sha256": _digest(bundle_path.read_bytes())})
    for requirement_id in sorted(requirement_ids):
        requirement_path = safe_resolve(root, root / "requirements" / f"{requirement_id}.md")
        if requirement_path is None or not requirement_path.is_file():
            raise PlanningGateError("current feature requirement is missing")
        requirement_metadata = _read_metadata(requirement_path)
        if requirement_metadata is None or requirement_metadata.get("id") != requirement_id:
            raise PlanningGateError("current feature requirement is malformed")
        if spec_path is not None:
            if any(
                not isinstance(requirement_metadata.get(field), str) or not str(requirement_metadata[field]).strip()
                for field in ("title", "statement", "domain")
            ) or not isinstance(requirement_metadata.get("upstream"), list):
                raise PlanningGateError("current feature requirement is incomplete")
            if not _source_matches(root, requirement_metadata.get("source"), spec_path):
                raise PlanningGateError("current feature requirement source is invalid")
        current[requirement_id] = _digest(requirement_path.read_bytes())
        evidence.append({"path": f"requirements/{requirement_id}.md", "sha256": current[requirement_id]})
    return current, evidence


def _resolve_requirement_consent(root: Path, run_id: str) -> tuple[str, list[dict[str, str]]]:
    try:
        run_dir = _planning_run_dir(root, run_id)
        current, current_evidence = _required_planning_sources(root, run_id)
        path = safe_resolve(root, run_dir / "requirement-consent.json")
        if path is None:
            raise PlanningGateError("requirement consent path is unsafe")
        # Legacy records remain readable but can never replace per-SR consent.
        if path.exists():
            consent = _read_json(path, "requirement consent is unreadable")
            if not isinstance(consent, dict) or set(consent) != _CONSENT_KEYS:
                raise PlanningGateError("requirement consent schema is invalid")
            if (
                type(consent.get("schema")) is not int or consent.get("schema") != 1
                or consent.get("run_id") != run_id or consent.get("decision") != "approve"
                or consent.get("reviewer") != "human"
                or not isinstance(consent.get("reason"), str) or not str(consent["reason"]).strip()
                or consent.get("requirements") != list(current)
            ):
                raise PlanningGateError("requirement consent is not current and approved")
            current_evidence.append({
                "path": f".factory/planning/{run_id}/requirement-consent.json",
                "sha256": _digest(path.read_bytes()),
            })
        consent_ok, _ = validate_sr_decisions(root, run_id, current)
        if not consent_ok:
            raise PlanningGateError("per-SR human consent is missing or stale")
        consent_dir = safe_resolve(root, run_dir / "consent")
        if consent_dir is None or not consent_dir.is_dir():
            raise PlanningGateError("per-SR human consent evidence is missing")
        expected_names = {f"{requirement_id}.json" for requirement_id in current}
        actual_names = {entry.name for entry in consent_dir.iterdir() if entry.is_file()}
        if actual_names != expected_names:
            raise PlanningGateError("per-SR human consent does not cover the exact requirement set")
        for requirement_id in current:
            decision_path = safe_resolve(
                root, run_dir / "consent" / f"{requirement_id}.json",
            )
            if decision_path is None or not decision_path.is_file():
                raise PlanningGateError("per-SR human consent evidence is missing")
            current_evidence.append({
                "path": f".factory/planning/{run_id}/consent/{requirement_id}.json",
                "sha256": _digest(decision_path.read_bytes()),
            })
        return "pass", _deduplicated_evidence(current_evidence)
    except PlanningGateError:
        return "fail", []


def _cross_artifact_record(
    root: Path, run_id: str, raw_tasks: object, selected_workflow: object,
) -> dict[str, object]:
    """Recompute explicit producer inputs against current canonical files."""
    if selected_workflow not in _WORKFLOWS:
        raise PlanningGateError("cross-artifact selected workflow is invalid")
    pack = compile_planning_gate_pack(_PLANNING_GATE_FEATURE, _PLANNING_GATE_VERSION)
    report, report_evidence = _planning_report(root, run_id)
    if not isinstance(raw_tasks, dict):
        raise PlanningGateError("cross-artifact task inputs are invalid")
    task_dir = safe_resolve(root, root / "tasks")
    if task_dir is None:
        raise PlanningGateError("cross-artifact task directory is unsafe")
    task_paths = sorted(path.relative_to(root).as_posix() for path in task_dir.glob("T-*.md"))
    report_paths = {entry["path"] for entry in report_evidence[1:]}
    if set(raw_tasks) != set(task_paths) or not set(task_paths) <= report_paths:
        raise PlanningGateError("cross-artifact review must cover every canonical generated task")
    for path in task_paths:
        if safe_resolve(root, root / path) is None:
            raise PlanningGateError("cross-artifact task path is unsafe")
        if _read_metadata(root / path) is None:
            raise PlanningGateError("cross-artifact task metadata is malformed")
    parsed_tasks = {task.path.relative_to(root).as_posix(): task for task in load_tasks(task_dir)}
    tasks: list[GeneratedTaskReviewInput] = []
    required_ids: set[str] = set()
    inputs: dict[str, str] = {entry["path"]: entry["sha256"] for entry in report_evidence}
    fields = {"id", "artifact_paths", "changes_production", "changes_validation", "affected_srs", "satisfies"}
    for path in task_paths:
        raw = raw_tasks[path]
        if not isinstance(raw, dict) or set(raw) != fields:
            raise PlanningGateError("cross-artifact task input schema is invalid")
        if (
            raw["id"] != parsed_tasks[path].id
            or type(raw["changes_production"]) is not bool
            or type(raw["changes_validation"]) is not bool
            or not isinstance(raw["artifact_paths"], list) or not raw["artifact_paths"]
            or not all(_safe_relative(item) for item in raw["artifact_paths"])
        ):
            raise PlanningGateError("cross-artifact task classification is invalid")
        for field in ("affected_srs", "satisfies"):
            value = raw[field]
            if value is not None and (
                not isinstance(value, list)
                or not all(isinstance(item, str) and _SR_ID.fullmatch(item) for item in value)
            ):
                raise PlanningGateError("cross-artifact SR declaration schema is invalid")
        metadata = _read_metadata(root / path)
        assert metadata is not None
        mirror = parsed_tasks[path].satisfies if {"satisfies", "justification"} & set(metadata) else None
        if raw["satisfies"] != mirror:
            raise PlanningGateError("cross-artifact satisfies input does not match the canonical task parser")
        task = GeneratedTaskReviewInput(
            raw["id"], tuple(raw["artifact_paths"]), raw["changes_production"],
            raw["changes_validation"],
            tuple(raw["affected_srs"]) if raw["affected_srs"] is not None else None,
            tuple(mirror) if mirror is not None else None,
        )
        tasks.append(task)
        for relative in task.artifact_paths:
            source = safe_resolve(root, root / relative)
            if source is None:
                raise PlanningGateError("cross-artifact task artifact path is unsafe")
            if source.is_file():
                inputs[relative] = _digest(source.read_bytes())
        if task.needs_sr_declaration:
            required_ids.update(task.affected_srs or ())
    requirements = []
    for sr_id in sorted(required_ids):
        relative = f"requirements/{sr_id}.md"
        path = safe_resolve(root, root / relative)
        if path is None:
            raise PlanningGateError("cross-artifact requirement path is unsafe")
        if not path.exists():
            continue  # The pure reviewer reports the dangling SR declaration.
        metadata = _read_metadata(path)
        if metadata is None or metadata.get("id") != sr_id:
            raise PlanningGateError("cross-artifact requirement metadata is invalid")
        try:
            requirements.append(parse_requirement(path))
        except (AttributeError, KeyError) as exc:
            raise PlanningGateError("cross-artifact requirement metadata is malformed") from exc
        inputs[relative] = _digest(path.read_bytes())
        for field in ("implemented_by", "verified_by"):
            entries = metadata.get(field)
            if not isinstance(entries, list):
                continue  # The relation resolver owns malformed relation findings.
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if not isinstance(entry.get("path"), str):
                    raise PlanningGateError("cross-artifact relation path must be a string")
                if "\\" in entry["path"]:
                    raise PlanningGateError("cross-artifact relation path must use forward slashes")
                relative = entry["path"]
                if not _safe_relative(relative):
                    raise PlanningGateError("cross-artifact relation path is unsafe")
                source = safe_resolve(root, root / relative)
                if source is None:
                    raise PlanningGateError("cross-artifact relation path is unsafe")
                if source.is_file():
                    inputs[relative] = _digest(source.read_bytes())
    review = review_cross_artifact_relations(root, requirements, tasks)
    return {
        "schema": 1, "run_id": run_id, "report_sha256": _canonical_digest(report),
        "selected_workflow": selected_workflow, "planning_gate_pack_sha256": pack["sha256"],
        "tasks": raw_tasks, "artifact_hashes": dict(sorted(inputs.items())),
        "review": review.to_dict(),
    }


def write_cross_artifact_review(
    root: Path,
    run_id: str,
    tasks: Mapping[str, GeneratedTaskReviewInput],
    *,
    selected_workflow: str = "standard-development",
) -> dict[str, object]:
    """Record producer-classified tasks, including blocking findings, for planning gates.

    Keys are canonical ``tasks/T-*.md`` paths. Every generated task must be
    represented and already included in report.json. Classifications are
    explicit producer facts; this boundary never infers docs-only exemptions.
    """
    root = safe_root(root) or root
    run_dir = _planning_run_dir(root, run_id)
    path = safe_resolve(root, run_dir / "cross-artifact-review.json")
    if path is None:
        raise PlanningGateError("cross-artifact review path is unsafe")
    try:
        raw_tasks = json.loads(json.dumps({path: asdict(task) for path, task in tasks.items()}))
        record = _cross_artifact_record(root, run_id, raw_tasks, selected_workflow)
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise PlanningGateError("cross-artifact review inputs are invalid") from exc
    _atomic_write(path, _encoded_result(record))
    return record


def _resolve_cross_artifact_review(root: Path, run_id: str) -> tuple[str, list[dict[str, str]]]:
    try:
        path = safe_resolve(root, _planning_run_dir(root, run_id) / "cross-artifact-review.json")
        if path is None or not path.is_file():
            raise PlanningGateError("cross-artifact review evidence is missing")
        record = _read_json(path, "cross-artifact review evidence is unreadable")
        if not isinstance(record, dict) or type(record.get("schema")) is not int:
            raise PlanningGateError("cross-artifact review schema is invalid")
        _, source_evidence = _required_planning_sources(root, run_id)
        current = _cross_artifact_record(
            root, run_id, record.get("tasks"), record.get("selected_workflow"),
        )
        review = current["review"]
        hashes = current["artifact_hashes"]
        assert isinstance(review, dict) and isinstance(hashes, dict)
        if _encoded_result(record) != _encoded_result(current) or review["ok"] is not True:
            raise PlanningGateError("cross-artifact review is stale or contains blocking findings")
        human_status, human_evidence = _resolve_human_review(root, run_id)
        consent_status, consent_evidence = _resolve_requirement_consent(root, run_id)
        if human_status != "pass" or consent_status != "pass":
            raise PlanningGateError("cross-artifact review lacks current approval evidence")
        evidence = [{"path": f".factory/planning/{run_id}/cross-artifact-review.json", "sha256": _digest(path.read_bytes())}]
        evidence.extend({"path": name, "sha256": digest} for name, digest in hashes.items())
        evidence.extend(source_evidence)
        evidence.extend(human_evidence)
        evidence.extend(consent_evidence)
        return "pass", _deduplicated_evidence(evidence)
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
        return "fail", []


def selected_planning_workflow(root: Path, run_id: str, pack: Mapping[str, object]) -> str:
    """Return the explicit, current workflow selection attested by the review."""
    validated_pack = _validated_pack(dict(pack))
    status, _ = _resolve_cross_artifact_review(root, run_id)
    if status != "pass":
        raise PlanningGateError("cross-artifact workflow selection is missing or stale")
    path = safe_resolve(root, _planning_run_dir(root, run_id) / "cross-artifact-review.json")
    if path is None or not path.is_file():
        raise PlanningGateError("cross-artifact workflow review is missing")
    record = _read_json(path, "cross-artifact workflow review is unreadable")
    selected = record.get("selected_workflow") if isinstance(record, dict) else None
    if (
        not isinstance(record, dict)
        or record.get("planning_gate_pack_sha256") != validated_pack["sha256"]
        or not isinstance(selected, str)
        or selected not in _WORKFLOWS
    ):
        raise PlanningGateError("cross-artifact workflow selection is invalid")
    return selected


_RESOLVERS = {
    "planning_report_current": _resolve_planning_report,
    "human_review_current": _resolve_human_review,
    "requirement_consent_current": _resolve_requirement_consent,
    "cross_artifact_review_current": _resolve_cross_artifact_review,
}


def _result_path(root: Path, run_id: str) -> Path:
    project_root = safe_root(root)
    if project_root is None:
        raise PlanningGateError("planning gate project root is unsafe")
    path = safe_resolve(project_root, _planning_run_dir(project_root, run_id) / "planning-gate-result.json")
    if path is None:
        raise PlanningGateError("planning gate result path is unsafe")
    return path


def _atomic_write(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".planning-gate-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _encoded_result(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def evaluate_planning_gate_pack(root: Path, run_id: str, pack: Mapping[str, object]) -> dict[str, object]:
    """Evaluate planning evidence only and atomically publish a current result."""
    try:
        validated_pack = _validated_pack(dict(pack))
    except (TypeError, ValueError) as exc:
        raise PlanningGateError("planning gate pack is invalid") from exc
    run_dir = _planning_run_dir(root, run_id)
    executions: list[dict[str, object]] = []
    gates = validated_pack["gates"]
    assert isinstance(gates, list)  # guaranteed by the compiled pack
    for gate in gates:
        assert isinstance(gate, dict)  # guaranteed by the compiled pack
        resolver = _RESOLVERS[str(gate["resolver"])]
        status, evidence = resolver(safe_root(root) or root, run_id)
        executions.append({
            "gate_id": gate["id"], "status": status, "required": gate["required"], "evidence": evidence,
        })
    payload: dict[str, object] = {
        "schema": 1, "run_id": run_id, "feature_id": validated_pack["feature_id"],
        "version": validated_pack["version"], "planning_gate_pack_sha256": validated_pack["sha256"],
        "executions": executions,
    }
    encoded = _encoded_result(payload)
    digest = _digest(encoded)
    immutable_dir = safe_resolve(safe_root(root) or root, run_dir / "planning-gate-results")
    if immutable_dir is None:
        raise PlanningGateError("planning gate result directory is unsafe")
    immutable_path = safe_resolve(safe_root(root) or root, immutable_dir / f"{digest}.json")
    if immutable_path is None:
        raise PlanningGateError("immutable planning gate result path is unsafe")
    immutable_dir.mkdir(parents=True, exist_ok=True)
    if immutable_path.exists() and immutable_path.read_bytes() != encoded:
        raise PlanningGateError("immutable planning gate result conflicts")
    if not immutable_path.exists():
        _atomic_write(immutable_path, encoded)
    _atomic_write(_result_path(root, run_id), encoded)
    return {**payload, "result_sha256": digest}


def validate_planning_gate_result(root: Path, run_id: str, pack: Mapping[str, object]) -> dict[str, object]:
    """Require a current, complete, evidence-bound execution of every required gate."""
    try:
        validated_pack = _validated_pack(dict(pack))
    except (TypeError, ValueError) as exc:
        raise PlanningGateError("planning gate pack is invalid") from exc
    path = _result_path(root, run_id)
    if not path.is_file():
        raise PlanningGateError("planning gate result is missing")
    payload = _read_json(path, "planning gate result is unreadable")
    if not isinstance(payload, dict) or set(payload) != _RESULT_KEYS:
        raise PlanningGateError("planning gate result schema is invalid")
    if (
        type(payload.get("schema")) is not int or payload.get("schema") != 1
        or payload.get("run_id") != run_id or payload.get("feature_id") != validated_pack["feature_id"]
        or payload.get("version") != validated_pack["version"]
        or payload.get("planning_gate_pack_sha256") != validated_pack["sha256"]
    ):
        raise PlanningGateError("planning gate result is not bound to this gate pack")
    encoded = _encoded_result(payload)
    digest = _digest(encoded)
    immutable = safe_resolve(
        project_root := safe_root(root) or root,
        _planning_run_dir(project_root, run_id) / "planning-gate-results" / f"{digest}.json",
    )
    if immutable is None or not immutable.is_file() or immutable.read_bytes() != encoded:
        raise PlanningGateError("planning gate result is not an immutable current result")
    executions = payload.get("executions")
    expected_gates = validated_pack["gates"]
    if not isinstance(executions, list) or not isinstance(expected_gates, list) or len(executions) != len(expected_gates):
        raise PlanningGateError("planning gate executions are incomplete")
    project_root = safe_root(root)
    if project_root is None:
        raise PlanningGateError("planning gate project root is unsafe")
    for gate, execution in zip(expected_gates, executions, strict=True):
        if not isinstance(gate, dict) or not isinstance(execution, dict) or set(execution) != _EXECUTION_KEYS:
            raise PlanningGateError("planning gate execution schema is invalid")
        if execution.get("gate_id") != gate["id"] or execution.get("required") is not gate["required"]:
            raise PlanningGateError("planning gate execution is silently downgraded or reordered")
        if execution.get("status") not in {"pass", "fail"} or not isinstance(execution.get("evidence"), list):
            raise PlanningGateError("planning gate execution status or evidence is invalid")
        resolver = _RESOLVERS.get(str(gate["resolver"]))
        if resolver is None:
            raise PlanningGateError("planning gate resolver is unknown")
        status, evidence = resolver(project_root, run_id)
        if execution["status"] != status or execution["evidence"] != evidence:
            raise PlanningGateError("planning gate execution is stale or unevidenced")
        if gate["required"] is True and (status != "pass" or not evidence):
            raise PlanningGateError("required planning gate did not pass with evidence")
    return {**payload, "result_sha256": digest}
def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip() or "\\" in value:
        return False
    if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        return False
    return not any(part in {"", ".", ".."} for part in value.split("/"))


def _inside(root: Path, path: Path) -> bool:
    return safe_resolve(root, path) is not None


def _read_metadata(path: Path) -> dict[str, Any] | None:
    try:
        post = strict_frontmatter_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
        return None
    return dict(post.metadata)


def _source_matches(root: Path, source: object, spec_path: Path) -> bool:
    if not isinstance(source, str) or "#" not in source:
        return False
    source_path, anchor = source.split("#", 1)
    if not _safe_relative(source_path) or not anchor.strip():
        return False
    try:
        safe_source = safe_resolve(root, root / source_path)
        safe_spec = safe_resolve(root, spec_path)
        if safe_source is None or safe_spec is None or safe_source != safe_spec:
            return False
        spec_body = strict_frontmatter_loads(spec_path.read_text(encoding="utf-8")).content
        return authority_anchor_matches(spec_body, anchor)
    except (OSError, RuntimeError, ValueError, yaml.YAMLError):
        return False


def _validate_feat17_bundle_members(
    members: object, requirement_ids: list[str]
) -> tuple[bool, str]:
    """Validate feature ownership while allowing its dossier projections."""
    if not isinstance(members, list) or any(not isinstance(item, str) for item in members):
        return False, "FEAT-017 bundle has invalid members"
    if len(members) != len(set(members)):
        return False, "FEAT-017 bundle has duplicate members"

    required = {"feat:FEAT-017", *(f"sr:{req_id}" for req_id in requirement_ids)}
    member_set = set(members)
    sr_ids = sorted(
        member.removeprefix("sr:") for member in members if member.startswith("sr:")
    )
    missing_ids = sorted(required - member_set)
    if missing_ids:
        return False, (
            "FEAT-017 bundle is missing required member(s): "
            f"{', '.join(missing_ids)}"
        )
    owned_ids = set(requirement_ids)
    unexpected_ids = sorted(set(sr_ids) - owned_ids)
    if unexpected_ids:
        return False, (
            "FEAT-017 bundle contains non-owned requirement(s): "
            f"{', '.join(unexpected_ids)}"
        )
    feature_members = sorted(member for member in members if member.startswith("feat:"))
    if feature_members != ["feat:FEAT-017"]:
        return False, "FEAT-017 bundle contains an invalid feature membership"
    return True, "FEAT-017 bundle ownership is current"


def validate_requirement_consent(
    root: Path,
    run_id: str,
    spec_path: Path,
) -> tuple[bool, str]:
    """Validate FEAT-017 registration and explicit external SR consent.

    This is read-only. The planning workflow never creates or modifies the
    dossier, bundle, requirements, or consent decision.
    """
    project_root = safe_root(root)
    if project_root is None:
        return False, "project root contains a symlink or reparse point"
    feature_path = project_root / "docs" / "features" / f"{_REQUIRED_FEATURE_ID}.md"
    bundle_path = project_root / "bundles" / f"{_REQUIRED_FEATURE_ID}.json"
    requirements_dir = project_root / "requirements"
    safe_feature_path = safe_resolve(project_root, feature_path)
    safe_bundle_path = safe_resolve(project_root, bundle_path)
    if safe_feature_path is None or not safe_feature_path.is_file():
        return False, "FEAT-017 feature dossier is missing"
    if safe_bundle_path is None or not safe_bundle_path.is_file():
        return False, "FEAT-017 bundle is missing"
    metadata = _read_metadata(safe_feature_path)
    if metadata is None or metadata.get("id") != _REQUIRED_FEATURE_ID:
        return False, "FEAT-017 feature dossier is malformed"
    raw_ids = metadata.get("requirements")
    if not isinstance(raw_ids, list) or not raw_ids or not all(isinstance(item, str) for item in raw_ids):
        return False, "FEAT-017 feature dossier has no valid requirement list"
    requirement_ids = sorted(raw_ids)
    if len(requirement_ids) != len(set(requirement_ids)) or not all(
        item.startswith("SR-") and _safe_relative(item) for item in requirement_ids
    ):
        return False, "FEAT-017 feature dossier has invalid requirement identifiers"

    try:
        bundle = strict_json_loads(safe_bundle_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return False, "FEAT-017 bundle is invalid JSON"
    if not isinstance(bundle, dict) or bundle.get("id") != _REQUIRED_FEATURE_ID:
        return False, "FEAT-017 bundle has an invalid id"
    members = bundle.get("members")
    bundle_valid, bundle_detail = _validate_feat17_bundle_members(members, requirement_ids)
    if not bundle_valid:
        return False, bundle_detail

    for req_id in requirement_ids:
        req_path = requirements_dir / f"{req_id}.md"
        safe_req_path = safe_resolve(project_root, req_path)
        if safe_req_path is None or not safe_req_path.is_file():
            return False, f"{req_id} requirement escapes the project root"
        req_metadata = _read_metadata(safe_req_path)
        if req_metadata is None:
            return False, f"{req_id} requirement is missing or malformed"
        if any(
            not isinstance(req_metadata.get(field), str) or not str(req_metadata[field]).strip()
            for field in ("id", "title", "statement", "domain")
        ):
            return False, f"{req_id} requirement has incomplete canonical fields"
        upstream = req_metadata.get("upstream")
        if not isinstance(upstream, list) or any(not isinstance(item, str) for item in upstream):
            return False, f"{req_id} requirement has invalid upstream metadata"
        if req_metadata.get("id") != req_id or not _source_matches(project_root, req_metadata.get("source"), spec_path):
            return False, f"{req_id} requirement is not sourced from the authority spec"

    consent_path = project_root / ".factory" / "planning" / run_id / "requirement-consent.json"
    if not _inside(project_root, consent_path):
        return False, "requirement consent path escapes the project root"
    try:
        consent = strict_json_loads(consent_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return False, "explicit human requirement consent is missing or invalid"
    if not isinstance(consent, dict) or set(consent) != _CONSENT_KEYS:
        return False, "explicit human requirement consent has an invalid schema"
    if type(consent.get("schema")) is not int or consent.get("schema") != 1:
        return False, "explicit human requirement consent schema must equal 1"
    if consent.get("run_id") != run_id or consent.get("decision") != "approve" or consent.get("reviewer") != "human":
        return False, "explicit human requirement consent is not approved by a human"
    reason = consent.get("reason")
    consent_ids = consent.get("requirements")
    if not isinstance(reason, str) or not reason.strip() or consent_ids != requirement_ids:
        return False, "explicit human requirement consent does not cover the exact requirement set"
    return True, "requirement consent and FEAT-017 registration are current"


def validate_sr_consent(
    root: Path,
    run_id: str,
    candidate_srs: list[str] | tuple[str, ...],
    derivation_report_sha256: str,
    artifact_hashes: dict[str, str],
) -> tuple[bool, str]:
    """Validate legacy aggregate SR consent for compatibility callers only.

    New guided lifecycle code must use
    :func:`coherence.planning.consent.validate_sr_decisions`; this aggregate
    record neither calls nor satisfies that per-SR human-consent contract.
    """
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None or not isinstance(candidate_srs, (list, tuple)):
        return False, "SR consent identity is invalid"
    expected_srs = list(candidate_srs)
    if expected_srs != sorted(expected_srs) or len(expected_srs) != len(set(expected_srs)) or not all(
        isinstance(item, str) and item.startswith("SR-") for item in expected_srs
    ):
        return False, "candidate SR set is invalid"
    if not isinstance(derivation_report_sha256, str) or _SHA256.fullmatch(derivation_report_sha256) is None:
        return False, "derivation report hash is invalid"
    if not isinstance(artifact_hashes, dict) or list(artifact_hashes) != sorted(artifact_hashes) or any(
        not isinstance(key, str) or not _safe_relative(key) or not isinstance(value, str)
        or _SHA256.fullmatch(value) is None
        for key, value in artifact_hashes.items()
    ):
        return False, "artifact hashes are invalid"
    path = root / ".factory" / "planning" / run_id / "sr-consent.json"
    try:
        payload = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return False, "explicit SR consent is missing or invalid"
    if not isinstance(payload, dict) or set(payload) != _SR_CONSENT_KEYS:
        return False, "explicit SR consent has an invalid schema"
    if (
        payload.get("schema") != 2 or payload.get("run_id") != run_id
        or payload.get("decision") != "approve" or payload.get("reviewer") != "human"
        or payload.get("phrase") != _CONSENT_PHRASE
        or payload.get("candidate_srs") != expected_srs
        or payload.get("derivation_report_sha256") != derivation_report_sha256
        or payload.get("artifact_hashes") != artifact_hashes
    ):
        return False, "explicit SR consent is not bound to the exact derivation"
    return True, "explicit SR consent is current and exact"


__all__ = [
    "PlanningGateError",
    "compile_planning_gate_pack",
    "evaluate_planning_gate_pack",
    "selected_planning_workflow",
    "validate_planning_gate_result",
    "validate_requirement_consent",
    "validate_sr_consent",
    "write_cross_artifact_review",
]
