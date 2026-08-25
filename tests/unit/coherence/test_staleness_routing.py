"""Staleness routing (Increment 6 Task 4).

`route` decides, for a recorded staleness finding's resolution class, whether
it goes to an owning writer (carrying that owner's ordered `resolve_cmd` tuple
unchanged) or to a blocker that must NOT execute a resolver -- matching the
spec: authoritative_gate -> owning resolve_cmd tuple unchanged;
provenance_blocked -> blocker without resolver execution. `unresolved_staleness`
reuses the existing freshness machinery to surface recorded staleness.
"""
from __future__ import annotations

import pytest

from coherence.staleness import UnresolvedStaleness, route
from substrate.freshness.recipes import ResolutionClass

pytestmark = pytest.mark.unit

OWNER_RESCUE_CMDS = (
    "coherence register rebind SR-001 --repo-root .",
    "coherence trace check --project-root .",
)


def _result(resolution_class, reason="stale", resolve_cmd=OWNER_RESCUE_CMDS):
    return UnresolvedStaleness(
        ref="sr:SR-001",
        resolution_class=resolution_class,
        reason=reason,
        resolve_cmd=resolve_cmd,
    )


def test_authoritative_gate_maps_to_owning_resolve_cmd_unchanged():
    # A staleness that is an authoritative gate must route to its owning
    # writer with the SAME ordered resolve_cmd tuple -- not reordered,
    # deduplicated, or a semicolon-joined string.
    out = route(_result(ResolutionClass.authoritative_gate))
    assert out.owner == "authoritative-writer"
    assert out.resolve_cmd == OWNER_RESCUE_CMDS
    assert list(out.resolve_cmd) == [
        "coherence register rebind SR-001 --repo-root .",
        "coherence trace check --project-root .",
    ]
    # A gate routes to its owning writer; it does not auto-execute a resolver.
    assert out.executes_resolver is False


def test_authoritative_gate_with_none_resolve_cmd_stays_none():
    out = route(_result(ResolutionClass.authoritative_gate, resolve_cmd=None))
    assert out.owner == "authoritative-writer"
    assert out.resolve_cmd is None
    assert out.executes_resolver is False


def test_provenance_blocked_maps_to_blocker_without_resolver_execution():
    # provenance_blocked cannot be auto-resolved (missing provenance): it maps
    # to a blocker and never executes a resolver, and carries no resolve_cmd.
    out = route(
        _result(
            ResolutionClass.provenance_blocked,
            reason="no recorded fingerprint",
            resolve_cmd=None,
        )
    )
    assert out.owner == "provenance-recovery"
    assert out.blocker_reason == "no recorded fingerprint"
    assert out.resolve_cmd is None
    assert out.executes_resolver is False


def test_derived_auto_is_not_handled_as_a_blocker_or_owner():
    # Only the named resolution classes get a routing decision here; an
    # auto-derived signal is resolved by its own resolver and is outside this
    # module's ownership routing.
    out = route(_result(ResolutionClass.derived_auto))
    assert out.owner is None
    assert out.executes_resolver is True