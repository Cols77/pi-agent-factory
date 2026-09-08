"""Per-SR, hash-bound human consent records for guided planning."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

from coherence.planning.paths import safe_resolve, safe_root
from coherence.planning.serialization import strict_json_dumps, strict_json_loads

CONSENT_PHRASE = "I independently approve this SR for adoption."

_DECISION_KEYS = frozenset(
    {
        "schema",
        "run_id",
        "sr_id",
        "requirement_sha256",
        "decision",
        "reviewer",
        "phrase",
        "reason",
    }
)
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SR_ID = re.compile(r"^SR-[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _valid_run_id(value: object) -> bool:
    return isinstance(value, str) and _RUN_ID.fullmatch(value) is not None


def _valid_sr_id(value: object) -> bool:
    return isinstance(value, str) and _SR_ID.fullmatch(value) is not None


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _decision_path(root: Path, run_id: str, sr_id: str) -> Path | None:
    return safe_resolve(
        root,
        root / ".factory" / "planning" / run_id / "consent" / f"{sr_id}.json",
    )


def _validate_write_inputs(
    run_id: object,
    sr_id: object,
    requirement_sha256: object,
    decision: object,
    reviewer: object,
    phrase: object,
    reason: object,
) -> None:
    if not _valid_run_id(run_id):
        raise ValueError("invalid planning run id")
    if not _valid_sr_id(sr_id):
        raise ValueError("invalid SR identifier")
    if not _valid_digest(requirement_sha256):
        raise ValueError("invalid requirement SHA-256")
    if decision != "approve" or reviewer != "human" or phrase != CONSENT_PHRASE:
        raise ValueError("invalid human consent decision")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("human consent reason is required")


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".consent-", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(strict_json_dumps(payload) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_sr_decision(
    root: Path,
    run_id: str,
    sr_id: str,
    requirement_sha256: str,
    decision: str,
    reviewer: str,
    phrase: str,
    reason: str,
) -> Path:
    """Atomically record exactly one independently reviewed SR decision."""
    _validate_write_inputs(
        run_id, sr_id, requirement_sha256, decision, reviewer, phrase, reason
    )
    project_root = safe_root(root)
    if project_root is None:
        raise ValueError("project root contains a symlink or reparse point")
    path = _decision_path(project_root, run_id, sr_id)
    if path is None:
        raise ValueError("planning consent path is unsafe")
    payload: dict[str, object] = {
        "schema": 1,
        "run_id": run_id,
        "sr_id": sr_id,
        "requirement_sha256": requirement_sha256,
        "decision": decision,
        "reviewer": reviewer,
        "phrase": phrase,
        "reason": reason,
    }
    _atomic_write(path, payload)
    return path


def _valid_record(
    payload: object,
    run_id: str,
    sr_id: str,
    requirement_sha256: str,
) -> tuple[bool, bool]:
    """Return ``(valid, stale)`` for one exact, independently reviewed record."""
    if not isinstance(payload, dict) or set(payload) != _DECISION_KEYS:
        return False, False
    if (
        type(payload.get("schema")) is not int
        or payload.get("schema") != 1
        or payload.get("run_id") != run_id
        or payload.get("sr_id") != sr_id
        or payload.get("decision") != "approve"
        or payload.get("reviewer") != "human"
        or payload.get("phrase") != CONSENT_PHRASE
    ):
        return False, False
    reason = payload.get("reason")
    stored_digest = payload.get("requirement_sha256")
    if not isinstance(reason, str) or not reason.strip() or not _valid_digest(stored_digest):
        return False, False
    return stored_digest == requirement_sha256, stored_digest != requirement_sha256


def validate_sr_decisions(
    root: Path,
    run_id: str,
    current: Mapping[str, str],
) -> tuple[bool, str]:
    """Read-only validation of a separate, hash-bound human decision per SR."""
    if not _valid_run_id(run_id) or not isinstance(current, Mapping):
        return False, "candidate SR set is invalid"
    candidates = list(current.items())
    if any(
        not _valid_sr_id(sr_id) or not _valid_digest(digest)
        for sr_id, digest in candidates
    ):
        return False, "candidate SR set is invalid"
    candidates.sort()
    project_root = safe_root(root)
    if project_root is None:
        return False, "project root contains a symlink or reparse point"

    for sr_id, digest in candidates:
        path = _decision_path(project_root, run_id, sr_id)
        if path is None:
            return False, f"invalid human consent: {sr_id}"
        if not path.exists():
            return False, f"missing human consent: {sr_id}"
        if not path.is_file():
            return False, f"invalid human consent: {sr_id}"
        try:
            payload = strict_json_loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
            return False, f"invalid human consent: {sr_id}"
        valid, stale = _valid_record(payload, run_id, sr_id, digest)
        if stale:
            return False, f"stale human consent: {sr_id}"
        if not valid:
            return False, f"invalid human consent: {sr_id}"
    return True, "human consent is current for all candidate SRs"


__all__ = ["CONSENT_PHRASE", "validate_sr_decisions", "write_sr_decision"]
