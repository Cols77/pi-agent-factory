"""End-to-end acceptance sequence for the contract-artifacts workstream (task 9).

A real, repeatable consumer-style contract closure, independent of SENTINEL's
evolving worktree. Uses the committed fixture project in
``tests/fixtures/contract_catalog_project`` (the *valid* catalog) and the
invalid variants in ``tests/fixtures/contract_catalog_project_invalid``, each
copied to ``tmp_path`` so the repo fixture is never mutated.

Asserted machine-readable sequence (compile -> trace -> coverage -> freshness
-> health):

* COMPILE: ``load_contract_catalog`` + ``compile_contracts`` emit the expected
  ``contract:<id>`` nodes/edges and the transitive-fingerprint property --
  editing the referenced ``common.schema.json`` changes ``WIRE``'s
  ``closure_fingerprint`` while its own ``content_fingerprint`` is unchanged.
* TRACE: ``build_graph`` contains ``contract:<id>`` nodes and all five typed
  contract edge kinds.
* BUNDLE COVERAGE: the fixture's ``FEAT-900`` bundle marks the contract members
  (including ``contract:WIRE``) bundled.
* FRESHNESS INVALIDATION: a recorded-evidence consumer path is fresh before a
  transitive ``$ref`` edit and reports ``CONTRACT_CONSUMER_STALE`` /
  ``CONTRACT_FIXTURE_STALE`` / ``CONTRACT_STALE`` afterwards.
* HEALTH FINDING: the invalid variants expose the stable codes
  ``CONTRACT_REFERENCE_BROKEN`` and ``CONTRACT_MISSING_PROVENANCE`` (plus the
  unsafe-path diagnostics) on the catalog/freshness surfaces.

New contract findings are only ever derived from *declared* relationships and
recorded evidence -- never from a file merely existing.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from coherence.contracts.catalog import load_contract_catalog
from coherence.contracts.compiler import compile_contracts
from coherence.contracts.model import (
    CODE_PATH_UNSAFE,
    CODE_REFERENCE_BROKEN,
)
from coherence.navigate.health import freshness_health
from coherence.trace.graph import build_graph
from factory.freshness.deps import _contract_closure_fingerprint

pytestmark = pytest.mark.unit

CATALOG_SCHEMA = "coherence.contract-catalog.v1"

_ALL_CONTRACT_CODES = {
    "CONTRACT_REFERENCE_BROKEN",
    "CONTRACT_MISSING_PROVENANCE",
    "CONTRACT_STALE",
    "CONTRACT_CONSUMER_STALE",
    "CONTRACT_FIXTURE_STALE",
    "CONTRACT_VALIDATION_UNAVAILABLE",
}

#: The committed, *valid* fixture project under tests/fixtures.
VALID_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "contract_catalog_project"
)
#: The committed *invalid* variants (a subdir of the fixture project, so they
#: stay inside the additive tests/fixtures tree; never pointed at by the CLI
#: commands run against the valid project root, which read only root-level
#: .factory/contracts.yaml, bundles/, evidence/ and markdown docs).
INVALID_FIXTURE = VALID_FIXTURE / "invalid"


def _copy_fixture(fixture: Path, tmp_path: Path, name: str = "project") -> Path:
    target = tmp_path / name
    shutil.copytree(fixture, target)
    return target


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _record_contract_evidence(root: Path, run_id: str, contract_id: str) -> str:
    """Record ``contract_id``'s *current* closure as validation evidence for a run."""
    digest = _contract_closure_fingerprint(root, contract_id)
    assert digest is not None
    run_dir = root / "evidence" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run": run_id,
        "feature": "FEAT-900",
        "dependencies": [
            {"kind": "contract", "name": contract_id, "source": contract_id, "digest": digest}
        ],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return digest


def _contract_findings(root: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for finding in freshness_health(root):
        if finding.code in _ALL_CONTRACT_CODES:
            out.setdefault(finding.code, []).append(
                {
                    "code": finding.code,
                    "severity": finding.severity,
                    "subject": finding.subject,
                    "detail": finding.detail,
                }
            )
    return out


def _compiled(root: Path):
    closure = load_contract_catalog(root)
    assert closure.present
    return compile_contracts(closure, root)


# ---------------------------------------------------------------------------
# COMPILE
# ---------------------------------------------------------------------------


def test_e2e_compile_emits_nodes_edges_and_transitive_fingerprint(tmp_path: Path) -> None:
    root = _copy_fixture(VALID_FIXTURE, tmp_path)

    compiled = _compiled(root)
    assert compiled.ok

    # Nodes: one per present accepted declaration, deterministic id order.
    assert [n.id for n in compiled.nodes] == ["COMMON", "MOUNTAIN", "WIRE"]
    by_id = {n.id: n for n in compiled.nodes}
    assert set(by_id["WIRE"].deps) == {"contracts/common/common.schema.json"}

    # Edges cover the declared relationships (WIRE authority/consumers, MOUNTAIN fixture).
    edges = {(e.src, e.dst, e.kind) for e in compiled.edges}
    assert ("WIRE", "COMMON", "references") in edges
    assert ("MOUNTAIN", "WIRE", "validates_against") in edges
    assert ("WIRE", "MOUNTAIN", "validated_by") in edges
    assert ("spec:WIRE-SPEC", "WIRE", "defines") in edges
    assert ("spec:WIRE-SPEC", "COMMON", "defines") in edges
    assert ("WIRE", "test:tests/wire_test.py", "consumed_by") in edges
    assert ("MOUNTAIN", "code:src/load_mountain.py", "consumed_by") in edges

    # Transitive fingerprint: editing the referenced schema changes WIRE's
    # closure fingerprint even though WIRE's own content is unchanged.
    wire_content_before = by_id["WIRE"].content_fingerprint
    wire_closure_before = by_id["WIRE"].closure_fingerprint
    _write(root, "contracts/common/common.schema.json", '{"type": "object", "x": 1}')

    compiled_after = _compiled(root)
    after = {n.id: n for n in compiled_after.nodes}
    assert after["WIRE"].content_fingerprint == wire_content_before
    assert after["WIRE"].closure_fingerprint != wire_closure_before


# ---------------------------------------------------------------------------
# TRACE
# ---------------------------------------------------------------------------


def test_e2e_trace_graph_has_contract_nodes_and_five_edge_kinds(tmp_path: Path) -> None:
    root = _copy_fixture(VALID_FIXTURE, tmp_path)

    graph = build_graph(root)
    contract_ids = sorted(n.id for n in graph.nodes if n.kind == "contract")
    assert contract_ids == ["contract:COMMON", "contract:MOUNTAIN", "contract:WIRE"]

    contract_edges = [e for e in graph.edges if e.kind in {
        "defines", "consumed_by", "validated_by", "validates_against", "references",
    }]
    assert {e.kind for e in contract_edges} == {
        "defines", "consumed_by", "validated_by", "validates_against", "references",
    }
    edge_pairs = {(e.src, e.dst, e.kind) for e in contract_edges}
    assert ("contract:WIRE", "contract:COMMON", "references") in edge_pairs
    assert ("contract:MOUNTAIN", "contract:WIRE", "validates_against") in edge_pairs

    # The valid fixture is coherent: the trace gate reports zero gaps.
    assert [g for g in graph.gaps if g.disposition == "pending"] == []


# ---------------------------------------------------------------------------
# BUNDLE COVERAGE
# ---------------------------------------------------------------------------


def test_e2e_bundle_coverage_marks_contract_bundled(tmp_path: Path) -> None:
    from coherence.navigate.coverage import bundle_coverage
    from coherence.navigate.models import to_dict

    root = _copy_fixture(VALID_FIXTURE, tmp_path)

    cov = to_dict(bundle_coverage(root))
    contract = next(k for k in cov["kinds"] if k["kind"] == "contract")
    assert contract["total"] == 3
    assert contract["bundled"] == 3
    assert contract["unbundled"] == []
    # WIRE is bundled by FEAT-900.
    assert "contract:WIRE" not in contract["unbundled"]


# ---------------------------------------------------------------------------
# FRESHNESS INVALIDATION (transitive change)
# ---------------------------------------------------------------------------


def test_e2e_freshness_invalidates_after_transitive_change(tmp_path: Path) -> None:
    root = _copy_fixture(VALID_FIXTURE, tmp_path)

    # Record WIRE's current closure as validation evidence.
    _record_contract_evidence(root, "RUN-WIRE", "WIRE")

    # Fresh before the change: the recorded evidence matches; no staleness.
    before = _contract_findings(root)
    assert "CONTRACT_STALE" not in before
    assert "CONTRACT_CONSUMER_STALE" not in before
    assert "CONTRACT_FIXTURE_STALE" not in before

    # Change a transitive $ref target -- WIRE's own bytes are untouched.
    _write(root, "contracts/common/common.schema.json", '{"type": "object", "x": 1}')

    after = _contract_findings(root)
    # The recorded consumer evidence is stale against the recompiled closure.
    assert any(f["subject"] == "run:RUN-WIRE" for f in after["CONTRACT_CONSUMER_STALE"])

    # WIRE's closure changed -> the contract itself is stale.
    assert any(f["subject"] == "contract:WIRE" for f in after.get("CONTRACT_STALE", []))

    # MOUNTAIN validates against WIRE -> the fixture is stale once WIRE changed.
    assert any(f["subject"] == "contract:MOUNTAIN" for f in after["CONTRACT_FIXTURE_STALE"])

    # Every finding is machine-readable.
    for code, items in after.items():
        for item in items:
            assert item["code"] == code and item["subject"] and item["detail"]


# ---------------------------------------------------------------------------
# HEALTH FINDINGS (invalid variants)
# ---------------------------------------------------------------------------


def test_e2e_health_reports_stable_contract_codes_on_invalid_variants(tmp_path: Path) -> None:
    # (b) missing-$ref variant: WIRE $refs nope.schema.json (missing) and has no
    # provenance declarations -> CONTRACT_REFERENCE_BROKEN + CONTRACT_MISSING_PROVENANCE.
    missing_ref = _copy_fixture(INVALID_FIXTURE / "missing_ref", tmp_path, "missing_ref")
    compiled = _compiled(missing_ref)
    assert compiled.ok is False
    assert {d.code for d in compiled.diagnostics} == {CODE_REFERENCE_BROKEN}

    findings = _contract_findings(missing_ref)
    assert any(f["subject"] == "contract:WIRE" for f in findings["CONTRACT_REFERENCE_BROKEN"])
    assert any(f["subject"] == "contract:WIRE" for f in findings["CONTRACT_MISSING_PROVENANCE"])

    # (a) unsafe-path variant: a declared `..` path is rejected lexically, reported
    # and excluded from the accepted declarations (never rescued by resolution).
    unsafe = _copy_fixture(INVALID_FIXTURE / "unsafe_path", tmp_path, "unsafe_path")
    closure = load_contract_catalog(unsafe)
    assert {d.code for d in closure.diagnostics} == {CODE_PATH_UNSAFE}
    assert all(d.declaration_id == "ESCAPE" for d in closure.diagnostics)
    assert [d.id for d in closure.declarations] == []

    # The legal compiled closure of the unsafe variant has no ESCAPE node.
    unsafe_compiled = compile_contracts(closure, unsafe)
    assert [n.id for n in unsafe_compiled.nodes] == []


def test_e2e_valid_fixture_has_no_provenance_or_broken_findings(tmp_path: Path) -> None:
    root = _copy_fixture(VALID_FIXTURE, tmp_path)
    findings = _contract_findings(root)
    assert "CONTRACT_REFERENCE_BROKEN" not in findings
    assert "CONTRACT_MISSING_PROVENANCE" not in findings
    assert "CONTRACT_STALE" not in findings
    # Without recorded evidence, declared consumers surface as validation-unavailable.
    assert any(
        f["subject"] == "test:tests/wire_test.py"
        for f in findings["CONTRACT_VALIDATION_UNAVAILABLE"]
    )
