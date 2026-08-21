"""Architecture decision records as structured artifacts.

`AdrDocument` and `parse_adr` now live in `substrate.documents.adr` (pure,
neutral parsing) and are re-exported here unchanged -- this is an internal
repoint, not a public API move, so no deprecation warning fires.

`adr_dir`, `load_adrs`, and `DuplicateAdrIdError` stay here: they embed the
`docs/adr` directory convention and are consumed only by factory-side
callers (`factory.memory.durable`, `factory.system.queries`,
`factory.system.labels`, `factory.system.coverage`, `factory.trace.graph`).
"""
from __future__ import annotations

from pathlib import Path

from substrate.documents.adr import AdrDocument, parse_adr

_ADR_DIR_PARTS = ("docs", "adr")


class DuplicateAdrIdError(ValueError):
    """Two ADR files declare the same `id`.

    Unlike every other ADR failure, this one is raised rather than degraded.
    A ref like `adr:ADR-0001` must resolve to exactly one document; if two
    claim the id, every ref to it is meaningless and silently picking one
    would make bundle membership depend on directory iteration order.
    """


def adr_dir(repo_root: Path) -> Path:
    return repo_root.joinpath(*_ADR_DIR_PARTS)


def load_adrs(repo_root: Path) -> dict[str, AdrDocument]:
    """Load every ADR under `docs/adr/`, keyed by declared id.

    An absent directory is a legitimate state, not an error -- the same rule
    `bundles.list_bundles` applies to an absent bundles directory. A document
    with no declared id has no key to file itself under and is skipped
    without aborting the rest of the directory. Duplicate ids raise.
    """
    directory = adr_dir(repo_root)
    if not directory.is_dir():
        return {}
    loaded: dict[str, AdrDocument] = {}
    for path in sorted(directory.glob("*.md")):
        doc = parse_adr(path)
        if doc.id is None:
            continue
        if doc.id in loaded:
            raise DuplicateAdrIdError(
                f"ADR id {doc.id!r} is declared by both {loaded[doc.id].path} and {path}"
            )
        loaded[doc.id] = doc
    return loaded


__all__ = ["AdrDocument", "parse_adr", "adr_dir", "load_adrs", "DuplicateAdrIdError"]
