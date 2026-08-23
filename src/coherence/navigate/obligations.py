"""Obligation-aware navigator view: effective profile and compiled obligations
for a scope, plus a plain-words explanation for any one obligation. Composes
`coherence.policy.compiler` only for the actual profile/obligation resolution
-- it never recomputes that logic itself. It also loads the trace graph
(`coherence.trace.model`) once per call and passes it through to
`resolve_profile`/`compile_obligations` via their `nodes=`/`edges=` params,
since both would otherwise reload the same graph independently (each
non-project scope call would load twice inside `effective_profile_view`
alone, and callers like `cmd_goal_show`/`cmd_sim_run` are hit on every
docs-server page load through `coherence.navigate.worker`).
"""
from __future__ import annotations

from pathlib import Path

from coherence.policy.compiler import compile_obligations, resolve_profile
from coherence.trace import model as trace_model
from coherence.navigate.queries import ScopeKindError
from substrate.policy.obligation import Obligation
from substrate.policy.vocabulary import (
    InvalidProfileError,
    ProfileConflictError,
    UncompiledPresetError,
)

#: Artifact kinds that resolve to a real trace-node policy scope. Narrower
#: than router.py's `_BROWSER_KINDS` (bundle/adr/metric are browser-navigable
#: but `coherence.trace.model.load_nodes` never loads them as lookup-by-id
#: trace nodes, so 2B's `resolve_profile` can never resolve them to anything
#: but the project default) -- see Task 1 docstring on `present_obligations`.
_WHY_REQUIRED_KINDS = ("sr", "task", "feat", "goal")

# 2B's compiler currently compiles a project-level obligation for any string
# that reaches it, then falls back to the project profile when no node exists.
# This adapter must validate the scope before calling it, so unknown goal ids
# and unsupported kinds cannot inherit project obligations. `run:` is kept
# separate because load_nodes currently exposes no run nodes; 3B reports it as
# explicitly unsupported rather than treating it as a declared scope.
_POLICY_SCOPE_KINDS = ("sr", "task", "feat", "goal")
_UNSUPPORTED_POLICY_SCOPE_KINDS = ("run",)
_NO_DECLARED_SCOPE = "no declared policy scope"

#: `ci_verification` is compiled unconditionally for every scope (2B D18);
#: excluding it here is what makes `obligations_open_count` mean something
#: scope-specific rather than a structural always->=1 (review finding #3).
_PROJECT_LEVEL_KINDS = ("ci_verification",)

_OPEN_SEVERITIES = ("blocking", "required")

# The compiler's list order is an implementation detail. Keep the view order
# fixed as later increments append verification_result/human_review, and sort
# unknown future kinds deterministically after the known kinds.
_OBLIGATION_KIND_ORDER = (
    "ci_verification",
    "task_justification",
    "verification_result",
    "human_review",
)


def _obligation_dict(o: Obligation) -> dict:
    return {
        "id": o.id,
        "scope_ref": o.scope_ref,
        "kind": o.kind,
        "requiredness": o.requiredness,
        "reason": o.reason,
        "source_policy": o.source_policy,
        "state": o.state,
        "resolve_cmd": o.resolve_cmd,
    }


def _obligation_sort_key(o: Obligation) -> tuple[int, str, str, str]:
    rank = _OBLIGATION_KIND_ORDER.index(o.kind) if o.kind in _OBLIGATION_KIND_ORDER else len(_OBLIGATION_KIND_ORDER)
    return rank, o.kind, o.scope_ref, o.id


def _declared_policy_scope(root: Path, scope_ref: str) -> bool:
    kind, separator, identifier = scope_ref.partition(":")
    if not separator or not identifier or kind not in _POLICY_SCOPE_KINDS:
        return False
    nodes = trace_model.load_nodes(root)
    return any(node.kind == kind and node.id == identifier for node in nodes)


def _require_declared_policy_scope(root: Path, scope_ref: str) -> None:
    if scope_ref == "project":
        return
    kind = scope_ref.partition(":")[0]
    if kind in _UNSUPPORTED_POLICY_SCOPE_KINDS:
        raise ScopeKindError(
            f"policy scope unsupported for {scope_ref!r}: load_nodes exposes no run nodes"
        )
    if not _declared_policy_scope(root, scope_ref):
        raise ScopeKindError(f"{_NO_DECLARED_SCOPE} for {scope_ref!r}")


def _compile(root: Path, scope_ref: str) -> list[Obligation]:
    _require_declared_policy_scope(root, scope_ref)
    nodes = None
    edges = None
    if scope_ref != "project":
        nodes = trace_model.load_nodes(root)
        edges = trace_model.extract_edges(root, nodes)
    # resolve_profile is still called once more inside compile_obligations
    # (2B's own internal contract) -- passing nodes/edges through means that
    # second call reuses the graph already loaded here rather than reloading
    # it, which is the actual redundant cost this avoids.
    return sorted(
        compile_obligations(root, scope_ref, nodes=nodes, edges=edges),
        key=_obligation_sort_key,
    )


def effective_profile_view(root: Path, scope_ref: str = "project") -> dict:
    _require_declared_policy_scope(root, scope_ref)
    nodes = None
    edges = None
    if scope_ref != "project":
        nodes = trace_model.load_nodes(root)
        edges = trace_model.extract_edges(root, nodes)
    profile = resolve_profile(root, scope_ref, nodes=nodes, edges=edges)
    obligations = sorted(
        compile_obligations(root, scope_ref, nodes=nodes, edges=edges),
        key=_obligation_sort_key,
    )
    return {
        "scope_ref": scope_ref,
        "profile": profile,
        "obligations": [_obligation_dict(o) for o in obligations],
    }


def why_required(
    root: Path,
    obligation_id: str,
    scope_ref: str = "project",
    *,
    obligations: list[Obligation] | None = None,
) -> str | None:
    compiled = obligations if obligations is not None else _compile(root, scope_ref)
    for obligation in compiled:
        if obligation.id == obligation_id:
            return (
                f"{obligation.reason} "
                f"(source_policy={obligation.source_policy}, requiredness={obligation.requiredness})"
            )
    return None


def obligations_open_count(
    root: Path,
    scope_ref: str,
    *,
    exclude_kinds: tuple[str, ...] = _PROJECT_LEVEL_KINDS,
) -> tuple[int, str | None]:
    """Count open, required-or-blocking obligations meaningfully scoped to
    `scope_ref`. Returns `(count, error)`; `error` is set (count is 0) only
    when the scope's profile could not be resolved at all -- see module
    docstring / Task 1 Interfaces for why this is not folded into `count`.
    """
    try:
        obligations = _compile(root, scope_ref)
    except (ScopeKindError, InvalidProfileError, ProfileConflictError, UncompiledPresetError) as exc:
        return 0, str(exc)
    count = sum(
        1
        for o in obligations
        if o.kind not in exclude_kinds and o.requiredness in _OPEN_SEVERITIES and o.state == "open"
    )
    return count, None


def present_obligations(root: Path, scope_ref: str) -> dict:
    """Obligations + why-required explanations for a `present --why-required`
    call. Shared by `coherence.navigate.cli.cmd_present` and
    `coherence.presentation.cli.main` (Tasks 2 and 4) -- one implementation,
    two thin call sites.
    """
    kind = scope_ref.partition(":")[0]
    if kind not in _WHY_REQUIRED_KINDS:
        return {"obligations": None, "obligations_note": "no policy scope for this artifact kind"}
    if not _declared_policy_scope(root, scope_ref):
        return {"obligations": None, "obligations_note": _NO_DECLARED_SCOPE}
    try:
        compiled = _compile(root, scope_ref)
    except (InvalidProfileError, ProfileConflictError, UncompiledPresetError) as exc:
        return {"obligations": [], "obligations_error": str(exc)}
    obligations = [_obligation_dict(o) for o in compiled]
    for ob, o in zip(obligations, compiled):
        if o.requiredness in _OPEN_SEVERITIES:
            ob["why"] = why_required(root, o.id, scope_ref, obligations=compiled)
    return {"obligations": obligations}
