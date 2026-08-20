"""Validated, time-bound observations and explicit facts registries."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Literal, Self

from substrate.artifacts import ArtifactRef, ProducerRef, SnapshotInputRef


__all__ = [
    "Diagnostic",
    "FactsValidator",
    "ObservationEnvelope",
    "Outcome",
    "PayloadRegistry",
    "RejectedObservation",
]


Outcome = Literal["pass", "fail", "invalid", "interrupted", "unknown"]
FactsValidator = Callable[[Mapping[str, object]], None]

_OUTCOMES: frozenset[str] = frozenset(
    {"pass", "fail", "invalid", "interrupted", "unknown"}
)


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    return value


def _reject_unknown_fields(data: Mapping[str, Any], allowed: set[str], field_name: str) -> None:
    unknown = [str(key) for key in data if key not in allowed]
    if unknown:
        raise ValueError(f"{field_name} has unknown field '{unknown[0]}'")


def _required(data: Mapping[str, Any], field_name: str) -> Any:
    if field_name not in data:
        raise ValueError(f"{field_name} is required")
    return data[field_name]


def _schema(value: object) -> None:
    if type(value) is not int or value != 1:
        raise ValueError("schema must be 1")


def _nonblank(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonblank string")
    return value


def _utc_iso8601(value: object, field_name: str = "observed_at") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a UTC ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be a UTC ISO-8601 timestamp")
    return value


def _ordered_refs(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be an ordered list of references")
    refs = tuple(_nonblank(item, f"{field_name} reference") for item in value)
    if len(set(refs)) != len(refs):
        raise ValueError(f"{field_name} must contain unique references")
    return refs


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be an ordered list")
    return value


def _outcome(value: object) -> Outcome:
    if not isinstance(value, str) or value not in _OUTCOMES:
        raise ValueError(
            "outcome must be one of pass, fail, invalid, interrupted, or unknown"
        )
    return value  # type: ignore[return-value]


def _facts(value: object) -> Mapping[str, object]:
    raw = _mapping(value, "facts")
    schema = raw.get("schema")
    if not isinstance(schema, str) or not schema.strip():
        raise TypeError("facts.schema must be a string")
    return raw


@dataclass(frozen=True)
class Diagnostic:
    """A stable, machine-readable observation diagnostic."""

    code: str
    summary: str

    def __post_init__(self) -> None:
        _nonblank(self.code, "diagnostic.code")
        _nonblank(self.summary, "diagnostic.summary")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        raw = _mapping(data, "diagnostic")
        _reject_unknown_fields(raw, {"code", "summary"}, "diagnostic")
        if "code" not in raw:
            raise ValueError("diagnostic.code is required")
        if "summary" not in raw:
            raise ValueError("diagnostic.summary is required")
        return cls(
            code=raw["code"],
            summary=raw["summary"],
        )

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "summary": self.summary}


class FactsValidationError(ValueError):
    """Raised when an explicitly registered facts validator rejects a payload."""


class PayloadRegistry:
    """An explicit, caller-owned mapping from facts schemas to validators."""

    def __init__(self, validators: Mapping[str, FactsValidator] | None = None) -> None:
        self._validators: dict[str, FactsValidator] = {}
        if validators is not None:
            for schema, validator in validators.items():
                self.register(schema, validator)

    def register(self, schema: str, validator: FactsValidator) -> None:
        _nonblank(schema, "facts schema")
        if not callable(validator):
            raise TypeError("facts validator must be callable")
        self._validators[schema] = validator

    def lookup(self, schema: str) -> FactsValidator | None:
        return self._validators.get(schema)

    def validate(self, facts: Mapping[str, object]) -> None:
        raw = _facts(facts)
        schema = raw["schema"]
        assert isinstance(schema, str)
        validator = self.lookup(schema)
        if validator is None:
            raise ValueError(f"unknown facts schema '{schema}'")
        try:
            validator(raw)
        except Exception as exc:
            raise FactsValidationError(f"facts validation rejected: {exc}") from exc


@dataclass(frozen=True)
class ObservationEnvelope:
    schema: int
    id: str
    kind: str
    producer: ProducerRef
    observed_at: str
    scope_refs: tuple[str, ...]
    inputs: tuple[SnapshotInputRef, ...]
    outcome: Outcome
    facts: Mapping[str, object]
    diagnostics: tuple[Diagnostic, ...]
    artifacts: tuple[ArtifactRef, ...]
    _gate_eligible: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _schema(self.schema)
        _nonblank(self.id, "id")
        _nonblank(self.kind, "kind")
        if not isinstance(self.producer, ProducerRef):
            raise TypeError("producer must be a ProducerRef")
        _utc_iso8601(self.observed_at)
        object.__setattr__(self, "scope_refs", _ordered_refs(self.scope_refs, "scope_refs"))

        input_values = tuple(self.inputs)
        if any(not isinstance(item, SnapshotInputRef) for item in input_values):
            raise TypeError("inputs must contain SnapshotInputRef values")
        input_refs = tuple(item.ref for item in input_values)
        if len(set(input_refs)) != len(input_refs):
            raise ValueError("inputs must contain unique references")
        object.__setattr__(self, "inputs", input_values)

        object.__setattr__(self, "outcome", _outcome(self.outcome))
        facts = _facts(self.facts)
        object.__setattr__(
            self,
            "facts",
            MappingProxyType(dict(deepcopy(facts))),
        )

        diagnostic_values = tuple(self.diagnostics)
        if any(not isinstance(item, Diagnostic) for item in diagnostic_values):
            raise TypeError("diagnostics must contain Diagnostic values")
        object.__setattr__(self, "diagnostics", diagnostic_values)

        artifact_values = tuple(self.artifacts)
        if any(not isinstance(item, ArtifactRef) for item in artifact_values):
            raise TypeError("artifacts must contain ArtifactRef values")
        artifact_refs = tuple(item.ref for item in artifact_values)
        if len(set(artifact_refs)) != len(artifact_refs):
            raise ValueError("artifacts must contain unique references")
        object.__setattr__(self, "artifacts", artifact_values)

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        registry: PayloadRegistry | None = None,
    ) -> ObservationEnvelope | RejectedObservation:
        raw = _mapping(data, "ObservationEnvelope")
        _reject_unknown_fields(
            raw,
            {
                "schema",
                "id",
                "kind",
                "producer",
                "observed_at",
                "scope_refs",
                "inputs",
                "outcome",
                "facts",
                "diagnostics",
                "artifacts",
            },
            "ObservationEnvelope",
        )

        inputs_raw = _sequence(_required(raw, "inputs"), "inputs")
        diagnostics_raw = _sequence(_required(raw, "diagnostics"), "diagnostics")
        artifacts_raw = _sequence(_required(raw, "artifacts"), "artifacts")
        envelope = cls(
            schema=_required(raw, "schema"),
            id=_required(raw, "id"),
            kind=_required(raw, "kind"),
            producer=ProducerRef.from_dict(_required(raw, "producer")),
            observed_at=_required(raw, "observed_at"),
            scope_refs=_required(raw, "scope_refs"),
            inputs=tuple(
                SnapshotInputRef.from_dict(_mapping(item, "input")) for item in inputs_raw
            ),
            outcome=_required(raw, "outcome"),
            facts=_required(raw, "facts"),
            diagnostics=tuple(
                Diagnostic.from_dict(_mapping(item, "diagnostic")) for item in diagnostics_raw
            ),
            artifacts=tuple(
                ArtifactRef.from_dict(_mapping(item, "artifact")) for item in artifacts_raw
            ),
        )

        if registry is None:
            return envelope

        try:
            envelope.validate_for_gate(registry)
        except FactsValidationError as exc:
            return RejectedObservation.from_envelope(envelope, str(exc))
        return envelope

    def validate_for_gate(self, registry: PayloadRegistry) -> None:
        if not isinstance(registry, PayloadRegistry):
            raise TypeError("registry must be a PayloadRegistry")
        try:
            registry.validate(self.facts)
        except Exception:
            object.__setattr__(self, "_gate_eligible", False)
            raise
        object.__setattr__(
            self,
            "_gate_eligible",
            self.outcome in {"pass", "fail"},
        )

    @property
    def gate_eligible(self) -> bool:
        return self._gate_eligible

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "id": self.id,
            "kind": self.kind,
            "producer": self.producer.to_dict(),
            "observed_at": self.observed_at,
            "scope_refs": list(self.scope_refs),
            "inputs": [item.to_dict() for item in self.inputs],
            "outcome": self.outcome,
            "facts": deepcopy(dict(self.facts)),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


@dataclass(frozen=True)
class RejectedObservation:
    """A structurally valid observation whose facts payload was rejected."""

    id: str
    kind: str
    producer: ProducerRef
    observed_at: str
    outcome: Literal["invalid"]
    diagnostics: tuple[Diagnostic, ...]
    raw_artifacts: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        _nonblank(self.id, "id")
        _nonblank(self.kind, "kind")
        if not isinstance(self.producer, ProducerRef):
            raise TypeError("producer must be a ProducerRef")
        _utc_iso8601(self.observed_at)
        if self.outcome != "invalid":
            raise ValueError("rejected observation outcome must be invalid")
        diagnostic_values = tuple(self.diagnostics)
        if any(not isinstance(item, Diagnostic) for item in diagnostic_values):
            raise TypeError("diagnostics must contain Diagnostic values")
        object.__setattr__(self, "diagnostics", diagnostic_values)
        object.__setattr__(
            self,
            "raw_artifacts",
            tuple(deepcopy(item) for item in self.raw_artifacts),
        )

    @classmethod
    def from_envelope(cls, envelope: ObservationEnvelope, reason: str) -> Self:
        return cls(
            id=envelope.id,
            kind=envelope.kind,
            producer=envelope.producer,
            observed_at=envelope.observed_at,
            outcome="invalid",
            diagnostics=(
                Diagnostic(code="FACTS_VALIDATION_REJECTED", summary=reason),
                *envelope.diagnostics,
            ),
            raw_artifacts=tuple(item.to_dict() for item in envelope.artifacts),
        )

    @property
    def gate_eligible(self) -> bool:
        return False

    def validate_for_gate(self, registry: PayloadRegistry) -> None:
        if not isinstance(registry, PayloadRegistry):
            raise TypeError("registry must be a PayloadRegistry")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "producer": self.producer.to_dict(),
            "observed_at": self.observed_at,
            "outcome": self.outcome,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "raw_artifacts": deepcopy(list(self.raw_artifacts)),
        }
