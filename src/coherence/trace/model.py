from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import frontmatter

from coherence.deferrals import parse_deferral

NodeKind = Literal[
    "br",
    "sr",
    "spec",
    "plan",
    "task",
    "adr",
    "feat",
    "metric",
    "goal",
    "run",
    "diag",
]

_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


class SpecError(ValueError):
    """Deterministic failure for an invalid frontmatter-authoritative spec.

    Raised when a spec's frontmatter is missing a required field, when two
    spec documents declare the same canonical id with differing content, or
    when a plan/spec relation references a spec id that has no node.
    """


_SPEC_REQUIRED_FIELDS = ("id", "title", "status")


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind
    title: str
    path: Path
    exempt: bool = False
    deferred: str | None = None
    proposed: bool = False
    diagram_file: str | None = None
    scope_error: str | None = None
    migration_hint: str | None = None


def _load_post(path: Path) -> frontmatter.Post | None:
    # A malformed artifact must degrade to a filename-labelled node, never crash the
    # whole graph -- same contract doc-lister.ts:26 already honours on the TS side.
    try:
        return frontmatter.load(str(path))
    except Exception:
        return None


def _disposition(meta: dict) -> tuple[bool, str | None]:
    exempt = bool(meta.get("trace_exempt", False))
    deferred = meta.get("trace_deferred")
    if deferred is None:
        return exempt, None
    # Reader-first migration (Inc 6 Task 3): both the legacy scalar and
    # structured dict form of trace_deferred render the SAME present deferral
    # (its reason); a malformed value is rejected, not silently treated as
    # current.
    return exempt, parse_deferral(deferred).reason


def _first_heading(text: str, fallback: str) -> str:
    match = _HEADING_RE.search(text)
    return match.group(1).strip() if match else fallback


_JUSTIFICATION_KINDS = (
    "satisfies", "corrects", "mitigates", "implements", "maintains", "explores",
)
JUSTIFICATION_EDGE_KINDS: frozenset[str] = frozenset(_JUSTIFICATION_KINDS)


def _justification_scope_error(meta: dict) -> str | None:
    """Mirrors substrate.ledger.tasks._parse_justification's shape/kind checks,
    independently -- this module never imports substrate.ledger.tasks (stays a
    pure frontmatter reader; extract_edges/load_nodes must work without it).
    """
    raw = meta.get("justification")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return "justification must be a list of single-key {kind: target_id} mappings"
    for entry in raw:
        if not isinstance(entry, dict) or len(entry) != 1:
            return f"each justification entry must be a single {{kind: target_id}} mapping, got {entry!r}"
        ((kind, _target_id),) = entry.items()
        if kind not in _JUSTIFICATION_KINDS:
            return f"unknown justification kind {kind!r} (have {_JUSTIFICATION_KINDS})"
    return None


def _id_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    if post is None or "id" not in post.metadata:
        return Node(id=path.name, kind=kind, title=path.name, path=path)
    exempt, deferred = _disposition(post.metadata)
    scope_error = _justification_scope_error(post.metadata) if kind == "task" else None
    return Node(
        id=str(post.metadata["id"]),
        kind=kind,
        title=str(post.metadata.get("title", path.name)),
        path=path,
        exempt=exempt,
        deferred=deferred,
        # The absence of a binding IS the proposed state -- read here rather than
        # from the register so build_graph never loads config or imports target code.
        proposed=kind == "sr" and "binding" not in post.metadata,
        diagram_file=str(post.metadata["diagram_file"])
        if kind == "diag" and "diagram_file" in post.metadata
        else None,
        scope_error=scope_error,
    )


def _file_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    if post is not None:
        body = post.content
    else:
        # `_load_post` already degraded a malformed/undecodable file to `None`
        # rather than raising (see its own contract comment above) -- this
        # fallback read must honour the same contract, not reopen the file
        # unguarded and crash the whole graph on one bad spec/plan.
        body = _read_text_or_empty(path)
    meta = post.metadata if post is not None else {}
    exempt, deferred = _disposition(meta)
    return Node(
        id=f"{kind}:{path.name}",
        kind=kind,
        title=_first_heading(body, path.name),
        path=path,
        exempt=exempt,
        deferred=deferred,
    )


def _legacy_spec_node(path: Path) -> Node:
    """A spec file with no frontmatter id degrades to a filename-derived node.

    Compatibility shim for specs that predate the frontmatter-authoritative
    scheme: still readable, still addressable as ``spec:<filename>``, but it
    carries a diagnostic/migration hint so a reader knows it is a legacy node.
    """
    post = _load_post(path)
    if post is not None:
        body = post.content
        meta = post.metadata
    else:
        body = _read_text_or_empty(path)
        meta = {}
    exempt, deferred = _disposition(meta)
    hint = (
        "legacy filename-derived spec node; migration hint: add "
        "frontmatter (id, title, status) to promote to a canonical spec:<id> node"
    )
    return Node(
        id=f"spec:{path.name}",
        kind="spec",
        title=_first_heading(body, path.name),
        path=path,
        exempt=exempt,
        deferred=deferred,
        migration_hint=hint,
    )


def _frontmatter_spec_node(path: Path) -> Node:
    """Parse a spec whose id comes from its YAML frontmatter (canonical source).

    ``id``, ``title`` and ``status`` are all required; a missing field is a
    deterministic failure, never a silent filename fallback.
    """
    post = _load_post(path)
    if post is None:
        # Undecodable/malformed frontmatter is NOT a valid frontmatter spec.
        raise SpecError(f"{path.name}: spec frontmatter is unreadable")
    meta = post.metadata
    missing = [field for field in _SPEC_REQUIRED_FIELDS if not meta.get(field)]
    if missing:
        raise SpecError(
            f"{path.name}: spec frontmatter missing required field(s): "
            f"{', '.join(missing)}"
        )
    exempt, deferred = _disposition(meta)
    return Node(
        id=f"spec:{meta['id']}",
        kind="spec",
        title=str(meta["title"]),
        path=path,
        exempt=exempt,
        deferred=deferred,
    )


def _has_frontmatter_block(path: Path) -> bool:
    """Whether ``path`` carries a leading frontmatter delimiter block.

    ``frontmatter.load`` collapses a genuine no-frontmatter file and an
    explicit empty ``---`` block to the same empty metadata dict, so the two are
    indistinguishable from parsed metadata. Ask the YAML handler directly
    whether the raw text actually splits on a frontmatter delimiter: a file
    that carries a block (even an empty or malformed one) is a
    frontmatter-bearing spec and must never degrade to a legacy filename node.
    """
    text = _read_text_or_empty(path).strip()
    handler = frontmatter.detect_format(text, frontmatter.handlers)
    if handler is None:
        return False
    try:
        handler.split(text)
    except ValueError:
        return False
    return True


def _spec_node(path: Path) -> Node:
    """Load a spec node, honouring the frontmatter-authoritative contract.

    A spec carrying frontmatter is validated against the required fields
    (``id``/``title``/``status``) and becomes the canonical node ``spec:<id>``;
    a missing required field (or undecodable frontmatter) is a deterministic
    error. Only a spec with NO frontmatter block at all is treated as a legacy
    filename-derived node (with a migration hint).
    """
    if not _has_frontmatter_block(path):
        return _legacy_spec_node(path)
    return _frontmatter_spec_node(path)


def _glob(root: Path, *parts: str, pattern: str) -> list[Path]:
    directory = root.joinpath(*parts)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(pattern))


def load_nodes(root: Path) -> list[Node]:
    nodes: list[Node] = []
    for path in _glob(root, "requirements", pattern="SR-*.md"):
        nodes.append(_id_node(path, "sr"))
    for path in _glob(root, "requirements", pattern="BR-*.md"):
        nodes.append(_id_node(path, "br"))
    for path in _glob(root, "docs", "features", pattern="FEAT-*.md"):
        nodes.append(_id_node(path, "feat"))
    for path in _glob(root, "docs", "diagrams", pattern="DIAG-*.md"):
        nodes.append(_id_node(path, "diag"))
    for path in _glob(root, "metrics", pattern="MET-*.md"):
        nodes.append(_id_node(path, "metric"))
    for path in _glob(root, "goals", pattern="GOAL-*.md"):
        nodes.append(_id_node(path, "goal"))
    for path in _glob(root, "tasks", pattern="T-*.md"):
        nodes.append(_id_node(path, "task"))
    for path in _glob(root, "docs", "superpowers", "plans", pattern="*.md"):
        nodes.append(_file_node(path, "plan"))

    # Increment 8 Task 1: specs are frontmatter-authoritative. A spec whose
    # frontmatter declares an id becomes the canonical node spec:<id>; a spec
    # without a frontmatter id stays a legacy filename-derived node carrying a
    # migration hint. Duplicate canonical ids with differing content fail
    # deterministically; identical duplicates are deduped.
    spec_ids: dict[str, tuple[Path, str]] = {}
    for path in _glob(root, "docs", "superpowers", "specs", pattern="*.md"):
        node = _spec_node(path)
        if node.migration_hint is None and node.id in spec_ids:
            prev_path, prev_content = spec_ids[node.id]
            current = _read_text_or_empty(path)
            if prev_content != current:
                raise SpecError(
                    f"duplicate spec id {node.id!r}: "
                    f"{prev_path.name} and {path.name} declare it with differing content"
                )
            continue
        spec_ids.setdefault(node.id, (path, _read_text_or_empty(path)))
        nodes.append(node)
    return nodes


EdgeKind = Literal[
    "source_plan",
    "satisfies",
    "upstream",
    "relates_to",
    "spec_ref",
    "parent_of",
    "verified_by",
    "demonstrates",
    "evaluates",
    "contains",
    "illustrates",
    # Typed lifecycle relationships (spec §4): intent, design, assurance, change.
    "derives",
    "decomposes",
    "refines",
    "allocates",
    "implements",
    "verifies",
    "validates",
    "mitigates",
    "evidences",
    "corrects",
    "impacts",
    "supersedes",
    # Task-justification-only kinds (substrate.ledger.tasks._JUSTIFICATION_KINDS)
    # that spec §4's lifecycle list does not itself name -- added so every
    # legal justification entry maps to a real edge kind (see Task 7 Decision 1).
    "maintains",
    "explores",
]

_SPEC_REF_RE = re.compile(r"docs/superpowers/specs/([A-Za-z0-9._-]+\.md)")


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: EdgeKind


def as_str_list(value: object) -> list[str]:
    """Coerce a frontmatter field that may be absent, scalar, or a list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _verified_by_edges(src_id: str, meta: dict) -> list[Edge]:
    """``verified_by`` carries two different shapes under the same key, on
    any node kind (including ``sr``): the pre-existing string-list graph
    edge (e.g. ``verified_by: [T-001]``, an SR/task/etc pointing at the
    task or run that verified it -- see tests/unit/system/test_vcycle.py's
    ``verified_by: [T-SUBSYSTEM]`` fixture) and the SR-050 canonical
    structured relation (``verified_by: [{path: ..., test: ...}, ...]``,
    resolved by ``coherence.register.relations.resolve_sr_relations``, a
    typed reference to a validation artifact, not a graph edge to another
    node at all).

    The two are told apart by the shape of each entry, not by node kind --
    an SR can legitimately carry the legacy string form (as the fixtures
    above show) so gating on ``node_kind == "sr"`` alone silently drops
    real edges. A dict entry is always the structured relation and is
    skipped here (reading it with ``as_str_list`` would stringify it, e.g.
    ``"{'path': ..., 'test': ...}"``, into a bogus edge target and surface
    as a spurious dangling-reference finding); a string entry is always the
    legacy edge and is kept. ``implemented_by`` needs no such guard: it is
    not read as a generic edge field at all.
    """
    raw = meta.get("verified_by")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [Edge(src_id, str(dst), "verified_by") for dst in raw if not isinstance(dst, dict)]


def edges_from_frontmatter(src_id: str, meta: dict, node_kind: NodeKind | None = None) -> list[Edge]:
    """Return declared V-cycle relationship edges without resolving their endpoints.

    ``node_kind`` is accepted for caller-signature stability but no longer
    gates any behaviour here: see ``_verified_by_edges`` for why the
    ``verified_by`` shape is now detected per entry instead.
    """
    del node_kind
    edges: list[Edge] = []
    for dst in as_str_list(meta.get("parent_of")):
        edges.append(Edge(src_id, dst, "parent_of"))
    for parent in as_str_list(meta.get("child_of")):
        edges.append(Edge(parent, src_id, "parent_of"))
    edges.extend(_verified_by_edges(src_id, meta))
    edge_fields: tuple[tuple[str, EdgeKind], ...] = (
        ("demonstrates", "demonstrates"),
        ("evaluates", "evaluates"),
        ("contains", "contains"),
        ("illustrates", "illustrates"),
    )
    for field, kind in edge_fields:
        for dst in as_str_list(meta.get(field)):
            edges.append(Edge(src_id, dst, kind))
    return edges


def _edges_from_justification(node_id: str, meta: dict) -> list[Edge]:
    """Task-node justification edges (spec §4 "typed task justification").
    Legacy `satisfies:` frontmatter with no `justification:` key is read as
    shorthand for `justification: [{satisfies: ...}]`, producing byte-
    identical `satisfies` edges to before this change. A malformed or
    unsupported-kind entry produces no edge here -- it is already recorded on
    the node as `scope_error` by `_id_node`/`_justification_scope_error`."""
    raw = meta.get("justification")
    if raw is None:
        return [Edge(node_id, sr_id, "satisfies") for sr_id in as_str_list(meta.get("satisfies"))]
    if not isinstance(raw, list):
        return []
    edges: list[Edge] = []
    for entry in raw:
        if not isinstance(entry, dict) or len(entry) != 1:
            continue
        ((kind, target_id),) = entry.items()
        if kind not in _JUSTIFICATION_KINDS:
            continue
        edges.append(Edge(node_id, str(target_id), kind))  # type: ignore[arg-type]
    return edges


def extract_edges(root: Path, nodes: list[Node]) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[Edge] = set()

    def add(edge: Edge) -> None:
        if edge not in seen:
            seen.add(edge)
            edges.append(edge)

    for node in nodes:
        if node.kind in ("task", "sr", "br"):
            post = _load_post(node.path)
            if post is None:
                continue
            meta = post.metadata
            source_plan = meta.get("source_plan")
            if source_plan:
                add(Edge(node.id, f"plan:{Path(str(source_plan)).name}", "source_plan"))
            if node.kind == "task":
                for edge in _edges_from_justification(node.id, meta):
                    add(edge)
            else:
                for sr_id in as_str_list(meta.get("satisfies")):
                    add(Edge(node.id, sr_id, "satisfies"))
            for upstream_id in as_str_list(meta.get("upstream")):
                add(Edge(node.id, upstream_id, "upstream"))
            if node.kind == "sr":
                # SR-057: `relates_to` lives on a requirement's own
                # frontmatter only (br/task never declare it) -- a flat list
                # of ids from any artifact family (`spec:<id>`-prefixed,
                # bare `SR-NNN`/`FEAT-NNN`), read literally with no per-kind
                # transform, matching how `upstream` is already read above.
                for target_id in as_str_list(meta.get("relates_to")):
                    add(Edge(node.id, target_id, "relates_to"))
            for edge in edges_from_frontmatter(node.id, meta, node.kind):
                add(edge)
        elif node.kind in ("feat", "metric", "goal", "run", "diag"):
            post = _load_post(node.path)
            if post is None:
                continue
            if node.kind == "feat":
                for requirement_id in as_str_list(post.metadata.get("requirements")):
                    add(Edge(node.id, requirement_id, "contains"))
            elif node.kind == "goal":
                for requirement_id in as_str_list(post.metadata.get("requirements")):
                    add(Edge(node.id, requirement_id, "demonstrates"))
                metric_id = post.metadata.get("metric")
                if isinstance(metric_id, str):
                    add(Edge(node.id, metric_id, "evaluates"))
            for edge in edges_from_frontmatter(node.id, post.metadata, node.kind):
                add(edge)
        elif node.kind == "plan":
            post = _load_post(node.path)
            meta = post.metadata if post is not None else {}
            spec_nodes = {n.id: n for n in nodes if n.kind == "spec"}
            # Canonical frontmatter spec refs (`spec:` field naming a spec id)
            # are the primary check: a relation to an unknown spec id is a
            # deterministic failure, never a silent dangling edge.
            for ref in as_str_list(meta.get("spec")):
                target = str(ref) if str(ref).startswith("spec:") else f"spec:{ref}"
                if target not in spec_nodes:
                    raise SpecError(
                        f"plan {node.id} references unknown spec id {ref!r}"
                    )
                add(Edge(node.id, target, "spec_ref"))
            # Legacy body references resolve against real spec nodes by
            # filename so the edge targets the canonical (or legacy) node id,
            # never a bare literal path. A path to a spec that has no node
            # still renders its legacy filename id (dangling, as before).
            body = post.content if post is not None else _read_text_or_empty(node.path)
            spec_by_filename = {n.path.name: n.id for n in nodes if n.kind == "spec"}
            for filename in _SPEC_REF_RE.findall(body):
                add(
                    Edge(
                        node.id,
                        spec_by_filename.get(filename, f"spec:{filename}"),
                        "spec_ref",
                    )
                )

    return edges
