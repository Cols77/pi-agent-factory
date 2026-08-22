"""Combined scope navigation dossier (docs server fast path).

One `coherence.navigate` invocation serves the whole scope-navigation payload
instead of the docs server firing one process per projection. Every section
is computed by the exact same `query_*` functions the individual CLI
subcommands use -- nothing here re-derives freshness, ordering, or
provenance, and no section is ever synthesized in TypeScript.

Section semantics mirror the browser's current per-endpoint contract
(design 2026-08-08 §6.1, 6.3):

* `brief`, `matrix`, `timeline` are the strict core -- any failure fails the
  dossier, exactly as a failing `/api/system/brief|matrix|timeline` response
  fails a scope load today;
* `guide` is best-effort: a failure degrades only the Guide tab
  (`guide: null` + `guide_error`), exactly as a failed guide endpoint
  degrades only that tab today;
* `vcycle` is computed only for `feat:`/`sr:` scopes and `validation` only
  for `sr:` scopes -- both best-effort, with the same degrade-only-the-tab
  semantics. For kinds that never carry them the keys are `null`, so the
  browser renders the same "Not applicable" affordance it renders today.
"""
from __future__ import annotations

from pathlib import Path

from coherence.navigate.cli import (
    cmd_brief,
    cmd_guide,
    cmd_matrix,
    cmd_timeline,
    cmd_validation,
    cmd_vcycle,
)
from coherence.navigate.queries import ScopeError


def _best_effort(fn):
    """Run one dossier section, degrading to `(None, error)` instead of raising.

    Only the exception classes the individual CLI subcommands already treat
    as structured errors degrade a section. Anything else is a real bug and
    propagates -- a degraded tab must never paper over one.
    """
    try:
        return fn(), None
    except (ScopeError, FileNotFoundError, ValueError) as exc:
        return None, str(exc)


def cmd_dossier(repo_root: Path, scope_raw: str) -> dict:
    """Assemble the full scope-navigation payload for one exact scope ref."""
    brief = cmd_brief(repo_root, scope_raw)
    scope = brief["scope"]
    matrix = cmd_matrix(repo_root, scope_raw)
    timeline = cmd_timeline(repo_root, scope_raw)

    guide, guide_error = _best_effort(lambda: cmd_guide(repo_root, scope_raw, None))

    vcycle = vcycle_error = None
    if scope["kind"] in ("feat", "sr"):
        vcycle, vcycle_error = _best_effort(lambda: cmd_vcycle(repo_root, scope_raw))

    validation = validation_error = None
    if scope["kind"] == "sr":
        validation, validation_error = _best_effort(lambda: cmd_validation(repo_root, scope_raw))

    # `scope` is read back from Python's own resolution (never from the raw
    # string) so the payload names the exact ref the projections resolved.
    return {
        "scope": scope,
        "brief": brief,
        "matrix": matrix,
        "timeline": timeline,
        "guide": guide,
        "guide_error": guide_error,
        "vcycle": vcycle,
        "vcycle_error": vcycle_error,
        "validation": validation,
        "validation_error": validation_error,
    }
