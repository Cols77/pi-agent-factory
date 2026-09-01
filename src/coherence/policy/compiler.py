"""Resolve an artifact's effective profile through the trace graph, and
compile the Obligation set for it. This lives in `coherence`, not `substrate`,
because it needs `coherence.trace.model` to find an SR's owning feature --
substrate stays pure and repo-root-only (mirrors how `coherence.navigate.health`
composes `coherence.trace` + substrate loaders without substrate depending
back on coherence).
"""
from __future__ import annotations

import stat
from pathlib import Path, PureWindowsPath

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
    `task:*` scope additionally compiles task_justification; a `sr:*` scope
    additionally compiles verification_result (Increment 4 addendum).
    Increment 6 extends this SAME function with human_review (see that plan's
    addendum) -- each new kind is appended to the branch for the scope kind
    it applies to, never a parallel compiler. For a non-`project` scope,
    `nodes`/`edges` are loaded at most once here (when the caller did not
    already supply them) and the same objects are forwarded to
    `resolve_profile` and to every obligation helper that accepts them.
    """
    if scope_ref != "project":
        if nodes is None:
            nodes = trace_model.load_nodes(root)
        if scope_ref.startswith("sr:"):
            sr_id = scope_ref.partition(":")[2]
            if _has_duplicate_sr_declarations(root, sr_id, nodes):
                return _ambiguous_sr_obligations(scope_ref)
        if edges is None:
            edges = trace_model.extract_edges(root, nodes)
    profile = resolve_profile(root, scope_ref, nodes=nodes, edges=edges)
    obligations = [_ci_verification_obligation(root, scope_ref, profile)]
    if scope_ref.startswith("task:"):
        obligations.append(_task_justification_obligation(root, scope_ref, profile))
    elif scope_ref.startswith("sr:"):
        obligations.append(
            _verification_result_obligation(root, scope_ref, profile, nodes=nodes, edges=edges)
        )
        obligations.append(
            _human_review_obligation(root, scope_ref, profile, nodes=nodes, edges=edges)
        )
        obligations.append(_test_marker_obligation(root, scope_ref, profile))
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


def _sr_node_path(sr_id: str, *, nodes) -> Path | None:
    """Resolve an SR's actual file from preloaded trace nodes.

    Match by node kind and frontmatter id; never guess ``requirements/<sr_id>.md``.
    The caller owns graph loading; this helper never reloads nodes.
    """
    node = next((n for n in nodes if n.kind == "sr" and n.id == sr_id), None)
    return node.path if node is not None else None


def _has_duplicate_sr_declarations(root: Path, sr_id: str, nodes) -> bool:
    """Detect duplicate SR declarations before any profile/map lookup.

    The trace loader and register loader intentionally return lists so this
    check does not collapse same-id declarations into a dict. They are two
    views of the requirement source, so a duplicate in either view is enough.
    """
    trace_matches = [node for node in nodes if node.kind == "sr" and node.id == sr_id]
    if len(trace_matches) > 1:
        return True

    from coherence.register import register as register_module

    registered = register_module.load_register(root / "requirements")
    return sum(req.id == sr_id for req in registered) > 1


def _ambiguous_sr_obligations(scope_ref: str) -> list[Obligation]:
    sr_id = scope_ref.partition(":")[2]
    reason = f"{sr_id} has duplicate SR declarations; source is ambiguous"
    resolve_cmd = (f"remove duplicate requirement registrations for {sr_id}",)
    return [
        Obligation(
            id=f"ob:{kind}:{scope_ref}",
            scope_ref=scope_ref,
            kind=kind,
            requiredness="blocking",
            reason=reason,
            source_policy="ambiguous",
            state="open",
            resolve_cmd=resolve_cmd,
        )
        for kind in (
            "ci_verification",
            "verification_result",
            "human_review",
            "test_marker",
        )
    ]


def _verification_result_obligation(
    root: Path, scope_ref: str, profile: str, *, nodes, edges,
) -> Obligation:
    from coherence.register import register as register_module
    from coherence.trace.validation_status import load_validation

    sr_id = scope_ref.partition(":")[2]
    sr_path = _sr_node_path(sr_id, nodes=nodes)
    status = load_validation(root).get(sr_id)
    passed = status is not None and status.state == "passed" and not status.stale
    reason_extra = None
    if passed and profile == "high_assurance":
        # guide §5.3: this addendum checks only a declared harness. Whether
        # human-review identity is part of this obligation or human_review is
        # intentionally unresolved; do not read either proposed field name.
        register = {r.id: r for r in register_module.load_register(root / "requirements")}
        req = register.get(sr_id)
        if req is None or req.binding is None or req.binding.harness is None:
            passed, reason_extra = False, "binding declares no harness"
    requiredness = "blocking" if profile == "high_assurance" else "required"
    reason = reason_extra or (
        "harness-validated result recorded" if passed
        else "no passing, non-stale validation result recorded"
    )
    return Obligation(
        id=f"ob:verification_result:{scope_ref}",
        scope_ref=scope_ref,
        kind="verification_result",
        requiredness=requiredness,
        reason=f"{profile} requires {reason} for {sr_id}",
        source_policy=profile,
        state="satisfied" if passed else "open",
        resolve_cmd=(
            (f"coherence register bind ...; rerun validation for {sr_path.name}",)
            if sr_path is not None
            else ("coherence register bind ...; rerun validation (SR trace node not found)",)
        ),
    )


def _human_review_obligation(
    root: Path, scope_ref: str, profile: str, *, nodes, edges,
) -> Obligation:
    """human_review: verification review -- "is this evidence adequate?" --
    the second of the two human gates (R-7's agent half; T-8a). Distinct from
    `sr:` authoring consent ("is this spec paragraph really this
    requirement?", wired elsewhere): this reads ONLY the canonical
    `review:<sr_id>` item, through the existing durable gate store
    (`coherence.gate.store`), never an `sr:` decision and never a parallel
    decision format.

    I-01 -- no self-certification -- means the producer of work is never the
    sole authority that it is done, so `reviewed` below is `True` only for an
    explicit human `accept` DecisionFile addressed to exactly this gate, this
    item, and this SR's own artifact. Absence, a corrupt/malformed file, any
    `reject`/`defer`, or a decision whose `gate_id`/`artifact_ref`/`item_id`
    names a different gate, artifact, or SR all leave `reviewed` `False` --
    there is no default-to-reviewed path and no path that infers a decision.
    """
    from coherence.gate.model import CorruptDecisionFile
    from coherence.gate.store import decision_path, load_decision

    sr_id = scope_ref.partition(":")[2]
    sr_path = _sr_node_path(sr_id, nodes=nodes)
    item_id = f"review:{sr_id}"
    path = decision_path(root, item_id)

    reviewed = False
    expected_artifact_ref: str | None = None
    if sr_path is not None:
        try:
            expected_artifact_ref = "artifact:" + sr_path.resolve().relative_to(
                root.resolve()
            ).as_posix()
        except (OSError, ValueError):
            expected_artifact_ref = None
        if expected_artifact_ref is not None and path.is_file():
            try:
                decision_file = load_decision(path)
            except CorruptDecisionFile:
                reviewed = False
            else:
                decisions = decision_file.decisions
                reviewed = (
                    decision_file.gate_id == item_id
                    and decision_file.artifact_ref == expected_artifact_ref
                    and len(decisions) == 1
                    and decisions[0].item_id == item_id
                    and decisions[0].action == "accept"
                )

    requiredness = "blocking" if profile == "high_assurance" else "not_applicable"
    if sr_path is None:
        resolve_cmd = (f"{sr_id}: no matching sr: trace node found -- register the SR first",)
    elif expected_artifact_ref is None:
        resolve_cmd = (f"{sr_id}: requirement path is outside the canonical project root",)
    else:
        # Never claims a human review occurred -- names the exact decision
        # path/action a human reviewer (not the producer of this work) still
        # needs to take, whether or not one has already been taken.
        resolve_cmd = (
            f"a human reviewer must record `accept` for {item_id} in a "
            f"DecisionFile at {path} (gate_id={item_id!r}, "
            f"artifact_ref={expected_artifact_ref!r})",
        )
    return Obligation(
        id=f"ob:human_review:{scope_ref}",
        scope_ref=scope_ref,
        kind="human_review",
        requiredness=requiredness,
        reason=f"{profile} requires a recorded human review decision for {sr_id}",
        source_policy=profile,
        state="satisfied" if reviewed else "open",
        resolve_cmd=resolve_cmd,
    )


def _test_marker_obligation(root: Path, scope_ref: str, profile: str) -> Obligation:
    """test_marker: a bound SR's experiment, when it resolves to a .py test
    file, must carry a matching @pytest.mark.sr(sr_id) marker. A command/non-file
    experiment is a separate configuration finding (Task 3), not this
    obligation's concern, and this kind is not_applicable for it. The
    marker-closure CHECK (Task 3) consumes THIS compiled obligation's
    requiredness rather than re-deriving severity from a raw profile string.

    Task 5 addendum: an SR that carries no `binding` (the proposed state --
    every FEAT-001 SR today) can still declare one or more `kind: test_marker`
    acceptance criteria (T-1/T-3). Those resolve THIS obligation too, alongside
    -- never merged with -- the legacy binding.experiment path: an SR with a
    binding.experiment behaves exactly as before regardless of any acceptance
    block it also carries (checked first, below). Only when there is no
    binding does acceptance become this obligation's source of truth. An SR
    with several test_marker criteria is satisfied only when EVERY one of them
    resolves to a file carrying a matching marker -- partial resolution is
    reported open, never satisfied (R-2: the criterion's `ref` is a
    navigational pointer that must be consistent with the authoritative
    @pytest.mark.sr decorator, or the mismatch must surface, never pass
    silently). `kind: manual`/`kind: harness` criteria are not this
    obligation's business and are ignored here."""
    from coherence.register import register as register_module
    from coherence.register.markers import MarkerCollectionError, collect_markers
    sr_id = scope_ref.partition(":")[2]
    registered = register_module.load_register(root / "requirements")
    matching = [req for req in registered if req.id == sr_id]
    requiredness = "blocking" if profile == "high_assurance" else "required"
    if len(matching) > 1:
        return Obligation(
            id=f"ob:test_marker:{scope_ref}",
            scope_ref=scope_ref,
            kind="test_marker",
            requiredness="blocking",
            reason=f"{sr_id} has duplicate requirement registrations; source is ambiguous",
            source_policy="ambiguous",
            state="open",
            resolve_cmd=(f"remove duplicate requirement registrations for {sr_id}",),
        )
    req = matching[0] if matching else None

    if req is not None and req.binding is not None:
        # Legacy path -- unchanged behaviour, acceptance criteria (if any) are
        # not consulted here.
        experiment_path = root / req.binding.experiment
        if not (experiment_path.suffix == ".py" and experiment_path.is_file()):
            return Obligation(id=f"ob:test_marker:{scope_ref}", scope_ref=scope_ref,
                kind="test_marker", requiredness="not_applicable",
                reason=f"{sr_id}'s experiment does not resolve to a test file",
                source_policy=profile, state="satisfied", resolve_cmd=None)
        markers = collect_markers(experiment_path)
        present = sr_id in markers
        return Obligation(id=f"ob:test_marker:{scope_ref}", scope_ref=scope_ref,
            kind="test_marker", requiredness=requiredness,
            reason=f"{profile} requires @pytest.mark.sr(\"{sr_id}\") on {sr_id}'s bound experiment test file",
            source_policy=profile, state="satisfied" if present else "open",
            resolve_cmd=(f'add @pytest.mark.sr("{sr_id}") to {experiment_path.name}',))

    test_marker_criteria = [
        c for c in (req.acceptance if req is not None else ())
        if c.verification.kind == "test_marker"
    ]
    if not test_marker_criteria:
        return Obligation(id=f"ob:test_marker:{scope_ref}", scope_ref=scope_ref,
            kind="test_marker", requiredness="not_applicable",
            reason=f"{sr_id} has no binding and no test_marker acceptance criteria to check",
            source_policy=profile, state="satisfied", resolve_cmd=None)

    canonical_root = root.resolve()
    missing_refs: list[str] = []
    for criterion in test_marker_criteria:
        ref = criterion.verification.ref or ""
        try:
            resolved_ref = _resolve_acceptance_ref(root, canonical_root, ref)
            has_marker = (
                resolved_ref.suffix == ".py"
                and resolved_ref.is_file()
                and sr_id in collect_markers(resolved_ref)
            )
        except (MarkerCollectionError, OSError, RuntimeError, TypeError, ValueError):
            has_marker = False
        if not has_marker and ref not in missing_refs:
            missing_refs.append(ref)

    satisfied = not missing_refs
    return Obligation(id=f"ob:test_marker:{scope_ref}", scope_ref=scope_ref,
        kind="test_marker", requiredness=requiredness,
        reason=(
            f"{profile} requires @pytest.mark.sr(\"{sr_id}\") on every file "
            f"{sr_id}'s test_marker acceptance criteria reference"
        ),
        source_policy=profile, state="satisfied" if satisfied else "open",
        resolve_cmd=(
            tuple(f'add @pytest.mark.sr("{sr_id}") to {ref}' for ref in missing_refs)
            if missing_refs else None
        ))


def _resolve_acceptance_ref(root: Path, canonical_root: Path, ref: str) -> Path:
    """Resolve a marker ref only after rejecting unsafe lexical path forms."""
    ref_path = Path(ref)
    windows_ref = PureWindowsPath(ref)
    if ref_path.is_absolute() or ref_path.anchor or windows_ref.anchor:
        raise ValueError("acceptance ref must be relative to the project root")
    if ".." in ref_path.parts or ".." in windows_ref.parts:
        raise ValueError("acceptance ref must not contain a parent-directory component")

    candidate = root
    for part in ref_path.parts:
        candidate /= part
        if _is_symlink_or_reparse_point(candidate):
            raise ValueError("acceptance ref contains a link or reparse point")

    resolved_ref = (canonical_root / ref_path).resolve()
    resolved_ref.relative_to(canonical_root)
    return resolved_ref


def _is_symlink_or_reparse_point(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    )
