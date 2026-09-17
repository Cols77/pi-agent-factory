"""Contract nodes, typed edges and contract findings for the trace graph.

Task 5 of the optional-contract-artifacts plan: make declared contracts
inspectable in the existing ``coherence trace`` graph by composing the contract
compiler's closure (``coherence.contracts.compiler.compile_contracts``) into
``build_graph`` -- in every surface except ordering, this module is a pure,
deterministic projection of that closure.

The contract contributions deliberately do NOT touch ``model.load_nodes``
(which stays a JSON/markdown-family globber) or ``gaps.find_gaps`` (which
remains node-family-agnostic and adds nothing for ``contract`` nodes). They are
composed separately in :func:`coherence.trace.graph.build_graph`, so a project
without a catalog (``closure.present`` is False) is byte-identical to the
pre-contract graph.

Three projections are exposed:

* :func:`contract_nodes` -- one ``contract:<id>`` node per *present* accepted
  declaration (the compiler already records which declarations resolved to a
  real file in ``closure.nodes``), in ``closure.declarations`` order.
* :func:`contract_edges` -- each compiler ``ContractEdge`` mapped to a trace
  ``Edge``, de-duplicated and sorted by ``(src, dst, kind)``.
* :func:`contract_gaps` -- the four contract-specific findings, computed from
  declarations and compiler diagnostics, sorted by ``(_KIND_ORDER[kind],
  node_id)``.

Contract-endpoint IDs in compiler edges are the declaration's bare id (the
compiler emits ``FIX``, not ``contract:FIX``); the graph nodes are keyed
``contract:<id>``, so :func:`contract_edges` prefixes a bare endpoint that
matches a declaration id. Endpoints that already carry a surface prefix
(``code:``, ``test:``, ``spec:``) and the ``references`` target that the
compiler already emitted as ``code:<path>``/bare-id are passed through
unchanged.

The freshness-class findings (stale consumer, stale fixture, unavailable
validation) are task 7's scope and are intentionally not computed here.
"""

from __future__ import annotations

from pathlib import Path

from coherence.contracts.model import (
    CODE_FILE_MISSING,
    CODE_REFERENCE_BROKEN,
    ContractClosure,
)
from coherence.trace.gaps import Gap, _KIND_ORDER
from coherence.trace.model import Edge, Node

__all__ = ["contract_nodes", "contract_edges", "contract_gaps"]


def contract_nodes(closure: ContractClosure, root: Path) -> list[Node]:
    """Return a ``contract:<id>`` Node per present accepted declaration.

    ``closure`` must be compiled (see ``compile_contracts``); only declarations
    the compiler resolved to a real file ("resolved presence", the ids in
    ``closure.nodes``) become graph nodes. A declaration whose file is missing
    is reported by :func:`contract_gaps` instead of being staged as a Node that
    pretends the artifact exists. Order is ``closure.declarations`` order
    (already deterministic).
    """
    root = Path(root)
    present_ids = {node.id for node in closure.nodes}
    nodes: list[Node] = []
    for declaration in closure.declarations:
        if declaration.id not in present_ids:
            continue
        nodes.append(
            Node(
                id=f"contract:{declaration.id}",
                kind="contract",
                title=declaration.id,
                path=root / declaration.path,
            )
        )
    return nodes


def contract_edges(closure: ContractClosure) -> list[Edge]:
    """Map compiler ``ContractEdge``-s to trace edges, deduped and sorted.

    A compiler edge endpoint that is a bare declaration id is promoted to
    ``contract:<id>`` so the edge connects the graph's contract nodes; an
    endpoint that already carries a surface prefix (``code:`` / ``test:`` /
    ``spec:``) is passed through as-is.
    """
    declaration_ids = {declaration.id for declaration in closure.declarations}

    def _qualify(endpoint: str) -> str:
        if endpoint in declaration_ids:
            return f"contract:{endpoint}"
        return endpoint

    edges: list[Edge] = []
    seen: set[Edge] = set()
    for compiled in closure.edges:
        edge = Edge(
            src=_qualify(compiled.src),
            dst=_qualify(compiled.dst),
            kind=compiled.kind,  # type: ignore[arg-type]
        )
        if edge in seen:
            continue
        seen.add(edge)
        edges.append(edge)
    edges.sort(key=lambda edge: (edge.src, edge.dst, edge.kind))
    return edges


def _consumer_file_present(
    declaration: object, root: Path, by_id: dict[str, object]
) -> bool:
    """Whether any declared consumer resolves to an existing file.

    ``code``/``test`` consumers name a repository-relative file directly; a
    ``contract`` consumer resolves through that declaration's own declared
    path. ``spec`` consumers name an id (no file path at this layer), so they
    are not evidence of a present file.
    """
    for consumer in declaration.consumers:
        if consumer.kind in ("code", "test"):
            if (root / consumer.target).is_file():
                return True
        elif consumer.kind == "contract":
            target = by_id.get(consumer.target)
            if target is not None and (root / target.path).is_file():
                return True
    return False


def _missing_consumer_paths(declaration: object, root: Path) -> list[str]:
    """The declared ``code``/``test`` consumer paths with no file on disk."""
    missing: list[str] = []
    for consumer in declaration.consumers:
        if consumer.kind not in ("code", "test"):
            continue
        if not (root / consumer.target).is_file():
            missing.append(consumer.target)
    return missing


def contract_gaps(closure: ContractClosure, root: Path) -> list[Gap]:
    """Return the four contract findings for ``closure``, deterministically.

    ``contract_reference_broken`` and ``contract_file_missing`` are grounded in
    the compiler's diagnostics (never re-derived from a file merely existing --
    a contract is never "covered" just because its file is present). The other
    two are computed from the declaration's declared relationships. Detail
    strings name the declaration id and its exact repo-relative path.
    """
    root = Path(root)
    by_id = {declaration.id: declaration for declaration in closure.declarations}
    reference_broken: set[str] = {
        diagnostic.declaration_id
        for diagnostic in closure.diagnostics
        if diagnostic.code == CODE_REFERENCE_BROKEN
    }
    file_missing: set[str] = {
        diagnostic.declaration_id
        for diagnostic in closure.diagnostics
        if diagnostic.code == CODE_FILE_MISSING
    }
    message_by_declaration: dict[str, list[str]] = {}
    for diagnostic in closure.diagnostics:
        message_by_declaration.setdefault(diagnostic.declaration_id, []).append(
            diagnostic.message
        )

    gaps: list[Gap] = []
    for declaration in closure.declarations:
        node_id = f"contract:{declaration.id}"
        path = declaration.path
        if (
            declaration.authority is None
            and declaration.validates_against is None
            and not declaration.consumers
        ):
            gaps.append(
                Gap(
                    node_id,
                    "contract_missing_provenance",
                    f"contract {declaration.id!r} ({path}) has no authority, no "
                    "validates_against and no consumers; its provenance is unreadable",
                )
            )
        if declaration.id in reference_broken:
            ref_detail = " ".join(message_by_declaration.get(declaration.id, ()))
            gaps.append(
                Gap(
                    node_id,
                    "contract_reference_broken",
                    f"contract {declaration.id!r} ({path}) carries a broken reference: "
                    f"{ref_detail}".strip(),
                )
            )
        if declaration.id in file_missing:
            gaps.append(
                Gap(
                    node_id,
                    "contract_file_missing",
                    f"contract {declaration.id!r} declares a file at "
                    f"{path!r} that does not exist at the resolved location",
                )
            )
        if declaration.consumers:
            if not _consumer_file_present(declaration, root, by_id):
                missing = _missing_consumer_paths(declaration, root)
                gaps.append(
                    Gap(
                        node_id,
                        "contract_missing_consumer",
                        f"contract {declaration.id!r} ({path}) declares consumers "
                        f"but none has a file at its resolved location: "
                        f"{', '.join(missing) if missing else 'no resolvable consumer file'}",
                    )
                )
        elif declaration.validates_against is None and declaration.authority is None:
            gaps.append(
                Gap(
                    node_id,
                    "contract_missing_consumer",
                    f"contract {declaration.id!r} ({path}) has no consumers, no "
                    "validates_against and no authority",
                )
            )

    gaps.sort(key=lambda gap: (_KIND_ORDER[gap.kind], gap.node_id))
    return gaps