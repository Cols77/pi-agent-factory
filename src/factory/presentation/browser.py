"""SCC-browser presentation adapter (spec §22, D2/D7).

The System Control Center browser is the sole primary human surface. In Inc 5
the V-cycle / Feature Dossier / Goal pages land in Inc 6, so every browser
scope degrades deterministically to the scope's Brief page (``system?scope=…``,
the ``/system`` docs-server route). The one exception is ``diag:`` (D7): its
canonical committed diagram HTML (``docs/diagrams/…html``) is resolved and
returned as the target — the browser links it, never re-derives the graph.
"""
from __future__ import annotations

from pathlib import Path

from factory.system.queries import ScopeNotFoundError, query_diagram

#: Spec §22 present(artifact=…) -> human page, landed in Inc 6 (before that,
#: the router degrades to the scope's Brief page per D2).
_SCOPE_PAGE = {
    "sr": "V-cycle view",
    "feat": "Feature Dossier",
    "goal": "Goal status",
    "metric": "Metric detail",
    "adr": "ADR view",
    "task": "Task view",
    "bundle": "Bundle view",
}

_DIAGRAM_PAGE = "diagram viewer"


def _brief_target(scope_ref: str) -> str:
    """The artifacts' docs-server route fragment (scope-parameterized)."""
    return f"system?scope={scope_ref}"


def browser_target(scope_ref: str, page: str) -> dict:
    """Resolve a browser scope to a target + degrade note (Inc 6 page absent)."""
    return {
        "target": _brief_target(scope_ref),
        "note": (
            f"{page} lands in Inc 6; degrading to the scope's Brief page (D2)."
        ),
    }


def resolve_browser(repo_root: Path, kind: str, identifier: str, scope_ref: str) -> dict:
    """Resolve a non-diagram browser scope to a target (or degrade to Brief)."""
    page = _SCOPE_PAGE.get(kind, "scope view")
    return browser_target(scope_ref, page)


def resolve_diagram(repo_root: Path, diagram_id: str, scope_ref: str) -> dict:
    """Resolve ``diag:<id>`` to its canonical committed HTML (D7).

    Reuses ``query_diagram`` (the sole diagram-dispatch path in
    ``factory.system``) so the traversal / missing-file guards are shared, not
    forked. A missing or unbuildable diagram degrades to the scope's Brief page
    rather than erroring loudly (spec §23 degrade rule).
    """
    try:
        payload = query_diagram(repo_root, diagram_id)
    except ScopeNotFoundError as exc:
        return browser_target(scope_ref, _DIAGRAM_PAGE) | {
            "note": f"diagram {diagram_id!r} not declared ({exc}); degrading to Brief page."
        }
    path = payload.get("diagram_path")
    if path:
        return {
            "target": str(path),
            "note": f"{_DIAGRAM_PAGE}: canonical diagram HTML (D7).",
        }
    errors = "; ".join(payload.get("errors", []))
    return browser_target(scope_ref, _DIAGRAM_PAGE) | {
        "note": f"{_DIAGRAM_PAGE} HTML unavailable ({errors}); degrading to Brief page."
    }
