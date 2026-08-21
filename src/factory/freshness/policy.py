"""Authority-aware refresh policy + reconciliation + closure (Inc 7, 5e/5f/5i/5j/5m).

Separates "this is stale" (``factory.freshness.deps.check_artifact``) from
"what should the factory do about it". The policy is deterministic and never
decides staleness itself; an LLM may *execute* a regeneration after the
action is selected but must not decide whether the source artifact is stale.

Resource/safety boundary (5e): when the required generator/harness is not
registered/executable, the state stays explicitly ``REQUEST_HUMAN_ACTION``
-- never silently FRESH.

Reconciliation (5i) never trusts that a refresh command ran: it verifies
current fingerprints with ``check_artifact`` after the action completes.
``refresh action executed != artifact is fresh``.

Loop protection (5m): a refresh pass is bounded (``max_attempts``); a
regenerated artifact is never its own input (edges come only from canonical
declared sources); repeated identical refresh attempts become BLOCKED.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import json

from factory.freshness.deps import (
    FreshnessState,
    check_artifact,
    collect_dependency_edges,
    compute_impact,
    normalize_ref,
)

#: Authoritative contract kinds: preserve; explicit workflow if they change.
_AUTHORITATIVE_KINDS = ("sr", "br", "goal", "metric", "adr", "feat")

#: Generated/derived kinds that can be recomputed/regenerated.
_GENERATED_KINDS = ("explainer", "diag")
_DERIVED_PREFIX = "health"


class RefreshAction(str, Enum):
    RECOMPUTE = "recompute"
    REGENERATE = "regenerate"
    RERUN_VALIDATION = "rerun-validation"
    ROUTE_TO_DEV = "route-to-dev"
    REQUEST_HUMAN_ACTION = "request-human-action"
    SUPERSEDE = "supersede"


@dataclass(frozen=True)
class RefreshDecision:
    artifact_ref: str
    action: RefreshAction
    reason: str


#: Generator registry: artifact kind -> deterministic regenerator.
#: ``(root, ref) -> bool`` (True = a new artifact was written). Tests and
#: callers register their own; an unregistered kind is not executable.
Generator = Callable[[Path, str], bool]
_GENERATORS: dict[str, Generator] = {}
_GENERATOR_VERSIONS: dict[str, str] = {}


def register_generator(kind: str, fn: Generator, version: str | None = None) -> None:
    """Register a deterministic regenerator for an artifact kind (5f).

    ``version`` is the generator's own fingerprint: a changed version marks
    previously generated artifacts stale (5f test 6) so they refresh.
    """
    _GENERATORS[kind] = fn
    if version is not None:
        _GENERATOR_VERSIONS[kind] = version


def generator_version(kind: str) -> str | None:
    return _GENERATOR_VERSIONS.get(kind)


def generators_for(kind: str) -> list[Generator]:
    fn = _GENERATORS.get(kind)
    return [fn] if fn is not None else []


def _rerun_validation(root: Path, ref: str) -> bool:
    """Execute a registered validation rerun for one evidence artifact.

    Reruns are safe/executable only when a harness rerun is registered
    (kind ``"run"``). Nothing here invents a harness.
    """
    fns = generators_for("run")
    if not fns:
        return False
    return fns[0](root, ref)


def refresh_decision(root: Path, ref: str) -> RefreshDecision:
    """The deterministic default policy for one stale/affected artifact (5e)."""
    ref = normalize_ref(ref)
    kind, _, identifier = ref.partition(":")

    if kind in _AUTHORITATIVE_KINDS:
        return RefreshDecision(
            ref,
            RefreshAction.REQUEST_HUMAN_ACTION,
            "authoritative contract: preserve; explicit workflow required if it must change",
        )
    if kind == "code":
        return RefreshDecision(
            ref,
            RefreshAction.ROUTE_TO_DEV,
            "semantically invalidated implementation must be repaired through the DEV workflow",
        )
    if kind == "run":
        # The required action is a rerun; availability of an executable
        # harness is a resource boundary checked at execution (5e), never a
        # policy change -- an unavailable harness must read BLOCKED, not
        # silently fresh.
        return RefreshDecision(
            ref, RefreshAction.RERUN_VALIDATION, "validation evidence must be re-run"
        )
    if kind in _GENERATED_KINDS:
        return RefreshDecision(
            ref,
            RefreshAction.REGENERATE,
            f"{kind} is a generated artifact: regenerate from canonical sources",
        )
    if ref.startswith(_DERIVED_PREFIX):
        return RefreshDecision(ref, RefreshAction.RECOMPUTE, "derived projection recomputes on demand")
    return RefreshDecision(
        ref, RefreshAction.REQUEST_HUMAN_ACTION, f"no policy for artifact kind {kind!r}"
    )


def _explainer_generator_outdated(root: Path, ref: str) -> bool:
    """True when an explainer records a generator version that differs from
    the registered one (5f test 6: generator fingerprint change refreshes).
    An explainer with no recorded generator is not judged by this check."""
    import frontmatter

    kind, _, identifier = ref.partition(":")
    if kind != "explainer":
        return False
    path = root / "docs" / "visual-explain" / identifier
    try:
        post = frontmatter.load(str(path))
        recorded = post.metadata.get("generator")
    except Exception:
        return False
    if not isinstance(recorded, str):
        return False
    current = generator_version("explainer")
    return current is not None and recorded != current


def _execute(root: Path, decision: RefreshDecision) -> bool:
    """Run the action when safe/registered; False when not executable."""
    kind = decision.artifact_ref.partition(":")[0]
    if decision.action is RefreshAction.RECOMPUTE:
        return True  # derived projections recompute on demand; nothing to write
    if decision.action is RefreshAction.REGENERATE:
        fns = generators_for(kind)
        return bool(fns and fns[0](root, decision.artifact_ref))
    if decision.action is RefreshAction.RERUN_VALIDATION:
        return _rerun_validation(root, decision.artifact_ref)
    return False  # ROUTE_TO_DEV / REQUEST_HUMAN_ACTION / SUPERSEDE: not auto-executable


@dataclass(frozen=True)
class FreshnessReconciliation:
    """Outcome of a bounded refresh pass over a set of artifacts (5i)."""

    refreshed: tuple[str, ...]
    still_stale: tuple[str, ...]
    blocked: tuple[str, ...]
    superseded: tuple[str, ...]
    closure_reached: bool


def reconcile(root: Path, refs: list[str], max_attempts: int = 1) -> FreshnessReconciliation:
    """One bounded refresh pass: decide -> execute -> *verify* (5i/5m).

    ``max_attempts`` bounds pathological chains (5m): an artifact whose
    recorded fingerprints still mismatch after the pass is ``still_stale``,
    and a second identical attempt is not retried. Verification is always
    ``check_artifact`` -- the fact that an action ran is never trusted.
    """
    refreshed: list[str] = []
    still_stale: list[str] = []
    blocked: list[str] = []
    superseded: list[str] = []

    for raw in refs:
        ref = normalize_ref(raw)
        before = check_artifact(root, ref)
        decision = refresh_decision(root, ref)
        if decision.action is RefreshAction.SUPERSEDE:
            superseded.append(ref)
            continue
        # 5f test 6: a changed generator version forces regeneration even when
        # the recorded content fingerprints still match.
        generator_outdated = _explainer_generator_outdated(root, ref)
        executed = False
        attempt = 0
        current = before
        while (
            attempt < max_attempts
            and (current.state is not FreshnessState.FRESH or generator_outdated)
        ):
            executed = _execute(root, decision) or executed
            current = check_artifact(root, ref)
            generator_outdated = _explainer_generator_outdated(root, ref)
            attempt += 1
        if current.state is FreshnessState.FRESH and not generator_outdated:
            refreshed.append(ref)
        elif decision.action in (RefreshAction.REGENERATE, RefreshAction.RERUN_VALIDATION) and not executed:
            blocked.append(ref)
        else:
            still_stale.append(ref)

    refreshed_sorted = tuple(sorted(refreshed))
    return FreshnessReconciliation(
        refreshed=refreshed_sorted,
        still_stale=tuple(sorted(still_stale)),
        blocked=tuple(sorted(blocked)),
        superseded=tuple(sorted(superseded)),
        closure_reached=not (still_stale or blocked),
    )


# ---------------------------------------------------------------------------
# Feature freshness closure (5j)
# ---------------------------------------------------------------------------


def feature_artifacts(root: Path, feature: str, *, dep_edges=None) -> list[str]:
    """Every artifact ref in a feature's slice (declared edges only)."""
    refs: set[str] = {f"feat:{feature}"}
    feat_ref = f"feat:{feature}"
    if dep_edges is None:
        dep_edges = collect_dependency_edges(root)
    for edge in dep_edges:
        if edge.source_ref == feat_ref:
            refs.add(edge.dependent_ref)
    # Runs whose manifest declares the feature.
    from factory.simulation.registry import load_runs

    from factory.system._claims import evidence_dir as _evidence_dir

    for run in load_runs(_evidence_dir(root)):
        if run.feature == feature:
            refs.add(f"run:{run.run_id}")
            refs.update(f"sr:{r}" for r in run.requirements if r.startswith(("SR-", "BR-")))
            refs.update(f"goal:{g}" for g in run.goals)
            # Code files the run fingerprinted as implementation dependencies.
            try:
                manifest = json.loads((run.path.parent / "manifest.json").read_text(encoding="utf-8"))
                for dep in manifest.get("dependencies", []):
                    if isinstance(dep, dict) and isinstance(dep.get("source"), str):
                        refs.add(f"code:{dep['source']}")
            except (OSError, ValueError):
                pass
    # Explainers depicting the feature's SRs.
    from factory.trace import explainers as explainers_module

    for explainer in explainers_module.load_explainers(root):
        if any(sr in refs for sr in (f"sr:{e}" for e in explainer.explains)):
            refs.add(f"explainer:{explainer.id}")
    return sorted(refs)


@dataclass(frozen=True)
class FreshnessClosure:
    """Whether the complete impacted feature slice is coherent again (5j)."""

    feature: str
    closure_reached: bool
    remaining: dict[str, str]  # artifact_ref -> state


def semantically_invalidated_code(root: Path, *, dep_edges=None) -> set[str]:
    """Code artifacts affected by a semantically-changed upstream requirement.

    An SR whose register checksum is no longer current (statement/binding
    changed since its last validation) semantically invalidates the
    implementation that its evidence fingerprinted. These code refs are
    ROUTE_TO_DEV: never auto-rewritten, and they keep feature closure open
    (5j example: ``remaining: code:... ROUTE_TO_DEV``).
    """
    from factory.requirements import register as req_register

    affected: set[str] = set()
    for req in req_register.load_register(root / "requirements"):
        if req.binding is None or req_register.is_checksum_current(req):
            continue
        impact = compute_impact(root, [f"sr:{req.id}"], dep_edges=dep_edges)
        for ref in impact.directly_affected + impact.transitively_affected:
            if ref.startswith("code:"):
                affected.add(ref)
    return affected


def freshness_closure(root: Path, feature: str, *, dep_edges=None) -> FreshnessClosure:
    """Feature freshness closure: every slice artifact fresh / superseded /
    intentionally unresolved with a visible state (never hidden staleness).

    Code kept authoritative-current is additionally marked ``route-to-dev``
    when semantically invalidated by a changed upstream requirement (5j) --
    such an implementation keeps the closure open until repaired.
    """
    remaining: dict[str, str] = {}
    for ref in feature_artifacts(root, feature, dep_edges=dep_edges):
        state = check_artifact(root, ref, dep_edges=dep_edges).state.value
        if state != FreshnessState.FRESH.value:
            remaining[ref] = state
        elif ref in semantically_invalidated_code(root, dep_edges=dep_edges):
            remaining[ref] = "route-to-dev"
    return FreshnessClosure(
        feature=feature,
        closure_reached=not remaining,
        remaining=remaining,
    )


def closure_after_reconcile(root: Path, feature: str, refs: list[str]) -> FreshnessClosure:
    """Run a bounded refresh pass over the slice, then recompute closure."""
    reconcile(root, refs)
    return freshness_closure(root, feature)
