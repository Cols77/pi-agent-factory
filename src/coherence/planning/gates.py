from __future__ import annotations

import json
import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

import yaml

from coherence.planning.anchors import authority_anchor_matches
from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_frontmatter_loads, strict_json_loads

_REQUIRED_FEATURE_ID = "FEAT-017"
_CONSENT_KEYS = frozenset({"schema", "run_id", "decision", "reviewer", "reason", "requirements"})
_SR_CONSENT_KEYS = frozenset({
    "schema", "run_id", "decision", "reviewer", "phrase", "candidate_srs",
    "derivation_report_sha256", "artifact_hashes",
})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_CONSENT_PHRASE = "I explicitly consent to adopt exactly these candidate SRs."

# Planning gates are deliberately a separate, small assurance surface.  They
# attest only the persisted planning records below; they never dispatch the
# factory gate runner or make claims about implementation validation.
_PLANNING_GATE_FEATURE = "FEAT-017"
_PLANNING_GATE_VERSION = "v1"
_PACK_KEYS = frozenset({"schema", "feature_id", "version", "gates", "sha256"})
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
            "expected_evidence": ["requirement-consent.json"],
            "failure_behavior": "block_handoff",
        },
    ]
    return {"schema": 1, "feature_id": feature_id, "version": version, "gates": gates}


def compile_planning_gate_pack(feature_id: str, version: str) -> dict[str, object]:
    """Compile the one supported, deterministic FEAT-017 planning gate pack."""
    if feature_id != _PLANNING_GATE_FEATURE:
        raise PlanningGateError("unknown planning gate feature")
    if version != _PLANNING_GATE_VERSION:
        raise PlanningGateError("unknown planning gate pack version")
    payload = _pack_without_digest(feature_id, version)
    return {**payload, "sha256": _canonical_digest(payload)}


def _validated_pack(pack: object) -> dict[str, object]:
    if not isinstance(pack, dict) or set(pack) != _PACK_KEYS:
        raise PlanningGateError("planning gate pack schema is invalid")
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


def _resolve_human_review(root: Path, run_id: str) -> tuple[str, list[dict[str, str]]]:
    try:
        report, report_evidence = _planning_report(root, run_id)
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
        return "pass", [{"path": ".factory/planning/%s/review-decision.json" % run_id, "sha256": _digest(path.read_bytes())}, report_evidence[0]]
    except PlanningGateError:
        return "fail", []


def _resolve_requirement_consent(root: Path, run_id: str) -> tuple[str, list[dict[str, str]]]:
    try:
        run_dir = _planning_run_dir(root, run_id)
        path = safe_resolve(root, run_dir / "requirement-consent.json")
        if path is None or not path.is_file():
            raise PlanningGateError("requirement consent is missing")
        consent = _read_json(path, "requirement consent is unreadable")
        if not isinstance(consent, dict) or set(consent) != _CONSENT_KEYS:
            raise PlanningGateError("requirement consent schema is invalid")
        requirements = consent.get("requirements")
        if (
            type(consent.get("schema")) is not int or consent.get("schema") != 1
            or consent.get("run_id") != run_id or consent.get("decision") != "approve"
            or consent.get("reviewer") != "human"
            or not isinstance(consent.get("reason"), str) or not str(consent["reason"]).strip()
            or not isinstance(requirements, list) or not all(isinstance(item, str) for item in requirements)
            or requirements != sorted(requirements) or len(requirements) != len(set(requirements))
        ):
            raise PlanningGateError("requirement consent is not current and approved")
        return "pass", [{"path": ".factory/planning/%s/requirement-consent.json" % run_id, "sha256": _digest(path.read_bytes())}]
    except PlanningGateError:
        return "fail", []


_RESOLVERS = {
    "planning_report_current": _resolve_planning_report,
    "human_review_current": _resolve_human_review,
    "requirement_consent_current": _resolve_requirement_consent,
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
    "validate_planning_gate_result",
    "validate_requirement_consent",
    "validate_sr_consent",
]
