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
    # Other findings carry a FreshnessSeverity member (a str subclass); the
    # missing-marker finding (Task 6 addendum) carries the compiled test_marker
    # obligation's requiredness string ("required"/"blocking") read off that
    # obligation -- never a value the closure check re-derives from a raw
    # profile string.
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
      finding whose severity is read OFF the compiled ``test_marker``
      obligation's requiredness for the SR's scope (Task 6 addendum), not a
      value re-derived from a raw profile string.
    * experiment is a command / non-file -- a CONFIGURATION finding; the closure
      never invents a marker result it could not inspect.

    On an ``UncompiledPresetError`` (Increment 2B -- an exploration/product
    profiled scope), the check does NOT silently fall back to the project
    default: it appends a message to ``errors`` (gaining a bare ``list[str]``
    channel when none was supplied) and skips the finding entirely rather than
    fabricating a severity for a profile the compiler could not resolve.
    """
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
        if errors is None:
            errors = []
        errors.append(f"{req.id}: marker-closure check skipped: {exc}")
        return None
    return ClosureFinding(
        req_id=req.id,
        state=RequirementState.PENDING,
        severity=requiredness,
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
