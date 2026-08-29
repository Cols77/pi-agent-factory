"""Strict, hash-bound contracts for semantic planning reviews."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_json_loads

REVIEW_STAGES = ("spec_alignment", "plan_task_alignment", "derivation_alignment")
_DISPOSITIONS = ("resolve_in_loop", "escalate_to_human", "informational")
_VERDICTS = ("clean", "findings", "escalate")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_MAX = 64 * 1024
_SECRET = re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|bearer|credential)")


class SemanticReviewError(ValueError):
    """Raised when untrusted semantic-review data fails closed."""


def _run_id(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value) or len(value) > 128:
        raise SemanticReviewError("invalid run_id")
    return value


def _text(value: object, field: str, *, max_len: int = _MAX) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise SemanticReviewError(f"invalid or oversized {field}")
    if _SECRET.search(value):
        raise SemanticReviewError(f"secret-shaped {field} rejected")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise SemanticReviewError(f"invalid {field}")
    return value


def _safe_rel(path: Path, root: Path) -> str:
    resolved = safe_resolve(root, path)
    root_resolved = safe_root(root)
    if resolved is None or root_resolved is None:
        raise SemanticReviewError("artifact path is outside a safe project root")
    try:
        relative = resolved.relative_to(root_resolved).as_posix()
    except ValueError as exc:
        raise SemanticReviewError("artifact path is outside project root") from exc
    if not relative or ".." in relative.split("/"):
        raise SemanticReviewError("path traversal rejected")
    return relative


def _artifact(path: Path, root: Path) -> dict[str, str]:
    relative = _safe_rel(path, root)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SemanticReviewError(f"artifact is unreadable: {relative}") from exc
    return {"path": relative, "sha256": hashlib.sha256(data).hexdigest()}


def _clean_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SemanticReviewError(f"{field} must be an object")
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > _MAX:
        raise SemanticReviewError(f"oversized {field}")
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, (str, int, bool, type(None), list, dict)):
            raise SemanticReviewError(f"invalid {field}")
        if _SECRET.search(key) or _SECRET.search(str(item)):
            raise SemanticReviewError(f"secret-shaped {field} rejected")
    return value


@dataclass(frozen=True)
class SemanticReviewPacket:
    schema: int
    run_id: str
    stage: str
    iteration: int
    artifacts: tuple[dict[str, str], ...]
    context: dict[str, Any]
    sr_context_digest: str
    model: dict[str, Any]
    reviewer_role: str
    reviewer_session_id: str | None

    def to_dict(self) -> dict[str, object]:
        return {"schema": self.schema, "run_id": self.run_id, "stage": self.stage,
                "iteration": self.iteration, "artifacts": list(self.artifacts),
                "context": self.context, "sr_context_digest": self.sr_context_digest,
                "model": self.model, "reviewer_role": self.reviewer_role,
                "reviewer_session_id": self.reviewer_session_id}

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict()).encode()).hexdigest()


@dataclass(frozen=True)
class SemanticReviewReport:
    schema: int
    run_id: str
    stage: str
    iteration: int
    packet_sha256: str
    artifacts: tuple[dict[str, str], ...]
    context: dict[str, Any]
    sr_context_digest: str
    model: dict[str, Any]
    reviewer_role: str
    reviewer_session_id: str | None
    findings: tuple[dict[str, Any], ...]
    human_prompts: tuple[str, ...]
    notes: tuple[str, ...]
    verdict: str

    def to_dict(self) -> dict[str, object]:
        return {"schema": self.schema, "run_id": self.run_id, "stage": self.stage,
                "iteration": self.iteration, "packet_sha256": self.packet_sha256,
                "artifacts": list(self.artifacts), "context": self.context,
                "sr_context_digest": self.sr_context_digest, "model": self.model,
                "reviewer_role": self.reviewer_role,
                "reviewer_session_id": self.reviewer_session_id,
                "findings": list(self.findings), "human_prompts": list(self.human_prompts),
                "notes": list(self.notes), "verdict": self.verdict}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _validate_packet(root: Path, packet: SemanticReviewPacket) -> None:
    if packet.schema != 1 or _run_id(packet.run_id) != packet.run_id:
        raise SemanticReviewError("packet identity is invalid")
    if packet.stage not in REVIEW_STAGES or type(packet.iteration) is not int or packet.iteration < 1:
        raise SemanticReviewError("packet identity is invalid")
    if not isinstance(packet.artifacts, tuple):
        raise SemanticReviewError("packet artifacts are invalid")
    paths: set[str] = set()
    for artifact in packet.artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise SemanticReviewError("packet artifacts are invalid")
        relative = _safe_rel(root / artifact["path"], root)
        if relative != artifact["path"] or relative in paths:
            raise SemanticReviewError("packet artifact path is invalid")
        _digest(artifact["sha256"], "artifact hash")
        paths.add(relative)
    if tuple(sorted(paths)) != tuple(paths):
        raise SemanticReviewError("packet artifacts are not sorted")
    _clean_mapping(packet.context, "context")
    if set(packet.model) - {"provider", "model", "revision", "temperature", "config_digest"}:
        raise SemanticReviewError("model metadata contains unsupported fields")
    model = _clean_mapping(packet.model, "model metadata")
    if "provider" not in model or "model" not in model:
        raise SemanticReviewError("model provider and model are required")
    if not isinstance(packet.reviewer_role, str) or not _ID.fullmatch(packet.reviewer_role):
        raise SemanticReviewError("invalid reviewer role")
    if packet.reviewer_session_id is not None:
        _text(packet.reviewer_session_id, "reviewer session")
    _digest(packet.sr_context_digest, "SR context digest")


def _validate_packet_fields(
    artifacts: tuple[dict[str, str], ...], model: dict[str, Any],
    reviewer_role: str, reviewer_session_id: str | None,
) -> None:
    if not isinstance(artifacts, tuple):
        raise SemanticReviewError("report artifacts are invalid")
    paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise SemanticReviewError("report artifacts are invalid")
        path = artifact["path"]
        if not isinstance(path, str) or not path or path.startswith(("/", "\\")) or ".." in Path(path).parts:
            raise SemanticReviewError("report artifact path is invalid")
        if path in paths:
            raise SemanticReviewError("report artifact path is duplicated")
        _digest(artifact["sha256"], "artifact hash")
        paths.add(path)
    if tuple(sorted(paths)) != tuple(paths):
        raise SemanticReviewError("report artifacts are not sorted")
    if set(model) - {"provider", "model", "revision", "temperature", "config_digest"}:
        raise SemanticReviewError("model metadata contains unsupported fields")
    cleaned = _clean_mapping(model, "model metadata")
    if "provider" not in cleaned or "model" not in cleaned:
        raise SemanticReviewError("model provider and model are required")
    if not isinstance(reviewer_role, str) or not _ID.fullmatch(reviewer_role):
        raise SemanticReviewError("invalid reviewer role")
    if reviewer_session_id is not None:
        _text(reviewer_session_id, "reviewer session")


def _validate_report(report: SemanticReviewReport) -> None:
    if report.schema != 1 or _run_id(report.run_id) != report.run_id or report.stage not in REVIEW_STAGES:
        raise SemanticReviewError("report identity is invalid")
    if type(report.iteration) is not int or report.iteration < 1:
        raise SemanticReviewError("report identity is invalid")
    _digest(report.packet_sha256, "packet_sha256")
    if not isinstance(report.artifacts, tuple) or not isinstance(report.context, dict):
        raise SemanticReviewError("report binding fields are invalid")
    _clean_mapping(report.context, "context")
    _digest(report.sr_context_digest, "SR context digest")
    if not isinstance(report.model, dict):
        raise SemanticReviewError("report model metadata is invalid")
    _validate_packet_fields(report.artifacts, report.model, report.reviewer_role, report.reviewer_session_id)
    payload = report.to_dict()
    if parse_review_report(_canonical(payload)).to_dict() != payload:
        raise SemanticReviewError("report fields are invalid")


def build_review_packet(*, run_id: str, stage: str, iteration: int, artifact_paths: list[Path] | tuple[Path, ...],
                        project_root: Path, context: dict[str, Any], sr_context_digest: str,
                        model: dict[str, Any], reviewer_role: str, reviewer_session_id: str | None) -> SemanticReviewPacket:
    _run_id(run_id)
    if stage not in REVIEW_STAGES or type(iteration) is not int or iteration < 1:
        raise SemanticReviewError("invalid review stage or iteration")
    artifacts = tuple(sorted((_artifact(path, project_root) for path in artifact_paths), key=lambda x: x["path"]))
    if len({item["path"] for item in artifacts}) != len(artifacts):
        raise SemanticReviewError("duplicate artifact path")
    if not isinstance(reviewer_role, str) or not _ID.fullmatch(reviewer_role):
        raise SemanticReviewError("invalid reviewer role")
    if reviewer_session_id is not None:
        _text(reviewer_session_id, "reviewer session")
    if not isinstance(model, dict) or set(model) - {"provider", "model", "revision", "temperature", "config_digest"}:
        raise SemanticReviewError("model metadata contains unsupported fields")
    model_clean = _clean_mapping(model, "model metadata")
    if "provider" not in model_clean or "model" not in model_clean:
        raise SemanticReviewError("model provider and model are required")
    return SemanticReviewPacket(1, run_id, stage, iteration, artifacts, _clean_mapping(context, "context"),
                                _digest(sr_context_digest, "SR context digest"), model_clean,
                                reviewer_role, reviewer_session_id)


def parse_review_report(text: str, *, packet: SemanticReviewPacket | None = None) -> SemanticReviewReport:
    if not isinstance(text, str) or len(text.encode("utf-8")) > _MAX:
        raise SemanticReviewError("report is oversized")
    try:
        payload = strict_json_loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SemanticReviewError("report must be strict JSON") from exc
    required_fields = {"schema", "run_id", "stage", "iteration", "packet_sha256", "artifacts", "context", "sr_context_digest", "model", "reviewer_role", "reviewer_session_id", "findings", "human_prompts", "notes", "verdict"}
    if not isinstance(payload, dict) or set(payload) != required_fields:
        raise SemanticReviewError("report fields are invalid")
    if payload["schema"] != 1 or payload["stage"] not in REVIEW_STAGES or type(payload["iteration"]) is not int or payload["iteration"] < 1:
        raise SemanticReviewError("report identity is invalid")
    run_id = _run_id(payload["run_id"])
    packet_digest = _digest(payload["packet_sha256"], "packet_sha256")
    if packet is not None and (packet.run_id != run_id or packet.stage != payload["stage"] or packet.iteration != payload["iteration"] or packet.sha256 != packet_digest):
        raise SemanticReviewError("report is not bound to packet")
    raw_artifacts = payload["artifacts"]
    if not isinstance(raw_artifacts, list):
        raise SemanticReviewError("report artifacts must be a list")
    artifacts = tuple(dict(item) for item in raw_artifacts if isinstance(item, dict))
    if len(artifacts) != len(raw_artifacts):
        raise SemanticReviewError("report artifacts are invalid")
    context = _clean_mapping(payload["context"], "context")
    sr_digest = _digest(payload["sr_context_digest"], "SR context digest")
    model = payload["model"]
    if not isinstance(model, dict):
        raise SemanticReviewError("report model metadata is invalid")
    _validate_packet_fields(artifacts, model, payload["reviewer_role"], payload["reviewer_session_id"])
    if packet is not None and (artifacts != packet.artifacts or context != packet.context or sr_digest != packet.sr_context_digest or model != packet.model or payload["reviewer_role"] != packet.reviewer_role or payload["reviewer_session_id"] != packet.reviewer_session_id):
        raise SemanticReviewError("report binding fields do not match packet")
    raw_findings = payload["findings"]
    if not isinstance(raw_findings, list):
        raise SemanticReviewError("findings must be a list")
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in raw_findings:
        if not isinstance(finding, dict) or set(finding) != {"id", "evidence", "confidence", "disposition"}:
            raise SemanticReviewError("finding fields are invalid")
        identifier = _text(finding["id"], "finding id", max_len=128)
        if identifier in seen or not _ID.fullmatch(identifier):
            raise SemanticReviewError("finding IDs must be unique and stable")
        seen.add(identifier)
        evidence = _text(finding["evidence"], "finding evidence")
        confidence = finding["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise SemanticReviewError("finding confidence must be between zero and one")
        disposition = finding["disposition"]
        if disposition not in _DISPOSITIONS:
            raise SemanticReviewError("invalid finding disposition")
        findings.append({"id": identifier, "evidence": evidence, "confidence": confidence, "disposition": disposition})
    def texts(field: str) -> tuple[str, ...]:
        values = payload[field]
        if not isinstance(values, list):
            raise SemanticReviewError(f"{field} must be a list")
        return tuple(_text(value, field) for value in values)
    verdict = payload["verdict"]
    if verdict not in _VERDICTS or (verdict == "clean" and findings):
        raise SemanticReviewError("verdict does not match findings")
    return SemanticReviewReport(1, run_id, payload["stage"], payload["iteration"], packet_digest,
                                artifacts, context, sr_digest, model, payload["reviewer_role"],
                                payload["reviewer_session_id"], tuple(findings),
                                texts("human_prompts"), texts("notes"), verdict)


def _atomic(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".semantic-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def write_review_packet(root: Path, packet: SemanticReviewPacket) -> Path:
    safe = safe_root(root)
    if safe is None:
        raise SemanticReviewError("unsafe project root")
    _validate_packet(safe, packet)
    filename = "semantic-review-packet.json" if packet.iteration == 1 else f"semantic-review-packet-{packet.iteration}.json"
    path = safe / ".factory" / "planning" / packet.run_id / filename
    if path.exists():
        raise SemanticReviewError("packet already exists; use a new iteration")
    return _atomic(path, json.dumps(packet.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n")

def write_review_report(root: Path, report: SemanticReviewReport) -> Path:
    """Persist one immutable report beside its packet."""
    safe = safe_root(root)
    if safe is None:
        raise SemanticReviewError("unsafe project root")
    _validate_report(report)
    filename = "semantic-review-report.json" if report.iteration == 1 else f"semantic-review-report-{report.iteration}.json"
    path = safe / ".factory" / "planning" / report.run_id / filename
    if path.exists():
        raise SemanticReviewError("report already exists; use a new iteration")
    return _atomic(path, json.dumps(report.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n")

def report_is_fresh(root: Path, packet: SemanticReviewPacket, report: SemanticReviewReport) -> bool:
    """Return true only when the persisted report still binds to this packet."""
    if report.run_id != packet.run_id or report.stage != packet.stage or report.iteration != packet.iteration or report.packet_sha256 != packet.sha256:
        return False
    safe = safe_root(root)
    if safe is None:
        return False
    try:
        for artifact in packet.artifacts:
            path = safe_resolve(safe, safe / artifact["path"])
            if path is None or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                return False
        filename = "semantic-review-report.json" if report.iteration == 1 else f"semantic-review-report-{report.iteration}.json"
        path = safe / ".factory" / "planning" / report.run_id / filename
        return parse_review_report(path.read_text(encoding="utf-8"), packet=packet).to_dict() == report.to_dict()
    except (OSError, UnicodeError, SemanticReviewError):
        return False


__all__ = ["REVIEW_STAGES", "SemanticReviewError", "SemanticReviewPacket", "SemanticReviewReport", "build_review_packet", "parse_review_report", "report_is_fresh", "write_review_packet", "write_review_report"]
