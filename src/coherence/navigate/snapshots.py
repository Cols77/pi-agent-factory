"""Freshness-guarded navigation inputs.

Navigation consumes authoritative files through a small read guard. A stored
navigation snapshot records the content fingerprint that the route last used;
when the source changes, callers receive a stale result with an explicit
resolver command instead of a current-looking narrative.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from substrate.artifacts import ArtifactRef
from substrate.freshness.fingerprint import fingerprint_file

Freshness = Literal["fresh", "stale", "missing"]
_SNAPSHOT_DIR = Path(".factory") / "navigation-snapshots"


@dataclass(frozen=True)
class GuardedNavigationSnapshot:
    ref: str
    freshness: Freshness
    artifact_ref: ArtifactRef | None
    resolver_cmd: str | None
    content: str | None = None


def _location(root: Path, ref: str) -> tuple[str, Path]:
    kind, separator, identifier = ref.partition(":")
    if not separator or not kind or not identifier:
        raise ValueError(f"invalid navigation snapshot ref: {ref!r}")
    locations = {
        "sr": Path("requirements") / f"{identifier}.md",
        "br": Path("requirements") / f"{identifier}.md",
        "task": Path("tasks") / f"{identifier}.md",
        "feat": Path("docs") / "features" / f"{identifier}.md",
        "metric": Path("metrics") / f"{identifier}.md",
        "goal": Path("goals") / f"{identifier}.md",
        "adr": Path("docs") / "adr" / f"{identifier}.md",
        "diag": Path("docs") / "diagrams" / f"{identifier}.md",
        "bundle": Path("bundles") / f"{identifier}.json",
    }
    candidate = locations.get(kind, Path(identifier))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"navigation snapshot path escapes repository: {ref!r}")
    path = (root / candidate).resolve()
    path.relative_to(root.resolve())
    return kind, path


def _slug(ref: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", ref)


def _metadata_path(root: Path, ref: str) -> Path:
    return root / _SNAPSHOT_DIR / f"{_slug(ref)}.json"


def _artifact(root: Path, ref: str, kind: str, path: Path) -> ArtifactRef | None:
    if not path.is_file():
        return None
    digest = fingerprint_file(ref, path, root).digest
    return ArtifactRef(
        schema=1,
        kind=kind,
        ref=ref,
        location=path.relative_to(root.resolve()).as_posix(),
        content_hash=digest,
        scope_refs=(ref,),
    )


def _current(root: Path, ref: str) -> tuple[str, Path, ArtifactRef | None]:
    kind, path = _location(root, ref)
    return kind, path, _artifact(root, ref, kind, path)


def write_navigation_snapshot(root: Path, ref: str) -> Path:
    """Persist the current source fingerprint for a route's next guarded read."""
    _, path, artifact = _current(root, ref)
    if artifact is None:
        raise FileNotFoundError(path)
    target = _metadata_path(root, ref)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "ref": ref,
                "fingerprint": artifact.content_hash,
                "location": artifact.location,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def resolve_navigation_snapshot(root: Path, ref: str) -> GuardedNavigationSnapshot:
    """Resolve one navigation input without hiding freshness or absence."""
    kind, path, artifact = _current(root, ref)
    if artifact is None:
        return GuardedNavigationSnapshot(
            ref=ref,
            freshness="missing",
            artifact_ref=None,
            resolver_cmd=f"coherence navigate snapshot refresh --ref {ref}",
        )

    metadata = _metadata_path(root, ref)
    if not metadata.exists():
        content = path.read_text(encoding="utf-8", errors="replace")
        return GuardedNavigationSnapshot(ref, "fresh", artifact, None, content)

    try:
        recorded = json.loads(metadata.read_text(encoding="utf-8"))
        expected = recorded["fingerprint"]
        if recorded["ref"] != ref or recorded["location"] != artifact.location:
            raise ValueError("snapshot identity mismatch")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        expected = None

    if expected == artifact.content_hash:
        content = path.read_text(encoding="utf-8", errors="replace")
        return GuardedNavigationSnapshot(ref, "fresh", artifact, None, content)
    return GuardedNavigationSnapshot(
        ref=ref,
        freshness="stale",
        artifact_ref=artifact,
        resolver_cmd=f"coherence navigate snapshot refresh --ref {ref}",
    )


__all__ = [
    "GuardedNavigationSnapshot",
    "resolve_navigation_snapshot",
    "write_navigation_snapshot",
]
