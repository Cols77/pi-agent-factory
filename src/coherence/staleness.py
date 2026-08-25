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
from pathlib import Path

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


def _suspect_edge_items(root: Path) -> list[UnresolvedStaleness]:
    """Sweep the trace graph for governed edges classified suspect/invalid/waived
    by `edge_validity` (Increment 6 Task 6 Step 4).

    Deterministic, read-only: builds the graph and classifies each SR's gap
    set. Per the spec's §13 amendment row 3 (STRICT), no path back to `valid`
    exists automatically at any requiredness level, so each non-`valid` edge
    is reported as an authoritative gate carrying the one policy-authorized
    restore action -- a human DecisionFile `accept`. This never executes a
    resolver.
    """
    from coherence.trace.graph import build_graph
    from coherence.trace.suspect import edge_validity

    graph = build_graph(root)
    gaps_by_node: dict[str, list] = {}
    for gap in graph.gaps:
        gaps_by_node.setdefault(gap.node_id, []).append(gap)

    findings: list[UnresolvedStaleness] = []
    for node in graph.nodes:
        if node.kind != "sr":
            continue
        gaps = gaps_by_node.get(node.id, [])
        state = edge_validity(gaps)
        if state not in (
            "suspect",
            "invalid",
            "waived",
        ):
            continue
        findings.append(
            UnresolvedStaleness(
                ref=f"sr:{node.id}",
                resolution_class=ResolutionClass.authoritative_gate,
                reason=(
                    f"edge {node.id} is {state}: restoring `valid` requires a "
                    "human DecisionFile accept, not an automatic transition"
                ),
                resolve_cmd=(f"accept {node.id}",),
            )
        )
    return findings


def unresolved_staleness(root: Path | str | None = None, *, now: str = "") -> list[UnresolvedStaleness]:
    """Sweep the trace graph for governed SR edges classified suspect/invalid/
    waived by `edge_validity` and report each as a blocking authoritative gate
    (`ResolutionBlocker` equivalent).

    Pure read: never executes a resolver, never writes a decision file. The
    inbox reads this sweep. With no runnable root (or a root with no
    requirements dir) it returns an empty list, so callers have a stable
    export target.
    """
    root_path = Path(root) if root else None
    if root_path is None or not (root_path / "requirements").is_dir():
        return []
    return _suspect_edge_items(root_path)


__all__ = ["Routing", "UnresolvedStaleness", "route", "unresolved_staleness"]