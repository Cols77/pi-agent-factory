"""Nonconformance records: a defect/change-request corrected by a task.

`docs/nonconformances/NC-*.md`. Structurally parallel to `docs/failures/FR-*.md`
(`factory.memory.failure_record`): identity is the `id` in YAML frontmatter,
never the filename; a malformed record degrades into `scope_errors` instead of
crashing the set; `external_ref` is a citation (`gh-issue:1`), never a live
sync -- coherence never calls the tracker's API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from substrate.validators.schema import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "nonconformance.schema.json"
_NC_DIR_PARTS = ("docs", "nonconformances")


class DuplicateNonconformanceIdError(ValueError):
    """Two nonconformance files declare the same `id`."""


@dataclass(frozen=True)
class NonconformanceRecord:
    id: str | None
    title: str | None
    path: Path
    external_ref: str | None = None
    detected_by: str | None = None
    status: str = "open"
    corrected_by: str | None = None
    scope_errors: list[str] = field(default_factory=list)


def parse_nonconformance(path: Path) -> NonconformanceRecord:
    """Parse one nonconformance record. Never raises: a bad record degrades itself."""
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError) as exc:
        return NonconformanceRecord(
            id=None, title=None, path=path, scope_errors=[f"{path}: unreadable ({exc})"]
        )

    meta = dict(post.metadata)
    if not meta:
        return NonconformanceRecord(
            id=None,
            title=None,
            path=path,
            scope_errors=[f"{path}: no frontmatter; a nonconformance record must declare id, title and status"],
        )

    errors = validate(meta, _SCHEMA)
    return NonconformanceRecord(
        id=meta.get("id"),
        title=meta.get("title"),
        path=path,
        external_ref=meta.get("external_ref"),
        detected_by=meta.get("detected_by"),
        status=meta.get("status", "open"),
        corrected_by=meta.get("corrected_by"),
        scope_errors=errors,
    )


def nonconformances_dir(repo_root: Path) -> Path:
    return repo_root.joinpath(*_NC_DIR_PARTS)


def load_nonconformance(path: Path) -> NonconformanceRecord:
    return parse_nonconformance(path)


def load_nonconformances(repo_root: Path) -> dict[str, NonconformanceRecord]:
    """Load every nonconformance record under `docs/nonconformances/`, keyed by id.

    An absent directory is a legitimate state, not an error. Duplicate ids raise.
    """
    directory = nonconformances_dir(repo_root)
    if not directory.is_dir():
        return {}
    loaded: dict[str, NonconformanceRecord] = {}
    for path in sorted(directory.glob("*.md")):
        rec = parse_nonconformance(path)
        if rec.id is None:
            continue
        if rec.id in loaded:
            raise DuplicateNonconformanceIdError(
                f"nonconformance id {rec.id!r} is declared by both {loaded[rec.id].path} and {path}"
            )
        loaded[rec.id] = rec
    return loaded
