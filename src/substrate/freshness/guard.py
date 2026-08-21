from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from substrate.artifacts import SnapshotRef
from substrate.freshness.evaluate import compare_dependencies
from substrate.freshness.fingerprint import fingerprint_value
from substrate.freshness.model import DependencyFingerprint, FreshnessSeverity
from substrate.freshness.recipes import CompiledRecipes, FreshnessRecipe, ResolutionClass


@dataclass(frozen=True)
class StalenessObservation:
    candidate_ref: str
    output_kind: str
    expected_fingerprint: str
    actual_fingerprint: str


@dataclass(frozen=True)
class ResolutionBlocker:
    resolution_class: ResolutionClass
    action: str
    reason: str


@dataclass(frozen=True)
class ResolutionFailure:
    code: str
    reason: str


@dataclass(frozen=True)
class GuardResult:
    snapshot: SnapshotRef | None
    stale: StalenessObservation | None = None
    blocker: ResolutionBlocker | None = None
    failure: ResolutionFailure | None = None

    @property
    def current(self) -> bool:
        return self.snapshot is not None and self.blocker is None and self.failure is None


class GuardSession:
    """Mutable state for one guarded-read run."""

    def __init__(self) -> None:
        self.observations: list[StalenessObservation] = []
        self._attempt_cache: dict[tuple[str, str, str], GuardResult] = {}


def _normalize_fingerprint(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, DependencyFingerprint):
        return value.digest
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if not all(isinstance(item, DependencyFingerprint) for item in value):
            raise TypeError("fingerprinter sequence must contain DependencyFingerprint values")
        return fingerprint_value("freshness-inputs", [item.digest for item in value]).digest
    raise TypeError(
        "fingerprinter must return a string, DependencyFingerprint, "
        "or a sequence of DependencyFingerprint values"
    )


def _blocker_for(recipe: FreshnessRecipe) -> ResolutionBlocker:
    actions = {
        ResolutionClass.repeatable_policy: "policy-review",
        ResolutionClass.authoritative_gate: "authoritative-writer",
        ResolutionClass.provenance_blocked: "provenance-recovery",
    }
    action = actions[recipe.resolution_class]
    return ResolutionBlocker(
        resolution_class=recipe.resolution_class,
        action=action,
        reason=f"{recipe.output_kind} is stale and requires {action}",
    )


def _replacement_failure(
    replacement: object,
    recipe: FreshnessRecipe,
    candidate: SnapshotRef,
    actual_fingerprint: str,
) -> ResolutionFailure | None:
    if (
        not isinstance(replacement, SnapshotRef)
        or replacement.kind != recipe.output_kind
        or replacement.supersedes != candidate.ref
    ):
        return ResolutionFailure(
            code="invalid_replacement",
            reason="replacement kind or supersedes lineage is invalid",
        )
    if replacement.fingerprint != actual_fingerprint:
        return ResolutionFailure(
            code="stale_replacement",
            reason="replacement fingerprint does not match current inputs",
        )
    return None


def guarded_read(
    session: GuardSession,
    compiled: CompiledRecipes,
    recipe: FreshnessRecipe,
    candidate: SnapshotRef,
    inputs: Sequence[object],
) -> GuardResult:
    fingerprinter = compiled.fingerprinters[recipe.fingerprinter]
    actual_fingerprint = _normalize_fingerprint(fingerprinter(inputs))
    cache_key = (recipe.output_kind, candidate.ref, actual_fingerprint)
    cached = session._attempt_cache.get(cache_key)
    if cached is not None:
        return cached

    if candidate.kind != recipe.output_kind:
        result = GuardResult(
            snapshot=None,
            failure=ResolutionFailure(
                code="candidate_kind_mismatch",
                reason="candidate kind does not match recipe output kind",
            ),
        )
        session._attempt_cache[cache_key] = result
        return result

    expected = DependencyFingerprint(
        name=recipe.output_kind,
        kind="snapshot",
        digest=candidate.fingerprint,
        source=candidate.ref,
    )
    actual = DependencyFingerprint(
        name=recipe.output_kind,
        kind="snapshot",
        digest=actual_fingerprint,
        source=candidate.ref,
    )
    report = compare_dependencies(
        [expected],
        [actual],
        subject=candidate.ref,
        severity_for=lambda _: FreshnessSeverity.WARNING,
    )
    if not report.issues:
        result = GuardResult(snapshot=candidate)
        session._attempt_cache[cache_key] = result
        return result

    observation = StalenessObservation(
        candidate_ref=candidate.ref,
        output_kind=recipe.output_kind,
        expected_fingerprint=candidate.fingerprint,
        actual_fingerprint=actual_fingerprint,
    )
    session.observations.append(observation)

    if recipe.resolution_class is not ResolutionClass.derived_auto:
        result = GuardResult(snapshot=None, stale=observation, blocker=_blocker_for(recipe))
    else:
        resolver = compiled.resolvers.lookup(recipe.resolver)
        if resolver is None:
            result = GuardResult(
                snapshot=None,
                stale=observation,
                failure=ResolutionFailure(
                    code="resolver_missing",
                    reason=f"resolver is not registered: {recipe.resolver}",
                ),
            )
        else:
            try:
                replacement = resolver(recipe, candidate)
            except Exception as exc:
                reason = str(exc) or type(exc).__name__
                result = GuardResult(
                    snapshot=None,
                    stale=observation,
                    failure=ResolutionFailure(code="resolver_failed", reason=reason),
                )
            else:
                failure = _replacement_failure(replacement, recipe, candidate, actual_fingerprint)
                if failure is not None:
                    result = GuardResult(snapshot=None, stale=observation, failure=failure)
                else:
                    assert isinstance(replacement, SnapshotRef)
                    result = GuardResult(snapshot=replacement, stale=observation)

    session._attempt_cache[cache_key] = result
    return result


__all__ = [
    "GuardResult",
    "GuardSession",
    "ResolutionBlocker",
    "ResolutionFailure",
    "StalenessObservation",
    "guarded_read",
]
