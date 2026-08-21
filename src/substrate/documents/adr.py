"""Architecture decision records as structured artifacts.

An ADR carries machine-readable identity in YAML frontmatter (validated
against `adr.schema.json`) and prose in the body. Identity is the `id`,
never the filename: bundle members and scope refs use `adr:ADR-0001`, which
matches the `sr:SR-001` / `task:T-059` convention and survives a file being
renamed for readability.

Nothing here recovers identity from prose. A document without frontmatter
has no id -- the parse reports that rather than guessing, which is the same
discipline `factory.system.bundles` applies to an unresolvable member ref.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from substrate.validators.schema import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "adr.schema.json"


@dataclass(frozen=True)
class AdrDocument:
    """One parsed ADR. Absent fields are `None`, never a substituted default."""

    path: Path
    id: str | None = None
    title: str | None = None
    status: str | None = None
    superseded_by: str | None = None
    sections: list[tuple[str, str]] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)


def _sections_of(body: str) -> list[tuple[str, str]]:
    """Split a body into `(## heading, prose)` pairs, in file order.

    Only `##` headings start a section. Text before the first one is
    preamble and belongs to no section, so it is dropped from `sections`
    rather than being attributed to a heading that did not introduce it.
    """
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
    """Parse one ADR file. Never raises: a bad document degrades itself."""
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

    errors = validate(meta, _SCHEMA)
    return AdrDocument(
        path=path,
        id=meta.get("id"),
        title=meta.get("title"),
        status=meta.get("status"),
        superseded_by=meta.get("superseded_by"),
        sections=sections,
        schema_errors=errors,
    )
