"""Freshness integration for `/catchup` (Inc 7 Task 5k).

Extends the deterministic ``ContextDelta`` with engineering invalidation and
repair, not only repository changes. The delta's changed refs (changed
requirements + changed code files) are fed through the freshness dependency
graph (``factory.freshness.deps.compute_impact``), the affected closure is
classified as ``invalidated``, and a bounded refresh pass
(``factory.freshness.policy.reconcile``) runs where safe/registered and is
*verified* by fingerprints -- an action that ran is never assumed to have
fixed anything.

All fields are deterministic and read recorded sources only; narrative
explanation may be generated separately but may not contradict them.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from factory.delta.compute import ContextDelta
from factory.freshness.deps import compute_impact
from factory.freshness.policy import reconcile


def apply_freshness(root: Path, delta: ContextDelta) -> ContextDelta:
    """Fill the delta's invalidation/refresh/closure fields (5k)."""
    changed_refs = [f"sr:{req}" for req in delta.requirements_changed]
    changed_refs += [f"code:{path}" for path in delta.code_files_changed]

    if not changed_refs:
        return replace(delta, invalidated=[], auto_refreshed=[], refresh_required=[], blocked_refreshes=[], freshness_closure_reached=True)

    impact = compute_impact(root, changed_refs)
    invalidated = sorted(set(impact.directly_affected) | set(impact.transitively_affected))

    result = reconcile(root, invalidated)
    return replace(
        delta,
        invalidated=invalidated,
        auto_refreshed=list(result.refreshed),
        refresh_required=list(result.still_stale),
        blocked_refreshes=list(result.blocked),
        freshness_closure_reached=result.closure_reached,
    )
