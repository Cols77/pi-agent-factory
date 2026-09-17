"""Unit tests for the pure contract-catalog model (optional-contract-artifacts task 2).

The model is fed a parsed catalog document (mapping) or raw catalog text. It owns no
filesystem traversal: catalog *file* discovery and path safety are a later task's job.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

CATALOG_SCHEMA_PATH = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "substrate"
    / "schemas"
    / "contract_catalog.schema.json"
)


def _declaration(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": "SENTINEL-V0-WIRE",
        "path": "docs/contracts/sentinel-v0-wire.schema.json",
        "kind": "json_schema",
        "status": "active",
    }
    entry.update(overrides)
    return entry


def _catalog(*contracts: dict[str, object], **top_level: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "coherence.contract-catalog.v1",
        "contracts": list(contracts),
    }
    document.update(top_level)
    return document


def _codes(closure: object) -> list[str]:
    return [str(diagnostic.code) for diagnostic in getattr(closure, "diagnostics")]


def test_minimal_catalog_parses_into_frozen_declarations():
    from coherence.contracts.model import parse_catalog

    closure = parse_catalog(_catalog(_declaration()))

    assert closure.present is True
    assert closure.diagnostics == ()
    assert len(closure.declarations) == 1
    (declaration,) = closure.declarations
    assert declaration.id == "SENTINEL-V0-WIRE"
    assert declaration.path == "docs/contracts/sentinel-v0-wire.schema.json"
    assert declaration.kind == "json_schema"
    assert declaration.status == "active"
    assert declaration.ref == "contract:SENTINEL-V0-WIRE"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(declaration, "id", "SOMETHING-ELSE")


def test_declared_relations_become_typed_relation_values():
    from coherence.contracts.model import ContractRelation, parse_catalog

    closure = parse_catalog(
        _catalog(
            _declaration(
                authority="spec:SPEC-SENTINEL-WP0",
                validates_against="contract:SENTINEL-V0-WIRE-SCHEMA",
                consumers=[
                    "code:src/sentinel/contracts/schemas.py",
                    "test:tests/contracts/test_schema_validation.py",
                ],
            )
        )
    )

    (declaration,) = closure.declarations
    assert declaration.authority == ContractRelation(
        kind="spec", target="SPEC-SENTINEL-WP0", raw="spec:SPEC-SENTINEL-WP0"
    )
    assert declaration.validates_against == ContractRelation(
        kind="contract", target="SENTINEL-V0-WIRE-SCHEMA", raw="contract:SENTINEL-V0-WIRE-SCHEMA"
    )
    assert [(c.kind, c.target) for c in declaration.consumers] == [
        ("code", "src/sentinel/contracts/schemas.py"),
        ("test", "tests/contracts/test_schema_validation.py"),
    ]
    assert declaration.consumers[0].ref == "code:src/sentinel/contracts/schemas.py"


def test_absent_catalog_is_a_valid_empty_closure_with_no_findings():
    from coherence.contracts.model import absent_closure

    closure = absent_closure()

    assert closure.present is False
    assert closure.declarations == ()
    assert closure.diagnostics == ()
    assert closure.ok is True
    assert closure.to_dict() == {
        "present": False,
        "declarations": [],
        "diagnostics": [],
        "nodes": [],
        "edges": [],
    }


def test_unsupported_kind_is_reported_and_the_entry_is_not_accepted():
    from coherence.contracts.model import parse_catalog

    closure = parse_catalog(_catalog(_declaration(kind="banana")))

    assert _codes(closure) == ["CONTRACT_KIND_UNSUPPORTED"]
    assert closure.diagnostics[0].declaration_id == "SENTINEL-V0-WIRE"
    assert closure.declarations == ()
    assert closure.ok is False


def test_status_is_required_and_is_never_silently_defaulted():
    from coherence.contracts.model import parse_catalog

    # A present-but-unsupported status is still a per-declaration rejection.
    unsupported = parse_catalog(_catalog(_declaration(status="archived")))
    assert _codes(unsupported) == ["CONTRACT_STATUS_UNSUPPORTED"]
    assert unsupported.diagnostics[0].declaration_id == "SENTINEL-V0-WIRE"
    assert unsupported.declarations == ()

    # An OMITTED status is rejected, never silently defaulted: `status` is a
    # required entry field, so the schema fails the document (naming the
    # declaration) instead of narrowing the entry to `active`.
    omitted = _declaration()
    del omitted["status"]
    rejected = parse_catalog(_catalog(omitted))
    assert _codes(rejected) == ["CONTRACT_CATALOG_INVALID"]
    assert rejected.diagnostics[0].declaration_id == "SENTINEL-V0-WIRE"
    assert rejected.declarations == ()

    # A blank status is present-but-unusable: the model reports it per-declaration.
    blank = parse_catalog(_catalog(_declaration(status="   ")))
    assert _codes(blank) == ["CONTRACT_DECLARATION_INVALID"]
    assert blank.diagnostics[0].declaration_id == "SENTINEL-V0-WIRE"
    assert blank.declarations == ()

    # An explicit, supported status parses clean.
    clean = parse_catalog(_catalog(_declaration(status="active")))
    assert clean.diagnostics == ()
    assert [d.status for d in clean.declarations] == ["active"]


def test_duplicate_raw_ids_keep_the_first_declaration_and_report_the_second():
    from coherence.contracts.model import parse_catalog

    closure = parse_catalog(
        _catalog(
            _declaration(),
            _declaration(path="docs/contracts/other.schema.json"),
        )
    )

    assert _codes(closure) == ["CONTRACT_DECLARATION_DUPLICATE_ID"]
    assert closure.diagnostics[0].declaration_id == "SENTINEL-V0-WIRE"
    assert [d.id for d in closure.declarations] == ["SENTINEL-V0-WIRE"]
    assert [d.path for d in closure.declarations] == [
        "docs/contracts/sentinel-v0-wire.schema.json"
    ]


def test_duplicate_normalized_repository_paths_are_reported():
    from coherence.contracts.model import parse_catalog

    closure = parse_catalog(
        _catalog(
            _declaration(id="WIRE", path="docs/contracts/wire.schema.json"),
            _declaration(id="WIRE-ALIAS", path="./docs//contracts\\wire.schema.json"),
        )
    )

    assert _codes(closure) == ["CONTRACT_DECLARATION_DUPLICATE_PATH"]
    assert closure.diagnostics[0].declaration_id == "WIRE-ALIAS"
    assert [d.id for d in closure.declarations] == ["WIRE"]


def test_absent_or_empty_declaration_ids_are_reported():
    from coherence.contracts.model import MISSING_DECLARATION_ID, parse_catalog

    missing = parse_catalog(
        _catalog({"path": "docs/contracts/a.json", "kind": "json_schema", "status": "active"})
    )
    assert _codes(missing) == ["CONTRACT_CATALOG_INVALID"]
    assert missing.diagnostics[0].declaration_id == MISSING_DECLARATION_ID
    assert missing.declarations == ()

    blank = parse_catalog(_catalog(_declaration(id="   ")))
    assert _codes(blank) == ["CONTRACT_DECLARATION_INVALID"]
    assert blank.diagnostics[0].declaration_id == MISSING_DECLARATION_ID
    assert blank.declarations == ()

    non_string = parse_catalog(_catalog(_declaration(id=17)))
    assert _codes(non_string) == ["CONTRACT_CATALOG_INVALID"]
    assert non_string.declarations == ()


def test_blank_or_non_string_paths_are_reported():
    from coherence.contracts.model import parse_catalog

    blank = parse_catalog(_catalog(_declaration(path="  ")))
    assert _codes(blank) == ["CONTRACT_DECLARATION_INVALID"]
    assert blank.diagnostics[0].declaration_id == "SENTINEL-V0-WIRE"
    assert blank.declarations == ()

    non_string = parse_catalog(_catalog(_declaration(path=3)))
    assert _codes(non_string) == ["CONTRACT_CATALOG_INVALID"]
    assert non_string.declarations == ()


def test_malformed_relationship_refs_are_reported_and_exclude_the_declaration():
    from coherence.contracts.model import parse_catalog

    for ref in ("SENTINEL-V0-WIRE", "wat:SENTINEL-V0-WIRE", "spec:", "spec :SPEC-X"):
        closure = parse_catalog(_catalog(_declaration(authority=ref)))
        assert _codes(closure) == ["CONTRACT_RELATION_INVALID"], ref
        assert closure.diagnostics[0].declaration_id == "SENTINEL-V0-WIRE", ref
        assert closure.declarations == (), ref
        assert ref in closure.diagnostics[0].message

    consumers = parse_catalog(_catalog(_declaration(consumers=["code:src/ok.py", "nope"])))
    assert _codes(consumers) == ["CONTRACT_RELATION_INVALID"]
    assert consumers.declarations == ()

    non_string = parse_catalog(_catalog(_declaration(validates_against=["contract:X"])))
    assert _codes(non_string) == ["CONTRACT_CATALOG_INVALID"]
    assert non_string.declarations == ()


@pytest.mark.sr("SR-073")
def test_ac2_catalog_requires_explicit_schema_identity_and_rejects_unknown_fields():
    from coherence.contracts.model import CATALOG_SCHEMA, CATALOG_SCHEMA_ID, parse_catalog

    unknown_version = parse_catalog(
        _catalog(_declaration(), schema="coherence.contract-catalog.v2")
    )
    assert _codes(unknown_version) == ["CONTRACT_CATALOG_INVALID"]
    assert unknown_version.declarations == ()

    missing_identity = parse_catalog({"contracts": [_declaration()]})
    assert _codes(missing_identity) == ["CONTRACT_CATALOG_INVALID"]
    assert missing_identity.declarations == ()

    unknown_top_level = parse_catalog(_catalog(_declaration(), project="sentinel"))
    assert _codes(unknown_top_level) == ["CONTRACT_CATALOG_INVALID"]
    assert unknown_top_level.declarations == ()

    unknown_entry_field = parse_catalog(_catalog(_declaration(notes="free text")))
    assert _codes(unknown_entry_field) == ["CONTRACT_CATALOG_INVALID"]
    assert unknown_entry_field.diagnostics[0].declaration_id == "SENTINEL-V0-WIRE"
    assert unknown_entry_field.declarations == ()

    # One versioned schema owns those rules, and it is the one the model validates against.
    on_disk = json.loads(CATALOG_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert CATALOG_SCHEMA == on_disk
    assert CATALOG_SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert CATALOG_SCHEMA["properties"]["schema"]["const"] == CATALOG_SCHEMA_ID
    assert CATALOG_SCHEMA_ID == "coherence.contract-catalog.v1"
    assert CATALOG_SCHEMA["additionalProperties"] is False
    item = CATALOG_SCHEMA["properties"]["contracts"]["items"]
    assert item["additionalProperties"] is False
    assert sorted(item["required"]) == ["id", "kind", "path", "status"]


def test_closure_projection_is_json_serializable_and_deterministic():
    from coherence.contracts.model import parse_catalog

    document = _catalog(
        _declaration(id="ZED", path="z.json"),
        _declaration(id="ALPHA", path="a.json", consumers=["test:tests/a.py"]),
    )

    first = parse_catalog(document)
    second = parse_catalog(document)

    assert first.to_dict() == second.to_dict()
    assert [d.id for d in first.declarations] == ["ALPHA", "ZED"]
    assert set(first.to_dict()) == {
        "present",
        "declarations",
        "diagnostics",
        "nodes",
        "edges",
    }
    assert first.to_dict()["declarations"][0] == {
        "id": "ALPHA",
        "path": "a.json",
        "kind": "json_schema",
        "status": "active",
        "authority": None,
        "validates_against": None,
        "consumers": ["test:tests/a.py"],
    }
    assert json.loads(json.dumps(first.to_dict())) == first.to_dict()


def test_parse_catalog_text_accepts_yaml_and_json_and_flags_an_empty_document():
    from coherence.contracts.model import parse_catalog_text

    closure = parse_catalog_text(
        "schema: coherence.contract-catalog.v1\n"
        "contracts:\n"
        "  - id: SENTINEL-V0-WIRE\n"
        "    path: docs/contracts/sentinel-v0-wire.schema.json\n"
        "    kind: json_schema\n"
        "    status: active\n"
    )

    assert closure.present is True
    assert closure.diagnostics == ()
    assert [d.id for d in closure.declarations] == ["SENTINEL-V0-WIRE"]
    assert [d.status for d in closure.declarations] == ["active"]

    assert parse_catalog_text(json.dumps(_catalog(_declaration()))).diagnostics == ()

    empty = parse_catalog_text("\n")
    assert empty.present is True
    assert _codes(empty) == ["CONTRACT_CATALOG_INVALID"]
    assert empty.declarations == ()

    unparsable = parse_catalog_text("schema: [unclosed\n")
    assert unparsable.present is True
    assert _codes(unparsable) == ["CONTRACT_CATALOG_INVALID"]


def test_non_mapping_documents_are_rejected_without_raising():
    from coherence.contracts.model import parse_catalog

    for document in (None, [], "text", 7):
        closure = parse_catalog(document)
        assert closure.present is True, document
        assert _codes(closure) == ["CONTRACT_CATALOG_INVALID"], document
        assert closure.declarations == (), document


def test_parsing_is_pure_and_does_not_read_the_filesystem(monkeypatch):
    from coherence.contracts.model import parse_catalog

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("catalog parsing must not touch the filesystem")

    for name in ("read_text", "read_bytes", "open", "iterdir", "rglob", "glob"):
        monkeypatch.setattr(Path, name, _refuse)

    closure = parse_catalog(
        _catalog(_declaration(id="ZED", path="z.json"), _declaration(id="ALPHA", path="a.json"))
    )

    assert [d.id for d in closure.declarations] == ["ALPHA", "ZED"]
    assert closure.diagnostics == ()


def test_vocabulary_constants_match_the_declared_catalog_model():
    from coherence.contracts.model import CONTRACT_KINDS, CONTRACT_STATUSES, RELATION_KINDS

    assert CONTRACT_KINDS == frozenset(
        {"json_schema", "fixture", "template", "ddl_manifest", "protocol", "other"}
    )
    assert CONTRACT_STATUSES == frozenset({"active", "deprecated", "draft"})
    assert RELATION_KINDS == frozenset({"contract", "code", "test", "spec"})