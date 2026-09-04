"""Append-only, fail-closed resolution evidence for planning reviews."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coherence.planning.paths import safe_root
from coherence.planning.serialization import strict_json_loads

_DISPOSITIONS = {"resolve_in_loop", "escalate_to_human", "informational"}
_STAGES = {"spec_alignment", "plan_task_alignment", "derivation_alignment"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SECRET = re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|bearer|credential)")
_MAX_HASH_ENTRIES = 4096
_MAX_HASH_BYTES = 262144


class ResolutionError(ValueError):
    """Raised when a resolution event cannot be safely persisted."""


def _safe_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value) or len(value) > 128:
        raise ResolutionError(f"invalid {field}")
    return value


def _safe_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 65536 or _SECRET.search(value):
        raise ResolutionError(f"invalid or secret-shaped {field}")
    return value


def _hashes(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise ResolutionError(f"invalid {field}")
    if len(value) > _MAX_HASH_ENTRIES:
        raise ResolutionError(f"oversized {field}")
    encoded_size = sum(len(key.encode("utf-8")) + len(item.encode("utf-8")) for key, item in value.items())
    if encoded_size > _MAX_HASH_BYTES:
        raise ResolutionError(f"oversized {field}")
    result = {key: value[key] for key in sorted(value)}
    if any(_SECRET.search(key) for key in result):
        raise ResolutionError(f"secret-shaped {field} rejected")
    if any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in result.values()):
        raise ResolutionError(f"invalid {field}")
    return result


def _validate_timestamp(value: object) -> str:
    stamp = _safe_text(value, "timestamp")
    try:
        parsed = datetime.fromisoformat(stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp)
    except ValueError as exc:
        raise ResolutionError("invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResolutionError("timestamp must include timezone")
    return stamp


def _validate_event(event: object, run_id: str, sequence: int) -> dict[str, Any]:
    required = {"schema", "run_id", "sequence", "stage", "iteration", "finding_id", "disposition", "prompt", "answer_or_fix", "pre_artifact_hashes", "post_artifact_hashes", "actor_kind", "timestamp"}
    if not isinstance(event, dict) or set(event) != required or event.get("schema") != 1:
        raise ResolutionError("resolution journal event fields are invalid")
    if _safe_id(event["run_id"], "run_id") != run_id or event["sequence"] != sequence:
        raise ResolutionError("resolution journal sequence is invalid")
    if event["stage"] not in _STAGES or type(event["iteration"]) is not int or event["iteration"] < 1:
        raise ResolutionError("resolution journal event identity is invalid")
    _safe_id(event["finding_id"], "finding_id")
    if event["disposition"] not in _DISPOSITIONS:
        raise ResolutionError("resolution journal disposition is invalid")
    _safe_text(event["prompt"], "prompt")
    _safe_text(event["answer_or_fix"], "answer_or_fix")
    _hashes(event["pre_artifact_hashes"], "pre_artifact_hashes")
    _hashes(event["post_artifact_hashes"], "post_artifact_hashes")
    _safe_id(event["actor_kind"], "actor_kind")
    _validate_timestamp(event["timestamp"])
    return event


def _path(root: Path, run_id: str) -> Path:
    safe = safe_root(root)
    if safe is None:
        raise ResolutionError("unsafe project root")
    return safe / ".factory" / "planning" / run_id / "resolution-events.jsonl"


def read_resolution_events(root: Path, run_id: str) -> list[dict[str, Any]]:
    path = _path(root, _safe_id(run_id, "run_id"))
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ResolutionError("resolution journal is unreadable") from exc
    events: list[dict[str, Any]] = []
    for expected, line in enumerate(lines, 1):
        try:
            event = strict_json_loads(line)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResolutionError("resolution journal contains malformed JSON") from exc
        events.append(_validate_event(event, run_id, expected))
    return events


def append_resolution_event(root: Path, *, run_id: str, stage: str, iteration: int, finding_id: str,
                            disposition: str, actor_kind: str, prompt: str, answer_or_fix: str,
                            pre_artifact_hashes: dict[str, str], post_artifact_hashes: dict[str, str],
                            timestamp: str | None = None) -> Path:
    run = _safe_id(run_id, "run_id")
    if stage not in _STAGES or type(iteration) is not int or iteration < 1:
        raise ResolutionError("invalid stage or iteration")
    finding = _safe_id(finding_id, "finding_id")
    if disposition not in _DISPOSITIONS:
        raise ResolutionError("invalid disposition")
    actor = _safe_id(actor_kind, "actor_kind")
    prompt_value = _safe_text(prompt, "prompt")
    fix_value = _safe_text(answer_or_fix, "answer_or_fix")
    pre = _hashes(pre_artifact_hashes, "pre_artifact_hashes")
    post = _hashes(post_artifact_hashes, "post_artifact_hashes")
    stamp = timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    stamp = _validate_timestamp(stamp)
    path = _path(root, run)
    existing = read_resolution_events(root, run)
    event: dict[str, Any] = {"schema": 1, "run_id": run, "sequence": len(existing) + 1,
        "stage": stage, "iteration": iteration, "finding_id": finding, "disposition": disposition,
        "prompt": prompt_value, "answer_or_fix": fix_value, "pre_artifact_hashes": pre,
        "post_artifact_hashes": post, "actor_kind": actor, "timestamp": stamp}
    _validate_event(event, run, event["sequence"])
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_APPEND ensures this function cannot replace an earlier iteration.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise ResolutionError("resolution event could not be appended") from exc
    return path


__all__ = ["ResolutionError", "append_resolution_event", "read_resolution_events"]
