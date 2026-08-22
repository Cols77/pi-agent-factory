"""Architecture decision records as neutral structured documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from substrate.validators.schema import SCHEMA_DIR, validate


_SCHEMA = SCHEMA_DIR / "adr.schema.json"
_ADR_DIR_PARTS = ("docs", "adr")


class DuplicateAdrIdError(ValueError):
    """Two ADR files declare the same identity."""


@dataclass(frozen=True)
class AdrDocument:
    """One parsed ADR. Absent fields are ``None``."""

    path: Path
    id: str | None = None
    title: str | None = None
    status: str | None = None
    superseded_by: str | None = None
    sections: list[tuple[str, str]] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)


def _sections_of(body: str) -> list[tuple[str, str]]:
    """Split a body into ``(## heading, prose)`` pairs in file order."""
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    buffer: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(buffer).strip()))
            heading = line[3:].strip()
            buffer = []
        elif heading is not None:
            buffer.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(buffer).strip()))
    return sections


def parse_adr(path: Path) -> AdrDocument:
    """Parse one ADR file; document-local failures degrade to schema errors."""
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError) as exc:
        return AdrDocument(path=path, schema_errors=[f"{path}: unreadable ({exc})"])

    meta = dict(post.metadata)
    sections = _sections_of(post.content)
    if not meta:
        return AdrDocument(
            path=path,
            sections=sections,
            schema_errors=[f"{path}: no frontmatter; an ADR must declare id, title and status"],
        )

    return AdrDocument(
        path=path,
        id=meta.get("id"),
        title=meta.get("title"),
        status=meta.get("status"),
        superseded_by=meta.get("superseded_by"),
        sections=sections,
        schema_errors=validate(meta, _SCHEMA),
    )


def adr_dir(repo_root: Path) -> Path:
    return repo_root.joinpath(*_ADR_DIR_PARTS)


def load_adrs(repo_root: Path) -> dict[str, AdrDocument]:
    """Load ADRs keyed by declared identity, rejecting duplicate identities."""
    directory = adr_dir(repo_root)
    if not directory.is_dir():
        return {}
    loaded: dict[str, AdrDocument] = {}
    for path in sorted(directory.glob("*.md")):
        document = parse_adr(path)
        if document.id is None:
            continue
        if document.id in loaded:
            raise DuplicateAdrIdError(
                f"ADR id {document.id!r} is declared by both "
                f"{loaded[document.id].path} and {path}"
            )
        loaded[document.id] = document
    return loaded
