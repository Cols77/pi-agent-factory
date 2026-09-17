"""Unit tests for deterministic contract compilation (optional-contract-artifacts task 4).

The compiler turns the parsed closure into a normalized dependency closure with
transitive fingerprints. It is deterministic (never globs the filesystem),
dependency-ordered (a transitive local `$ref` change invalidates the referencing
contract's compiled fingerprint), and fail-closed (cycles, network URLs and
non-file URI schemes are reported, never silently followed).

Evidence for SR-075:
  * AC-1: transitive `$ref` change alters a root contract's compiled fingerprint
          without that root's own bytes changing, and the references edges that
          produced it are recorded.
  * AC-2: node ordering and every fingerprint are stable across repeated
          compilations and across differing declaration order.
  * AC-3: a cycle, network URL or non-file URI scheme is rejected as a reported
          diagnostic and never silently followed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coherence.contracts.catalog import load_contract_catalog
from coherence.contracts.compiler import CONTRACT_EDGE_KINDS, compile_contracts
from coherence.contracts.model import (
    CODE_DECLARATION_INVALID,
    CODE_FILE_MISSING,
    CODE_REFERENCE_BROKEN,
    CODE_REFERENCE_CYCLE,
    ContractClosure,
    ContractDeclaration,
    ContractRelation,
    parse_catalog,
)

pytestmark = pytest.mark.unit


def _contract(**overrides: object) -> dict[str, object]:
    """A minimal, valid json_schema declaration; override fields per test."""
    entry: dict[str, object] = {
        "id": "WIRE-API",
        "path": "docs/wire.schema.json",
        "kind": "json_schema",
        "status": "active",
    }
    entry.update(overrides)
    return entry


def _document(*contracts: dict[str, object]) -> dict[str, object]:
    return {"schema": "coherence.contract-catalog.v1", "contracts": list(contracts)}


def _write_catalog(root: Path, document: object) -> None:
    import json

    catalog_file = root / ".factory" / "contracts.yaml"
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    catalog_file.write_text(json.dumps(document), encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    return root


def _write_file(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _compile(
    tmp_path: Path,
    contracts: tuple[dict[str, object], ...],
    files: dict[str, str],
) -> tuple[Path, ContractClosure]:
    """Write catalog + files, load, and compile. Returns (root, compiled)."""
    root = _project(tmp_path)
    _write_catalog(root, _document(*contracts))
    for rel, content in files.items():
        _write_file(root, rel, content)
    return root, compile_contracts(load_contract_catalog(root), root)


def _node(compiled: ContractClosure, identifier: str) -> object:
    return next(node for node in compiled.nodes if node.id == identifier)


def _edge_kinds(compiled: ContractClosure, src: str, dst: str) -> list[str]:
    return sorted(
        edge.kind for edge in compiled.edges if edge.src == src and edge.dst == dst
    )


def _codes(compiled: ContractClosure) -> list[str]:
    return [str(diagnostic.code) for diagnostic in compiled.diagnostics]


def _recompile(root: Path) -> ContractClosure:
    return compile_contracts(load_contract_catalog(root), root)


# ---------------------------------------------------------------------------
# Stable ordering, basic edges, non-JSON artifacts (SR-075 / AC-2 baseline)
# ---------------------------------------------------------------------------


def test_compiled_closure_carries_ordered_nodes_and_sorted_edges(tmp_path: Path) -> None:
    _, compiled = _compile(
        tmp_path,
        (
            _contract(id="ZED", path="z.schema.json"),
            _contract(id="ALPHA", path="a.schema.json"),
        ),
        {
            "z.schema.json": '{"type": "object"}',
            "a.schema.json": '{"type": "object"}',
        },
    )
    assert [node.id for node in compiled.nodes] == ["ALPHA", "ZED"]
    assert all(node.closure_fingerprint == node.content_fingerprint for node in compiled.nodes)
    assert CONTRACT_EDGE_KINDS == (
        "defines",
        "consumed_by",
        "validated_by",
        "validates_against",
        "references",
    )


@pytest.mark.sr("SR-075")
def test_sr075_ac2_repeat_compilation_is_byte_identical(tmp_path: Path) -> None:
    contracts = (
        _contract(id="ROOT", path="api/root.schema.json"),
        _contract(id="A", path="shared/a.schema.json"),
    )
    files = {
        "api/root.schema.json": '{"$ref": "../shared/a.schema.json"}',
        "shared/a.schema.json": '{"type": "object"}',
    }
    root = _project(tmp_path)
    _write_catalog(root, _document(*contracts))
    for rel, content in files.items():
        _write_file(root, rel, content)

    first = compile_contracts(load_contract_catalog(root), root)
    second = compile_contracts(load_contract_catalog(root), root)

    assert [node.id for node in first.nodes] == [node.id for node in second.nodes]
    assert [node.deps for node in first.nodes] == [node.deps for node in second.nodes]
    assert [node.closure_fingerprint for node in first.nodes] == [
        node.closure_fingerprint for node in second.nodes
    ]
    assert [(e.src, e.dst, e.kind) for e in first.edges] == [
        (e.src, e.dst, e.kind) for e in second.edges
    ]


@pytest.mark.sr("SR-075")
def test_sr075_ac2_output_is_identical_across_declaration_order(tmp_path: Path) -> None:
    # Differing declaration order (a proxy for differing enumeration order) must
    # not change the compiled closure: nodes/deps/fingerprints/edges are canonical.
    root = _project(tmp_path)
    files = {
        "api/root.schema.json": '{"$ref": "../shared/a.schema.json"}',
        "shared/a.schema.json": '{"title": "A"}',
    }
    for rel, content in files.items():
        _write_file(root, rel, content)

    def declaration(identifier: str, path: str, state: str) -> ContractDeclaration:
        return ContractDeclaration(
            id=identifier,
            path=path,
            kind="json_schema",
            status=state,
            consumers=(ContractRelation(kind="test", target="tests/x.py", raw="test:tests/x.py"),),
        )

    forward = parse_catalog(
        _document(
            {"id": "ROOT", "path": "api/root.schema.json", "kind": "json_schema"},
            {"id": "A", "path": "shared/a.schema.json", "kind": "json_schema"},
        )
    )
    # Build closure manually with the reverse declaration order.
    reversed_doc = _document(
        {"id": "A", "path": "shared/a.schema.json", "kind": "json_schema"},
        {"id": "ROOT", "path": "api/root.schema.json", "kind": "json_schema"},
    )
    reversed_closure = parse_catalog(reversed_doc)

    compiled_forward = compile_contracts(forward, root)
    compiled_reversed = compile_contracts(reversed_closure, root)

    assert [node.id for node in compiled_forward.nodes] == [
        node.id for node in compiled_reversed.nodes
    ]
    assert [node.deps for node in compiled_forward.nodes] == [
        node.deps for node in compiled_reversed.nodes
    ]
    assert [node.closure_fingerprint for node in compiled_forward.nodes] == [
        node.closure_fingerprint for node in compiled_reversed.nodes
    ]
    assert [(e.src, e.dst, e.kind) for e in compiled_forward.edges] == [
        (e.src, e.dst, e.kind) for e in compiled_reversed.edges
    ]


def test_non_json_schema_artifact_receives_only_its_own_hash(tmp_path: Path) -> None:
    contracts = (
        _contract(id="FIX", path="fixtures/seed.json", kind="fixture"),
        _contract(id="WIRE", path="docs/wire.schema.json"),
    )
    files = {
        "fixtures/seed.json": '{"$ref": "https://ignored.example/x.json", "a": 1}',
        "docs/wire.schema.json": '{"type": "object"}',
    }
    root = _project(tmp_path)
    _write_catalog(root, _document(*contracts))
    for rel, content in files.items():
        _write_file(root, rel, content)
    compiled = compile_contracts(load_contract_catalog(root), root)

    fixture = _node(compiled, "FIX")
    assert fixture.closure_fingerprint == fixture.content_fingerprint
    # $ref in fixture content is NOT traversed: no references edge, no broken diagnostic.
    assert CODE_REFERENCE_BROKEN not in _codes(compiled)
    assert _edge_kinds(compiled, "FIX", "https://ignored.example/x.json") == []


def test_declared_relationships_produce_edges(tmp_path: Path) -> None:
    contracts = (
        _contract(
            id="FIX",
            path="fixtures/seed.json",
            kind="fixture",
            validates_against="contract:WIRE",
            consumers=["code:backend/app.py", "test:tests/seed.py"],
            authority="spec:SPEC-1",
        ),
        _contract(id="WIRE", path="docs/wire.schema.json"),
    )
    files = {
        "fixtures/seed.json": '{"a": 1}',
        "docs/wire.schema.json": '{"type": "object"}',
    }
    root = _project(tmp_path)
    _write_catalog(root, _document(*contracts))
    for rel, content in files.items():
        _write_file(root, rel, content)
    compiled = compile_contracts(load_contract_catalog(root), root)

    assert _edge_kinds(compiled, "FIX", "WIRE") == ["validates_against"]
    assert _edge_kinds(compiled, "WIRE", "FIX") == ["validated_by"]
    assert _edge_kinds(compiled, "FIX", "code:backend/app.py") == ["consumed_by"]
    assert _edge_kinds(compiled, "FIX", "test:tests/seed.py") == ["consumed_by"]
    assert _edge_kinds(compiled, "spec:SPEC-1", "FIX") == ["defines"]


# ---------------------------------------------------------------------------
# Local JSON Schema $ref: edges, transitive fingerprints (SR-075 / AC-1)
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-075")
def test_sr075_ac1_transitive_dep_change_invalidates_root_without_root_changing(
    tmp_path: Path,
) -> None:
    contracts = (
        _contract(id="ROOT", path="api/root.schema.json"),
        _contract(id="A", path="shared/a.schema.json"),
        _contract(id="B", path="shared/b.schema.json"),
    )
    files = {
        "api/root.schema.json": '{"$ref": "../shared/a.schema.json"}',
        "shared/a.schema.json": '{"$ref": "b.schema.json"}',
        "shared/b.schema.json": '{"type": "object", "version": 1}',
    }
    root = _project(tmp_path)
    _write_catalog(root, _document(*contracts))
    for rel, content in files.items():
        _write_file(root, rel, content)

    first = compile_contracts(load_contract_catalog(root), root)
    root_before = _node(first, "ROOT")
    assert root_before.deps == ("shared/a.schema.json", "shared/b.schema.json")

    # References edges record the full source-to-target chain the closure came from.
    assert _edge_kinds(first, "ROOT", "A") == ["references"]
    assert _edge_kinds(first, "A", "B") == ["references"]

    # Mutate ONLY the transitive leaf B, then compile again.
    _write_file(root, "shared/b.schema.json", '{"type": "object", "version": 2}')
    second = _recompile(root)
    root_after = _node(second, "ROOT")
    a_after = _node(second, "A")

    # Root content fingerprint is unchanged (its own bytes did not move)...
    assert root_before.content_fingerprint == root_after.content_fingerprint
    # ...but its transitive compiled fingerprint changed because B did.
    assert root_before.closure_fingerprint != root_after.closure_fingerprint
    assert a_after.closure_fingerprint != root_before.closure_fingerprint


def test_local_ref_to_declared_contract_records_references_edge_and_deps(tmp_path: Path) -> None:
    contracts = (
        _contract(id="ROOT", path="api/root.schema.json"),
        _contract(id="A", path="defs/a.schema.json"),
    )
    files = {
        "api/root.schema.json": '{"$ref": "../defs/a.schema.json"}',
        "defs/a.schema.json": '{"type": "object"}',
    }
    root, compiled = _compile(tmp_path, contracts, files)

    root_node = _node(compiled, "ROOT")
    assert root_node.deps == ("defs/a.schema.json",)
    assert root_node.closure_fingerprint != root_node.content_fingerprint
    assert _edge_kinds(compiled, "ROOT", "A") == ["references"]


def test_local_ref_to_non_contract_file_records_code_references_edge(tmp_path: Path) -> None:
    contracts = (_contract(id="ROOT", path="api/root.schema.json"),)
    files = {
        "api/root.schema.json": '{"$ref": "../docs/note.json"}',
        "docs/note.json": '{"shared": true}',
    }
    root, compiled = _compile(tmp_path, contracts, files)

    root_node = _node(compiled, "ROOT")
    assert root_node.deps == ("docs/note.json",)
    assert _edge_kinds(compiled, "ROOT", "code:docs/note.json") == ["references"]


def test_fragment_intra_file_ref_is_not_a_dependency(tmp_path: Path) -> None:
    contracts = (_contract(id="ROOT", path="api/root.schema.json"),)
    files = {"api/root.schema.json": '{"$ref": "#/definitions/Foo", "definitions": {}}'}
    root, compiled = _compile(tmp_path, contracts, files)

    assert _node(compiled, "ROOT").deps == ()
    assert _edge_kinds(compiled, "ROOT", "#/definitions/Foo") == []


def test_duplicate_alias_refs_dedupe_by_resolved_path(tmp_path: Path) -> None:
    contracts = (_contract(id="ROOT", path="api/root.schema.json"),)
    files = {
        "api/root.schema.json": (
            '{"allOf": [{"$ref": "../defs/app.json"}, {"$ref": "./../defs/app.json"}]}'
        ),
        "defs/app.json": '{"type": "string"}',
    }
    root, compiled = _compile(tmp_path, contracts, files)

    node = _node(compiled, "ROOT")
    assert node.deps == ("defs/app.json",)
    # two aliases -> one references edge.
    assert len([e for e in compiled.edges if e.kind == "references"]) == 1


def test_invalid_json_is_a_syntax_diagnostic_over_content_hash(tmp_path: Path) -> None:
    contracts = (_contract(id="ROOT", path="api/root.schema.json"),)
    files = {"api/root.schema.json": '{"$ref": "defs/a.schema.json", '}
    root, compiled = _compile(tmp_path, contracts, files)

    assert CODE_DECLARATION_INVALID in _codes(compiled)
    node = _node(compiled, "ROOT")
    assert node.closure_fingerprint == node.content_fingerprint
    assert _edge_kinds(compiled, "ROOT", "A") == []


def test_missing_declared_file_is_skipped_by_compiler_with_its_own_diagnostic(
    tmp_path: Path,
) -> None:
    contracts = (
        _contract(id="ROOT", path="api/root.schema.json"),
        _contract(id="GHOST", path="api/ghost.schema.json"),
    )
    files = {"api/root.schema.json": '{"type": "object"}'}
    root = _project(tmp_path)
    _write_catalog(root, _document(*contracts))
    for rel, content in files.items():
        _write_file(root, rel, content)

    loaded = load_contract_catalog(root)
    # the catalog keeps the missing-file declaration with CODE_FILE_MISSING...
    assert CODE_FILE_MISSING in [str(d.code) for d in loaded.diagnostics]
    assert any(d.id == "GHOST" for d in loaded.declarations)

    compiled = compile_contracts(loaded, root)
    # ...but the compiler cannot hash it, so it emits no node.
    assert all(node.id != "GHOST" for node in compiled.nodes)
    assert CODE_FILE_MISSING in _codes(compiled)


# ---------------------------------------------------------------------------
# Fail-closed rejection: cycles and non-local references (SR-075 / AC-3)
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-075")
def test_sr075_ac3_cycle_is_reported_and_stabilizes(tmp_path: Path) -> None:
    contracts = (
        _contract(id="A", path="a.schema.json"),
        _contract(id="B", path="b.schema.json"),
    )
    files = {
        "a.schema.json": '{"$ref": "b.schema.json"}',
        "b.schema.json": '{"$ref": "a.schema.json"}',
    }
    root, compiled = _compile(tmp_path, contracts, files)

    assert CODE_REFERENCE_CYCLE in _codes(compiled)
    # Both nodes still compiled; nothing hangs or crashes.
    assert {node.id for node in compiled.nodes} == {"A", "B"}
    for node in compiled.nodes:
        assert node.closure_fingerprint.startswith("sha256:")


@pytest.mark.sr("SR-075")
def test_sr075_ac3_network_url_and_uri_scheme_are_rejected(tmp_path: Path) -> None:
    contracts = (_contract(id="ROOT", path="api/root.schema.json"),)
    files = {
        "api/root.schema.json": (
            '{"$ref": "https://example.com/x.schema.json"}'
        ),
    }
    root, compiled = _compile(tmp_path, contracts, files)

    assert CODE_REFERENCE_BROKEN in _codes(compiled)
    assert all("references" not in e.kind for e in compiled.edges)

    # Non-file URI scheme (URN), an absolute file:// URI and a UNC path are all
    # rejected the same way.
    contracts = (_contract(id="ROOT2", path="api/root2.schema.json"),)
    files = {
        "api/root2.schema.json": (
            '{"anyOf": [{"$ref": "urn:ietf:params:x"}, '
            '{"$ref": "file:///etc/passwd"}, '
            '{"$ref": "C:/defs/win.json"}, '
            '{"$ref": "//host/share/x.json"}]}'
        ),
    }
    _, compiled2 = _compile(tmp_path, contracts, files)
    assert CODE_REFERENCE_BROKEN in _codes(compiled2)
    assert all("references" not in e.kind for e in compiled2.edges)


# ---------------------------------------------------------------------------
# SR-075 regression: $ref base = containing file's directory, in-tree '..' OK
# ---------------------------------------------------------------------------


@pytest.mark.sr("SR-075")
def test_sr075_t1_same_directory_ref_resolves_relative_to_containing_file(
    tmp_path: Path,
) -> None:
    # A catalog declares A at shared/a.schema.json whose content is {"$ref":
    # "b.schema.json"} and B at shared/b.schema.json. The ref is same-directory,
    # so it MUST resolve to shared/b.schema.json (not root/b.schema.json).
    contracts = (
        _contract(id="B", path="shared/b.schema.json"),
        _contract(id="A", path="shared/a.schema.json"),
    )
    files = {
        "shared/a.schema.json": '{"$ref": "b.schema.json"}',
        "shared/b.schema.json": '{"type": "object", "version": 1}',
    }
    root, compiled = _compile(tmp_path, contracts, files)

    assert CODE_REFERENCE_BROKEN not in _codes(compiled)
    assert _edge_kinds(compiled, "A", "B") == ["references"]
    a_node = _node(compiled, "A")
    assert a_node.deps == ("shared/b.schema.json",)
    assert a_node.closure_fingerprint != a_node.content_fingerprint

    # Transitive closure: changing B changes A's compiled fingerprint.
    _write_file(root, "shared/b.schema.json", '{"type": "object", "version": 2}')
    second = _recompile(root)
    assert a_node.closure_fingerprint != _node(second, "A").closure_fingerprint


@pytest.mark.sr("SR-075")
def test_sr075_t2_cross_directory_in_tree_parent_ref_resolves_and_chains(
    tmp_path: Path,
) -> None:
    # ROOT at api/root.schema.json holds {"$ref": "../shared/a.schema.json"}.
    # The '..' stays in-tree (shared/ is under the repo root) so it is legal:
    # it must resolve to shared/a.schema.json, emit references ROOT->A, and the
    # transitive closure must reach B (shared/a refs shared/b).
    contracts = (
        _contract(id="B", path="shared/b.schema.json"),
        _contract(id="A", path="shared/a.schema.json"),
        _contract(id="ROOT", path="api/root.schema.json"),
    )
    files = {
        "api/root.schema.json": '{"$ref": "../shared/a.schema.json"}',
        "shared/a.schema.json": '{"$ref": "b.schema.json"}',
        "shared/b.schema.json": '{"type": "object", "version": 1}',
    }
    root, compiled = _compile(tmp_path, contracts, files)

    assert CODE_REFERENCE_BROKEN not in _codes(compiled)
    assert _edge_kinds(compiled, "ROOT", "A") == ["references"]
    assert _edge_kinds(compiled, "A", "B") == ["references"]
    root_node = _node(compiled, "ROOT")
    assert root_node.deps == ("shared/a.schema.json", "shared/b.schema.json")

    # A change to the transitive leaf B propagates to ROOT's closure fingerprint.
    root_before = root_node.closure_fingerprint
    _write_file(root, "shared/b.schema.json", '{"type": "object", "version": 2}')
    second = _recompile(root)
    assert _node(second, "ROOT").closure_fingerprint != root_before


@pytest.mark.sr("SR-075")
def test_sr075_t3_parent_ref_escaping_the_repo_root_is_rejected(tmp_path: Path) -> None:
    # A catalog contract whose JSON holds {"$ref": "../../outside/x.json"}: the
    # '..' traversal escapes the temp project root, so it must be CODE_REFERENCE
    # _BROKEN with no references edge -- even though in-tree '..' is legal.
    contracts = (_contract(id="ROOT", path="api/root.schema.json"),)
    files = {
        "api/root.schema.json": '{"$ref": "../../outside/x.json"}',
    }
    root, compiled = _compile(tmp_path, contracts, files)

    assert CODE_REFERENCE_BROKEN in _codes(compiled)
    assert all("references" not in e.kind for e in compiled.edges)
    assert _node(compiled, "ROOT").deps == ()