from __future__ import annotations

from collections.abc import Callable

import pytest

from substrate.artifacts import ProducerRef, SnapshotInputRef, SnapshotRef
from substrate.freshness.fingerprint import fingerprint_value
from substrate.freshness.guard import (
    GuardResult,
    GuardSession,
    ResolutionFailure,
    StalenessObservation,
    guarded_read,
)
from substrate.freshness.model import DependencyFingerprint
from substrate.freshness.recipes import (
    CompiledRecipes,
    FreshnessLimits,
    FreshnessRecipe,
    ResolutionClass,
    compile_recipes,
)


pytestmark = pytest.mark.unit


def make_recipe(
    resolution_class: ResolutionClass = ResolutionClass.derived_auto,
) -> FreshnessRecipe:
    return FreshnessRecipe(
        schema=1,
        output_kind="code-map",
        inputs=("source-set",),
        fingerprinter="source/v1",
        resolver="resolver/v1",
        resolution_class=resolution_class,
        limits=FreshnessLimits(attempts=1, timeout_s=1),
    )


def make_compiled(
    recipe: FreshnessRecipe,
    fingerprinter: Callable[[list[object]], object],
    resolver: Callable[[FreshnessRecipe, SnapshotRef], object],
) -> CompiledRecipes:
    return compile_recipes(
        [recipe],
        fingerprinters={recipe.fingerprinter: fingerprinter},
        resolvers={recipe.resolver: resolver},
    )


def make_snapshot(
    ref: str = "snapshot:old",
    fingerprint: str = "old-fingerprint",
    *,
    kind: str = "code-map",
    supersedes: str | None = None,
) -> SnapshotRef:
    return SnapshotRef(
        schema=1,
        kind=kind,
        ref=ref,
        fingerprint=fingerprint,
        producer=ProducerRef(name="test", version=1),
        inputs=(SnapshotInputRef(ref="artifact:source"),),
        generated_at="2026-08-20T00:00:00+00:00",
        supersedes=supersedes,
    )


def test_current_snapshot_returns_without_resolution() -> None:
    candidate = make_snapshot(fingerprint="current")
    resolver_calls: list[SnapshotRef] = []

    def fingerprinter(inputs: list[object]) -> str:
        assert inputs == ["input"]
        return "current"

    def resolver(recipe: FreshnessRecipe, snapshot: SnapshotRef) -> SnapshotRef:
        resolver_calls.append(snapshot)
        return snapshot

    result = guarded_read(
        GuardSession(),
        make_compiled(make_recipe(), fingerprinter, resolver),
        make_recipe(),
        candidate,
        ["input"],
    )

    assert result == GuardResult(snapshot=candidate)
    assert result.current
    assert result.stale is None
    assert result.blocker is None
    assert result.failure is None
    assert resolver_calls == []


@pytest.mark.parametrize(
    ("fingerprint_result", "expected"),
    [
        ("actual", "actual"),
        (DependencyFingerprint("source", "file", "actual", "source.txt"), "actual"),
        (
            [
                DependencyFingerprint("source", "file", "source-digest", "source.txt"),
                DependencyFingerprint("engine", "tool", "engine-digest", "parser"),
            ],
            fingerprint_value(
                "freshness-inputs", ["source-digest", "engine-digest"]
            ).digest,
        ),
    ],
)
def test_fingerprinter_results_are_normalized(
    fingerprint_result: object, expected: str
) -> None:
    candidate = make_snapshot(fingerprint="old")
    resolver_calls = 0

    def fingerprinter(inputs: list[object]) -> object:
        return fingerprint_result

    def resolver(recipe: FreshnessRecipe, snapshot: SnapshotRef) -> SnapshotRef:
        nonlocal resolver_calls
        resolver_calls += 1
        return make_snapshot(
            ref="snapshot:new",
            fingerprint=expected,
            supersedes=snapshot.ref,
        )

    recipe = make_recipe()
    result = guarded_read(
        GuardSession(),
        make_compiled(recipe, fingerprinter, resolver),
        recipe,
        candidate,
        [],
    )

    assert result.snapshot is not None
    assert result.snapshot.fingerprint == expected
    assert result.stale == StalenessObservation(
        candidate_ref=candidate.ref,
        output_kind=recipe.output_kind,
        expected_fingerprint=candidate.fingerprint,
        actual_fingerprint=expected,
    )
    assert resolver_calls == 1


def test_derived_auto_success_records_staleness_and_lineage() -> None:
    candidate = make_snapshot(fingerprint="old")
    recipe = make_recipe()
    resolver_calls: list[tuple[FreshnessRecipe, SnapshotRef]] = []
    replacement = make_snapshot(
        ref="snapshot:new",
        fingerprint="new",
        supersedes=candidate.ref,
    )

    def fingerprinter(inputs: list[object]) -> str:
        return "new"

    def resolver(received_recipe: FreshnessRecipe, snapshot: SnapshotRef) -> SnapshotRef:
        resolver_calls.append((received_recipe, snapshot))
        return replacement

    session = GuardSession()
    result = guarded_read(
        session,
        make_compiled(recipe, fingerprinter, resolver),
        recipe,
        candidate,
        ["input"],
    )

    assert result.snapshot is replacement
    assert result.current
    assert result.blocker is None
    assert result.failure is None
    assert resolver_calls == [(recipe, candidate)]
    assert result.stale == StalenessObservation(
        candidate_ref="snapshot:old",
        output_kind="code-map",
        expected_fingerprint="old",
        actual_fingerprint="new",
    )
    assert session.observations == [result.stale]


def test_repeated_successful_resolution_is_cached_by_exact_key() -> None:
    candidate = make_snapshot(fingerprint="old")
    recipe = make_recipe()
    resolver_calls = 0
    replacement = make_snapshot(
        ref="snapshot:new",
        fingerprint="new",
        supersedes=candidate.ref,
    )

    def fingerprinter(inputs: list[object]) -> str:
        return "new"

    def resolver(recipe: FreshnessRecipe, snapshot: SnapshotRef) -> SnapshotRef:
        nonlocal resolver_calls
        resolver_calls += 1
        return replacement

    compiled = make_compiled(recipe, fingerprinter, resolver)
    session = GuardSession()
    first = guarded_read(session, compiled, recipe, candidate, [])
    second = guarded_read(session, compiled, recipe, candidate, [])

    assert first is second
    assert resolver_calls == 1
    assert session.observations == [first.stale]


def test_repeated_failed_resolution_is_cached_by_exact_key() -> None:
    candidate = make_snapshot(fingerprint="old")
    recipe = make_recipe()
    resolver_calls = 0

    def fingerprinter(inputs: list[object]) -> str:
        return "new"

    def resolver(recipe: FreshnessRecipe, snapshot: SnapshotRef) -> SnapshotRef:
        nonlocal resolver_calls
        resolver_calls += 1
        raise RuntimeError("resolver exploded")

    compiled = make_compiled(recipe, fingerprinter, resolver)
    session = GuardSession()
    first = guarded_read(session, compiled, recipe, candidate, [])
    second = guarded_read(session, compiled, recipe, candidate, [])

    assert first is second
    assert first == GuardResult(
        snapshot=None,
        stale=first.stale,
        failure=ResolutionFailure(code="resolver_failed", reason="resolver exploded"),
    )
    assert not first.current
    assert resolver_calls == 1
    assert len(session.observations) == 1


@pytest.mark.parametrize(
    ("resolution_class", "action"),
    [
        (ResolutionClass.repeatable_policy, "policy-review"),
        (ResolutionClass.authoritative_gate, "authoritative-writer"),
        (ResolutionClass.provenance_blocked, "provenance-recovery"),
    ],
)
def test_non_automatic_classes_block_without_resolver(
    resolution_class: ResolutionClass, action: str
) -> None:
    candidate = make_snapshot(fingerprint="old")
    recipe = make_recipe(resolution_class)
    resolver_calls = 0

    def fingerprinter(inputs: list[object]) -> str:
        return "new"

    def resolver(recipe: FreshnessRecipe, snapshot: SnapshotRef) -> SnapshotRef:
        nonlocal resolver_calls
        resolver_calls += 1
        raise AssertionError("blockers must not invoke the resolver")

    result = guarded_read(
        GuardSession(),
        make_compiled(recipe, fingerprinter, resolver),
        recipe,
        candidate,
        [],
    )

    assert result.snapshot is None
    assert result.failure is None
    assert result.blocker is not None
    assert result.blocker.resolution_class is resolution_class
    assert result.blocker.action == action
    assert result.blocker.reason
    assert result.stale is not None
    assert resolver_calls == 0


def test_invalid_replacement_is_not_current() -> None:
    candidate = make_snapshot(fingerprint="old")
    recipe = make_recipe()

    def fingerprinter(inputs: list[object]) -> str:
        return "new"

    def resolver(recipe: FreshnessRecipe, snapshot: SnapshotRef) -> SnapshotRef:
        return make_snapshot(
            ref="snapshot:new",
            fingerprint="new",
            kind="wrong-kind",
            supersedes=snapshot.ref,
        )

    result = guarded_read(
        GuardSession(),
        make_compiled(recipe, fingerprinter, resolver),
        recipe,
        candidate,
        [],
    )

    assert result.snapshot is None
    assert result.failure == ResolutionFailure(
        code="invalid_replacement",
        reason="replacement kind or supersedes lineage is invalid",
    )
    assert not result.current


def test_stale_replacement_is_not_current() -> None:
    candidate = make_snapshot(fingerprint="old")
    recipe = make_recipe()

    def fingerprinter(inputs: list[object]) -> str:
        return "new"

    def resolver(recipe: FreshnessRecipe, snapshot: SnapshotRef) -> SnapshotRef:
        return make_snapshot(
            ref="snapshot:new",
            fingerprint="still-old",
            supersedes=snapshot.ref,
        )

    result = guarded_read(
        GuardSession(),
        make_compiled(recipe, fingerprinter, resolver),
        recipe,
        candidate,
        [],
    )

    assert result.snapshot is None
    assert result.failure == ResolutionFailure(
        code="stale_replacement",
        reason="replacement fingerprint does not match current inputs",
    )
    assert not result.current
