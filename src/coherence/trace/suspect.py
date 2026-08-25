"""Classify a gap SET into the five-state edge-validity vocabulary.

Spec section 4 semantics, made deterministic: computing code only ever
DOWNGRADES from an assumed `valid` baseline (to `suspect`/`invalid`), or
records an explicit `waived` disposition when every gap was deferred or
exempted by policy. Restoring `valid` after a downgrade or waiver is a
policy-authorized HUMAN action -- a DecisionFile accept (later increment) --
never computed here. No requiredness level relaxes that rule (spec section
13 amendment, row 3, STRICT reading): a `blocking` obligation elsewhere can
force an edge invalid, but that still goes through the same vocabulary and
must likewise be restored by a human accept, never by code.

The five states and when `edge_validity` returns them:
- `proposed`  -- a new edge whose gaps are neither clearly disqualifying
                 nor fully waived;
- `valid`     -- no gaps, and no recorded prior state to preserve;
- `suspect`   -- a pending staleness (or other non-fatal) gap;
- `invalid`   -- a pending fatal gap (unsatisfied / unvalidated /
                 unvalidatable);
- `waived`    -- every gap on the edge was deferred or exempted.

The unit tests drive this through a `_FakeGap`, so the module imports the
real `Gap` type only at type-check time (`TYPE_CHECKING`); there is no hard
runtime dependency on `coherence.trace.gaps`.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # never imported at runtime -- tests use _FakeGap
    from coherence.trace.gaps import Gap

ValidityState = Literal["proposed", "valid", "suspect", "invalid", "waived"]

# Kinds that, pending, make an edge's satisfaction claim untrusted -> invalid.
_INVALID_GAP_KINDS = ("sr_unsatisfied", "sr_unvalidated", "sr_unvalidatable")
# Kinds that are non-fatal but signal decay -> suspect.
_SUSPECT_GAP_KINDS = ("sr_stale",)
# Dispositions that, applied to EVERY gap, record an explicit waiver.
_WAIVER_DISPOSITIONS = ("deferred", "exempt")


def edge_validity(
    gaps_for_edge: list[Gap], *, prior_state: ValidityState | None = None
) -> ValidityState:
    """Classify one edge's gap set into the five-state vocabulary.

    An empty set returns the recorded ``prior_state`` if one exists, else
    ``"valid"`` (assumed baseline). A non-empty set is scored from its
    ``pending`` gaps: any fatal kind -> ``invalid``, any suspect kind ->
    ``suspect``; if every gap carries a waiver disposition the edge is
    ``"waived"``; otherwise there is some pending gap we cannot yet rule on,
    so it is ``"proposed"``.
    """
    if not gaps_for_edge:
        return prior_state if prior_state is not None else "valid"

    pending = [g for g in gaps_for_edge if g.disposition == "pending"]
    if any(g.kind in _INVALID_GAP_KINDS for g in pending):
        return "invalid"
    if any(g.kind in _SUSPECT_GAP_KINDS for g in pending):
        return "suspect"
    if all(g.disposition in _WAIVER_DISPOSITIONS for g in gaps_for_edge):
        return "waived"
    return "proposed"


def _scope_sr_ids(scope: list[str]) -> list[str]:
    """Extract the `sr:<id>` refs from a baseline `scope` list."""
    return [s.partition(":")[2] for s in (scope or []) if s.startswith("sr:")]


def expired_baselines(root: Path) -> list[str]:
    """Return baseline ids whose scope contains an SR now suspect or invalid
    (Increment 6 Task 7 Step 3).

    A baseline pins a snapshot over accepted requirements; when one of the SRs
    it covers has since decayed to `suspect`/`invalid` via `edge_validity`, the
    snapshot is stale -- reported here by baseline id. This is a QUERY, never an
    auto-transition: closing an expired baseline is a human decision recorded
    the same way any other gate-protocol decision is (DecisionFile accept), and
    this function mutates nothing (tests assert the repo is unchanged).
    """
    from coherence.trace.graph import build_graph

    try:
        graph = build_graph(root)
    except Exception:
        return []
    gaps_by_node: dict[str, list] = {}
    for gap in graph.gaps:
        gaps_by_node.setdefault(gap.node_id, []).append(gap)

    suspect_or_invalid: set[str] = set()
    for node in graph.nodes:
        if node.kind != "sr":
            continue
        state = edge_validity(gaps_by_node.get(node.id, []))
        if state in ("suspect", "invalid"):
            suspect_or_invalid.add(node.id)

    from factory.memory.baseline import load_baselines

    expired: list[str] = []
    for baseline_id, baseline in sorted(load_baselines(root).items()):
        if any(sr in suspect_or_invalid for sr in _scope_sr_ids(baseline.scope)):
            expired.append(baseline_id)
    return expired