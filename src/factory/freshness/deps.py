"""Artifact dependency provenance + transitive impact (Inc 7, Tasks 5c/5d).

Implements HLR-09 with the *existing* trace / freshness / evidence
substrates -- it builds no parallel staleness framework and no second
graph. Edges are declared (read from run manifests, explainer frontmatter,
trace `illustrates` edges) or deterministically authoritative (a run depends
on the SRs / goals / code files it records). Only declared or
deterministically-authoritative relations drive freshness.

Two services:

* ``compute_impact`` -- given the refs that changed, the transitive closure
  of every dependent artifact that must be re-examined (topology only;
  cycle-protected; deterministic).
* ``check_artifact`` -- one artifact's independent freshness from its
  *recorded* fingerprints (run manifests record code-file digests; explainer
  frontmatter records SR + code digests). A missing fingerprint degrades to
  ``UNKNOWN`` -- never silently fresh.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from factory.freshness.fingerprint import fingerprint_file, fingerprint_value
from factory.simulation.registry import Run, load_runs
from factory.system._claims import evidence_dir as _evidence_dir
from factory.trace import explainers as explainers_module
from factory.trace import model as trace_model

#: Artifact kinds that are authoritative sources of truth; they never go stale
#: against themselves (their *dependents* go stale). Cover 5h separately.
_AUTHORITATIVE_PREFIXES = ("sr:", "br:", "goal:", "metric:", "adr:", "feat:")

#: Derived projections that recompute on demand (always current).
_RECOMPUTED_PREFIXES = ("health",)


class FreshnessState(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ArtifactDependency:
    """One declared/authoritative dependency: ``dependent`` depends on ``source``."""

    source_ref: str
    dependent_ref: str
    fingerprint: str | None  # recorded fingerprint of the source at the dependent's last refresh
    dependency_kind: str


@dataclass(frozen=True)
class ArtifactFreshness:
    artifact_ref: str
    state: FreshnessState
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Impact:
    """The affected-closure of a set of changed artifact refs."""

    changed: tuple[str, ...]
    directly_affected: tuple[str, ...]
    transitively_affected: tuple[str, ...]


# ---------------------------------------------------------------------------
# Dependency declarations (declared / deterministically authoritative only)
# ---------------------------------------------------------------------------


def _run_manifest(run: Run) -> dict:
    try:
        raw = json.loads(run.path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _run_dependencies(root: Path, run: Run) -> list[ArtifactDependency]:
    """The run's declared edges (requirement/goal/code sources it depends on).

    Code-file digests come from the manifest's recorded ``dependencies``
    (the reconcile-freshness store); SR/goal dependencies are declared by the
    manifest's ``requirements``/``goals`` lists (authoritative, git-checked,
    no recorded digest here).
    """
    out: list[ArtifactDependency] = []
    manifest = _run_manifest(run)
    for req in run.requirements:
        if req.startswith(("SR-", "BR-")):
            out.append(
                ArtifactDependency(f"sr:{req}", f"run:{run.run_id}", None, "requirement->evidence")
            )
    for goal in run.goals:
        out.append(
            ArtifactDependency(f"goal:{goal}", f"run:{run.run_id}", None, "metric-definition->evidence")
        )
    for dep in manifest.get("dependencies", []):
        if not isinstance(dep, dict) or dep.get("kind") != "file":
            continue
        source = dep.get("source")
        digest = dep.get("digest")
        if isinstance(source, str):
            out.append(
                ArtifactDependency(
                    f"code:{source}",
                    f"run:{run.run_id}",
                    str(digest) if digest else None,
                    "implementation->evidence",
                )
            )
    return out


def _explainer_edges(root: Path, explainer: explainers_module.Explainer) -> list[ArtifactDependency]:
    """Explainer depends on the SRs/code it depicts *with recorded digests*."""
    out: list[ArtifactDependency] = []
    ref = f"explainer:{explainer.id}"
    for sr_id in explainer.explains:
        out.append(
            ArtifactDependency(
                f"sr:{sr_id}", ref, explainer.fingerprints.get(sr_id), "requirement->explainer"
            )
        )
    for relpath, digest in explainer.code_fingerprints.items():
        out.append(
            ArtifactDependency(f"code:{relpath}", ref, digest, "implementation->explainer")
        )
    if explainer.dep_diagram:
        out.append(
            ArtifactDependency(f"diag:{explainer.dep_diagram}", ref, None, "diagram->explainer")
        )
    return out


def _diagram_edges(root: Path) -> list[ArtifactDependency]:
    """A diagram depends on the feature/requirement/goal it illustrates.

    The topology edge (``illustrates``) carries no recorded fingerprint;
    when the diagram doc records ``dep_fingerprint`` (ref -> content digest)
    those become verifiable dependencies for ``check_artifact``.
    """
    out: list[ArtifactDependency] = []
    nodes = trace_model.load_nodes(root)
    edges = trace_model.extract_edges(root, nodes)
    node_kinds = {node.id: node.kind for node in nodes}
    recorded: dict[str, dict[str, str]] = {}
    for node in nodes:
        if node.kind != "diag":
            continue
        post = trace_model._load_post(node.path)
        if post is None:
            continue
        fp_raw = post.metadata.get("dep_fingerprint")
        if isinstance(fp_raw, dict):
            recorded[node.id] = {
                str(k): v for k, v in fp_raw.items() if isinstance(v, str)
            }
    for edge in edges:
        if edge.kind != "illustrates" or edge.src not in node_kinds:
            continue
        if node_kinds[edge.src] != "diag":
            continue
        out.append(
            ArtifactDependency(
                edge.dst, f"diag:{edge.src}", None, "illustrated->diagram"
            )
        )
    for diag_id, fingerprints in recorded.items():
        for source_ref, digest in fingerprints.items():
            out.append(
                ArtifactDependency(
                    normalize_ref(source_ref),
                    f"diag:{diag_id}",
                    digest,
                    "illustrated->diagram",
                )
            )
    return out


def collect_dependency_edges(root: Path) -> list[ArtifactDependency]:
    """Every declared/authoritative artifact dependency, deterministically ordered."""
    edges: list[ArtifactDependency] = []
    for run in load_runs(_evidence_dir(root)):
        edges.extend(_run_dependencies(root, run))
    for explainer in explainers_module.load_explainers(root):
        edges.extend(_explainer_edges(root, explainer))
    edges.extend(_diagram_edges(root))
    dedup: dict[tuple[str, str], ArtifactDependency] = {}
    for edge in sorted(edges, key=lambda e: (e.dependent_ref, e.source_ref, e.dependency_kind)):
        key = (edge.dependent_ref, edge.source_ref)
        # First recorded fingerprint wins (dedupe keeps a recorded digest when present).
        dedup.setdefault(key, edge)
    return [dedup[k] for k in sorted(dedup)]


def dependencies_of(root: Path, ref: str) -> list[ArtifactDependency]:
    """All declared dependencies of one artifact ref."""
    return [e for e in collect_dependency_edges(root) if e.dependent_ref == ref]


# ---------------------------------------------------------------------------
# Transitive impact (5d)
# ---------------------------------------------------------------------------


def _dependent_index(edges: list[ArtifactDependency]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for edge in edges:
        index.setdefault(edge.source_ref, []).append(edge.dependent_ref)
    for source in index:
        index[source] = sorted(set(index[source]))
    return index


def normalize_ref(raw: str) -> str:
    """Normalize a bare id or a `kind:` ref to a `kind:identifier` artifact ref."""
    if ":" in raw:
        return raw
    for prefix in ("SR-", "BR-", "GOAL-", "MET-", "DIAG-", "FEAT-", "RUN-"):
        if raw.startswith(prefix):
            kind = {
                "SR-": "sr",
                "BR-": "br",
                "GOAL-": "goal",
                "MET-": "metric",
                "DIAG-": "diag",
                "FEAT-": "feat",
                "RUN-": "run",
            }[prefix]
            return f"{kind}:{raw}"
    return raw


def compute_impact(root: Path, changed_refs: Sequence[str]) -> Impact:
    """The transitive affected-closure of `changed_refs` over declared edges."""
    changed = tuple(dict.fromkeys(normalize_ref(r) for r in changed_refs))
    edges = collect_dependency_edges(root)
    dependents = _dependent_index(edges)
    closed: set[str] = set(changed)
    frontier: list[str] = list(changed)
    order: list[str] = []
    while frontier:
        current = frontier.pop(0)
        for next_ref in dependents.get(current, []):
            if next_ref not in closed:
                closed.add(next_ref)
                frontier.append(next_ref)
                order.append(next_ref)
    # Classification by first-hop: direct = reached from a changed source.
    changed_set = set(changed)
    directly: list[str] = []
    transitive: list[str] = []
    seen: set[str] = set()
    for start in changed:
        for next_ref in dependents.get(start, []):
            if next_ref in changed_set or next_ref in seen:
                continue
            seen.add(next_ref)
            directly.append(next_ref)
    for ref in order:
        if ref not in directly:
            transitive.append(ref)
    return Impact(
        changed=changed,
        directly_affected=tuple(sorted(directly)),
        transitively_affected=tuple(sorted(transitive)),
    )


# ---------------------------------------------------------------------------
# Per-artifact freshness (5c test list)
# ---------------------------------------------------------------------------


def _sr_content_digest(root: Path, sr_id: str) -> str | None:
    req_dir = root / "requirements"
    if not req_dir.is_dir():
        return None
    for path in sorted(req_dir.glob("SR-*.md")):
        try:
            post = trace_model._load_post(path)
            if post is not None and str(post.metadata.get("id")) == sr_id:
                return fingerprint_value(sr_id, path.read_text(encoding="utf-8")).digest
        except Exception:
            continue
    return None


def _code_digest(root: Path, relpath: str) -> str | None:
    fp = fingerprint_file("file", root / relpath, root)
    return None if fp.digest == "missing" else fp.digest


def _current_source_digest(root: Path, source_ref: str) -> str | None:
    kind, sep, identifier = source_ref.partition(":")
    if not sep:
        return None
    if kind == "sr":
        return _sr_content_digest(root, identifier)
    if kind == "code":
        return _code_digest(root, identifier)
    return None


def check_artifact(root: Path, ref: str) -> ArtifactFreshness:
    """One artifact's current freshness from its recorded fingerprints.

    Authoritative and recomputed artifacts are FRESH by construction (their
    dependents carry staleness). Evidenced artifacts (runs, explainers) are
    STALE when any recorded dependency digest differs from the source's
    current digest, and UNKNOWN when a dependency has no recorded fingerprint
    or its source file is missing -- never silently FRESH.
    """
    ref = normalize_ref(ref)
    kind, _, _ = ref.partition(":")

    # Authoritative sources of truth and recomputed projections never go stale
    # against themselves -- their dependents carry the staleness.
    if kind in ("sr", "br", "goal", "metric", "adr", "feat") or ref.startswith("health"):
        return ArtifactFreshness(ref, FreshnessState.FRESH, ())

    deps = dependencies_of(root, ref)
    if not deps:
        # No declared dependencies: nothing recorded to verify. Report UNKNOWN
        # rather than assuming fresh, unless the artifact is self-authoritative
        # (handled above).
        return ArtifactFreshness(ref, FreshnessState.UNKNOWN, ("no declared dependencies",))

    stale_reasons: list[str] = []
    unknown_reasons: list[str] = []
    any_verdict = False  # at least one dependency produced a fresh/stale verdict
    degraded = False  # a recorded dependency's source has vanished (forces UNKNOWN)
    for dep in deps:
        if dep.fingerprint is not None:
            current = _current_source_digest(root, dep.source_ref)
            if current is None:
                degraded = True
                unknown_reasons.append(f"{dep.source_ref}: source missing")
            elif current != dep.fingerprint:
                stale_reasons.append(f"{dep.source_ref}: changed since evidence")
                any_verdict = True
            else:
                any_verdict = True
            continue
        # No recorded digest: place the dependency in time via the dependent's
        # recorded commit (SR/goal sources). Missing commit -> cannot verify.
        reason = _novelty_reason(root, ref, dep.source_ref)
        if reason == "unknown":
            unknown_reasons.append(f"{dep.source_ref}: no recorded fingerprint or commit")
        elif reason == "stale":
            stale_reasons.append(f"{dep.source_ref}: changed since evidence")
            any_verdict = True
        else:
            any_verdict = True
    if stale_reasons:
        state, reasons = FreshnessState.STALE, stale_reasons
    elif degraded:
        state, reasons = FreshnessState.UNKNOWN, unknown_reasons
    elif any_verdict:
        state, reasons = FreshnessState.FRESH, []
    else:
        state, reasons = FreshnessState.UNKNOWN, unknown_reasons
    return ArtifactFreshness(ref, state, tuple(reasons))


def _novelty_reason(root: Path, dependent_ref: str, source_ref: str) -> str:
    """'stale' / 'fresh' / 'unknown': did the source file change after the
    dependent's recorded commit? Deterministic via git; unknown when the
    dependent records no commit or the source has no tracked file."""
    from factory.delta import git_ops

    dependent_id = dependent_ref.partition(":")[2]
    run = next(
        (r for r in load_runs(_evidence_dir(root)) if r.run_id == dependent_id), None
    )
    commit = run.commit if run is not None else None
    if not commit or not git_ops.commit_exists(root, commit):
        return "unknown"
    kind, _, identifier = source_ref.partition(":")
    if kind == "sr":
        relpath = Path("requirements") / f"{identifier}.md"
    elif kind == "goal":
        relpath = Path("goals") / f"{identifier}.md"
    else:
        return "unknown"
    changed = git_ops.changed_files_since(root, commit, [relpath])
    return "stale" if changed else "fresh"