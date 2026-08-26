from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from coherence.register.markers import MarkerCollectionError, collect_markers
from coherence.register.register import Requirement, is_checksum_current
from substrate.freshness.model import FreshnessSeverity
from substrate.policy.vocabulary import UncompiledPresetError


class RequirementState(str, Enum):
    MEASURED_PASSING = "measured-passing"
    MEASURED_FAILING = "measured-failing"
    PLANNED = "planned"
    UNMEASURABLE = "unmeasurable"
    DECLINED = "declined"
    PENDING = "pending"
    # A bound experiment that cannot be statically read as a test file. The
    # closure must not fabricate an sr marker for it; it reports the gap instead.
    CONFIGURATION = "configuration"


@dataclass(frozen=True)
class ClosureFinding:
    req_id: str
    state: RequirementState
    # None for every healthy state: a healthy finding is not a problem report,
    # and giving it a severity would force every consumer to filter one out.
    # Other findings carry a FreshnessSeverity member (a str subclass) mapped
    # from the compiled `test_marker` obligation's requiredness -- never a raw
    # string nor a value the closure check re-derives from a profile string.
    # The degraded marker-check diagnostic (UncompiledPresetError skip with no
    # errors channel) also uses a None severity so it is visible but non-gating.
    severity: str | None
    detail: str


def classify(
    req: Requirement,
    *,
    validation: str | None,
    linked_task_status: str | None,
    deferred_reason: str | None,
) -> ClosureFinding:
    if req.binding is not None and not is_checksum_current(req):
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.PENDING,
            severity=FreshnessSeverity.BLOCKING,
            detail=f"{req.id}: binding checksum is stale; re-bind to refresh it",
        )

    if validation == "passing":
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.MEASURED_PASSING,
            severity=None,
            detail=f"{req.id}: measured passing",
        )
    if validation == "failing":
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.MEASURED_FAILING,
            severity=None,
            detail=f"{req.id}: measured failing",
        )

    if req.binding is not None and req.binding.harness is None:
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.UNMEASURABLE,
            severity=FreshnessSeverity.WARNING,
            detail=f"{req.id}: binding names no harness yet",
        )

    if deferred_reason:
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.DECLINED,
            severity=None,
            detail=f"{req.id}: deferred -- {deferred_reason}",
        )

    if req.binding is not None and linked_task_status is not None and linked_task_status != "done":
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.PLANNED,
            severity=None,
            detail=f"{req.id}: linked task is {linked_task_status}",
        )

    return ClosureFinding(
        req_id=req.id,
        state=RequirementState.PENDING,
        severity=FreshnessSeverity.BLOCKING,
        detail=f"{req.id}: no measurement, task, or deferral accounts for this requirement",
    )


def resolve_experiment_path(experiment: str, *, project_root: Path) -> Path | None:
    """Resolve an experiment id to a readable ``.py`` test file, else ``None``.

    A command (e.g. ``patrol``) and a path that does not exist are both
    non-resolvable: the closure cannot statically read a marker out of them.
    """
    candidate = Path(experiment)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    if candidate.suffix == ".py" and candidate.is_file():
        return candidate
    return None


def _test_marker_requiredness(req_id: str, *, project_root: Path) -> str:
    """Read the compiled `test_marker` obligation's requiredness for this SR's
    scope, via the SAME compiler the profile-aware closure CHECK must consume.
    Raising on an unresolved profile (e.g. UncompiledPresetError for an
    exploration/product-profiled scope) is intentional: the check never falls
    back to the project default nor fabricates a severity."""
    from coherence.policy.compiler import compile_obligations

    obligations = compile_obligations(project_root, f"sr:{req_id}")
    obligation = next(o for o in obligations if o.kind == "test_marker")
    return obligation.requiredness


def verify_sr_marker(
    req: Requirement,
    *,
    project_root: Path,
    errors: list[str] | None = None,
) -> ClosureFinding | None:
    """Verify a bound SR's experiment carries its ``@pytest.mark.sr`` marker.

    Checks ONLY resolvable test-file experiment paths:

    * proposed/unbound -- there is no experiment to verify; ``None`` (unchanged).
    * experiment resolves to an existing ``.py`` test file with the matching
      marker -- ``None`` (healthy).
    * experiment resolves to a ``.py`` file WITHOUT the matching marker -- a
      finding whose severity is the compiled ``test_marker`` obligation's
      requiredness for the SR's scope (Task 6 addendum) mapped to a
      ``FreshnessSeverity`` member (``"required"`` -> WARNING,
      ``"blocking"`` -> BLOCKING, ``"not_applicable"`` -> None),
      never a raw string value.
    * experiment is a command / non-file -- a CONFIGURATION finding; the closure
      never invents a marker result it could not inspect.

    On an ``UncompiledPresetError`` (Increment 2B -- an exploration/product
    profiled scope), the check does NOT silently fall back to the project
    default: when an ``errors`` list is supplied, the message is appended there
    and the finding is skipped; when no channel is supplied, the SKIP is still
    surfaced as a visible None-severity finding so a skipped marker check is
    never silently discarded.
    """
    # NOTE (wired, gating): verify_sr_marker is now part of the PRODUCTION
    # path, not an API-level check consumed by unit tests only. `coherence
    # register check` (cmd_check) surfaces its findings -- a missing-marker
    # finding on a bound .py experiment whose severity is the compiled
    # test_marker obligation's requiredness, mapped to a FreshnessSeverity
    # member as below (BLOCKING -> pending/gate, required -> visible WARNING) --
    # and the runs service gates on the compiled BLOCKING test_marker
    # obligation. Pass an `errors` list when skips must be surfaced on the
    # caller's errors channel (cmd_check does this so a skipped marker check
    # stays visible); when no channel is supplied the skip is surfaced as a
    # visible non-gating finding so it is never silently dropped.
    if req.binding is None:
        return None
    path = resolve_experiment_path(req.binding.experiment, project_root=project_root)
    if path is None:
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.CONFIGURATION,
            severity=FreshnessSeverity.WARNING,
            detail=(
                f"{req.id}: experiment {req.binding.experiment!r} is not an existing "
                ".py test file; cannot verify an sr marker -- no marker assumed"
            ),
        )
    try:
        has_marker = req.id in collect_markers(path)
    except MarkerCollectionError as exc:
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.CONFIGURATION,
            severity=FreshnessSeverity.WARNING,
            detail=(
                f"{req.id}: experiment file {path.name} could not be inspected "
                f"for an sr marker: {exc}"
            ),
        )
    if has_marker:
        return None
    try:
        requiredness = _test_marker_requiredness(req.id, project_root=project_root)
    except UncompiledPresetError as exc:
        skip_reason = f"{req.id}: marker-closure check skipped: {exc}"
        if errors is not None:
            # A channel was supplied: keep the degrade path, append the message
            # so the caller sees exactly why the check was skipped.
            errors.append(skip_reason)
            return None
        # No errors channel supplied. Do NOT swallow the skip: surface it as a
        # visible non-gating diagnostic so a skipped marker check is never
        # invisible to a caller that did not pass an errors list.
        return ClosureFinding(
            req_id=req.id,
            state=RequirementState.CONFIGURATION,
            severity=None,
            detail=skip_reason,
        )
    # Map the compiled requiredness to a proper FreshnessSeverity member so a
    # consumer gating on GATE_FAILING_SEVERITIES never sees a raw string slip
    # through ("blocking" -> BLOCKING). Unknown values degrade to None (visible
    # but non-gating) rather than mis-gating.
    severity = {
        "blocking": FreshnessSeverity.BLOCKING,
        "required": FreshnessSeverity.WARNING,
        "not_applicable": None,
    }.get(requiredness)
    return ClosureFinding(
        req_id=req.id,
        state=RequirementState.PENDING,
        severity=severity,
        detail=(
            f"{req.id}: experiment file {path.name} has no "
            f"@pytest.mark.sr({req.id!r}) marker"
        ),
    )


__all__ = [
    "ClosureFinding",
    "RequirementState",
    "classify",
    "resolve_experiment_path",
    "verify_sr_marker",
]
