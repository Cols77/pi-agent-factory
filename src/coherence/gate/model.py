"""Data model for explicit, durable gate decisions.

The one allowed decision ``action`` vocabulary for this repo's gate items is
``accept``, ``reject``, ``defer``. ``kind``s follow the Review Amendments item
prefix families:

- ``coverage:<run>:proposal:<id>``
- ``coverage:<run>:warning:<id>``
- ``doctor:<id>``
- ``trace:<id>``
- ``review:<id>``

Validation rules (enforced by `validate_decisions`, and therefore by every
store write and file read):

- the decision set must not be empty;
- every ``action`` must be one of ``accept`` / ``reject`` / ``defer``;
- every ``item_id`` must carry a recognised prefix family;
- ``reject`` / ``defer`` require a non-blank ``reason``;
- ``defer`` requires an ISO-8601 ``review_after``;
- item ids must be unique within a file.

``decided_at`` / ``review_after`` stay ISO-8601 *strings* in the data model
for round-trip fidelity; they are not flattened to ``datetime`` objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DecisionAction = Literal["accept", "reject", "defer"]

#: The one allowed decision action values for this repo's gate items.
ACCEPTED_ACTIONS: tuple[str, ...] = ("accept", "reject", "defer")

#: Allowed item-id prefix families (Review Amendments item-id prefixes).
ITEM_ID_PREFIXES: tuple[str, ...] = (
    "coverage:",
    "doctor:",
    "trace:",
    "review:",
)


class DecisionValidationError(ValueError):
    """A decision set or a decision file violates a gate-decision rule."""


class CorruptDecisionFile(ValueError):
    """A persisted decision file is not a well-formed valid decision file.

    Raised on malformed JSON or on content that fails to decode into a valid
    `DecisionFile` -- never a bare ``JSONDecodeError``/``ValueError`` and
    never a silent ``{}`` or empty decision set.
    """


@dataclass(frozen=True)
class Decision:
    """One explicit decision on a single item.

    ``reason`` may be empty for ``accept``. ``decided_by`` is optional and
    defaults to ``None`` at the item level (the owning file carries the
    authoritative actor).
    """

    item_id: str
    action: str = "accept"
    reason: str = ""
    review_after: str | None = None
    decided_by: str | None = None


@dataclass(frozen=True)
class DecisionFile:
    """A versioned, durable, atomic record of a gate's explicit decision.

    ``schema`` is ``1``. ``decided_at``/``review_after`` are kept verbatim as
    ISO-8601 strings for round-trip fidelity. Construction requires the
    decisions to validate.
    """

    schema: int = 1
    gate_id: str = ""
    artifact_ref: str = ""
    decisions: tuple[Decision, ...] = field(default_factory=tuple)
    decided_at: str = ""
    decided_by: str = ""

    def __post_init__(self) -> None:
        validate_decisions(self.decisions)

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "gate_id": self.gate_id,
            "artifact_ref": self.artifact_ref,
            "decisions": [_decision_to_dict(d) for d in self.decisions],
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "DecisionFile":
        try:
            schema = raw["schema"]
            gate_id = _as_str(raw["gate_id"])
            artifact_ref = _as_str(raw.get("artifact_ref", ""))
            decisions_raw = raw.get("decisions") or []
            decided_at = _as_str(raw["decided_at"])
            decided_by = _as_str(raw.get("decided_by", ""))
        except (KeyError, TypeError) as exc:
            raise CorruptDecisionFile(
                f"decision file is missing a required field: {exc}"
            ) from exc
        if schema != 1:
            raise CorruptDecisionFile(f"unsupported decision file schema {schema!r}")
        try:
            return cls(
                schema=schema,
                gate_id=gate_id,
                artifact_ref=artifact_ref,
                decisions=tuple(_decision_from_raw(d) for d in decisions_raw),
                decided_at=decided_at,
                decided_by=decided_by,
            )
        except (DecisionValidationError, CorruptDecisionFile) as exc:
            raise CorruptDecisionFile(
                f"decision file content is invalid: {exc}"
            ) from exc


def validate_decisions(decisions: tuple[Decision, ...]) -> None:
    """Validate a decision set, raising `DecisionValidationError` on any
    violation: empty set, unknown action, unrecognised item-id prefix, blank
    required reason, missing/non-ISO ``review_after``, or duplicate item id.
    """
    if not decisions:
        raise DecisionValidationError("decision set is empty")
    seen: set[str] = set()
    for d in decisions:
        if d.action not in ACCEPTED_ACTIONS:
            raise DecisionValidationError(
                f"unknown decision action {d.action!r}; allowed {ACCEPTED_ACTIONS}"
            )
        if not d.item_id.startswith(tuple(ITEM_ID_PREFIXES)):
            raise DecisionValidationError(
                f"item id {d.item_id!r} has no recognised prefix (allowed:"
                f" {ITEM_ID_PREFIXES})"
            )
        if d.action in ("reject", "defer") and not (d.reason and d.reason.strip()):
            raise DecisionValidationError(
                f"{d.action} requires a non-blank reason"
            )
        if d.action == "defer" and not (d.review_after and _is_iso(d.review_after)):
            raise DecisionValidationError(
                f"defer requires an ISO-8601 review_after, got {d.review_after!r}"
            )
        if d.item_id in seen:
            raise DecisionValidationError(f"duplicate item id {d.item_id!r}")
        seen.add(d.item_id)


def _is_iso(value: str) -> bool:
    """Cheap ISO-8601 shape check for a timestamp string.

    Accepts the repo's verbatim stamps (e.g. ``2026-08-20T00:00:00Z`` and
    ``2026-08-20 00:00:00+00:00``) while rejecting junk. It validates shape,
    not instant semantics -- the plan stores these stamps verbatim.
    """
    s = value.strip()
    if not s or len(s) < 10:
        return False
    return ("T" in s) or (" " in s)


def _as_str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise CorruptDecisionFile(f"expected a string, got {value!r}")


def _decision_from_raw(raw: object) -> Decision:
    if not isinstance(raw, dict):
        raise CorruptDecisionFile(f"decision entry is not an object: {raw!r}")
    item_id = _as_str(raw.get("item_id", ""))
    action = _as_str(raw.get("action", "accept"))
    reason = _as_str(raw.get("reason", ""))
    review_after_raw = raw.get("review_after")
    review_after = _as_str(review_after_raw) if review_after_raw is not None else None
    decided_by_raw = raw.get("decided_by")
    decided_by = _as_str(decided_by_raw) if decided_by_raw is not None else None
    return Decision(
        item_id=item_id,
        action=action,
        reason=reason,
        review_after=review_after,
        decided_by=decided_by,
    )


def _decision_to_dict(d: Decision) -> dict:
    return {
        "item_id": d.item_id,
        "action": d.action,
        "reason": d.reason,
        "review_after": d.review_after,
        "decided_by": d.decided_by,
    }