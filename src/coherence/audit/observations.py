"""Adapts completed audit reports and per-SR verdicts into audit/v1 envelopes.

``coherence.audit`` produces one consolidated ``report.json`` per run
(``coherence.audit.cli.cmd_consolidate``) carrying every SR's classified
``SrState`` (``coherence.audit.audit.SrState``) plus human-readable notes,
and zero-or-one raw subagent verdict per SR under ``verdicts/<SR>.json``.
This adapter emits one ``audit/v1`` envelope per SR: the typed state and
notes come straight from the report (already structured), while the report
file itself and the raw verdict (its narrative ``reasoning``/``checked``/
``assumed``/``verify`` fields) are content-hashed into their own
``ArtifactRef``s rather than embedded in facts, per this increment's review
amendment ("each content-hashes raw output artifacts").

Outcome defaults mirror ``coherence.audit.gate.run_gate``'s own per-SR
disposition exactly, so a workflow (tool-dispatch) failure can only resolve
to ``"fail"`` or ``"unknown"`` -- consistent with the existing gate state and
never a synthetic ``"pass"``:

* ``pass`` -> ``"pass"``.
* ``unlinked``/``not_implemented``/``dishonest`` (gate hard-fail states) ->
  ``"fail"``.
* ``unverified`` -> ``"unknown"`` when a tool/dispatch failure is on record
  for this SR (the gate degrades it), else ``"fail"`` (the gate hard-fails
  it: no verdict, no excuse).
* ``suspect``/``unmeasured`` (gate warn states -- non-blocking, but not a
  genuine pass claim) -> ``"unknown"``.
* ``declined`` (a recorded human decision not to measure) -> ``"unknown"``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from substrate.artifacts import ArtifactRef, ProducerRef, SnapshotInputRef
from substrate.freshness.fingerprint import sha256_bytes
from substrate.observations import Diagnostic, ObservationEnvelope, Outcome, PayloadRegistry

from coherence.audit.audit import SrState

__all__ = ["AUDIT_SCHEMA", "REGISTRY", "audit_observation"]

AUDIT_SCHEMA = "audit/v1"

_SR_STATES = frozenset(state.value for state in SrState)
_FAIL_STATES = frozenset(
    {SrState.UNLINKED.value, SrState.NOT_IMPLEMENTED.value, SrState.DISHONEST.value}
)
_UNKNOWN_STATES = frozenset(
    {SrState.SUSPECT.value, SrState.UNMEASURED.value, SrState.DECLINED.value}
)


def _dedupe(refs: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return tuple(ordered)


def _sr_state_and_notes(report: Mapping[str, object], sr_id: str) -> tuple[str, list[str]]:
    states = report.get("states")
    entry = states.get(sr_id) if isinstance(states, Mapping) else None
    if not isinstance(entry, (list, tuple)) or len(entry) < 2:
        raise ValueError(f"audit/v1: no classified state recorded for SR {sr_id!r}")
    state, notes = entry[0], entry[1]
    notes_list = notes if isinstance(notes, (list, tuple)) else []
    return str(state), [str(n) for n in notes_list]


def _sr_tool_failure(report: Mapping[str, object], sr_id: str) -> tuple[bool, str | None]:
    issues = report.get("workflow_issues")
    if not isinstance(issues, (list, tuple)):
        return False, None
    for issue in issues:
        if isinstance(issue, Mapping) and issue.get("sr_id") == sr_id:
            summary = issue.get("issue")
            return True, str(summary) if summary else "workflow failure"
    return False, None


def _default_outcome(state: str, tool_failure: bool) -> Outcome:
    if state == SrState.PASS.value:
        return "pass"
    if state in _FAIL_STATES:
        return "fail"
    if state == SrState.UNVERIFIED.value:
        return "unknown" if tool_failure else "fail"
    if state in _UNKNOWN_STATES:
        return "unknown"
    return "unknown"


def _report_artifact(
    report_path: Path | None, *, id: str, scope_refs: Sequence[str]
) -> ArtifactRef | None:
    if report_path is None or not report_path.is_file():
        return None
    return ArtifactRef(
        schema=1,
        kind="audit-report",
        ref=f"artifact:audit-report:{id}",
        location=str(report_path),
        content_hash=sha256_bytes(report_path.read_bytes()),
        scope_refs=tuple(scope_refs),
        media_type="application/json",
    )


def _verdict_artifact(
    verdict: Mapping[str, object] | None, sr_id: str, *, id: str, scope_refs: Sequence[str]
) -> ArtifactRef | None:
    if verdict is None:
        return None
    payload = json.dumps(
        dict(verdict), sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return ArtifactRef(
        schema=1,
        kind="audit-verdict",
        ref=f"artifact:audit-verdict:{id}",
        location=f"inline:audit-verdict:{sr_id}:{id}",
        content_hash=sha256_bytes(payload),
        scope_refs=tuple(scope_refs),
        media_type="application/json",
    )


def _sr_diagnostics(notes: Sequence[str], tool_failure: bool, issue: str | None) -> tuple[Diagnostic, ...]:
    diagnostics = [Diagnostic(code="AUDIT_SR_NOTE", summary=note) for note in notes if note]
    if tool_failure:
        diagnostics.append(
            Diagnostic(code="AUDIT_WORKFLOW_FAILURE", summary=issue or "workflow failure")
        )
    return tuple(diagnostics)


def _validate_audit_facts(facts: Mapping[str, object]) -> None:
    feature = facts.get("feature")
    if not isinstance(feature, str) or not feature.strip():
        raise ValueError("audit/v1 facts.feature must be a nonblank string")
    sr_id = facts.get("sr_id")
    if not isinstance(sr_id, str) or not sr_id.strip():
        raise ValueError("audit/v1 facts.sr_id must be a nonblank string")
    state = facts.get("state")
    if state not in _SR_STATES:
        raise ValueError(f"audit/v1 facts.state must be one of {sorted(_SR_STATES)}")
    notes = facts.get("notes")
    if not isinstance(notes, (list, tuple)) or any(not isinstance(n, str) for n in notes):
        raise ValueError("audit/v1 facts.notes must be a list of strings")
    if not isinstance(facts.get("tool_failure"), bool):
        raise ValueError("audit/v1 facts.tool_failure must be a bool")
    for key in ("implemented", "honest"):
        value = facts.get(key)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"audit/v1 facts.{key} must be a bool or null")
    for key in ("confidence", "margin"):
        value = facts.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"audit/v1 facts.{key} must be a string or null")
    _validate_ref_list(facts.get("artifacts"), "audit/v1 facts.artifacts")
    for key in ("verdict", "report"):
        value = facts.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"audit/v1 facts.{key} must be a nonblank ref string or null")


def _validate_ref_list(value: object, field_name: str) -> None:
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(ref, str) or not ref.strip() for ref in value
    ):
        raise ValueError(f"{field_name} must be a list of ref strings")


REGISTRY = PayloadRegistry()
REGISTRY.register(AUDIT_SCHEMA, _validate_audit_facts)


def audit_observation(
    report: Mapping[str, object],
    sr_id: str,
    verdict: Mapping[str, object] | None,
    inputs: Sequence[SnapshotInputRef],
    artifacts: Sequence[ArtifactRef],
    *,
    report_path: Path | None,
    id: str,
    producer: ProducerRef,
    observed_at: str,
    scope_refs: Sequence[str] = (),
    outcome: Outcome | None = None,
    diagnostics: Sequence[Diagnostic] = (),
) -> ObservationEnvelope:
    """Adapt one SR's slice of a consolidated audit ``report`` (plus its raw
    ``verdict``, or ``None`` when unverified) into an ``audit/v1`` envelope.

    ``report`` is the dict written to ``report.json`` by
    ``coherence.audit.cli.cmd_consolidate`` -- this reads ``report["states"]``
    and ``report["workflow_issues"]`` for ``sr_id``. ``report_path`` is
    content-hashed into its own ``ArtifactRef`` (the "report ArtifactRef");
    when ``verdict`` is given it is likewise content-hashed into its own
    artifact rather than folding its narrative fields into facts.

    ``scope_refs`` always gets ``feat:<feature>`` and ``sr:<sr_id>`` prefixed
    (deduplicated against anything the caller already included).

    ``outcome`` defaults from the SR's classified state and whether a tool
    failure is recorded for it, mirroring ``coherence.audit.gate.run_gate``'s
    own disposition; pass an explicit override for a claim the caller knows
    better than the stored report (e.g. ``"interrupted"``).
    """
    feature = str(report.get("feature", ""))
    state, notes = _sr_state_and_notes(report, sr_id)
    tool_failure, issue = _sr_tool_failure(report, sr_id)

    full_scope_refs = _dedupe((f"feat:{feature}", f"sr:{sr_id}", *scope_refs))

    report_ref = _report_artifact(report_path, id=id, scope_refs=full_scope_refs)
    verdict_ref = _verdict_artifact(verdict, sr_id, id=id, scope_refs=full_scope_refs)
    all_artifacts = tuple(artifacts)
    if report_ref is not None:
        all_artifacts += (report_ref,)
    if verdict_ref is not None:
        all_artifacts += (verdict_ref,)

    facts = {
        "schema": AUDIT_SCHEMA,
        "feature": feature,
        "sr_id": sr_id,
        "state": state,
        "notes": notes,
        "tool_failure": tool_failure,
        "implemented": verdict.get("implemented") if verdict else None,
        "honest": verdict.get("honest") if verdict else None,
        "confidence": verdict.get("confidence") if verdict else None,
        "margin": verdict.get("margin") if verdict else None,
        "artifacts": [a.ref for a in artifacts],
        "verdict": verdict_ref.ref if verdict_ref is not None else None,
        "report": report_ref.ref if report_ref is not None else None,
    }

    envelope = ObservationEnvelope(
        schema=1,
        id=id,
        kind="audit",
        producer=producer,
        observed_at=observed_at,
        scope_refs=full_scope_refs,
        inputs=tuple(inputs),
        outcome=outcome if outcome is not None else _default_outcome(state, tool_failure),
        facts=facts,
        diagnostics=(*_sr_diagnostics(notes, tool_failure, issue), *diagnostics),
        artifacts=all_artifacts,
    )
    return envelope.validate_for_gate(REGISTRY)
