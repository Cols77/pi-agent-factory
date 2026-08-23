"""Resolve an artifact's effective profile through the trace graph, and
compile the Obligation set for it. This lives in `coherence`, not `substrate`,
because it needs `coherence.trace.model` to find an SR's owning feature --
substrate stays pure and repo-root-only (mirrors how `coherence.navigate.health`
composes `coherence.trace` + substrate loaders without substrate depending
back on coherence).
"""
from __future__ import annotations

from pathlib import Path

from coherence.trace import model as trace_model
from substrate.policy.obligation import Obligation
from substrate.policy.vocabulary import (
    COMPILED_PRESETS,
    UncompiledPresetError,
    artifact_profile_override,
    path_override_profile,
    project_default_profile,
)


class UnsupportedScopeError(ValueError):
    """The scope is not `project` and is not a supported, existing trace artifact."""


def resolve_profile(
    root: Path,
    scope_ref: str = "project",
    *,
    nodes: list[trace_model.Node] | None = None,
    edges: list[trace_model.Edge] | None = None,
) -> str:
    """Effective preset for scope_ref. Precedence: artifact/requirement >
    feature/bundle > path/component > project default. Raises
    UncompiledPresetError if the resolved preset is not in COMPILED_PRESETS.

    `nodes=`/`edges=` mirror `coherence.navigate.health`'s own passthrough
    pattern: a caller that already loaded the trace graph (e.g. Increment 5's
    per-SR health loop) supplies them so this never reloads per call.
    """
    if scope_ref == "project":
        profile = project_default_profile(root)
    else:
        if nodes is None:
            nodes = trace_model.load_nodes(root)
        by_id = {n.id: n for n in nodes}
        scope_kind, separator, artifact_id = scope_ref.partition(":")
        if not separator or not scope_kind or not artifact_id:
            raise UnsupportedScopeError(
                f"{scope_ref!r}: only `project` or a kind:id artifact scope is supported"
            )
        # Trace nodes use both bare artifact IDs (for SR/task files) and
        # kind-prefixed IDs (for plan/spec files), so accept either exact form
        # but require the prefix to agree with the loaded node's kind.
        node = by_id.get(scope_ref) or by_id.get(artifact_id)
        if node is None or node.kind != scope_kind:
            raise UnsupportedScopeError(
                f"{scope_ref!r}: unknown or unsupported trace artifact scope"
            )
        profile = artifact_profile_override(node.path)
        if profile is None and node.kind == "sr":
            if edges is None:
                edges = trace_model.extract_edges(root, nodes)
            owning_feature = next(
                (by_id.get(e.src) for e in edges if e.kind == "contains" and e.dst == node.id),
                None,
            )
            if owning_feature is not None:
                profile = artifact_profile_override(owning_feature.path)
        if profile is None:
            rel = str(node.path.relative_to(root)).replace("\\", "/")
            profile = path_override_profile(root, rel)
        if profile is None:
            # This fallback is intentionally limited to a known artifact that
            # has no narrower override; `scope_ref="project"` is handled above.
            profile = project_default_profile(root)
    if profile not in COMPILED_PRESETS:
        raise UncompiledPresetError(
            f"{scope_ref}: profile {profile!r} is not yet compiled (compiled presets: {COMPILED_PRESETS})"
        )
    return profile


def compile_obligations(
    root: Path,
    scope_ref: str = "project",
    *,
    nodes: list[trace_model.Node] | None = None,
    edges: list[trace_model.Edge] | None = None,
) -> list[Obligation]:
    """Every default preset compiles a blocking ci_verification obligation (D18)
    -- CI (Increment 2C) reads this, never a hand-maintained step list. A
    `task:*` scope additionally compiles task_justification. Increment 4 and
    Increment 6 extend this SAME function with verification_result and
    human_review respectively (see those plans' addenda) -- each new kind is
    appended to the branch for the scope kind it applies to, never a parallel
    compiler. `nodes=`/`edges=` pass straight through to `resolve_profile`.
    """
    profile = resolve_profile(root, scope_ref, nodes=nodes, edges=edges)
    obligations = [_ci_verification_obligation(root, scope_ref, profile)]
    if scope_ref.startswith("task:"):
        obligations.append(_task_justification_obligation(root, scope_ref, profile))
    return obligations


def _ci_verification_obligation(root: Path, scope_ref: str, profile: str) -> Obligation:
    """Reuses `factory.config.load_config` (already parses `.factory/factory.yaml`
    into `FactoryConfig.gates`, layering-legal here since `coherence` may
    import `factory`) instead of re-parsing the YAML a second time, and reuses
    `factory.orchestrator.backends`'s own `{python}` substitution
    (`_target_python`/`_quote_for_shell`) instead of joining raw `step.cmd`
    strings -- spec §13's first corrected decision: one substitution rule,
    not two. Both are imported locally, matching this file's existing style
    for `factory`-layer imports (`_task_justification_obligation` below
    already imports `substrate.ledger.tasks` locally the same way), so every
    cross-layer dependency stays visible at its call site.
    """
    from factory.config import load_config
    from factory.orchestrator.backends import _quote_for_shell, _target_python

    gates = load_config(root).gates
    python = _quote_for_shell(_target_python(root))
    cmds = tuple(
        step.cmd.replace("{python}", python) for steps in gates.values() for step in steps
    )
    return Obligation(
        id=f"ob:ci_verification:{scope_ref}",
        scope_ref=scope_ref,
        kind="ci_verification",
        requiredness="blocking",
        reason=f"every default preset ({profile}) requires CI-verified gates (D18)",
        source_policy=profile,
        state="open",
        resolve_cmd=cmds or None,
    )


def _task_justification_obligation(root: Path, scope_ref: str, profile: str) -> Obligation:
    from substrate.ledger.tasks import get_task, load_tasks

    task_id = scope_ref.partition(":")[2]
    task = get_task(load_tasks(root / "tasks"), task_id)
    has_justification = bool(task and task.justification)
    requiredness = "blocking" if profile == "high_assurance" else "advisory"
    return Obligation(
        id=f"ob:task_justification:{scope_ref}",
        scope_ref=scope_ref,
        kind="task_justification",
        requiredness=requiredness,
        reason=(
            f"{profile} requires every task to name a typed justification "
            "(satisfies/corrects/mitigates/implements/maintains/explores)"
        ),
        source_policy=profile,
        state="satisfied" if has_justification else "open",
        resolve_cmd=("add a `justification:` entry to the task's frontmatter",),
    )
