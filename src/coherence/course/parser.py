from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

_SR_RE = re.compile(r"^SR-[0-9]+$")
_SPEC_RE = re.compile(r"^SPEC-[A-Za-z0-9._-]+$")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def is_node_id(token: str) -> bool:
    """A bare course reference token is a node id iff it matches the grammar.

    Node ids appear ONLY inside wikilinks; a bare title or path (anything that
    does not match ``SR-\\d+`` / ``SPEC-...``) is declared ambiguous.
    """
    return bool(_SR_RE.match(token) or _SPEC_RE.match(token))


@dataclass
class CourseNote:
    """One course note: its path plus the SR/spec node references it declares.

    ``refs`` is the merged node-id set driving coverage; ``frontmatter_refs``
    come from the ``traceability`` frontmatter, ``body_refs`` from ``[[ID]]``
    wikilinks in the body. ``errors`` holds any parse-time problems (malformed
    traceability frontmatter, ambiguous wikilink targets).
    """

    path: Path
    frontmatter_refs: list[str] = field(default_factory=list)
    body_refs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def refs(self) -> set[str]:
        return set(self.frontmatter_refs) | set(self.body_refs)


def _course_notes_dir(root: Path) -> Path:
    return root / "docs" / "course"


def parse_course_note(path: Path, *, rel: str) -> CourseNote:
    """Parse one course note, returning the note plus parse errors.

    Malformed/ambiguous input is surfaced as ``CourseNote.errors`` (the caller
    collects them into the report); the note itself is never the cause of a
    crash.
    """
    note = CourseNote(path=path)
    try:
        post = frontmatter.load(str(path))
    except Exception:  # noqa: BLE001 - a malformed file degrades to an error
        note.errors.append(f"{rel}: unreadable frontmatter")
        return note

    meta = post.metadata

    raw_trace = meta.get("traceability")
    if "traceability" in meta:
        if not isinstance(raw_trace, list):
            note.errors.append(
                f"{rel}: traceability must be a list of node ids, got "
                f"{type(raw_trace).__name__}"
            )
        else:
            for item in raw_trace:
                if not isinstance(item, str) or not is_node_id(item):
                    note.errors.append(
                        f"{rel}: malformed traceability entry {item!r}; "
                        "expected SR-xxx or SPEC-... node ids"
                    )
                else:
                    note.frontmatter_refs.append(item)

    for raw in _WIKILINK_RE.findall(post.content):
        token = raw.strip()
        if is_node_id(token):
            note.body_refs.append(token)
        else:
            note.errors.append(
                f"{rel}: ambiguous wikilink [[{token}]]; node ids must be "
                "SR-xxx or SPEC-... (bare titles/paths are rejected)"
            )
    return note


def load_course_notes(root: Path) -> list[CourseNote]:
    directory = _read_course_notes_dir(root)
    if not directory.is_dir():
        return []
    notes: list[CourseNote] = []
    for path in sorted(directory.glob("*.md")):
        rel = str(path.relative_to(root))
        notes.append(parse_course_note(path, rel=rel))
    return notes


def _read_course_notes_dir(root: Path) -> Path:
    return _course_notes_dir(root)


__all__ = ["CourseNote", "is_node_id", "load_course_notes", "parse_course_note"]