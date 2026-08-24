from __future__ import annotations

from enum import Enum


class SrState(str, Enum):
    DECLINED = "declined"
    PASS = "pass"
    SUSPECT = "suspect"
    UNMEASURED = "unmeasured"
    UNLINKED = "unlinked"
    UNVERIFIED = "unverified"
    NOT_IMPLEMENTED = "not_implemented"
    DISHONEST = "dishonest"


# Required fields and their expected types
_VERDICT_REQUIRED = {
    "sr_id": str,
    "implemented": bool,
    "honest": bool,
    "confidence": str,
    "reasoning": str,
    "checked": list,
    "assumed": list,
    "verify": list,
}


def validate_verdict(raw: dict) -> tuple[dict | None, str | None]:
    """Return (validated_verdict, error) — error is None when valid."""
    for field, expected_type in _VERDICT_REQUIRED.items():
        if field not in raw:
            return None, f"missing required field: {field}"
        if not isinstance(raw[field], expected_type):
            return None, (
                f"field {field}: expected {expected_type.__name__}, "
                f"got {type(raw[field]).__name__}"
            )
    if not isinstance(raw.get("margin"), (str, type(None))):
        return None, "field margin: expected str or None"

    for i, item in enumerate(raw.get("verify", [])):
        if not isinstance(item, dict):
            return None, f"verify[{i}]: expected dict"
        if "item" not in item or not isinstance(item["item"], str):
            return None, f"verify[{i}]: missing required str field 'item'"

    return raw, None


def classify(
    sr: dict,
    overlap: dict | None,
    verdict: dict | None,
    tool_failure: bool,
) -> tuple[SrState, list[str]]:
    """Classify an SR's coverage state (spec §8 priority order).

    Returns (state, notes) where notes are human-readable warnings or
    explanations.
    """
    notes: list[str] = []

    # 1. Declined (recorded decision, not a gap)
    if sr.get("deferred"):
        return SrState.DECLINED, []

    # 2. Unlinked (no satisfying task)
    if not sr.get("tasks"):
        return SrState.UNLINKED, ["no satisfying task"]

    # 3. Unverified (no subagent verdict)
    if verdict is None:
        if tool_failure:
            notes.append("subagent dispatch failed")
        else:
            notes.append("no subagent verdict recorded")
        return SrState.UNVERIFIED, notes

    # 4. Not implemented
    if not verdict["implemented"]:
        return SrState.NOT_IMPLEMENTED, [verdict.get("reasoning", "")]

    # 5. Dishonest
    if not verdict["honest"]:
        return SrState.DISHONEST, [verdict.get("reasoning", "")]

    # 6. Overlap check
    overlap_ok = overlap is not None and overlap.get("ok", False)
    if not overlap_ok:
        notes.append("import-graph overlap check failed — test does not reach changed files")

    # 7. Measurement
    measured = sr.get("measurement") is not None
    stale = sr.get("checksum_state") == "stale"
    if stale:
        notes.append("requirement statement is stale (checksum mismatch)")

    if overlap_ok and not stale and measured:
        state = SrState.PASS
    elif overlap_ok and not stale and not measured:
        state = SrState.UNMEASURED
        notes.append("no passing measurement recorded")
    else:
        state = SrState.SUSPECT

    return state, notes


__all__ = ["SrState", "classify", "validate_verdict"]
