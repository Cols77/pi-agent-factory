"""Failure records as structured, provenance-carrying artifacts.

A failure record (``docs/failures/FR-*.md``) captures a reproducible failure
as: reproduction ref → root cause → rejected hypotheses → fix → permanent
regression guard. Identity is the ``id`` (``FR-...``) in YAML frontmatter,
never the filename, mirroring the ADR discipline.

Records are *recorded, never inferred*: every root cause cites evidence or an
ADR, and rejected hypotheses carry their own evidence refs. A malformed
record degrades into ``scope_errors`` instead of crashing the set, so one bad
file never hides the rest. A record whose ``reproduced_by`` run is missing is
an orphan — surfaced by health (Inc 8 Task 4), not a load-time error.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from substrate.validators.schema import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "failure.schema.json"

_FAILURES_DIR_PARTS = ("docs", "failures")


class DuplicateFailureIdError(ValueError):
    """Two failure-record files declare the same `id`.

    Like duplicate ADR ids, this is the one failure-record condition that is
    raised rather than degraded: a ref like `fr:FR-NAV-0001` must resolve to
    exactly one document.
    """


@dataclass(frozen=True)
class FailureRecord:
    """One parsed failure record. Absent fields are `None` / empty."""

    id: str | None
    title: str | None
    path: Path
    reproduced_by: str | None = None
    root_cause: str = ""
    rejected_hypotheses: list[dict] = field(default_factory=list)
    fix: str = ""
    regression_link: str | None = None
    linked_req: list[str] = field(default_factory=list)
    linked_feature: list[str] = field(default_factory=list)
    scope_errors: list[str] = field(default_factory=list)


def parse_failure(path: Path) -> FailureRecord:
    """Parse one failure-record file. Never raises: a bad record degrades itself."""
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError) as exc:
        return FailureRecord(id=None, title=None, path=path, scope_errors=[f"{path}: unreadable ({exc})"])

    meta = dict(post.metadata)

    if not meta:
        return FailureRecord(
            id=None,
            title=None,
            path=path,
            scope_errors=[f"{path}: no frontmatter; a failure record must declare id, title, root_cause and fix"],
        )

    errors = validate(meta, _SCHEMA)
    return FailureRecord(
        id=meta.get("id"),
        title=meta.get("title"),
        path=path,
        reproduced_by=meta.get("reproduced_by"),
        root_cause=meta.get("root_cause", ""),
        rejected_hypotheses=list(meta.get("rejected_hypotheses") or []),
        fix=meta.get("fix", ""),
        regression_link=meta.get("regression_link"),
        linked_req=list(meta.get("linked_req") or []),
        linked_feature=list(meta.get("linked_feature") or []),
        scope_errors=errors,
    )


def failures_dir(repo_root: Path) -> Path:
    return repo_root.joinpath(*_FAILURES_DIR_PARTS)


def load_failure(path: Path) -> FailureRecord:
    """Load one failure record by path."""
    return parse_failure(path)


def load_failures(repo_root: Path) -> dict[str, FailureRecord]:
    """Load every failure record under `docs/failures/`, keyed by declared id.

    An absent directory is a legitimate state, not an error. A record with no
    declared id has no key to file itself under and is skipped without
    aborting the rest of the directory. Duplicate ids raise.
    """
    directory = failures_dir(repo_root)
    if not directory.is_dir():
        return {}
    loaded: dict[str, FailureRecord] = {}
    for path in sorted(directory.glob("*.md")):
        rec = parse_failure(path)
        if rec.id is None:
            continue
        if rec.id in loaded:
            raise DuplicateFailureIdError(
                f"failure id {rec.id!r} is declared by both {loaded[rec.id].path} and {path}"
            )
        loaded[rec.id] = rec
    return loaded
