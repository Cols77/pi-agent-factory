from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from coherence.course.parser import CourseNote, is_node_id, load_course_notes
from coherence.trace.graph import build_graph


def _graph_id(ref: str) -> str:
    """Map a course node-id reference to the coherence graph node id.

    SR ids are already bare in the graph (``SR-001``). A ``SPEC-...`` course
    reference addresses the frontmatter spec node ``spec:<id>``.
    """
    if ref.startswith("SPEC-"):
        return f"spec:{ref[len('SPEC-'):]}"
    return ref


@dataclass
class CourseReport:
    """Result of ``check_course``. ``ok`` is true only when there are no
    errors and every known SR/spec node is reached by some course note."""

    notes: list[CourseNote] = field(default_factory=list)
    unreached: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.unreached

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "notes": [
                {
                    "path": str(n.path),
                    "refs": sorted(n.refs),
                    "frontmatter": sorted(set(n.frontmatter_refs)),
                    "body": sorted(set(n.body_refs)),
                }
                for n in self.notes
            ],
            "unreached": list(self.unreached),
            "errors": list(self.errors),
        }


def check_course(root: Path) -> CourseReport:
    """Validate every course note against the coherence traceability graph.

    Pure and stateless: builds the same graph ``trace check`` uses, resolves
    each course reference against it (unknown/malformed refs are errors), and
    reports which known SR/spec nodes no course note reaches. Never writes
    beside the notes.
    """
    graph = build_graph(root)
    known_ids = {n.id for n in graph.nodes}
    known_sr_spec = sorted(
        n.id for n in graph.nodes if n.kind in ("sr", "spec")
    )

    notes = load_course_notes(root)
    covered: set[str] = set()
    errors: list[str] = []

    for note in notes:
        rel = str(note.path.relative_to(root))
        errors.extend(note.errors)
        for ref in note.frontmatter_refs:
            if not is_node_id(ref):
                # guard against malformed entries the parser already flagged
                continue
            gid = _graph_id(ref)
            if gid not in known_ids:
                errors.append(f"{rel}: traceability references unknown node {ref!r}")
            else:
                covered.add(gid)
        for ref in note.body_refs:
            gid = _graph_id(ref)
            if gid not in known_ids:
                errors.append(f"{rel}: wikilink references unknown node [[{ref}]]")
            else:
                covered.add(gid)

    unreached = [nid for nid in known_sr_spec if nid not in covered]
    return CourseReport(notes=notes, unreached=unreached, errors=errors)


__all__ = ["CourseNote", "CourseReport", "check_course"]