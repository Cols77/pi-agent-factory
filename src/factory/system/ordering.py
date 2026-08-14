"""Which bundle was most recently touched, and the resulting order.

"Touched" means a commit changed one of the bundle's *member artifacts*.
Editing the bundle file itself is curation, not development; counting it
would make the navigator's sidebar a record of what was last tidied rather
than where work is happening.

Recency comes from git, never from filesystem mtime: mtime would reorder the
whole sidebar on a fresh clone, and the factory already bans mtime for
freshness. When git cannot answer, every recency is None and the caller is
told so -- an arbitrary order presented as meaningful is worse than an
admitted fallback.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from factory.system import bundles as bundles_module
from factory.system.coverage import ArtifactLookup, member_target


class RecencySource(Protocol):
    """Last-commit lookup. Mirrors `orchestrator.git_ops.GitOps`'s shape:
    a Protocol with a subprocess implementation and a test double, so no test
    needs a real repository."""

    def last_commit_iso(self, repo_root: Path, paths: list[Path]) -> str | None: ...


class GitRecency:
    """Real git. Returns the newest author date across `paths`, or None."""

    def last_commit_iso(self, repo_root: Path, paths: list[Path]) -> str | None:
        if not paths:
            return None
        try:
            completed = subprocess.run(
                ["git", "log", "-1", "--format=%aI", "--", *[str(p) for p in paths]],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        stamp = completed.stdout.strip()
        return stamp or None


@dataclass
class FixedRecency:
    """Test double: a path -> ISO timestamp table. No subprocess, no repo."""

    stamps: dict[Path, str]

    def last_commit_iso(self, repo_root: Path, paths: list[Path]) -> str | None:
        found = [self.stamps[p] for p in paths if p in self.stamps]
        return max(found) if found else None


def bundle_recency(
    repo_root: Path, git: RecencySource, *, lookup: ArtifactLookup | None = None
) -> dict[str, str | None]:
    """Newest member-artifact commit timestamp per bundle id, or None."""
    recency: dict[str, str | None] = {}
    for bundle in bundles_module.list_bundles(repo_root / "bundles"):
        targets = [
            target
            for target in (member_target(repo_root, m.ref, lookup=lookup) for m in bundle.members)
            if target is not None
        ]
        recency[bundle.id] = git.last_commit_iso(repo_root, targets)
    return recency


def _descending(stamp: str | None) -> tuple[int, ...]:
    """Sort key that reverses an ISO timestamp while keeping id ascending.

    `sorted(reverse=True)` would reverse the id tiebreak too, which would make
    two bundles committed in the same second order z-to-a. Inverting each
    character's code point reverses only this component. `None` sorts together
    with the undated group (the first key component already separated it), so
    the empty tuple here is defensive, not load-bearing.
    """
    if stamp is None:
        return ()
    return tuple(-ord(ch) for ch in stamp)


def ordered_bundle_ids(
    repo_root: Path, git: RecencySource, *, lookup: ArtifactLookup | None = None
) -> tuple[list[str], bool]:
    """Bundle ids most-recent-first, plus whether any recency was available.

    Undated bundles sort after every dated one. The tiebreak is id ascending
    -- deterministic, never random (`factory.trace.propose` line 129 sets the
    same rule for candidate ordering).
    """
    recency = bundle_recency(repo_root, git, lookup=lookup)
    available = any(stamp is not None for stamp in recency.values())
    order = sorted(
        recency,
        # `stamp is None` sorts False(0) before True(1), so dated bundles lead;
        # ISO-8601 author dates compare correctly as text, so no parsing.
        key=lambda bundle_id: (
            recency[bundle_id] is None,
            _descending(recency[bundle_id]),
            bundle_id,
        ),
    )
    return order, available
