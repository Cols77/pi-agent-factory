"""Immutable references for authoritative artifacts and derived snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import re
from typing import Any, Self


__all__ = ["ArtifactRef", "SnapshotInputRef", "ProducerRef", "SnapshotRef"]

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^v?(?P<core>[0-9]+(?:\.[0-9]+)*)(?:[-+][0-9A-Za-z.-]+)?$")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be an object")
    return value


def _reject_unknown_fields(data: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = [str(key) for key in data if key not in allowed]
    if unknown:
        raise ValueError(f"{field} has unknown field '{unknown[0]}'")


def _required(data: Mapping[str, Any], field: str) -> Any:
    if field not in data:
        raise ValueError(f"{field} is required")
    return data[field]


def _schema(value: object) -> None:
    if type(value) is not int or value != 1:
        raise ValueError("schema must be 1")


def _nonblank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonblank string")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field} must be a string when provided")
    return value


def _content_hash(value: object, field: str = "content_hash") -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must match sha256:<64 lowercase hex digits>")
    return value


def _ordered_refs(value: object, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise TypeError(f"{field} must be an ordered list of references")
    refs = tuple(_nonblank(item, f"{field} reference") for item in value)
    if len(set(refs)) != len(refs):
        raise ValueError(f"{field} must contain unique references")
    return refs


def _version(value: object, field: str = "version") -> str | int | float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive valid version")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"{field} must be a positive valid version")
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{field} must be a positive valid version")
        return value
    if isinstance(value, str):
        candidate = value.strip()
        match = _VERSION_RE.fullmatch(candidate)
        if match is None or not any(int(part) > 0 for part in match.group("core").split(".")):
            raise ValueError(f"{field} must be a positive valid version")
        return value
    raise ValueError(f"{field} must be a positive valid version")


def _utc_iso8601(value: object, field: str = "generated_at") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a UTC ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must be a UTC ISO-8601 timestamp")
    return value


@dataclass(frozen=True)
class ArtifactRef:
    schema: int
    kind: str
    ref: str
    location: str
    content_hash: str
    scope_refs: tuple[str, ...]
    media_type: str | None = None

    def __post_init__(self) -> None:
        _schema(self.schema)
        _nonblank(self.kind, "kind")
        _nonblank(self.ref, "ref")
        _nonblank(self.location, "location")
        _content_hash(self.content_hash)
        object.__setattr__(self, "scope_refs", _ordered_refs(self.scope_refs, "scope_refs"))
        _optional_string(self.media_type, "media_type")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        raw = _mapping(data, "ArtifactRef")
        _reject_unknown_fields(
            raw,
            {"schema", "kind", "ref", "location", "content_hash", "scope_refs", "media_type"},
            "ArtifactRef",
        )
        return cls(
            schema=_required(raw, "schema"),
            kind=_required(raw, "kind"),
            ref=_required(raw, "ref"),
            location=_required(raw, "location"),
            content_hash=_required(raw, "content_hash"),
            scope_refs=_required(raw, "scope_refs"),
            media_type=raw.get("media_type"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema": self.schema,
            "kind": self.kind,
            "ref": self.ref,
            "location": self.location,
            "content_hash": self.content_hash,
            "scope_refs": list(self.scope_refs),
        }
        if self.media_type is not None:
            result["media_type"] = self.media_type
        return result


@dataclass(frozen=True)
class SnapshotInputRef:
    ref: str
    content_hash: str | None = None

    def __post_init__(self) -> None:
        _nonblank(self.ref, "ref")
        if self.content_hash is not None:
            _content_hash(self.content_hash)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        raw = _mapping(data, "SnapshotInputRef")
        _reject_unknown_fields(raw, {"ref", "content_hash"}, "SnapshotInputRef")
        return cls(ref=_required(raw, "ref"), content_hash=raw.get("content_hash"))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"ref": self.ref}
        if self.content_hash is not None:
            result["content_hash"] = self.content_hash
        return result


@dataclass(frozen=True)
class ProducerRef:
    name: str
    version: str | int | float
    engine: str | None = None

    def __post_init__(self) -> None:
        _nonblank(self.name, "producer.name")
        _version(self.version, "producer.version")
        _optional_string(self.engine, "producer.engine")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        raw = _mapping(data, "producer")
        _reject_unknown_fields(raw, {"name", "version", "engine"}, "producer")
        if "name" not in raw:
            raise ValueError("producer.name is required")
        if "version" not in raw:
            raise ValueError("producer.version is required")
        return cls(
            name=raw["name"],
            version=raw["version"],
            engine=raw.get("engine"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name, "version": self.version}
        if self.engine is not None:
            result["engine"] = self.engine
        return result


@dataclass(frozen=True)
class SnapshotRef:
    schema: int
    kind: str
    ref: str
    fingerprint: str
    producer: ProducerRef
    inputs: tuple[SnapshotInputRef, ...]
    generated_at: str
    supersedes: str | None = None

    def __post_init__(self) -> None:
        _schema(self.schema)
        _nonblank(self.kind, "kind")
        _nonblank(self.ref, "ref")
        _nonblank(self.fingerprint, "fingerprint")
        if not isinstance(self.producer, ProducerRef):
            raise TypeError("producer must be a ProducerRef")
        if isinstance(self.inputs, (str, bytes, Mapping)) or not isinstance(self.inputs, Sequence):
            raise TypeError("inputs must be an ordered list of SnapshotInputRef values")
        inputs = tuple(self.inputs)
        if not inputs:
            raise ValueError("inputs must be non-empty")
        if any(not isinstance(item, SnapshotInputRef) for item in inputs):
            raise TypeError("inputs must contain SnapshotInputRef values")
        input_refs = tuple(item.ref for item in inputs)
        if len(set(input_refs)) != len(input_refs):
            raise ValueError("inputs must contain unique references")
        object.__setattr__(self, "inputs", inputs)
        _utc_iso8601(self.generated_at)
        if self.supersedes is not None:
            _nonblank(self.supersedes, "supersedes")
            if self.supersedes == self.ref:
                raise ValueError("supersedes must not equal ref")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        raw = _mapping(data, "SnapshotRef")
        _reject_unknown_fields(
            raw,
            {"schema", "kind", "ref", "fingerprint", "producer", "inputs", "generated_at", "supersedes"},
            "SnapshotRef",
        )
        inputs_raw = _required(raw, "inputs")
        if isinstance(inputs_raw, (str, bytes, Mapping)) or not isinstance(inputs_raw, Sequence):
            raise TypeError("inputs must be an ordered list of SnapshotInputRef values")
        inputs = tuple(SnapshotInputRef.from_dict(item) for item in inputs_raw)
        return cls(
            schema=_required(raw, "schema"),
            kind=_required(raw, "kind"),
            ref=_required(raw, "ref"),
            fingerprint=_required(raw, "fingerprint"),
            producer=ProducerRef.from_dict(_required(raw, "producer")),
            inputs=inputs,
            generated_at=_required(raw, "generated_at"),
            supersedes=raw.get("supersedes"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema": self.schema,
            "kind": self.kind,
            "ref": self.ref,
            "fingerprint": self.fingerprint,
            "producer": self.producer.to_dict(),
            "inputs": [input_ref.to_dict() for input_ref in self.inputs],
            "generated_at": self.generated_at,
        }
        if self.supersedes is not None:
            result["supersedes"] = self.supersedes
        return result
