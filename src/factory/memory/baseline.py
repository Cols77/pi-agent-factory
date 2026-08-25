"""Milestone baseline records: an optional product/high_assurance snapshot.

`docs/baselines/BASELINE-*.md`. Structurally parallel to `docs/failures/
FR-*.md` (`factory.memory.failure_record`) and `docs/nonconformances/NC-*.md`
(`factory.memory.nonconformance`): identity is the `id` in YAML frontmatter,
never the filename; a malformed record degrades into `scope_errors` instead
of crashing the set; an absent directory is a legitimate state (baselines are
optional per spec section 4 -- not required to run an experiment or ship a
prototype).

A baseline pins a Git-state snapshot over a `scope` of accepted needs/
requirements/decisions. It is a semantic snapshot only: coherence records it,
and `coherence.trace.suspect.expired_baselines` queries it against the live
graph -- closing an expired baseline is a human gate-protocol decision, never
an auto-transition.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from substrate.validators.schema import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "baseline.schema.json"
_BASELINE_DIR_PARTS = ("docs", "baselines")


class DuplicateBaselineIdError(ValueError):
    """Two baseline files declare the same `id`."""


@dataclass(frozen=True)
class Baseline:
    id: str | None
    title: str | None
    path: Path
    git_ref: str | None = None
    scope: list[str] = field(default_factory=list)
    approved_by: str | None = None
    scope_errors: list[str] = field(default_factory=list)


def _meta_str(value: object) -> str | None:
    """Coerce a frontmatter value to str, or None when it is absent/null (
    mirrors how other record loaders read optional string frontmatter)."""
    return str(value) if value is not None else None


def parse_baseline(path: Path) -> Baseline:
    """Parse one baseline record. Never raises: a bad record degrades itself."""
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError) as exc:
        return Baseline(
            id=None, title=None, path=path, scope_errors=[f"{path}: unreadable ({exc})"]
        )

    meta = dict(post.metadata)
    if not meta:
        return Baseline(
            id=None,
            title=None,
            path=path,
            scope_errors=[f"{path}: no frontmatter; a baseline record must declare id, title, git_ref and approved_by"],
        )

    errors = validate(meta, _SCHEMA)
    raw_scope = meta.get("scope")
    scope = (
        [str(s) for s in raw_scope] if isinstance(raw_scope, list) else []
    )
    return Baseline(
        id=_meta_str(meta.get("id")),
        title=_meta_str(meta.get("title")),
        path=path,
        git_ref=_meta_str(meta.get("git_ref")),
        scope=scope,
        approved_by=_meta_str(meta.get("approved_by")),
        scope_errors=errors,
    )


def baselines_dir(repo_root: Path) -> Path:
    return repo_root.joinpath(*_BASELINE_DIR_PARTS)


def load_baselines(repo_root: Path) -> dict[str, Baseline]:
    """Load every baseline record under `docs/baselines/`, keyed by id.

    An absent directory is a legitimate state (baselines are optional), not an
    error. Duplicate ids raise.
    """
    directory = baselines_dir(repo_root)
    if not directory.is_dir():
        return {}
    loaded: dict[str, Baseline] = {}
    for path in sorted(directory.glob("*.md")):
        rec = parse_baseline(path)
        if rec.id is None:
            continue
        if rec.id in loaded:
            raise DuplicateBaselineIdError(
                f"baseline id {rec.id!r} is declared by both {loaded[rec.id].path} and {path}"
            )
        loaded[rec.id] = rec
    return loaded
