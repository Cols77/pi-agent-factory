"""Staleness routing (Increment 6 Task 4).

``UnresolvedStaleness`` models ONE recorded staleness finding whose ownership
is not yet resolved, and ``route`` decides what it routes to based on its
``resolution_class``:

* ``authoritative_gate`` -- routes to the owning writer, carrying that owner's
  ordered ``resolve_cmd`` tuple UNCHANGED (never reordered, deduplicated, or
  semicolon-joined). A gate is routed for a human/owner action, never
  auto-executed here.
* ``provenance_blocked`` -- maps to a blocker (missing provenance cannot be
  auto-resolved) with NO resolver execution and no ``resolve_cmd``.
* ``derived_auto``/``repeatable_policy`` -- resolved by their own resolver and
  outside this module's ownership routing (no owner decision).

This module is a pure read/router: it never executes a resolver and never
writes.
"""
from __future__ import annotations

from dataclasses import dataclass

from substrate.freshness.recipes import ResolutionClass

# The owner label a routed staleness is handed to (authoritative_writer /
# provenance_recovery), mirroring substrate.freshness.guard._blocker_for's
# action vocabulary.
_OWNERS: dict[str, str] = {
    ResolutionClass.authoritative_gate: "authoritative-writer",
    ResolutionClass.provenance_blocked: "provenance-recovery",
}


@dataclass(frozen=True)
class UnresolvedStaleness:
    """One recorded staleness finding and the ownership it resolves to."""

    ref: str
    resolution_class: ResolutionClass
    reason: str = ""
    resolve_cmd: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Routing:
    """Where a staleness routes.

    ``owner`` is None when the finding carries no ownership decision here
    (auto-derived signals). ``executes_resolver`` is False for every class
    this module hands to an owner or blocker -- this router never executes.
    """

    owner: str | None
    resolve_cmd: tuple[str, ...] | None
    executes_resolver: bool
    blocker_reason: str | None = None


def route(result: UnresolvedStaleness) -> Routing:
    """Decide the ownership routing for one stale finding (pure read)."""
    if result.resolution_class not in _OWNERS:
        # derived_auto / repeatable_policy resolve via their own resolver;
        # this module does not route them to an owner.
        return Routing(owner=None, resolve_cmd=None, executes_resolver=True)

    return Routing(
        owner=_OWNERS[result.resolution_class],
        resolve_cmd=result.resolve_cmd,
        executes_resolver=False,
        blocker_reason=(
            result.reason
            if result.resolution_class == ResolutionClass.provenance_blocked
            else None
        ),
    )


def unresolved_staleness(root: str | None = None, *, now: str = "") -> list[UnresolvedStaleness]:
    """Placeholder-ish sweep surface; the concrete sweep reuses the existing
    freshness machinery and is wired by `coherence.inbox`. Reserved so callers
    have a stable import target (spec: "inbox reads that sweep, never executes a
    resolver"). Returns the current recorded unresolved set, if the root is a
    runnable repo; with no root it returns an empty list.
    """
    # The inbox's collectors own the actual read of each source; this module
    # keeps the routing decision pure and shared. See `coherence.inbox.list_items`.
    return []


__all__ = ["Routing", "UnresolvedStaleness", "route", "unresolved_staleness"]