"""Pure machine, human, and compact views of observation envelopes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
import json

from substrate.observations import ObservationEnvelope, RejectedObservation


__all__ = ["agent_compact", "human", "machine"]

_Envelope = ObservationEnvelope | RejectedObservation
_Projection = dict[str, object]
_REDACTED = "[REDACTED]"


def _schema(envelope: _Envelope) -> int:
    """Return the envelope schema, including the schema retained by rejection."""

    if isinstance(envelope, ObservationEnvelope):
        return envelope.schema
    # RejectedObservation is only constructed from the currently supported
    # schema-1 envelope and deliberately keeps only the rejection-safe fields.
    return 1


def _artifact_dicts(envelope: _Envelope) -> list[dict[str, object]]:
    if isinstance(envelope, ObservationEnvelope):
        return [artifact.to_dict() for artifact in envelope.artifacts]
    return envelope.to_dict()["raw_artifacts"]


def _base(
    envelope: _Envelope,
    freshness: object,
    *,
    truncated: bool,
    redacted: bool,
    redactions: tuple[str, ...] = (),
) -> _Projection:
    source_id, source_id_redacted = _redact_value(envelope.id, redactions)
    freshness_value, freshness_redacted = _redact_value(freshness, redactions)
    diagnostic_rows, diagnostics_redacted = _diagnostic_rows(envelope, redactions)
    return {
        "source_id": source_id,
        "schema": _schema(envelope),
        "freshness": freshness_value,
        "truncated": truncated,
        "redacted": redacted
        or source_id_redacted
        or freshness_redacted
        or diagnostics_redacted,
        "outcome": envelope.outcome,
        "diagnostics": diagnostic_rows,
        "invalid": envelope.outcome == "invalid",
    }


def _redact_value(value: object, redactions: tuple[str, ...]) -> tuple[object, bool]:
    if isinstance(value, str):
        if any(value == redaction for redaction in redactions):
            return _REDACTED, True
        return value, False
    if isinstance(value, Mapping):
        result: dict[object, object] = {}
        redacted = False
        for key, item in value.items():
            replacement, item_redacted = _redact_value(item, redactions)
            result[key] = replacement
            redacted = redacted or item_redacted
        return result, redacted
    if isinstance(value, list):
        result_list: list[object] = []
        redacted = False
        for item in value:
            replacement, item_redacted = _redact_value(item, redactions)
            result_list.append(replacement)
            redacted = redacted or item_redacted
        return result_list, redacted
    if isinstance(value, tuple):
        result_tuple: list[object] = []
        redacted = False
        for item in value:
            replacement, item_redacted = _redact_value(item, redactions)
            result_tuple.append(replacement)
            redacted = redacted or item_redacted
        return tuple(result_tuple), redacted
    return deepcopy(value), False


def _json_default(value: object) -> object:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return str(value)


def _render_value(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
    except (TypeError, ValueError):
        return str(value)


def _diagnostic_rows(
    envelope: _Envelope,
    redactions: tuple[str, ...],
) -> tuple[list[dict[str, str]], bool]:
    rows: list[dict[str, str]] = []
    redacted = False
    for diagnostic in envelope.diagnostics:
        summary, summary_redacted = _redact_value(diagnostic.summary, redactions)
        rows.append({"code": diagnostic.code, "summary": str(summary)})
        redacted = redacted or summary_redacted
    rows.sort(key=lambda row: row["code"])
    return rows, redacted


def _mapping_value(value: object, key: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _material_text(
    envelope: _Envelope,
    freshness: object,
    redactions: tuple[str, ...],
) -> tuple[str, bool, list[dict[str, str]]]:
    lines = [
        f"source_id: {envelope.id}",
        f"schema: {_schema(envelope)}",
        f"outcome: {envelope.outcome}",
        f"freshness: {_render_value(freshness)}",
    ]
    redacted = False

    if isinstance(envelope, RejectedObservation):
        lines.append("validity: rejected observation")

    if isinstance(envelope, ObservationEnvelope):
        scope_refs, scope_redacted = _redact_value(list(envelope.scope_refs), redactions)
        if scope_refs:
            lines.append(f"scope_refs: {_render_value(scope_refs)}")
        redacted = redacted or scope_redacted

        input_refs, inputs_redacted = _redact_value(
            [input_ref.to_dict() for input_ref in envelope.inputs], redactions
        )
        if input_refs:
            lines.append(f"inputs: {_render_value(input_refs)}")
        redacted = redacted or inputs_redacted

        # Invalid and unknown observations are not trusted as an interpretable
        # result.  Keep their full facts in the machine projection, but do not
        # let a fact such as ``passed`` make an explanatory view look like a
        # successful observation.
        if envelope.outcome not in {"invalid", "unknown"}:
            facts, facts_redacted = _redact_value(dict(envelope.facts), redactions)
            if isinstance(facts, Mapping):
                lines.append("facts:")
                for key in sorted(facts, key=lambda item: str(item)):
                    lines.append(f"- {key}: {_render_value(facts[key])}")
            redacted = redacted or facts_redacted

    diagnostic_rows, diagnostics_redacted = _diagnostic_rows(envelope, redactions)
    if diagnostic_rows:
        lines.append("diagnostics:")
        lines.extend(
            f"- {row['code']}: {_render_value(row['summary'])}" for row in diagnostic_rows
        )
    redacted = redacted or diagnostics_redacted

    artifacts, artifacts_redacted = _redact_value(_artifact_dicts(envelope), redactions)
    if isinstance(artifacts, list) and artifacts:
        lines.append("artifacts:")
        pointers: list[tuple[str, str]] = []
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                continue
            ref = str(_mapping_value(artifact, "ref") or "")
            location = str(_mapping_value(artifact, "location") or "")
            pointers.append((ref, location))
        pointers.sort()
        for ref, location in pointers:
            if location:
                lines.append(f"- {ref} @ {location}")
            else:
                lines.append(f"- {ref}")
    redacted = redacted or artifacts_redacted

    return "\n".join(lines), redacted, diagnostic_rows


def _fit_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    if max_chars == 0:
        return "", True

    selected: list[str] = []
    used = 0
    for line in text.splitlines():
        extra = len(line) if not selected else len(line) + 1
        if used + extra > max_chars:
            break
        selected.append(line)
        used += extra
    return "\n".join(selected), True


def machine(envelope: _Envelope, freshness: object) -> _Projection:
    """Return the complete validated envelope plus projection metadata."""

    result = _base(envelope, freshness, truncated=False, redacted=False)
    result.update(deepcopy(envelope.to_dict()))
    return result


def human(envelope: _Envelope, freshness: object) -> _Projection:
    """Return a deterministic explanatory rendering of an observation."""

    text, redacted, _ = _material_text(envelope, freshness, ())
    result = _base(envelope, freshness, truncated=False, redacted=redacted)
    result["text"] = text
    return result


def _compact_text(
    envelope: _Envelope,
    freshness: object,
    redactions: tuple[str, ...],
) -> tuple[str, bool, list[dict[str, str]]]:
    """Render the material fields in a compact, stable order.

    Compact output deliberately uses references rather than copying artifact
    metadata such as hashes.  The machine projection remains the complete
    source of truth, while this view keeps the fields an agent can retrieve or
    reason about within a small character budget.
    """

    redacted = False

    def value_text(value: object) -> str:
        nonlocal redacted
        replacement, value_redacted = _redact_value(value, redactions)
        redacted = redacted or value_redacted
        return _render_value(replacement)

    lines = [
        f"source_id={value_text(envelope.id)}",
        f"schema={_schema(envelope)}",
        f"outcome={envelope.outcome}",
        f"freshness={value_text(freshness)}",
    ]

    if isinstance(envelope, ObservationEnvelope):
        if envelope.scope_refs:
            lines.append(f"scope_refs={value_text(list(envelope.scope_refs))}")

        if envelope.inputs:
            input_refs = [input_ref.ref for input_ref in envelope.inputs]
            lines.append(f"inputs={value_text(input_refs)}")

        # As in the human view, invalid and unknown facts are retained only in
        # the machine projection so their fields cannot imply a pass outcome.
        if envelope.outcome not in {"invalid", "unknown"} and envelope.facts:
            facts: list[str] = []
            for key in sorted(envelope.facts, key=lambda item: str(item)):
                facts.append(f"{key}={value_text(envelope.facts[key])}")
            lines.append(f"facts={';'.join(facts)}")

    diagnostic_rows, diagnostics_redacted = _diagnostic_rows(envelope, redactions)
    if diagnostic_rows:
        diagnostics = [
            f"{row['code']}={_render_value(row['summary'])}" for row in diagnostic_rows
        ]
        lines.append(f"diagnostics={';'.join(diagnostics)}")
    redacted = redacted or diagnostics_redacted

    artifacts, artifacts_redacted = _redact_value(_artifact_dicts(envelope), redactions)
    if isinstance(artifacts, list) and artifacts:
        pointers: list[tuple[str, str]] = []
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                continue
            ref = str(_mapping_value(artifact, "ref") or "")
            location = str(_mapping_value(artifact, "location") or "")
            pointers.append((ref, location))
        pointers.sort()
        lines.append(
            "artifacts="
            + ";".join(
                f"{value_text(ref)}@{value_text(location)}" if location else value_text(ref)
                for ref, location in pointers
            )
        )
    redacted = redacted or artifacts_redacted

    return "\n".join(lines), redacted, diagnostic_rows


def agent_compact(
    envelope: _Envelope,
    freshness: object,
    max_chars: int,
    redactions: Iterable[str] = (),
) -> _Projection:
    """Return a deterministic text view constrained to ``max_chars``."""

    if isinstance(max_chars, bool) or not isinstance(max_chars, int):
        raise TypeError("max_chars must be a non-negative integer")
    if max_chars < 0:
        raise ValueError("max_chars must be a non-negative integer")

    declared_redactions = tuple(redactions)
    full_text, redacted, diagnostic_rows = _compact_text(
        envelope,
        freshness,
        declared_redactions,
    )
    text, truncated = _fit_text(full_text, max_chars)
    result = _base(
        envelope,
        freshness,
        truncated=truncated,
        redacted=redacted,
        redactions=declared_redactions,
    )
    result["diagnostics"] = diagnostic_rows
    result["text"] = text
    return result
