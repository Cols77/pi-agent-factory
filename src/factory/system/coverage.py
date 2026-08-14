"""Which artifacts belong to no bundle.

Membership is many-to-many, so the only question coverage asks is whether an
artifact belongs to *at least one* bundle. Counts are over the artifact set,
never summed across bundles: summing would double-count anything two features
share and report more requirements than the repo contains.

Refs are not uniform. `sr:`, `task:` and `adr:` are id-based; `spec:` and
`plan:` are repo-relative paths (`queries._resolve_spec_or_plan_member`). Task
filenames carry slugs, so an id cannot be concatenated into a path. Everything
is therefore normalised to a resolved `Path` -- the one representation all five
kinds share -- and compared on that.

Artifact enumeration reuses `factory.trace.model.load_nodes` rather than
re-globbing: a second set of parsing rules is how two surfaces start disagreeing
about what exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from factory.system import adr as adr_module
from factory.system import bundles as bundles_module
from factory.trace import model as trace_model

# Ordered for stable reporting. `br` is deliberately absent: the BR tier is
# SP-D, and counting a kind with no artifacts would report a permanent 0/0.
_KINDS = ("sr", "task", "spec", "plan", "adr")


@dataclass(frozen=True)
class KindCoverage:
    kind: str
    total: int
    bundled: int
    unbundled: list[str]


@dataclass(frozen=True)
class Coverage:
    kinds: list[KindCoverage]
    total: int
    bundled: int
    unbundled: list[str]


def _artifacts(repo_root: Path) -> dict[str, list[tuple[str, Path]]]:
    """Every bundleable artifact as `{kind: [(ref, resolved_path), ...]}`.

    `ref` is the exact string a bundle member would have to declare to claim
    this artifact -- id-based for sr/task/adr, repo-relative path for
    spec/plan.
    """
    found: dict[str, list[tuple[str, Path]]] = {kind: [] for kind in _KINDS}
    for node in trace_model.load_nodes(repo_root):
        path = node.path.resolve()
        if node.kind in ("sr", "task"):
            found[node.kind].append((f"{node.kind}:{node.id}", path))
        elif node.kind in ("spec", "plan"):
            relative = node.path.relative_to(repo_root).as_posix()
            found[node.kind].append((f"{node.kind}:{relative}", path))
        # `br` nodes exist in trace but are not bundleable in SP-A.
    for adr_id, doc in adr_module.load_adrs(repo_root).items():
        found["adr"].append((f"adr:{adr_id}", doc.path.resolve()))
    for kind in found:
        found[kind].sort(key=lambda pair: pair[0])
    return found


def member_target(repo_root: Path, member_ref: str) -> Path | None:
    """Resolve a bundle member ref to the artifact path it names, or None.

    None means the ref is well-formed but names nothing that exists -- a typo
    in a bundle file, not a crash.
    """
    kind, _, identifier = member_ref.partition(":")
    if not identifier:
        return None
    if kind in ("spec", "plan"):
        path = repo_root / identifier
        return path.resolve() if path.is_file() else None
    if kind == "adr":
        doc = adr_module.load_adrs(repo_root).get(identifier)
        return doc.path.resolve() if doc is not None else None
    if kind in ("sr", "task"):
        for node in trace_model.load_nodes(repo_root):
            if node.kind == kind and node.id == identifier:
                return node.path.resolve()
        return None
    return None


def bundle_coverage(repo_root: Path) -> Coverage:
    """Per-kind bundled/unbundled split over every bundleable artifact."""
    artifacts = _artifacts(repo_root)

    claimed: set[Path] = set()
    for bundle in bundles_module.list_bundles(repo_root / "bundles"):
        for member in bundle.members:
            target = member_target(repo_root, member.ref)
            if target is not None:
                claimed.add(target)

    kinds: list[KindCoverage] = []
    all_unbundled: list[str] = []
    total = 0
    bundled = 0
    for kind in _KINDS:
        entries = artifacts[kind]
        unbundled = [ref for ref, path in entries if path not in claimed]
        kinds.append(
            KindCoverage(
                kind=kind,
                total=len(entries),
                bundled=len(entries) - len(unbundled),
                unbundled=unbundled,
            )
        )
        total += len(entries)
        bundled += len(entries) - len(unbundled)
        all_unbundled.extend(unbundled)

    return Coverage(kinds=kinds, total=total, bundled=bundled, unbundled=all_unbundled)
